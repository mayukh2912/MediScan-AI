"""Liver function analysis: reference comparison, documented derived ratios, injury-pattern
R-ratio and (optionally) the ILPD XGBoost research score with SHAP contributions."""
from __future__ import annotations

import functools
import logging

import numpy as np
import pandas as pd

from backend.services.analyzers.common import assess_all, by_key, derived_measure, missing_fields
from ml.model_registry import load_metadata, model_path

log = logging.getLogger("mediscan.liver")
LFT_FIELDS = ["alt", "ast", "alp", "total_bilirubin", "direct_bilirubin", "indirect_bilirubin",
              "albumin", "total_protein", "globulin", "ag_ratio"]
MODEL_REQUIRED = ["total_bilirubin", "direct_bilirubin", "alp", "alt", "ast", "total_protein", "albumin"]


@functools.lru_cache(maxsize=1)
def _load_model():
    import joblib

    p = model_path("liver", "xgboost.joblib")
    if not p.exists():
        return None
    return joblib.load(p)


def research_score(values: dict, age: int | None, sex: str | None) -> dict:
    meta = load_metadata("liver")
    model = _load_model()
    if model is None or meta is None:
        return {"available": False, "reason": "Liver model has not been trained (run `python -m ml.liver.train`)."}
    missing = [k for k in MODEL_REQUIRED if values.get(k) is None]
    if age is None or sex not in ("male", "female"):
        missing += [x for x, v in (("age", age), ("sex", sex)) if v is None or (x == "sex" and v not in ("male", "female"))]
    if missing:
        return {"available": False, "reason": "Required inputs missing for the research model: " + ", ".join(missing)}
    ag = values.get("ag_ratio")
    if ag is None and values["total_protein"] - values["albumin"] > 0:
        ag = None  # left missing: the pipeline's training-fitted median imputer handles it, and we say so
    row = pd.DataFrame([{
        "Age": age, "Gender": "Male" if sex == "male" else "Female",
        "Total_Bilirubin": values["total_bilirubin"], "Direct_Bilirubin": values["direct_bilirubin"],
        "Alkaline_Phosphotase": values["alp"], "Alamine_Aminotransferase": values["alt"],
        "Aspartate_Aminotransferase": values["ast"], "Total_Protiens": values["total_protein"],
        "Albumin": values["albumin"], "Albumin_and_Globulin_Ratio": ag if ag is not None else np.nan,
    }])
    proba = float(model.predict_proba(row)[0, 1])
    # local SHAP explanation
    contributions = []
    try:
        import shap

        from ml.liver.features import FRIENDLY_NAMES, NUMERIC_MODEL_FEATURES

        xt = model[:-1].transform(row)
        sv = shap.TreeExplainer(model.named_steps["clf"]).shap_values(xt)[0]
        for name, val, s in sorted(zip(NUMERIC_MODEL_FEATURES, xt[0], sv), key=lambda t: -abs(t[2])):
            contributions.append({"feature": FRIENDLY_NAMES[name], "value": round(float(val), 3),
                                  "shap": round(float(s), 4),
                                  "direction": "towards 'liver patient' label" if s > 0 else "away from 'liver patient' label"})
    except Exception as e:  # noqa: BLE001
        log.warning("SHAP explanation failed: %s", type(e).__name__)
    test = meta["models"][meta["served_model"]]["test"]
    return {
        "available": True,
        "model": meta["served_model"],
        "model_version": meta["model_version"],
        "score": round(proba, 3),
        "score_meaning": "Model probability that this record resembles the ILPD records labelled 'liver patient'. "
                         "It is a research classification score, not a diagnosis or a risk of disease.",
        "imputed": ["A/G ratio (median of training data)"] if ag is None else [],
        "explanation": contributions,
        "explanation_note": "SHAP values show how each input moved this model's output relative to its average. "
                            "They describe statistical association in the training data, not causation.",
        "test_performance": {k: round(test[k], 3) for k in ("roc_auc", "pr_auc", "f1", "recall", "precision")},
        "limitations": meta["limitations"],
    }


def analyze_liver(measurements: list[dict], sex: str | None = None, age: int | None = None) -> dict:
    assessed = assess_all([m for m in measurements if m["key"] in LFT_FIELDS], sex)
    b = by_key(assessed)
    v = {k: b[k]["value"] for k in b}
    derived = []
    if "ast" in v and "alt" in v and v["alt"] > 0:
        derived.append(derived_measure("ast_alt_ratio", "AST/ALT (De Ritis) ratio", v["ast"] / v["alt"], "",
                                       "AST ÷ ALT", "A ratio >2 is described in association with alcohol-related liver "
                                       "disease and >1 with advanced fibrosis in some conditions; it is not diagnostic on its own."))
    if "indirect_bilirubin" not in v and "total_bilirubin" in v and "direct_bilirubin" in v:
        derived.append(derived_measure("indirect_bilirubin", "Indirect bilirubin",
                                       max(v["total_bilirubin"] - v["direct_bilirubin"], 0), "mg/dL",
                                       "Total bilirubin − direct bilirubin"))
    if "globulin" not in v and "total_protein" in v and "albumin" in v:
        derived.append(derived_measure("globulin", "Globulin", v["total_protein"] - v["albumin"], "g/dL",
                                       "Total protein − albumin"))
    glob = v.get("globulin") or next((d["value"] for d in derived if d["key"] == "globulin"), None)
    if "ag_ratio" not in v and "albumin" in v and glob and glob > 0:
        derived.append(derived_measure("ag_ratio", "Albumin/Globulin ratio", v["albumin"] / glob, "",
                                       "Albumin ÷ globulin"))
    patterns = []
    # R ratio (ACG 2017): (ALT/ULN_ALT) / (ALP/ULN_ALP) using the ULNs actually applied
    if "alt" in b and "alp" in b:
        uln_alt = (b["alt"]["assessment"].get("range_used") or {}).get("high")
        uln_alp = (b["alp"]["assessment"].get("range_used") or {}).get("high")
        abnormal = b["alt"]["assessment"]["interpretation"] == "high" or b["alp"]["assessment"]["interpretation"] == "high"
        if uln_alt and uln_alp and abnormal:
            r = (v["alt"] / uln_alt) / (v["alp"] / uln_alp)
            kind = "hepatocellular" if r >= 5 else ("cholestatic" if r <= 2 else "mixed")
            derived.append(derived_measure("r_ratio", "R ratio", r, "", "(ALT/ULN of ALT) ÷ (ALP/ULN of ALP)",
                                           "ACG 2017: ≥5 hepatocellular, ≤2 cholestatic, 2–5 mixed pattern of liver test elevation."))
            patterns.append({"pattern": f"{kind.capitalize()} pattern of enzyme elevation (R = {r:.1f})",
                             "evidence": [b["alt"]["assessment"]["rule"], b["alp"]["assessment"]["rule"]],
                             "explanation": "Describes the shape of the abnormality, not its cause.",
                             "rule": "R ratio (ACG 2017) computed only when ALT or ALP is above range"})
    for k, lbl in (("total_bilirubin", "Raised total bilirubin"), ("albumin", "Low albumin")):
        if k in b and b[k]["assessment"]["interpretation"] == ("high" if k == "total_bilirubin" else "low"):
            patterns.append({"pattern": lbl, "evidence": [b[k]["assessment"]["rule"]],
                             "explanation": "Outside the range used; clinical context is required.",
                             "rule": f"{k} compared with range used"})
    values_for_model = dict(v)
    for d in derived:
        values_for_model.setdefault(d["key"], d["value"])
    return {
        "module": "liver",
        "method": "rule-based comparison + optional XGBoost research score (ILPD)",
        "measurements": assessed,
        "derived": derived,
        "patterns": patterns,
        "missing": missing_fields(measurements, LFT_FIELDS),
        "research_model": research_score(values_for_model, age, sex),
        "disclaimer": "An abnormal liver test does not by itself indicate a specific disease. Interpretation requires a "
                      "qualified clinician.",
    }
