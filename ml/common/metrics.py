"""Evaluation helpers. Every number produced here is computed from real predictions on held-out data."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.preprocessing import label_binarize


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _downsample_curve(x: np.ndarray, y: np.ndarray, n: int = 60) -> list[dict]:
    if len(x) > n:
        idx = np.unique(np.linspace(0, len(x) - 1, n).astype(int))
        x, y = x[idx], y[idx]
    return [{"x": round(float(a), 4), "y": round(float(b), 4)} for a, b in zip(x, y)]


def binary_metrics(y_true: np.ndarray, proba: np.ndarray, threshold: float = 0.5) -> dict:
    """Metrics for a binary classifier given positive-class probabilities."""
    y_true = np.asarray(y_true).astype(int)
    proba = np.asarray(proba, dtype=float)
    y_pred = (proba >= threshold).astype(int)
    fpr, tpr, _ = roc_curve(y_true, proba)
    prec, rec, _ = precision_recall_curve(y_true, proba)
    frac_pos, mean_pred = calibration_curve(y_true, proba, n_bins=8, strategy="quantile")
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return {
        "threshold": threshold,
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if (tn + fp) else None,
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "brier": float(brier_score_loss(y_true, proba)),
        "positive_rate_in_test": float(y_true.mean()),
        "confusion_matrix": {"labels": [0, 1], "matrix": cm.tolist()},
        "roc_curve": _downsample_curve(fpr, tpr),
        "pr_curve": _downsample_curve(rec[::-1], prec[::-1]),
        "calibration": [
            {"mean_predicted": round(float(m), 4), "fraction_positive": round(float(f), 4)}
            for m, f in zip(mean_pred, frac_pos)
        ],
    }


def multiclass_metrics(y_true: np.ndarray, proba: np.ndarray, class_names: Sequence[str]) -> dict:
    """Metrics for a multi-class classifier. proba has shape (n, k)."""
    y_true = np.asarray(y_true).astype(int)
    proba = np.asarray(proba, dtype=float)
    k = len(class_names)
    y_pred = proba.argmax(axis=1)
    labels = list(range(k))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    y_bin = label_binarize(y_true, classes=labels)
    per_class = {}
    prec = precision_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    rec = recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    f1 = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    roc_curves, pr_curves = {}, {}
    for i, name in enumerate(class_names):
        support = int((y_true == i).sum())
        entry = {
            "support": support,
            "precision": float(prec[i]),
            "recall": float(rec[i]),
            "f1": float(f1[i]),
            "roc_auc": None,
            "pr_auc": None,
        }
        if 0 < support < len(y_true):
            entry["roc_auc"] = float(roc_auc_score(y_bin[:, i], proba[:, i]))
            entry["pr_auc"] = float(average_precision_score(y_bin[:, i], proba[:, i]))
            fpr, tpr, _ = roc_curve(y_bin[:, i], proba[:, i])
            p, r, _ = precision_recall_curve(y_bin[:, i], proba[:, i])
            roc_curves[name] = _downsample_curve(fpr, tpr)
            pr_curves[name] = _downsample_curve(r[::-1], p[::-1])
        per_class[name] = entry
    valid_auc = [v["roc_auc"] for v in per_class.values() if v["roc_auc"] is not None]
    valid_pr = [v["pr_auc"] for v in per_class.values() if v["pr_auc"] is not None]
    # top-label calibration (confidence vs accuracy)
    conf = proba.max(axis=1)
    correct = (y_pred == y_true).astype(int)
    bins = np.quantile(conf, np.linspace(0, 1, 9))
    calib = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (conf >= lo) & (conf <= hi)
        if m.sum():
            calib.append({"mean_predicted": round(float(conf[m].mean()), 4),
                          "fraction_positive": round(float(correct[m].mean()), 4)})
    return {
        "n": int(len(y_true)),
        "classes": list(class_names),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_precision": float(np.mean(prec)),
        "macro_recall": float(np.mean(rec)),
        "macro_f1": float(np.mean(f1)),
        "macro_roc_auc_ovr": float(np.mean(valid_auc)) if valid_auc else None,
        "macro_pr_auc": float(np.mean(valid_pr)) if valid_pr else None,
        "per_class": per_class,
        "confusion_matrix": {"labels": list(class_names), "matrix": cm.tolist()},
        "roc_curves": roc_curves,
        "pr_curves": pr_curves,
        "calibration_top_label": calib,
    }
