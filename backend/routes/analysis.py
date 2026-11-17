"""Direct (manual-entry) analysis endpoints for each module. Stateless: nothing is stored.

Per the project structure these could live in blood.py / liver.py / lipid.py / echo.py; they
share one validation path so they are grouped here and re-exported by those modules.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import ManualAnalysisRequest
from backend.services.analyzers.blood import analyze_blood
from backend.services.analyzers.echo import analyze_echo
from backend.services.analyzers.lipid import analyze_lipid
from backend.services.analyzers.liver import analyze_liver
from backend.services.measurement_extractor import CATALOG_BY_KEY
from backend.services.units import DISPLAY, convert
from backend.services.validation_service import validate_measurements

router = APIRouter(prefix="/api", tags=["analysis"])


def _prepare(body: ManualAnalysisRequest) -> list[dict]:
    out = []
    for m in body.measurements:
        if m.value is None:
            continue
        a = CATALOG_BY_KEY[m.key]
        value = m.value
        if m.input_unit and m.input_unit != a.canonical_unit:
            value, st = convert(m.key, m.value, m.input_unit)
            if value is None:
                raise HTTPException(422, f"Unit '{m.input_unit}' is not valid for {a.name}")
        out.append({"key": m.key, "test": a.name, "panel": a.panel, "value": round(value, 4), "unit": a.canonical_unit, "unit_display": DISPLAY.get(a.canonical_unit, a.canonical_unit),
                    "reference_range": m.reference_range.model_dump() if m.reference_range else None,
                    "origin": "manual", "extraction_confidence": 1.0, "issues": [], "status": "ok",
                    "lab_calculated": bool(m.lab_calculated)})
    v = validate_measurements(out)
    bad = [m for m in v["measurements"] if m["status"] == "invalid"]
    if bad:
        raise HTTPException(422, "Implausible values: " + "; ".join(f"{m['test']}: {m['issues'][-1]}" for m in bad))
    return v["measurements"]


@router.post("/blood/analyze")
def blood(body: ManualAnalysisRequest):
    return analyze_blood(_prepare(body), body.demographics.sex)


@router.post("/liver/analyze")
def liver(body: ManualAnalysisRequest):
    return analyze_liver(_prepare(body), body.demographics.sex, body.demographics.age)


@router.post("/lipid/analyze")
def lipid(body: ManualAnalysisRequest):
    return analyze_lipid(_prepare(body), body.demographics.sex)


@router.post("/echo/analyze")
def echo(body: ManualAnalysisRequest):
    return analyze_echo(_prepare(body), body.echo_findings, body.demographics.sex)


@router.get("/catalog")
def catalog():
    from backend.services.analyzers.reference import default_range
    from backend.services.units import CONVERSIONS

    return [{"key": a.key, "name": a.name, "panel": a.panel, "unit": a.canonical_unit,
             "accepted_units": [u for u in CONVERSIONS.get(a.key, {}) if u != "none"],
             "default_range": default_range(a.key, None)} for a in CATALOG_BY_KEY.values()]
