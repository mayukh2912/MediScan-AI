from __future__ import annotations

import copy

from backend.services.analyzers.reference import compare
from backend.services.measurement_extractor import CATALOG_BY_KEY


def by_key(measurements: list[dict]) -> dict[str, dict]:
    return {m["key"]: m for m in measurements if m.get("value") is not None and m.get("status") != "invalid"}


def assess_all(measurements: list[dict], sex: str | None) -> list[dict]:
    out = []
    for m in measurements:
        m = copy.deepcopy(m)
        if m.get("value") is None or m.get("status") == "invalid":
            m["assessment"] = {"interpretation": "not_assessed", "range_used": None,
                               "rule": "Value missing or marked invalid"}
        else:
            m["assessment"] = compare(m, sex)
        out.append(m)
    return out


def missing_fields(measurements: list[dict], fields: list[str]) -> list[dict]:
    present = {m["key"] for m in measurements if m.get("value") is not None}
    return [{"key": k, "test": CATALOG_BY_KEY[k].name} for k in fields if k not in present]


def derived_measure(key: str, name: str, value: float | None, unit: str, formula: str, note: str | None = None,
                    applicable: bool = True) -> dict:
    return {"key": key, "name": name, "value": None if value is None else round(value, 3), "unit": unit,
            "formula": formula, "note": note, "applicable": applicable, "origin": "derived",
            "label": "Calculated by MediScan AI (not laboratory-measured)"}
