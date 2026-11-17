"""Lipid profile: exact measurements, transparent derived values and NCEP ATP III categories.

No ML model: the measurements are already the quantities of interest, and no public dataset
labels lipid abnormality independently of those same measurements.

LDL estimation (only when LDL was NOT reported by the lab):
* Friedewald (1972): LDL = TC − HDL − TG/5 (mg/dL). Valid only for TG < 400 mg/dL and
  non-fasting/very-low-LDL samples are less accurate.
* Sampson / NIH equation 2 (JAMA Cardiol 2020) for 400 ≤ TG ≤ 800 mg/dL:
  LDL = TC/0.948 − HDL/0.971 − (TG/8.56 + TG·NonHDL/2140 − TG²/16100) − 9.44
* TG > 800 mg/dL: no estimate is made; direct LDL measurement is required.
"""
from __future__ import annotations

from backend.services.analyzers.common import assess_all, by_key, derived_measure, missing_fields
from backend.services.analyzers.reference import lipid_category

LIPID_FIELDS = ["total_cholesterol", "hdl", "ldl", "vldl", "triglycerides"]


def friedewald(tc: float, hdl: float, tg: float) -> float:
    return tc - hdl - tg / 5.0


def sampson(tc: float, hdl: float, tg: float) -> float:
    non_hdl = tc - hdl
    return tc / 0.948 - hdl / 0.971 - (tg / 8.56 + tg * non_hdl / 2140 - tg ** 2 / 16100) - 9.44


def estimate_ldl(tc, hdl, tg) -> dict:
    if None in (tc, hdl, tg):
        return {"value": None, "method": None, "reason": "Needs total cholesterol, HDL and triglycerides"}
    if tg < 400:
        return {"value": friedewald(tc, hdl, tg), "method": "Friedewald", "reason": "TG < 400 mg/dL"}
    if tg <= 800:
        return {"value": sampson(tc, hdl, tg), "method": "Sampson (NIH eq. 2)",
                "reason": "TG 400–800 mg/dL: Friedewald is not valid"}
    return {"value": None, "method": None, "reason": "TG > 800 mg/dL: no equation is reliable; direct LDL needed"}


def analyze_lipid(measurements: list[dict], sex: str | None = None) -> dict:
    assessed = assess_all([m for m in measurements if m["key"] in LIPID_FIELDS + ["non_hdl"]], sex)
    for m in assessed:
        cat = lipid_category(m["key"], m.get("value"))
        if cat:
            m["category"] = {"label": cat, "scheme": "NCEP ATP III (adult, general population)"}
    b = by_key(assessed)
    v = {k: b[k]["value"] for k in b}
    derived, warnings = [], []
    tc, hdl, tg, ldl = v.get("total_cholesterol"), v.get("hdl"), v.get("triglycerides"), v.get("ldl")

    if tc is not None and hdl is not None:
        nh = tc - hdl
        d = derived_measure("non_hdl", "Non-HDL cholesterol", nh, "mg/dL", "Total cholesterol − HDL")
        d["category"] = {"label": lipid_category("non_hdl", nh), "scheme": "NCEP ATP III (LDL goal + 30)"}
        derived.append(d)
        if hdl > 0:
            derived.append(derived_measure("tc_hdl_ratio", "Total cholesterol / HDL ratio", tc / hdl, "",
                                           "Total cholesterol ÷ HDL",
                                           "Higher ratios are associated with higher cardiovascular risk in population studies."))
    ldl_estimated = None
    if ldl is None:
        est = estimate_ldl(tc, hdl, tg)
        if est["value"] is not None:
            ldl_estimated = est["value"]
            d = derived_measure("ldl_estimated", f"LDL cholesterol (estimated, {est['method']})", est["value"],
                                "mg/dL", est["method"], f"Calculated because LDL was not reported. {est['reason']}.")
            d["category"] = {"label": lipid_category("ldl", est["value"]), "scheme": "NCEP ATP III"}
            derived.append(d)
        else:
            warnings.append(f"LDL not reported and not estimated: {est['reason']}.")
    elif "ldl" in b and b["ldl"].get("lab_calculated"):
        warnings.append("The laboratory marked LDL as calculated (not directly measured).")
        if tg is not None and tg >= 400:
            warnings.append("Triglycerides ≥ 400 mg/dL: a Friedewald-calculated LDL from the lab may be inaccurate.")

    ldl_for_ratio = ldl if ldl is not None else ldl_estimated
    if ldl_for_ratio is not None and hdl:
        derived.append(derived_measure("ldl_hdl_ratio", "LDL / HDL ratio", ldl_for_ratio / hdl, "",
                                       "LDL ÷ HDL", None if ldl is not None else "Uses the estimated LDL."))
    if "vldl" not in v and tg is not None and tg < 400:
        derived.append(derived_measure("vldl_estimated", "VLDL cholesterol (estimated)", tg / 5, "mg/dL", "TG ÷ 5",
                                       "Friedewald assumption (TG:VLDL-C ≈ 5:1); valid only when TG < 400 mg/dL."))
    if tg is not None and hdl:
        derived.append(derived_measure("tg_hdl_ratio", "Triglyceride / HDL ratio", tg / hdl, "", "TG ÷ HDL (mg/dL units)"))

    if tc is not None and hdl is not None and ldl is not None and tg is not None and tg < 400:
        implied = friedewald(tc, hdl, tg)
        if abs(implied - ldl) > 30:
            warnings.append(f"Reported LDL ({ldl:.0f}) differs from TC−HDL−TG/5 ({implied:.0f}) by >30 mg/dL; "
                            "this is possible with direct LDL assays, but please re-check the extracted values.")
    patterns = []
    for m in assessed:
        if m.get("category") and m["category"]["label"] in ("High", "Very high", "Borderline high", "Low"):
            patterns.append({"pattern": f"{m['test']}: {m['category']['label']}",
                             "evidence": [f"{m['test']} = {m['value']} mg/dL"],
                             "explanation": "Category from NCEP ATP III adult thresholds. Treatment targets depend on "
                                            "individual cardiovascular risk and current guidelines.",
                             "rule": "NCEP ATP III cut-points"})
    return {
        "module": "lipid",
        "method": "transparent calculations + NCEP ATP III categories (no ML)",
        "measurements": assessed,
        "derived": derived,
        "patterns": patterns,
        "warnings": warnings,
        "missing": missing_fields(measurements, LIPID_FIELDS),
        "chart": [{"name": m["test"], "value": m["value"],
                   "low": (m["assessment"].get("range_used") or {}).get("low"),
                   "high": (m["assessment"].get("range_used") or {}).get("high")}
                  for m in assessed if m.get("value") is not None],
        "disclaimer": "Lipid targets depend on overall cardiovascular risk; discuss results with a clinician.",
    }
