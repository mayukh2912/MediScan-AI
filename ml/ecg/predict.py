"""Inference for the heartbeat classifier on an arbitrary single-lead signal."""
from __future__ import annotations

import functools

import numpy as np

from ml.ecg.beat_dataset import CLASS_DESCRIPTIONS, CLASSES
from ml.ecg.signal_processing import (
    TARGET_FS, clean_ecg, detect_r_peaks, extract_beats, heart_rate_bpm, resample, signal_quality,
    tabular_features,
)
from ml.model_registry import load_metadata, model_path


@functools.lru_cache(maxsize=4)
def load_model(name: str):
    if name in ("xgboost", "random_forest"):
        import joblib

        p = model_path("ecg", f"{name}.joblib")
        return joblib.load(p) if p.exists() else None
    if name == "cnn_1d":
        import torch

        from ml.ecg.cnn import BeatCNN

        p = model_path("ecg", "cnn.pt")
        if not p.exists():
            return None
        ck = torch.load(p, map_location="cpu", weights_only=False)
        m = BeatCNN(beat_len=ck["beat_len"], n_rr=ck.get("n_rr", 4), n_classes=len(ck["classes"]))
        m.load_state_dict(ck["state_dict"])
        m.eval()
        return {"model": m, "rr_mu": np.array(ck["rr_mu"]), "rr_sd": np.array(ck["rr_sd"])}
    raise ValueError(name)


def predict_proba(name: str, beats: np.ndarray, rr: np.ndarray) -> np.ndarray:
    m = load_model(name)
    if m is None:
        raise FileNotFoundError(f"ECG model '{name}' is not trained")
    if name == "cnn_1d":
        import torch

        with torch.no_grad():
            b = torch.tensor(beats, dtype=torch.float32)
            r = torch.tensor((rr - m["rr_mu"]) / m["rr_sd"], dtype=torch.float32)
            return torch.softmax(m["model"](b, r), 1).numpy()
    p = m.predict_proba(tabular_features(beats, rr))
    full = np.zeros((len(beats), len(CLASSES)))
    full[:, m.classes_] = p
    return full


def analyze_signal(x: np.ndarray, fs: float, mains: float | None = 50.0, model: str | None = None,
                   allow_classification: bool = True) -> dict:
    meta = load_metadata("ecg")
    x = np.asarray(x, dtype=float)
    clean = clean_ecg(x, fs, mains=mains)
    r = detect_r_peaks(clean, fs)
    sqi = signal_quality(clean, fs, r)
    out = {
        "fs": fs, "duration_s": round(len(x) / fs, 2),
        "signal_quality": sqi,
        "heart_rate_bpm": None,
        "rr_intervals_s": [round(float(v), 3) for v in np.diff(r) / fs][:500],
        "r_peaks": r.tolist()[:2000],
        "waveform_preview": _preview(clean, fs, r),
        "classification": None,
    }
    if sqi.get("usable"):
        out["heart_rate_bpm"] = heart_rate_bpm(r, fs)
    if not allow_classification:
        out["classification"] = {"available": False, "reason": "Classification disabled for this input (see warnings)."}
        return out
    if meta is None:
        out["classification"] = {"available": False, "reason": "ECG model not trained (run `python -m ml.ecg.train`)."}
        return out
    if not sqi.get("usable"):
        out["classification"] = {"available": False,
                                 "reason": "Signal quality too low for beat classification; results would be unreliable."}
        return out
    x125 = resample(clean, fs, TARGET_FS)
    r125 = np.round(r * TARGET_FS / fs).astype(int)
    beats, rr, kept = extract_beats(x125, r125)
    if len(beats) == 0:
        out["classification"] = {"available": False, "reason": "No complete beats could be segmented."}
        return out
    name = model or meta["served_model"]
    proba = predict_proba(name, beats.astype(np.float32), rr.astype(np.float32))
    pred = proba.argmax(1)
    counts = {c: int((pred == i).sum()) for i, c in enumerate(CLASSES)}
    per_class_test = meta["models"][name]["test"]["per_class"]
    out["classification"] = {
        "available": True,
        "model": name,
        "model_version": meta["model_version"],
        "n_beats": int(len(beats)),
        "counts": counts,
        "fractions": {c: round(counts[c] / len(beats), 4) for c in CLASSES},
        "mean_probabilities": {c: round(float(proba[:, i].mean()), 4) for i, c in enumerate(CLASSES)},
        "beats": [{"index": int(k), "r_sample": int(r[k]), "time_s": round(float(r[k] / fs), 3),
                   "predicted": CLASSES[int(p)], "probability": round(float(proba[j, p]), 3),
                   "probabilities": {c: round(float(proba[j, i]), 3) for i, c in enumerate(CLASSES)}}
                  for j, (k, p) in enumerate(zip(kept, pred))][:1000],
        "class_descriptions": CLASS_DESCRIPTIONS,
        "test_recall_by_class": {c: round(per_class_test[c]["recall"], 3) for c in CLASSES},
        "test_precision_by_class": {c: round(per_class_test[c]["precision"], 3) for c in CLASSES},
        "explanation": _explain(name, beats, rr, pred) if name == "xgboost" else None,
        "caveat": "Beat-level classification into AAMI classes only. This is not a complete ECG interpretation or "
                  "diagnosis. Probabilities are model outputs, not clinical certainty.",
    }
    return out


def _explain(name, beats, rr, pred):
    """SHAP for the non-N beats with the highest model confidence (max 5)."""
    try:
        import shap

        from ml.ecg.signal_processing import FEATURE_NAMES

        m = load_model(name)
        X = tabular_features(beats, rr)
        idx = [i for i in np.where(pred != 0)[0]][:5] or [0]
        sv = np.asarray(shap.TreeExplainer(m).shap_values(X[idx]))
        if sv.ndim == 3 and sv.shape[0] == len(idx):
            pass  # (n, f, k)
        elif sv.ndim == 3:
            sv = np.transpose(sv, (1, 2, 0))
        out = []
        for j, i in enumerate(idx):
            c = int(pred[i])
            s = sv[j, :, c]
            top = np.argsort(np.abs(s))[::-1][:6]
            out.append({"beat": int(i), "predicted": CLASSES[c],
                        "top_features": [{"feature": FEATURE_NAMES[t], "value": round(float(X[i, t]), 3),
                                          "shap": round(float(s[t]), 4)} for t in top]})
        return out
    except Exception:  # noqa: BLE001
        return None


def _preview(x, fs, r, seconds=10.0):
    n = int(min(len(x), seconds * fs))
    step = max(1, n // 1500)
    pts = [{"t": round(i / fs, 3), "v": round(float(x[i]), 4)} for i in range(0, n, step)]
    return {"points": pts, "r_peaks_s": [round(float(p / fs), 3) for p in r if p < n]}
