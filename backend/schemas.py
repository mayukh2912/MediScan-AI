"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.services.measurement_extractor import CATALOG_BY_KEY


class Demographics(BaseModel):
    age: int | None = Field(default=None, ge=0, le=120)
    sex: Literal["male", "female"] | None = None


class RangeIn(BaseModel):
    low: float | None = None
    high: float | None = None
    text: str | None = None


class MeasurementIn(BaseModel):
    key: str
    value: float | None
    input_unit: str | None = Field(default=None, description="Unit of `value` if not the canonical unit")
    reference_range: RangeIn | None = None
    test: str | None = None
    # passthrough fields from extraction (kept for audit)
    original_value: str | None = None
    original_unit: str | None = None
    extraction_confidence: float | None = None
    source_line: str | None = None
    lab_flag: str | None = None
    lab_calculated: bool | None = None

    @field_validator("key")
    @classmethod
    def known_key(cls, v):
        if v not in CATALOG_BY_KEY:
            raise ValueError(f"Unknown measurement key '{v}'")
        return v


class ConfirmRequest(BaseModel):
    measurements: list[MeasurementIn]
    demographics: Demographics = Demographics()
    report_type: str | None = None
    panels: list[str] | None = None
    report_date: str | None = None


class ManualAnalysisRequest(BaseModel):
    measurements: list[MeasurementIn]
    demographics: Demographics = Demographics()
    echo_findings: dict | None = None


class UploadResponse(BaseModel):
    report_id: str
    job_id: str
    duplicate_of: str | None = None
    file_stored: bool


class JobStatus(BaseModel):
    id: str
    report_id: str | None
    status: str
    progress: int
    stage: str
    attempts: int
    error: str | None = None
