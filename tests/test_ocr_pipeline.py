"""OCR on synthetic documents, including rotated, blurry and PDF inputs."""
import pytest

from backend.services.pipeline import extract_from_document

EXPECTED_CBC = {"hemoglobin": 10.5, "wbc": 7.5, "platelets": 250, "mcv": 72, "mch": 21.4, "mchc": 31.8,
                "rdw": 16.9, "hematocrit": 33.0, "ferritin": 9.0, "rbc": 4.9}


def _vals(res):
    return {m["key"]: m["value"] for m in res["measurements"]}


def _read(p):
    return open(p, "rb").read()


def test_cbc_image(fixtures):
    res = extract_from_document(_read(fixtures["cbc_png"]), "image")
    assert res["classification"]["report_type"] == "CBC"
    vals = _vals(res)
    hits = sum(1 for k, v in EXPECTED_CBC.items() if vals.get(k) is not None and abs(vals[k] - v) < 1e-6)
    assert hits >= 9, vals
    assert res["report_date"]["date"] == "2025-03-14"
    assert res["demographics_suggested"] == {"age": 34, "sex": "female"}


def test_rotated_90_image_is_corrected(fixtures):
    res = extract_from_document(_read(fixtures["cbc_rot90_png"]), "image")
    assert res["ocr"]["rotation_applied"] in (90, 270)
    assert _vals(res).get("hemoglobin") == 10.5


def test_skewed_image_is_deskewed(fixtures):
    res = extract_from_document(_read(fixtures["cbc_rotated_png"]), "image")
    assert abs(res["ocr"]["skew_corrected_deg"]) > 2
    # every value is either correct or flagged (never silently wrong)
    for m in res["measurements"]:
        if m["key"] in EXPECTED_CBC and m["value"] is not None and abs(m["value"] - EXPECTED_CBC[m["key"]]) > 1e-6:
            assert m["status"] in ("uncertain", "invalid"), m


def test_blurry_image_fails_safely(fixtures):
    res = extract_from_document(_read(fixtures["cbc_blurry_png"]), "image")
    assert res["ocr"]["quality_warnings"]
    for m in res["measurements"]:  # anything extracted from garbage must not be silently trusted
        if m["value"] is not None and abs(m["value"] - EXPECTED_CBC.get(m["key"], -1)) > 1e-6:
            assert m["status"] != "ok"


def test_pdf_text_layer(fixtures):
    res = extract_from_document(_read(fixtures["lft_lipid_pdf"]), "pdf")
    assert set(res["classification"]["panels"]) >= {"LFT", "LIPID"}
    v = _vals(res)
    assert v["alt"] == 96 and v["ast"] == 71 and v["total_cholesterol"] == 232 and v["hdl"] == 38
    assert all(m["extraction_confidence"] == 1.0 for m in res["measurements"])


def test_echo_pdf(fixtures):
    res = extract_from_document(_read(fixtures["echo_pdf"]), "pdf")
    assert res["classification"]["report_type"] == "ECHO"
    v = _vals(res)
    assert v["ef"] == 45 and v["lvidd"] == 5.1 and v["la_diameter"] == 4.2
    f = res["echo_findings"]
    assert "mitral" in f["valve_findings"]
    assert any("Inferior wall hypokinesia" in t for t in f["impression"])
