"""Report processing orchestration: OCR -> classify -> extract -> validate -> store (awaiting
confirmation) and, after confirmation, analysis."""
from __future__ import annotations

import copy
import logging

from backend.database import Report, SessionLocal, add_audit, decrypt_json, encrypt_json
from backend.services.analyzers.blood import analyze_blood
from backend.services.analyzers.echo import analyze_echo
from backend.services.analyzers.lipid import analyze_lipid
from backend.services.analyzers.liver import analyze_liver
from backend.services.document_classifier import classify_document
from backend.services.measurement_extractor import (
    CATALOG_BY_KEY, extract_demographics, extract_echo_findings, extract_measurements, extract_report_date,
)
from backend.services.ocr_service import run_ocr
from backend.services.units import DISPLAY, convert
from backend.services.validation_service import validate_measurements

log = logging.getLogger("mediscan.pipeline")


def extract_from_document(data: bytes, kind: str, progress=lambda p, s: None) -> dict:
    progress(10, "ocr")
    ocr = run_ocr(data, kind)
    lines = [l.__dict__ for l in ocr.lines]
    progress(55, "classifying")
    cls = classify_document(ocr.text)
    progress(65, "extracting")
    meas = [m.as_dict() for m in extract_measurements(lines, cls["panels"])]
    progress(80, "validating")
    validated = validate_measurements(meas)
    narrative = [l for l in lines if l["source"] != "pdf_text_row"]  # row-joined PDF lines would duplicate text
    echo_findings = extract_echo_findings(narrative) if "ECHO" in cls["panels"] else None
    ecg = None
    if cls["report_type"] == "ECG":
        progress(85, "digitizing ecg")
        ecg = _ecg_from_document(data, kind)
    return {
        "classification": cls,
        "measurements": validated["measurements"],
        "validation": validated["summary"],
        "report_date": extract_report_date(lines),
        "demographics_suggested": extract_demographics(lines),
        "echo_findings": echo_findings,
        "ecg": ecg,
        "ocr": {"method": ocr.method, "pages": ocr.pages, "mean_confidence": ocr.mean_confidence,
                "preprocessing": ocr.preprocessing, "rotation_applied": ocr.rotation_applied,
                "skew_corrected_deg": ocr.skew_corrected_deg, "quality_warnings": ocr.quality_warnings,
                "n_lines": len(ocr.lines)},
        "_ocr_lines": lines,
    }


def _ecg_from_document(data: bytes, kind: str) -> dict | None:
    from backend.services.analyzers.ecg import analyze_ecg_image

    try:
        if kind == "pdf":
            import fitz

            doc = fitz.open(stream=data, filetype="pdf")
            png = doc[0].get_pixmap(dpi=200).tobytes("png")
            doc.close()
            return analyze_ecg_image(png)
        return analyze_ecg_image(data)
    except Exception as e:  # noqa: BLE001
        log.warning("ECG digitisation failed: %s", type(e).__name__)
        return {"classification": {"available": False, "reason": "ECG digitisation failed"}, "warnings": []}


def process_report(report_id: str, data: bytes, kind: str, progress) -> dict:
    result = extract_from_document(data, kind, progress)
    progress(92, "saving")
    with SessionLocal() as db:
        rep = db.get(Report, report_id)
        lines = result.pop("_ocr_lines")
        rep.ocr_blob = encrypt_json({"lines": lines})  # original OCR text preserved, encrypted at rest
        rep.extraction_blob = encrypt_json(result)
        rep.report_type = result["classification"]["report_type"]
        rep.panels = ",".join(result["classification"]["panels"])
        rep.report_date = (result.get("report_date") or {}).get("date")
        rep.n_measurements = len(result["measurements"])
        rep.n_uncertain = result["validation"]["n_uncertain"] + result["validation"]["n_invalid"]
        rep.status = "awaiting_confirmation" if (result["measurements"] or result.get("ecg")) else "needs_manual_entry"
        add_audit(db, report_id, "extracted", {"n_measurements": rep.n_measurements, "n_uncertain": rep.n_uncertain})
        db.commit()
    return {"report_id": report_id, "status": rep.status}


def _rng(r: dict | None) -> tuple:
    r = r or {}
    return (r.get("low"), r.get("high"))


def _diff_and_mark(original: list[dict], confirmed: list[dict]) -> tuple[list[dict], list[dict]]:
    orig = {m["key"]: m for m in original}
    out, changes = [], []
    for m in confirmed:
        key = m["key"]
        if key not in CATALOG_BY_KEY:
            continue
        a = CATALOG_BY_KEY[key]
        m = copy.deepcopy(m)
        m["test"] = a.name
        m["panel"] = a.panel
        m["unit_display"] = DISPLAY.get(a.canonical_unit, a.canonical_unit)
        if m.get("value") is not None and m.get("input_unit") and m["input_unit"] != a.canonical_unit:
            conv, st = convert(key, float(m["value"]), m["input_unit"])
            if conv is None:
                raise ValueError(f"Unit {m['input_unit']} cannot be converted for {a.name}")
            m["value"] = round(conv, 4)
        m["unit"] = a.canonical_unit
        o = orig.get(key)
        if o is None:
            m["origin"] = "manual"
            m["extraction_confidence"] = 1.0
            m["issues"] = ["Entered manually by user"]
            changes.append({"key": key, "from": None, "to": m.get("value")})
        elif o.get("value") != m.get("value") or _rng(o.get("reference_range")) != _rng(m.get("reference_range")):
            m["origin"] = "manual"
            m["extraction_confidence"] = 1.0
            m["issues"] = [f"Corrected by user (extracted value: {o.get('value')})"]
            changes.append({"key": key, "from": o.get("value"), "to": m.get("value")})
        else:
            m["origin"] = o.get("origin", "ocr")
            m["issues"] = [i for i in o.get("issues", []) if not i.startswith("Low extraction confidence")]
            m["status"] = "ok"  # user explicitly confirmed this value
            m["confirmed_by_user"] = True
        m["status"] = "ok" if m["origin"] == "manual" else m.get("status", "ok")
        out.append(m)
    for key in orig:
        if key not in {m["key"] for m in confirmed}:
            changes.append({"key": key, "from": orig[key].get("value"), "to": "removed"})
    return out, changes


def run_analyses(measurements: list[dict], panels: list[str], demographics: dict, echo_findings=None) -> dict:
    sex, age = demographics.get("sex"), demographics.get("age")
    keys = {m["key"] for m in measurements}
    panel_of = {m["key"]: CATALOG_BY_KEY[m["key"]].panel for m in measurements}
    present = set(panel_of.values()) | set(panels)
    out = {}
    if present & {"CBC", "BLOOD", "IRON_VITAMIN"} and keys & {"hemoglobin", "rbc", "wbc", "platelets", "mcv", "mch",
                                                              "mchc", "rdw", "hematocrit", "ferritin", "vitamin_b12", "folate"}:
        out["blood"] = analyze_blood(measurements, sex)
    if "LFT" in present and any(panel_of.get(k) == "LFT" for k in keys):
        out["liver"] = analyze_liver(measurements, sex, age)
    if "LIPID" in present and any(panel_of.get(k) == "LIPID" for k in keys):
        out["lipid"] = analyze_lipid(measurements, sex)
    if "ECHO" in present and (any(panel_of.get(k) == "ECHO" for k in keys) or echo_findings):
        out["echo"] = analyze_echo(measurements, echo_findings, sex)
    return out


def confirm_report(db, rep: Report, confirmed: list[dict], demographics: dict, report_type: str | None,
                   panels: list[str] | None, report_date: str | None) -> dict:
    extraction = decrypt_json(rep.extraction_blob) or {}
    measurements, changes = _diff_and_mark(extraction.get("measurements", []), confirmed)
    validated = validate_measurements(measurements)
    invalid = [m for m in validated["measurements"] if m["status"] == "invalid"]
    if invalid:
        raise ValueError("Implausible values must be corrected or removed before analysis: "
                         + ", ".join(f"{m['test']}={m['value']}" for m in invalid))
    panels = panels or (rep.panels.split(",") if rep.panels else [])
    analysis = run_analyses(validated["measurements"], panels, demographics, extraction.get("echo_findings"))
    if extraction.get("ecg"):
        analysis["ecg"] = extraction["ecg"]
    analysis["_meta"] = {"demographics": demographics, "report_date": report_date or rep.report_date,
                         "confirmed_measurements": validated["measurements"]}
    rep.analysis_blob = encrypt_json(analysis)
    if report_type:
        rep.report_type = report_type
    rep.panels = ",".join(panels)
    rep.report_date = report_date or rep.report_date
    rep.n_measurements = len(validated["measurements"])
    rep.n_uncertain = 0
    rep.n_abnormal = sum(1 for mod in analysis.values() if isinstance(mod, dict)
                         for m in mod.get("measurements", []) if m.get("assessment", {}).get("interpretation") in ("low", "high"))
    rep.status = "analysed"
    add_audit(db, rep.id, "confirmed", {"changes": changes})
    db.commit()
    return analysis
