"""Measurement validation: physiological plausibility, unit sanity, cross-field consistency,
confidence gating. Validation never changes a value; it only annotates status and issues.

Plausibility limits are deliberately wide (they catch OCR errors such as a dropped decimal
point, not clinical abnormality). Reference ranges for abnormality live in analyzers/reference.py.
"""
from __future__ import annotations

from backend.config import settings

# canonical-unit plausibility limits: values outside are almost certainly extraction errors
PLAUSIBLE = {
    "hemoglobin": (2, 25), "rbc": (0.5, 10), "wbc": (0.1, 500), "platelets": (1, 3000),
    "mcv": (40, 160), "mch": (10, 60), "mchc": (20, 45), "rdw": (8, 40), "hematocrit": (5, 75),
    "ferritin": (0.5, 100000), "vitamin_b12": (20, 20000), "folate": (0.2, 100),
    "alt": (1, 20000), "ast": (1, 30000), "alp": (5, 5000), "total_bilirubin": (0.05, 60),
    "direct_bilirubin": (0, 40), "indirect_bilirubin": (0, 40), "albumin": (0.5, 7.5),
    "total_protein": (2, 15), "globulin": (0.5, 10), "ag_ratio": (0.1, 5),
    "total_cholesterol": (40, 1500), "hdl": (5, 200), "ldl": (5, 1000), "vldl": (1, 500),
    "triglycerides": (10, 10000), "non_hdl": (10, 1400),
    "ef": (5, 90), "lvidd": (2, 10), "lvids": (1, 9), "ivsd": (0.3, 3.5), "lvpwd": (0.3, 3.5),
    "la_diameter": (1.5, 9), "aortic_root": (1.5, 7), "rv_diameter": (1, 7), "tapse": (0.3, 4.5),
    "e_a_ratio": (0.2, 6), "e_e_prime": (2, 50), "rvsp": (10, 150),
}


def _issue(m: dict, text: str, status: str | None = None):
    m.setdefault("issues", []).append(text)
    if status == "invalid" or (status == "uncertain" and m.get("status") != "invalid"):
        m["status"] = status


def validate_measurements(measurements: list[dict]) -> dict:
    """Mutates and returns measurements with status/issues; also returns summary."""
    by = {m["key"]: m for m in measurements}
    for m in measurements:
        m.setdefault("issues", [])
        m["status"] = m.get("status") or "ok"
        if m.get("origin") == "manual":
            m["status"] = "ok"
        if m["value"] is None:
            _issue(m, "No usable numeric value (unit missing or not convertible)", "uncertain")
            continue
        lo, hi = PLAUSIBLE.get(m["key"], (None, None))
        if lo is not None and not (lo <= m["value"] <= hi):
            _issue(m, f"Value {m['value']} {m.get('unit', '')} is outside the physiologically plausible range "
                      f"({lo}–{hi}); likely an extraction or unit error", "invalid")
        if m.get("origin") != "manual" and m.get("extraction_confidence", 1) < settings.uncertain_confidence:
            _issue(m, f"Low extraction confidence ({m['extraction_confidence']:.2f})", "uncertain")
        if any("not valid for" in i or "Unit not found" in i or "Multiple different values" in i for i in m["issues"]):
            if m["status"] == "ok":
                m["status"] = "uncertain"
        rr = m.get("reference_range")
        if rr and rr.get("low") is not None and rr.get("high") is not None and m["value"] is not None:
            width = rr["high"] - rr["low"]
            if width > 0 and (m["value"] > rr["high"] + 20 * width):
                _issue(m, "Value is far outside the lab's own reference range; check for a misplaced decimal point",
                       "uncertain")

    def v(k):
        x = by.get(k)
        return x["value"] if x and x.get("value") is not None and x.get("status") != "invalid" else None

    # ---- cross-field consistency checks (all documented identities)
    if v("direct_bilirubin") is not None and v("total_bilirubin") is not None and v("direct_bilirubin") > v("total_bilirubin") + 0.05:
        for k in ("direct_bilirubin", "total_bilirubin"):
            _issue(by[k], "Direct bilirubin exceeds total bilirubin (inconsistent)", "uncertain")
    if v("hdl") is not None and v("total_cholesterol") is not None and v("hdl") >= v("total_cholesterol"):
        for k in ("hdl", "total_cholesterol"):
            _issue(by[k], "HDL is not lower than total cholesterol (inconsistent)", "uncertain")
    if v("ldl") is not None and v("total_cholesterol") is not None and v("ldl") >= v("total_cholesterol"):
        for k in ("ldl", "total_cholesterol"):
            _issue(by[k], "LDL is not lower than total cholesterol (inconsistent)", "uncertain")
    if v("albumin") is not None and v("total_protein") is not None and v("albumin") >= v("total_protein"):
        for k in ("albumin", "total_protein"):
            _issue(by[k], "Albumin is not lower than total protein (inconsistent)", "uncertain")
    if v("lvids") is not None and v("lvidd") is not None and v("lvids") >= v("lvidd"):
        for k in ("lvids", "lvidd"):
            _issue(by[k], "LVIDs is not smaller than LVIDd (inconsistent)", "uncertain")
    # Red cell index identities: MCHC = Hb/Hct*100 ; MCH = Hb/RBC*10 ; MCV = Hct/RBC*10
    for key, calc, label in (
        ("mchc", (lambda: v("hemoglobin") / v("hematocrit") * 100) if v("hemoglobin") and v("hematocrit") else None, "Hb/Hct×100"),
        ("mch", (lambda: v("hemoglobin") / v("rbc") * 10) if v("hemoglobin") and v("rbc") else None, "Hb/RBC×10"),
        ("mcv", (lambda: v("hematocrit") / v("rbc") * 10) if v("hematocrit") and v("rbc") else None, "Hct/RBC×10"),
    ):
        if calc and v(key):
            expected = calc()
            if abs(expected - v(key)) / v(key) > 0.15:
                _issue(by[key], f"Differs >15% from value implied by other indices ({label} = {expected:.1f}); "
                                "one of the related values may be misread", "uncertain")

    summary = {
        "n_total": len(measurements),
        "n_ok": sum(m["status"] == "ok" for m in measurements),
        "n_uncertain": sum(m["status"] == "uncertain" for m in measurements),
        "n_invalid": sum(m["status"] == "invalid" for m in measurements),
    }
    summary["requires_confirmation"] = True  # analysis always runs only after user confirmation
    summary["has_blocking_issues"] = summary["n_invalid"] > 0
    return {"measurements": measurements, "summary": summary}
