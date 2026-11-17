"""ECHO report analysis: structured extraction + ASE/EACVI reference comparison.

Deliberate constraints:
* EF is never inferred from qualitative wording ("normal LV function").
* No heart-failure or other diagnosis is produced from a single measurement.
* Narrative findings are quoted verbatim.
"""
from __future__ import annotations

from backend.services.analyzers.common import assess_all, by_key, missing_fields
from backend.services.measurement_extractor import PANEL_FIELDS

ECHO_FIELDS = PANEL_FIELDS["ECHO"]


def _ef_band(ef: float, sex: str | None) -> str:
    # ASE 2015 LVEF ranges (normal ≥52% men, ≥54% women)
    normal_low = 54 if sex == "female" else 52
    if ef >= normal_low:
        return "within the ASE normal range" if ef <= 74 else "above the ASE normal range"
    if ef >= 41:
        return "mildly abnormal (ASE 41–51/53%)"
    if ef >= 30:
        return "moderately abnormal (ASE 30–40%)"
    return "severely abnormal (ASE <30%)"


def analyze_echo(measurements: list[dict], findings: dict | None, sex: str | None = None) -> dict:
    assessed = assess_all([m for m in measurements if m["key"] in ECHO_FIELDS], sex)
    b = by_key(assessed)
    notes = []
    if "ef" in b:
        ef = b["ef"]["value"]
        b["ef"]["ef_band"] = _ef_band(ef, sex)
        notes.append(f"Reported LVEF {ef:g}% is {_ef_band(ef, sex)}. A single EF value is not a diagnosis of heart "
                     "failure; diagnosis requires symptoms, signs and further assessment.")
    else:
        notes.append("No numeric ejection fraction was found. EF is not inferred from qualitative wording.")
        if findings and findings.get("lv_function_text"):
            notes.append("The report describes LV function in words (quoted below).")
    return {
        "module": "echo",
        "method": "structured extraction + ASE/EACVI 2015/2016 reference comparison (no ML)",
        "measurements": assessed,
        "findings": findings or {},
        "notes": notes,
        "missing": missing_fields(measurements, ECHO_FIELDS),
        "disclaimer": "Echocardiography must be interpreted by a cardiologist together with the images and the "
                      "clinical picture. This module only organises the written report.",
    }
