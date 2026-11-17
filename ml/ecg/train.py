"""Train and evaluate heartbeat classifiers (Random Forest, XGBoost, 1-D CNN).

Usage:
    python -m ml.ecg.train --mitdb datasets/mitdb            # inter-patient (default, served)
    python -m ml.ecg.train --kaggle-dir datasets/heartbeat   # optional Kaggle CSV benchmark

Inter-patient protocol: train/tune on DS1 records only (GroupKFold by record), test once on
DS2 records. The served model is selected on DS1 validation performance, never on DS2.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shap
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold
from sklearn.utils.class_weight import compute_sample_weight
from torch import nn
from xgboost import XGBClassifier

from ml.common.metrics import multiclass_metrics
from ml.common.paths import FIGURES_DIR, REPORTS_DIR
from ml.ecg.beat_dataset import (
    CLASS_DESCRIPTIONS, CLASSES, DS1, DS2, PACED, build_mitdb, load_kaggle_csv,
)
from ml.ecg.cnn import BeatCNN
from ml.ecg.signal_processing import BEAT_LEN, FEATURE_NAMES, N_RR, RR_FEATURES, PRE_S, POST_S, TARGET_FS, tabular_features
from ml.model_registry import model_path, save_metadata

SEED = 42
MODEL_VERSION = "ecg-beat-mitdb-1.0.0"
torch.manual_seed(SEED)
np.random.seed(SEED)


def grouped_cv_macro_f1(make_model, X, y, groups, fit_kwargs_fn=None, n_splits=4) -> tuple[float, float]:
    scores = []
    for tr, va in GroupKFold(n_splits=n_splits).split(X, y, groups):
        m = make_model()
        kw = fit_kwargs_fn(y[tr]) if fit_kwargs_fn else {}
        m.fit(X[tr], y[tr], **kw)
        p = m.predict_proba(X[va])
        full = np.zeros((len(va), len(CLASSES)))
        full[:, m.classes_] = p
        scores.append(f1_score(y[va], full.argmax(1), labels=range(len(CLASSES)), average="macro", zero_division=0))
    return float(np.mean(scores)), float(np.std(scores))


def train_cnn(tr: dict, va: dict, rr_mu, rr_sd, epochs=15, log=print):
    dev = torch.device("cpu")
    torch.set_num_threads(2)
    model = BeatCNN(beat_len=BEAT_LEN, n_rr=N_RR, n_classes=len(CLASSES)).to(dev)
    counts = np.bincount(tr["y"], minlength=len(CLASSES)).astype(float)
    w = torch.tensor((counts.sum() / (len(CLASSES) * np.maximum(counts, 1))) ** 0.5, dtype=torch.float32)
    lossf = nn.CrossEntropyLoss(weight=w)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    Xb = torch.tensor(tr["beats"]); Xr = torch.tensor((tr["rr"] - rr_mu) / rr_sd, dtype=torch.float32)
    Y = torch.tensor(tr["y"])
    Vb = torch.tensor(va["beats"]); Vr = torch.tensor((va["rr"] - rr_mu) / rr_sd, dtype=torch.float32)
    best, best_state, patience = -1, None, 0
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Y))
        for i in range(0, len(Y), 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            loss = lossf(model(Xb[idx], Xr[idx]), Y[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            pv = torch.softmax(model(Vb, Vr), 1).numpy()
        f1 = f1_score(va["y"], pv.argmax(1), labels=range(len(CLASSES)), average="macro", zero_division=0)
        log(f"  CNN epoch {ep + 1}: val macro-F1 {f1:.3f}")
        if f1 > best:
            best, best_state, patience = f1, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            patience += 1
            if patience >= 4:
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, best


def cnn_predict(model, beats, rr, rr_mu, rr_sd):
    with torch.no_grad():
        out = []
        for i in range(0, len(beats), 4096):
            b = torch.tensor(beats[i:i + 4096])
            r = torch.tensor((rr[i:i + 4096] - rr_mu) / rr_sd, dtype=torch.float32)
            out.append(torch.softmax(model(b, r), 1).numpy())
    return np.concatenate(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mitdb", default="datasets/mitdb")
    ap.add_argument("--kaggle-dir", default=None, help="Optional: folder with mitbih_train.csv/mitbih_test.csv")
    ap.add_argument("--epochs", type=int, default=15)
    args = ap.parse_args(argv)
    t0 = time.time()

    cache = Path(args.mitdb) / "_beats_cache.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        ds1, ds2 = z["ds1"].item(), z["ds2"].item()
    else:
        print("Building DS1/DS2 beat sets from raw MIT-BIH records ...")
        ds1, ds2 = build_mitdb(args.mitdb, DS1), build_mitdb(args.mitdb, DS2)
        np.savez_compressed(cache, ds1=np.array(ds1, dtype=object), ds2=np.array(ds2, dtype=object))
    for n, d in (("DS1", ds1), ("DS2", ds2)):
        print(n, len(d["y"]), dict(zip(CLASSES, np.bincount(d["y"], minlength=4).tolist())))

    Xtr = tabular_features(ds1["beats"], ds1["rr"]); ytr, gtr = ds1["y"], ds1["groups"]
    Xte = tabular_features(ds2["beats"], ds2["rr"]); yte = ds2["y"]

    results, val_scores, test_proba = {}, {}, {}

    # ---- Random Forest ----
    rf_grid = [dict(n_estimators=200, max_depth=12, min_samples_leaf=5),
               dict(n_estimators=200, max_depth=20, min_samples_leaf=2),
               dict(n_estimators=200, max_depth=None, min_samples_leaf=10)]
    best_rf = None
    for p in rf_grid:
        mk = lambda p=p: RandomForestClassifier(**p, class_weight="balanced_subsample", n_jobs=2, random_state=SEED)
        s, sd = grouped_cv_macro_f1(mk, Xtr, ytr, gtr)
        print(f"RF {p} grouped-CV macro-F1 {s:.3f}±{sd:.3f}")
        if best_rf is None or s > best_rf[1]:
            best_rf = (p, s, sd)
    rf = RandomForestClassifier(**best_rf[0], class_weight="balanced_subsample", n_jobs=2, random_state=SEED).fit(Xtr, ytr)
    joblib.dump(rf, model_path("ecg", "random_forest.joblib"), compress=3)
    test_proba["random_forest"] = rf.predict_proba(Xte)
    val_scores["random_forest"] = (best_rf[1], best_rf[2])
    results["random_forest"] = {"best_params": best_rf[0]}

    # ---- XGBoost ----
    xgb_grid = [dict(n_estimators=300, max_depth=4, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8),
                dict(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8),
                dict(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.8, colsample_bytree=0.6, min_child_weight=5)]
    sw = lambda yy: {"sample_weight": compute_sample_weight("balanced", yy)}
    best_x = None
    for p in xgb_grid:
        mk = lambda p=p: XGBClassifier(**p, objective="multi:softprob", tree_method="hist", n_jobs=2, random_state=SEED)
        s, sd = grouped_cv_macro_f1(mk, Xtr, ytr, gtr, sw)
        print(f"XGB {p} grouped-CV macro-F1 {s:.3f}±{sd:.3f}")
        if best_x is None or s > best_x[1]:
            best_x = (p, s, sd)
    xgb = XGBClassifier(**best_x[0], objective="multi:softprob", tree_method="hist", n_jobs=2, random_state=SEED)
    xgb.fit(Xtr, ytr, **sw(ytr))
    joblib.dump(xgb, model_path("ecg", "xgboost.joblib"))
    test_proba["xgboost"] = xgb.predict_proba(Xte)
    val_scores["xgboost"] = (best_x[1], best_x[2])
    results["xgboost"] = {"best_params": best_x[0]}

    # ---- 1-D CNN (validation = 4 held-out DS1 records) ----
    val_recs = {"203", "208", "116", "223"}  # contain S, V and F beats
    vm = np.isin(gtr, list(val_recs))
    tr = {k: ds1[k][~vm] for k in ("beats", "rr", "y")}
    va = {k: ds1[k][vm] for k in ("beats", "rr", "y")}
    rr_mu, rr_sd = tr["rr"].mean(0), tr["rr"].std(0) + 1e-6
    cnn, cnn_val = train_cnn(tr, va, rr_mu, rr_sd, epochs=args.epochs)
    torch.save({"state_dict": cnn.state_dict(), "rr_mu": rr_mu.tolist(), "rr_sd": rr_sd.tolist(),
                "beat_len": BEAT_LEN, "n_rr": N_RR, "classes": CLASSES}, model_path("ecg", "cnn.pt"))
    test_proba["cnn_1d"] = cnn_predict(cnn, ds2["beats"], ds2["rr"], rr_mu, rr_sd)
    val_scores["cnn_1d"] = (cnn_val, None)
    results["cnn_1d"] = {"best_params": {"architecture": "3x(conv-bn-relu x2, maxpool) + GAP, RR branch, 2 dense",
                                         "validation_records": sorted(val_recs)}}

    for name, proba in test_proba.items():
        results[name]["validation_macro_f1"] = val_scores[name][0]
        results[name]["validation_macro_f1_std"] = val_scores[name][1]
        results[name]["test"] = multiclass_metrics(yte, proba, CLASSES)
        m = results[name]["test"]
        print(f"{name:14s} DS2 acc {m['accuracy']:.3f} macroF1 {m['macro_f1']:.3f} "
              + " ".join(f"{c}:F1={m['per_class'][c]['f1']:.2f}" for c in CLASSES))

    served = max(val_scores, key=lambda k: val_scores[k][0])

    # ---- SHAP (XGBoost on tabular features) ----
    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(Xte), size=min(1500, len(Xte)), replace=False)
    explainer = shap.TreeExplainer(xgb)
    sv = np.asarray(explainer.shap_values(Xte[idx]))  # (n, f, k) in shap>=0.45
    if sv.ndim == 3 and sv.shape[0] == len(CLASSES) and sv.shape[1] == len(idx):
        sv = np.transpose(sv, (1, 2, 0))
    per_class_imp = {c: np.abs(sv[:, :, i]).mean(0) for i, c in enumerate(CLASSES)}
    overall = np.mean([v for v in per_class_imp.values()], axis=0)
    order = np.argsort(overall)[::-1][:15]
    shap_global = [{"feature": FEATURE_NAMES[i], "mean_abs_shap": float(overall[i]),
                    **{f"class_{c}": float(per_class_imp[c][i]) for c in CLASSES}} for i in order]
    plt.figure(figsize=(7, 5))
    plt.barh([FEATURE_NAMES[i] for i in order][::-1], overall[order][::-1], color="#0e7490")
    plt.xlabel("mean |SHAP| (averaged over classes)")
    plt.title("ECG XGBoost — global feature importance (DS2 sample)")
    plt.tight_layout(); plt.savefig(FIGURES_DIR / "ecg_xgb_shap_importance.png", dpi=130); plt.close("all")

    # confusion matrix figure for each model
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, (name, r) in zip(axes, results.items()):
        cm = np.array(r["test"]["confusion_matrix"]["matrix"])
        cmn = cm / cm.sum(1, keepdims=True).clip(min=1)
        ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
        for i in range(4):
            for j in range(4):
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8,
                        color="white" if cmn[i, j] > 0.5 else "black")
        ax.set(xticks=range(4), yticks=range(4), xticklabels=CLASSES, yticklabels=CLASSES,
               title=f"{name} (DS2)", xlabel="Predicted", ylabel="True")
    fig.tight_layout(); fig.savefig(FIGURES_DIR / "ecg_confusion_matrices.png", dpi=130); plt.close(fig)

    meta = {
        "task": "ecg",
        "display_name": "ECG heartbeat classifier (MIT-BIH, AAMI classes)",
        "model_version": MODEL_VERSION,
        "served_model": served,
        "served_model_selection": "Highest macro-F1 on DS1 validation (grouped CV / held-out DS1 records). DS2 not used for selection.",
        "classes": CLASSES,
        "class_descriptions": CLASS_DESCRIPTIONS,
        "unsupported_classes": {"Q": "Unclassifiable/paced beats: only ~15 examples after excluding paced records; not trained."},
        "preprocessing": {
            "lead": "MLII", "filters": "0.5 Hz high-pass, mains notch, 40 Hz low-pass (zero-phase Butterworth)",
            "resample_hz": TARGET_FS, "window_s": [-PRE_S, POST_S], "beat_len": BEAT_LEN,
            "normalisation": "per-beat z-score", "rr_features": RR_FEATURES,
            "r_peaks_for_training": "Reference annotations (.atr). At inference R-peaks come from the built-in detector.",
        },
        "dataset": {
            "name": "MIT-BIH Arrhythmia Database v1.0.0 (PhysioNet)",
            "relation_to_kaggle": "Kaggle shayanfazeli/heartbeat is derived from this database; the raw records are used so record IDs are available for an inter-patient split.",
            "license": "Open Data Commons Attribution License v1.0",
            "split": "de Chazal 2004 inter-patient: DS1 (22 records) train, DS2 (22 records) test; paced records 102,104,107,217 excluded",
            "excluded_records": sorted(PACED),
            "train_beats": int(len(ytr)), "test_beats": int(len(yte)),
            "train_class_counts": dict(zip(CLASSES, np.bincount(ytr, minlength=4).tolist())),
            "test_class_counts": dict(zip(CLASSES, np.bincount(yte, minlength=4).tolist())),
        },
        "models": results,
        "shap_global": shap_global,
        "feature_names": FEATURE_NAMES,
        "limitations": [
            "Classifies individual beats into 4 AAMI classes from a single lead. It is NOT a full ECG interpretation and does not detect ischaemia, conduction intervals, AF episodes, etc.",
            "Trained on 2-lead ambulatory Holter recordings from 1975-1979 (47 subjects); performance on other devices, 12-lead resting ECGs or digitised paper ECGs is unknown and likely lower.",
            "Inter-patient performance for S and F classes is known to be poor in the literature and is poor here as well; see per-class metrics.",
            "Not clinically validated. Research/educational use only.",
        ],
        "training_seconds": round(time.time() - t0, 1),
    }

    if args.kaggle_dir:  # optional intra-patient benchmark on the Kaggle CSVs
        kd = Path(args.kaggle_dir)
        Xk, yk = load_kaggle_csv(kd / "mitbih_train.csv")
        Xkt, ykt = load_kaggle_csv(kd / "mitbih_test.csv")
        kx = XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.1, tree_method="hist", n_jobs=2)
        kx.fit(Xk, yk, sample_weight=compute_sample_weight("balanced", yk))
        meta["kaggle_intra_patient_benchmark"] = {
            "note": "Kaggle split has no patient IDs: train/test share patients, so this is optimistic.",
            "xgboost": multiclass_metrics(ykt, kx.predict_proba(Xkt), ["N", "S", "V", "F", "Q"]),
        }

    save_metadata("ecg", meta)
    (REPORTS_DIR / "ecg_evaluation.json").write_text(json.dumps(meta, indent=2, default=float))
    print("served:", served, "seconds:", meta["training_seconds"])


if __name__ == "__main__":
    main()
