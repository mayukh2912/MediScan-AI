"""Unit recognition and conversion to one canonical unit per analyte.

Every conversion factor is a documented constant (molar masses / SI conventions). If a unit is
not recognised for an analyte we do NOT guess: the measurement is flagged as a unit mismatch.
"""
from __future__ import annotations

import re

# (regex, unit_key). Order matters: longer / more specific first.
UNIT_PATTERNS: list[tuple[str, str]] = [
    (r"lakhs?\s*/\s*(?:cu\.?\s*mm|cumm|cmm|mm3|mm³|[uµμ]l)", "lakh/uL"),
    (r"(?:x\s*)?10\s*(?:\^|e|\*\*)?\s*12\s*/\s*l", "10^12/L"),
    (r"(?:x\s*)?10\s*(?:\^|e|\*\*)?\s*9\s*/\s*l", "10^9/L"),
    (r"(?:x\s*)?10\s*(?:\^|e|\*\*)?\s*[6⁶]\s*/\s*(?:[uµμ]l|cu\.?\s*mm|cumm|cmm|mm3|mm³)", "10^6/uL"),
    (r"(?:x\s*)?10\s*(?:\^|e|\*\*)?\s*[3³]\s*/\s*(?:[uµμ]l|cu\.?\s*mm|cumm|cmm|mm3|mm³)", "10^3/uL"),
    (r"mill(?:ion)?s?\s*/?\s*(?:[uµμ]l|cu\.?\s*mm|cumm|cmm|mm3|mm³)", "10^6/uL"),
    (r"(?:thou|thousand|k)\s*/\s*(?:[uµμ]l|cu\.?\s*mm|cumm|cmm|mm3|mm³)", "10^3/uL"),
    (r"(?:cells\s*)?/\s*(?:[uµμ]l|cu\.?\s*mm|cumm|cmm|mm3|mm³)", "/uL"),
    (r"g(?:m|ms)?\s*/\s*d\s*l|g(?:m)?\s*%", "g/dL"),
    (r"mg\s*/\s*d\s*l|mg\s*%", "mg/dL"),
    (r"g(?:m)?\s*/\s*l", "g/L"),
    (r"[uµμ]\s*mol\s*/\s*l", "umol/L"),
    (r"mmol\s*/\s*l", "mmol/L"),
    (r"nmol\s*/\s*l", "nmol/L"),
    (r"pmol\s*/\s*l", "pmol/L"),
    (r"ng\s*/\s*m\s*l", "ng/mL"),
    (r"[uµμ]g\s*/\s*l", "ug/L"),
    (r"pg\s*/\s*m\s*l", "pg/mL"),
    (r"(?:i\.?\s*)?u\s*/\s*l|units?\s*/\s*l", "U/L"),
    (r"\bf\s*l\b|femtolit(?:re|er)s?|cu\.?\s*microns?|[uµμ]\s*m\s*3|[uµμ]m³", "fL"),
    (r"\bpg\b|picograms?", "pg"),
    (r"mm\s*hg", "mmHg"),
    (r"\bl\s*/\s*l\b", "L/L"),
    (r"%", "%"),
    (r"\bcm\b", "cm"),
    (r"\bmm\b", "mm"),
    (r"\bm\s*/\s*s\b", "m/s"),
    (r"ratio", "ratio"),
]
_COMPILED = [(re.compile(p, re.I), k) for p, k in UNIT_PATTERNS]

DISPLAY = {"10^3/uL": "×10³/µL", "10^6/uL": "×10⁶/µL", "umol/L": "µmol/L", "ug/L": "µg/L", "/uL": "/µL",
           "lakh/uL": "lakh/µL", "ratio": "", "none": ""}


def find_unit(text: str) -> tuple[str | None, str | None, int]:
    """Return (unit_key, matched_text, end_position) for the first unit near the start of text."""
    best = None
    for rx, key in _COMPILED:
        m = rx.search(text)
        if m and m.start() <= 25:
            if best is None or m.start() < best[2] or (m.start() == best[2] and len(m.group(0)) > len(best[1])):
                best = (key, m.group(0), m.start(), m.end())
    if best is None:
        return None, None, 0
    return best[0], best[1], best[3]


# analyte -> {unit_key: factor to canonical}; canonical unit has factor 1
CONVERSIONS: dict[str, dict[str, float]] = {
    "hemoglobin": {"g/dL": 1, "g/L": 0.1, "mmol/L": 1.611},
    "rbc": {"10^6/uL": 1, "10^12/L": 1, "/uL": 1e-6},
    "wbc": {"10^3/uL": 1, "10^9/L": 1, "/uL": 1e-3},
    "platelets": {"10^3/uL": 1, "10^9/L": 1, "/uL": 1e-3, "lakh/uL": 100},
    "mcv": {"fL": 1},
    "mch": {"pg": 1},
    "mchc": {"g/dL": 1, "g/L": 0.1, "%": 1},
    "rdw": {"%": 1},
    "hematocrit": {"%": 1, "L/L": 100},
    "ferritin": {"ng/mL": 1, "ug/L": 1, "pmol/L": 1 / 2.247},
    "vitamin_b12": {"pg/mL": 1, "pmol/L": 1.355, "ng/L": 1},
    "folate": {"ng/mL": 1, "ug/L": 1, "nmol/L": 1 / 2.266},
    "alt": {"U/L": 1},
    "ast": {"U/L": 1},
    "alp": {"U/L": 1},
    "total_bilirubin": {"mg/dL": 1, "umol/L": 1 / 17.1},
    "direct_bilirubin": {"mg/dL": 1, "umol/L": 1 / 17.1},
    "indirect_bilirubin": {"mg/dL": 1, "umol/L": 1 / 17.1},
    "albumin": {"g/dL": 1, "g/L": 0.1},
    "total_protein": {"g/dL": 1, "g/L": 0.1},
    "globulin": {"g/dL": 1, "g/L": 0.1},
    "ag_ratio": {"none": 1, "ratio": 1},
    "total_cholesterol": {"mg/dL": 1, "mmol/L": 38.67},
    "hdl": {"mg/dL": 1, "mmol/L": 38.67},
    "ldl": {"mg/dL": 1, "mmol/L": 38.67},
    "vldl": {"mg/dL": 1, "mmol/L": 38.67},
    "non_hdl": {"mg/dL": 1, "mmol/L": 38.67},
    "triglycerides": {"mg/dL": 1, "mmol/L": 88.57},
    "ef": {"%": 1},
    "lvidd": {"cm": 1, "mm": 0.1},
    "lvids": {"cm": 1, "mm": 0.1},
    "ivsd": {"cm": 1, "mm": 0.1},
    "lvpwd": {"cm": 1, "mm": 0.1},
    "la_diameter": {"cm": 1, "mm": 0.1},
    "aortic_root": {"cm": 1, "mm": 0.1},
    "rv_diameter": {"cm": 1, "mm": 0.1},
    "tapse": {"cm": 1, "mm": 0.1},
    "e_a_ratio": {"none": 1, "ratio": 1},
    "e_e_prime": {"none": 1, "ratio": 1},
    "rvsp": {"mmHg": 1},
}


def convert(analyte: str, value: float, unit_key: str | None) -> tuple[float | None, str]:
    """Convert to canonical. Returns (value or None if not convertible, status) where status is
    'canonical' | 'converted' | 'unit_missing' | 'unit_mismatch'."""
    table = CONVERSIONS.get(analyte, {})
    if unit_key is None:
        if "none" in table:
            return value, "canonical"
        return None, "unit_missing"
    if unit_key not in table:
        return None, "unit_mismatch"
    f = table[unit_key]
    return (value * f, "canonical" if f == 1 else "converted")
