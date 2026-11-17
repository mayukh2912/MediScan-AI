"""Default adult reference information, used ONLY when the laboratory did not print its own
range. Every comparison records which range was used and where it came from.

Reference ranges vary by laboratory, method, age, sex, pregnancy and population. Values here
are typical adult intervals from widely used references and are configurable (override by
setting MEDISCAN_REFERENCE_OVERRIDES to a JSON file with the same structure).
"""
from __future__ import annotations

import json
import os

SOURCES = {
    "WHO2011": "WHO (2011) Haemoglobin concentrations for the diagnosis of anaemia (WHO/NMH/NHD/MNM/11.1)",
    "MERCK": "Merck Manual Professional – Normal Laboratory Values (adult)",
    "WHO2020": "WHO (2020) Guideline on use of ferritin concentrations to assess iron status",
    "ATP3": "NCEP Adult Treatment Panel III (2002) lipid classification",
    "ASE2015": "Lang RM et al. Recommendations for Cardiac Chamber Quantification, JASE 2015 (ASE/EACVI)",
    "ASE2016": "Nagueh SF et al. Evaluation of LV Diastolic Function, JASE 2016 (ASE/EACVI)",
    "AASLD": "Kwo PY et al. ACG Clinical Guideline: Evaluation of Abnormal Liver Chemistries, 2017",
}

# key -> {"all"|"male"|"female": (low, high)}, source
DEFAULT_RANGES: dict[str, dict] = {
    "hemoglobin": {"male": (13.0, 17.5), "female": (12.0, 15.5), "source": "WHO2011",
                    "note": "Lower limits are the WHO anaemia thresholds for non-pregnant adults."},
    "rbc": {"male": (4.5, 5.9), "female": (4.0, 5.2), "source": "MERCK"},
    "wbc": {"all": (4.0, 11.0), "source": "MERCK"},
    "platelets": {"all": (150, 400), "source": "MERCK"},
    "mcv": {"all": (80, 100), "source": "MERCK"},
    "mch": {"all": (27, 33), "source": "MERCK"},
    "mchc": {"all": (32, 36), "source": "MERCK"},
    "rdw": {"all": (11.5, 14.5), "source": "MERCK"},
    "hematocrit": {"male": (41, 53), "female": (36, 46), "source": "MERCK"},
    "ferritin": {"all": (15, None), "source": "WHO2020",
                 "note": "WHO: ferritin <15 µg/L indicates iron deficiency in adults without inflammation; "
                         "ferritin is an acute-phase reactant and can be normal/high despite iron deficiency."},
    "vitamin_b12": {"all": (200, 900), "source": "MERCK",
                    "note": "200–300 pg/mL is often considered borderline; methylmalonic acid can clarify."},
    "folate": {"all": (4.0, None), "source": "MERCK", "note": "Serum folate reflects recent intake."},
    "alt": {"all": (7, 56), "source": "MERCK", "note": "Many labs use ULN ~33 (men) / 25 (women) per ACG 2017."},
    "ast": {"all": (10, 40), "source": "MERCK"},
    "alp": {"all": (44, 147), "source": "MERCK", "note": "Higher in adolescents and pregnancy."},
    "total_bilirubin": {"all": (0.1, 1.2), "source": "MERCK"},
    "direct_bilirubin": {"all": (0.0, 0.3), "source": "MERCK"},
    "indirect_bilirubin": {"all": (0.1, 1.0), "source": "MERCK"},
    "albumin": {"all": (3.5, 5.0), "source": "MERCK"},
    "total_protein": {"all": (6.0, 8.3), "source": "MERCK"},
    "globulin": {"all": (2.0, 3.5), "source": "MERCK"},
    "ag_ratio": {"all": (1.0, 2.2), "source": "MERCK"},
    "ef": {"male": (52, 72), "female": (54, 74), "source": "ASE2015"},
    "lvidd": {"male": (4.2, 5.8), "female": (3.8, 5.2), "source": "ASE2015"},
    "lvids": {"male": (2.5, 4.0), "female": (2.2, 3.5), "source": "ASE2015"},
    "ivsd": {"male": (0.6, 1.0), "female": (0.6, 0.9), "source": "ASE2015"},
    "lvpwd": {"male": (0.6, 1.0), "female": (0.6, 0.9), "source": "ASE2015"},
    "la_diameter": {"male": (3.0, 4.0), "female": (2.7, 3.8), "source": "ASE2015"},
    "rv_diameter": {"all": (2.5, 4.1), "source": "ASE2015", "note": "Basal RV diameter (RVD1)."},
    "tapse": {"all": (1.7, None), "source": "ASE2015"},
    "e_e_prime": {"all": (None, 14), "source": "ASE2016", "note": "Average E/e' > 14 is one criterion of elevated filling pressure."},
    "rvsp": {"all": (None, 35), "source": "ASE2015", "note": "Upper limit varies with age and body size."},
}

# NCEP ATP III categories (mg/dL)
LIPID_CATEGORIES = {
    "ldl": [(0, 100, "Optimal"), (100, 130, "Near/above optimal"), (130, 160, "Borderline high"),
            (160, 190, "High"), (190, 1e9, "Very high")],
    "total_cholesterol": [(0, 200, "Desirable"), (200, 240, "Borderline high"), (240, 1e9, "High")],
    "hdl": [(0, 40, "Low"), (40, 60, "Normal"), (60, 1e9, "High (desirable)")],
    "triglycerides": [(0, 150, "Normal"), (150, 200, "Borderline high"), (200, 500, "High"), (500, 1e9, "Very high")],
    "non_hdl": [(0, 130, "Optimal"), (130, 160, "Near/above optimal"), (160, 190, "Borderline high"),
                (190, 220, "High"), (220, 1e9, "Very high")],
}

_override = os.environ.get("MEDISCAN_REFERENCE_OVERRIDES")
if _override and os.path.exists(_override):
    with open(_override) as f:
        for k, v in json.load(f).items():
            DEFAULT_RANGES[k] = {kk: tuple(vv) if isinstance(vv, list) else vv for kk, vv in v.items()}


def default_range(key: str, sex: str | None) -> dict | None:
    d = DEFAULT_RANGES.get(key)
    if not d:
        return None
    rng = d.get(sex) if sex in ("male", "female") else None
    sex_note = None
    if rng is None:
        rng = d.get("all")
    if rng is None:  # sex-specific only and sex unknown: use the widest envelope and say so
        lows = [d[s][0] for s in ("male", "female") if d.get(s) and d[s][0] is not None]
        highs = [d[s][1] for s in ("male", "female") if d.get(s) and d[s][1] is not None]
        rng = (min(lows) if lows else None, max(highs) if highs else None)
        sex_note = "Sex not provided: using the combined male/female envelope."
    return {"low": rng[0], "high": rng[1], "source": "default", "reference": SOURCES[d["source"]],
            "note": " ".join(x for x in (d.get("note"), sex_note) if x) or None}


def compare(m: dict, sex: str | None) -> dict:
    """Compare a measurement against the lab range if present, else the default range."""
    val = m.get("value")
    lab = m.get("reference_range")
    if lab and (lab.get("low") is not None or lab.get("high") is not None):
        rng = {"low": lab.get("low"), "high": lab.get("high"), "source": "laboratory",
               "reference": "Reference range printed on the report", "note": None}
    else:
        rng = default_range(m["key"], sex)
    if val is None or rng is None:
        return {"interpretation": "not_assessed", "range_used": rng,
                "rule": "No value or no reference range available"}
    lo, hi = rng.get("low"), rng.get("high")
    if lo is not None and val < lo:
        interp = "low"
    elif hi is not None and val > hi:
        interp = "high"
    else:
        interp = "within_range"
    bounds = f"{lo if lo is not None else '–'} to {hi if hi is not None else '–'}"
    return {"interpretation": interp, "range_used": rng,
            "rule": f"{m.get('test', m['key'])} {val} compared with {rng['source']} range {bounds} {m.get('unit', '')}".strip()}


def lipid_category(key: str, mgdl: float | None) -> str | None:
    if mgdl is None or key not in LIPID_CATEGORIES:
        return None
    for lo, hi, label in LIPID_CATEGORIES[key]:
        if lo <= mgdl < hi:
            return label
    return None
