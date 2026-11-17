"""Unit normalisation, measurement parsing, classification and validation."""
import pytest

from backend.services.document_classifier import classify_document
from backend.services.measurement_extractor import extract_measurements, extract_report_date
from backend.services.units import convert, find_unit
from backend.services.validation_service import validate_measurements


def lines(*texts, conf=0.95):
    return [{"text": t, "confidence": conf, "page": 1, "source": "ocr"} for t in texts]


def by_key(ms):
    return {m.key: m for m in ms}


@pytest.mark.parametrize("text,unit", [
    ("g/dL 12-15", "g/dL"), ("gm/dl", "g/dL"), ("gm%", "g/dL"), ("mill/cumm", "10^6/uL"), ("x10^3/µL", "10^3/uL"),
    ("lakhs/cumm", "lakh/uL"), ("cells/cumm", "/uL"), ("10^9/L", "10^9/L"), ("µmol/L", "umol/L"), ("IU/L", "U/L"),
    ("mmol/L", "mmol/L"), ("fL", "fL"), ("pg/mL", "pg/mL"),
])
def test_find_unit(text, unit):
    assert find_unit(text)[0] == unit


def test_unit_conversions():
    assert convert("hemoglobin", 105, "g/L") == (pytest.approx(10.5), "converted")
    assert convert("total_bilirubin", 17.1, "umol/L")[0] == pytest.approx(1.0)
    assert convert("total_cholesterol", 5.0, "mmol/L")[0] == pytest.approx(193.35)
    assert convert("triglycerides", 1.0, "mmol/L")[0] == pytest.approx(88.57)
    assert convert("platelets", 2.5, "lakh/uL")[0] == pytest.approx(250)
    assert convert("wbc", 7500, "/uL")[0] == pytest.approx(7.5)
    assert convert("hemoglobin", 10.5, None) == (None, "unit_missing")
    assert convert("hemoglobin", 10.5, "U/L") == (None, "unit_mismatch")


def test_parse_cbc_lines_with_ranges_and_flags():
    ms = by_key(extract_measurements(lines(
        "Hemoglobin 10.5 L g/dL 12.0 - 15.5",
        "Total Leucocyte Count 7,500 cells/cumm 4000 - 11000",
        "Platelet Count 2,50,000 /cumm 150000-410000",
        "MCV 72 fL 80-100", "MCH 21.4 pg 27-33", "MCHC 31.8 g/dL 32-36",
    )))
    hb = ms["hemoglobin"]
    assert hb.value == 10.5 and hb.unit == "g/dL" and hb.lab_flag == "L"
    assert hb.reference_range["low"] == 12.0 and hb.reference_range["high"] == 15.5
    assert ms["wbc"].value == 7.5 and ms["wbc"].reference_range["high"] == 11.0
    assert ms["platelets"].value == 250 and ms["platelets"].reference_range["high"] == 410
    assert ms["mch"].value == 21.4 and ms["mchc"].value == 31.8  # MCH must not swallow MCHC


def test_lipid_aliases_do_not_collide():
    ms = by_key(extract_measurements(lines(
        "Total Cholesterol 5.2 mmol/L", "HDL Cholesterol 1.0 mmol/L", "LDL Cholesterol (Direct) 3.1 mmol/L",
        "VLDL 0.6 mmol/L", "Triglycerides 1.5 mmol/L", "Non-HDL Cholesterol 4.2 mmol/L", "LDL/HDL Ratio 3.1",
    )))
    assert ms["total_cholesterol"].value == pytest.approx(201.08, abs=0.01)
    assert ms["hdl"].value == pytest.approx(38.67, abs=0.01)
    assert ms["ldl"].value == pytest.approx(119.88, abs=0.01)
    assert ms["triglycerides"].value == pytest.approx(132.86, abs=0.01)
    assert ms["non_hdl"].value == pytest.approx(162.41, abs=0.01)
    assert "Converted" in " ".join(ms["hdl"].issues)


def test_missing_unit_is_flagged_not_guessed():
    ms = by_key(extract_measurements(lines("Hemoglobin 10.5")))
    assert ms["hemoglobin"].value is None
    assert any("Unit not found" in i for i in ms["hemoglobin"].issues)


def test_multiple_units_bilirubin_si():
    ms = by_key(extract_measurements(lines("Bilirubin Total 34.2 µmol/L 3-21", "Bilirubin Direct 10 umol/L")))
    assert ms["total_bilirubin"].value == pytest.approx(2.0)
    assert ms["total_bilirubin"].reference_range["high"] == pytest.approx(21 / 17.1, rel=1e-3)
    assert ms["direct_bilirubin"].value == pytest.approx(0.5848, rel=1e-3)


def test_reference_range_is_not_taken_as_value():
    ms = extract_measurements(lines("Hemoglobin 13.0 - 17.0 g/dL"))
    assert ms == []


def test_ocr_digit_confusion_fixed():
    ms = by_key(extract_measurements(lines("Hemoglobin 1O.5 g/dL")))
    assert ms["hemoglobin"].value == 10.5


def test_echo_fields_only_when_echo_panel():
    txt = lines("LA 4.2 cm", "LVEF 55 %")
    assert extract_measurements(txt, ["CBC"]) == []
    assert {m.key for m in extract_measurements(txt, ["ECHO"])} == {"la_diameter", "ef"}


def test_report_date():
    d = extract_report_date(lines("Patient: XXX", "Reported On: 03/04/2025 10:15"))
    assert d["date"] == "2025-04-03" and d["ambiguous_day_month"] is True


@pytest.mark.parametrize("text,expected", [
    ("Complete Blood Count Haemoglobin RBC WBC Platelet MCV MCH", "CBC"),
    ("Liver Function Test SGPT SGOT Bilirubin Total Albumin", "LFT"),
    ("Lipid Profile Total Cholesterol HDL LDL Triglycerides", "LIPID"),
    ("2D Echocardiography LVEF 60% LVIDd mitral regurgitation", "ECHO"),
    ("ECG 12 lead sinus rhythm QRS QTc aVR aVL aVF 25 mm/s 10 mm/mV", "ECG"),
    ("Invoice for consultation fee", "UNKNOWN"),
])
def test_classifier(text, expected):
    assert classify_document(text)["report_type"] == expected


def test_validation_flags_impossible_and_inconsistent():
    ms = [
        {"key": "hemoglobin", "test": "Hemoglobin", "value": 105.0, "unit": "g/dL", "extraction_confidence": 0.95},
        {"key": "total_bilirubin", "test": "TB", "value": 0.8, "unit": "mg/dL", "extraction_confidence": 0.95},
        {"key": "direct_bilirubin", "test": "DB", "value": 1.5, "unit": "mg/dL", "extraction_confidence": 0.95},
        {"key": "mcv", "test": "MCV", "value": 85.0, "unit": "fL", "extraction_confidence": 0.5},
    ]
    out = {m["key"]: m for m in validate_measurements(ms)["measurements"]}
    assert out["hemoglobin"]["status"] == "invalid"
    assert out["direct_bilirubin"]["status"] == "uncertain"
    assert out["mcv"]["status"] == "uncertain"
