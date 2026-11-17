"""Train and evaluate liver research classifiers on the Indian Liver Patient Dataset.

Usage:
    python -m ml.liver.train --data datasets/liver/indian_liver_patient.csv

Pipeline: ingestion -> schema validation -> de-duplication -> stratified train/test split
-> per-model sklearn Pipeline (derived features + imputation + scaling/log where relevant)
-> hyperparameter search with stratified 5-fold CV on the TRAINING split only
-> single evaluation on the untouched test split -> SHAP for XGBoost -> serialization.
"""
from __future__ import annotations

import argparse
import json
import time
import warnings

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from xgboost import XGBClassifier

from ml.common.metrics import binary_metrics, sha256_file
from ml.common.paths import FIGURES_DIR, REPORTS_DIR
from ml.liver.data import load_ilpd, to_xy, validate_ilpd
from ml.liver.features import (
    FRIENDLY_NAMES,
    NUMERIC_MODEL_FEATURES,
    add_derived_features,
    log1p_safe,
)
from ml.model_registry import model_path, save_metadata

warnings.filterwarnings("ignore", category=UserWarning)
SEED = 42
MODEL_VERSION = "liver-ilpd-1.0.0"
SKEWED = [
    "Total_Bilirubin",
    "Direct_Bilirubin",
    "Alkaline_Phosphotase",
    "Alamine_Aminotransferase",
    "Aspartate_Aminotransferase",
    "Indirect_Bilirubin",
    "AST_ALT_Ratio",
]
OTHER = [c for c in NUMERIC_MODEL_FEATURES if c not in SKEWED]


def build_pipelines(pos_weight: float) -> dict[str, tuple[Pipeline, dict]]:
    linear_pre = ColumnTransformer(
        [
            ("skewed", Pipeline([("imp", SimpleImputer(strategy="median")),
                                 ("log", FunctionTransformer(log1p_safe, feature_names_out="one-to-one")),
                                 ("sc", StandardScaler())]), SKEWED),
            ("other", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), OTHER),
        ]
    )
    tree_pre = ColumnTransformer(
        [("all", SimpleImputer(strategy="median"), NUMERIC_MODEL_FEATURES)]
    )

    def wrap(pre, clf):
        return Pipeline([("derive", FunctionTransformer(add_derived_features, validate=False)),
                         ("pre", pre), ("clf", clf)])

    return {
        "logistic_regression": (
            wrap(linear_pre, LogisticRegression(max_iter=2000, class_weight="balanced")),
            {"clf__C": np.logspace(-3, 2, 30)},
        ),
        "random_forest": (
            wrap(tree_pre, RandomForestClassifier(class_weight="balanced", random_state=SEED, n_jobs=-1)),
            {
                "clf__n_estimators": [200, 400],
                "clf__max_depth": [3, 4, 6, 8, None],
                "clf__min_samples_leaf": [1, 3, 5, 10],
                "clf__max_features": ["sqrt", 0.5],
            },
        ),
        "gradient_boosting": (
            wrap(tree_pre, GradientBoostingClassifier(random_state=SEED)),
            {
                "clf__n_estimators": [100, 200, 300],
                "clf__learning_rate": [0.01, 0.03, 0.1],
                "clf__max_depth": [2, 3, 4],
                "clf__subsample": [0.7, 1.0],
            },
        ),
        "xgboost": (
            wrap(tree_pre, XGBClassifier(eval_metric="logloss", random_state=SEED, n_jobs=2,
                                         scale_pos_weight=pos_weight, tree_method="hist")),
            {
                "clf__n_estimators": [100, 200, 400],
                "clf__learning_rate": [0.01, 0.03, 0.1],
                "clf__max_depth": [2, 3, 4, 5],
                "clf__min_child_weight": [1, 3, 5],
                "clf__subsample": [0.7, 0.9, 1.0],
                "clf__colsample_bytree": [0.6, 0.8, 1.0],
                "clf__reg_lambda": [1, 5, 10],
            },
        ),
    }


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="datasets/liver/indian_liver_patient.csv")
    ap.add_argument("--n-iter", type=int, default=40)
    args = ap.parse_args(argv)

    t0 = time.time()
    df = load_ilpd(args.data)
    report = validate_ilpd(df)
    print("Validation:", json.dumps(report.as_dict(), indent=1))
    if report.issues and any("Implausible" in i for i in report.issues):
        raise SystemExit("Refusing to train on data with implausible values: " + str(report.issues))

    # Exact duplicate rows would leak between train and test; drop them before splitting.
    n_before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    n_dupes = n_before - len(df)

    X, y = to_xy(df)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
    pos_weight = float((y_tr == 0).sum() / (y_tr == 1).sum())
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    results, fitted = {}, {}
    for name, (pipe, grid) in build_pipelines(pos_weight).items():
        search = RandomizedSearchCV(pipe, grid, n_iter=args.n_iter, scoring="roc_auc", cv=cv,
                                    random_state=SEED, n_jobs=1, refit=True)
        search.fit(X_tr, y_tr)
        best = search.best_estimator_
        proba = best.predict_proba(X_te)[:, 1]
        m = binary_metrics(y_te, proba)
        cv_std = float(search.cv_results_["std_test_score"][search.best_index_])
        results[name] = {
            "cv_roc_auc_mean": float(search.best_score_),
            "cv_roc_auc_std": cv_std,
            "best_params": {k.replace("clf__", ""): (v if not isinstance(v, np.generic) else v.item())
                            for k, v in search.best_params_.items()},
            "test": m,
        }
        fitted[name] = best
        joblib.dump(best, model_path("liver", f"{name}.joblib"))
        print(f"{name:22s} CV AUC {search.best_score_:.3f}±{cv_std:.3f} | test AUC {m['roc_auc']:.3f} "
              f"PR-AUC {m['pr_auc']:.3f} F1 {m['f1']:.3f} recall {m['recall']:.3f}")

    # ---- SHAP for XGBoost (served model) ----
    xgb = fitted["xgboost"]
    Xt_tr = xgb[:-1].transform(X_tr)
    Xt_te = xgb[:-1].transform(X_te)
    explainer = shap.TreeExplainer(xgb.named_steps["clf"])
    sv = explainer.shap_values(Xt_te)
    names = [FRIENDLY_NAMES[c] for c in NUMERIC_MODEL_FEATURES]
    mean_abs = np.abs(sv).mean(axis=0)
    order = np.argsort(mean_abs)[::-1]
    global_importance = [{"feature": names[i], "mean_abs_shap": float(mean_abs[i])} for i in order]
    # compact beeswarm data (feature value percentile vs shap) for the UI
    beeswarm = {}
    for i in order[:8]:
        col = Xt_te[:, i]
        pct = pd.Series(col).rank(pct=True).fillna(0.5).to_numpy()
        beeswarm[names[i]] = [{"shap": round(float(s), 4), "value_pct": round(float(p), 3)}
                              for s, p in zip(sv[:, i], pct)]
    plt.figure()
    shap.summary_plot(sv, Xt_te, feature_names=names, show=False, max_display=13)
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "liver_xgb_shap_summary.png", dpi=130)
    plt.close("all")
    joblib.dump({"expected_value": float(np.ravel(explainer.expected_value)[0]),
                 "background": Xt_tr[:200]}, model_path("liver", "shap_background.joblib"))

    # Figures: ROC/PR comparison
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for name, r in results.items():
        roc = r["test"]["roc_curve"]
        pr = r["test"]["pr_curve"]
        ax[0].plot([p["x"] for p in roc], [p["y"] for p in roc], label=f"{name} ({r['test']['roc_auc']:.2f})")
        ax[1].plot([p["x"] for p in pr], [p["y"] for p in pr], label=f"{name} ({r['test']['pr_auc']:.2f})")
    ax[0].plot([0, 1], [0, 1], "k--", lw=0.8)
    ax[0].set(title="ROC (held-out test)", xlabel="FPR", ylabel="TPR")
    ax[1].set(title="Precision-Recall (held-out test)", xlabel="Recall", ylabel="Precision")
    for a in ax:
        a.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "liver_roc_pr.png", dpi=130)
    plt.close(fig)

    meta = {
        "task": "liver",
        "display_name": "Liver research classifier (ILPD)",
        "model_version": MODEL_VERSION,
        "served_model": "xgboost",
        "dataset": {
            "name": "Indian Liver Patient Dataset (ILPD)",
            "source": "UCI ML Repository id 225 / Kaggle uciml/indian-liver-patient-records",
            "license": "CC BY 4.0 (UCI)",
            "file": str(args.data),
            "sha256": sha256_file(args.data),
            "validation": report.as_dict(),
            "exact_duplicates_removed": n_dupes,
            "rows_used": int(len(df)),
            "train_size": int(len(y_tr)),
            "test_size": int(len(y_te)),
            "label_definition": "1 = record labelled 'liver patient' by dataset authors; 0 = 'non liver patient'",
        },
        "split": "Stratified 80/20 hold-out (seed 42). Hyper-parameters tuned with 5-fold stratified CV on the training split only.",
        "features": NUMERIC_MODEL_FEATURES,
        "models": results,
        "shap_global": global_importance,
        "shap_beeswarm": beeswarm,
        "limitations": [
            "583 records from a single region in India (NE Andhra Pradesh); not representative of other populations.",
            "The label marks whether a record came from a liver patient; it is not a specific diagnosis and its clinical definition is not documented.",
            "Held-out test set is small (~115 records), so metrics have wide uncertainty; compare against CV mean±std.",
            "No external validation has been performed. Not clinically validated. Research/educational use only.",
            "SHAP values describe the model's statistical associations, not causal effects.",
        ],
        "training_seconds": round(time.time() - t0, 1),
    }
    save_metadata("liver", meta)
    (REPORTS_DIR / "liver_evaluation.json").write_text(json.dumps(meta, indent=2, default=float))
    return meta


if __name__ == "__main__":
    main()
