"""Indian Liver Patient Dataset (ILPD) ingestion and validation.

Accepts either the Kaggle file ``indian_liver_patient.csv`` (with header) or the original
UCI file ``Indian Liver Patient Dataset (ILPD).csv`` (no header). The schema is checked
before any modelling happens.

Label semantics (from the dataset documentation): ``Dataset == 1`` marks a record from a
"liver patient" and ``Dataset == 2`` a "non liver patient". It is NOT a specific diagnosis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CANONICAL_COLUMNS = [
    "Age",
    "Gender",
    "Total_Bilirubin",
    "Direct_Bilirubin",
    "Alkaline_Phosphotase",
    "Alamine_Aminotransferase",
    "Aspartate_Aminotransferase",
    "Total_Protiens",
    "Albumin",
    "Albumin_and_Globulin_Ratio",
    "Dataset",
]
NUMERIC_COLUMNS = [c for c in CANONICAL_COLUMNS if c not in ("Gender", "Dataset")]

# Physiologically plausible bounds used only to detect corrupted rows (not reference ranges).
PLAUSIBLE = {
    "Age": (0, 110),
    "Total_Bilirubin": (0, 80),
    "Direct_Bilirubin": (0, 40),
    "Alkaline_Phosphotase": (10, 5000),
    "Alamine_Aminotransferase": (1, 10000),
    "Aspartate_Aminotransferase": (1, 10000),
    "Total_Protiens": (1, 15),
    "Albumin": (0.5, 7),
    "Albumin_and_Globulin_Ratio": (0.05, 5),
}


@dataclass
class ValidationReport:
    n_rows: int
    n_columns: int
    missing: dict
    out_of_range: dict
    exact_duplicates: int
    class_counts: dict
    gender_counts: dict
    issues: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__


def load_ilpd(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    with open(path) as f:
        first = f.readline()
    if "Age" in first or "age" in first.lower():
        df = pd.read_csv(path)
        # Kaggle and UCI header spellings vary slightly; map positionally after checking count
    else:
        df = pd.read_csv(path, header=None)
    if df.shape[1] != len(CANONICAL_COLUMNS):
        raise ValueError(f"Expected {len(CANONICAL_COLUMNS)} columns, found {df.shape[1]}")
    df.columns = CANONICAL_COLUMNS
    df["Gender"] = df["Gender"].astype(str).str.strip().str.capitalize()
    lab = df["Dataset"]
    if lab.dtype == object:
        df["Dataset"] = lab.map(lambda v: 1 if str(v).strip().lower() in {"1", "liver_disease"} else 2)
    for c in NUMERIC_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def validate_ilpd(df: pd.DataFrame) -> ValidationReport:
    issues = []
    if set(df["Gender"].unique()) - {"Male", "Female"}:
        issues.append("Unexpected Gender values")
    if set(df["Dataset"].unique()) - {1, 2}:
        issues.append("Unexpected label values")
    oor = {}
    for c, (lo, hi) in PLAUSIBLE.items():
        bad = df[c].notna() & ((df[c] < lo) | (df[c] > hi))
        if bad.any():
            oor[c] = int(bad.sum())
    if oor:
        issues.append(f"Implausible values present: {oor}")
    bad_db = (df["Direct_Bilirubin"] > df["Total_Bilirubin"] + 1e-9).sum()
    if bad_db:
        issues.append(f"{int(bad_db)} rows with direct bilirubin > total bilirubin")
    return ValidationReport(
        n_rows=len(df),
        n_columns=df.shape[1],
        missing={k: int(v) for k, v in df.isna().sum().items() if v},
        out_of_range=oor,
        exact_duplicates=int(df.duplicated().sum()),
        class_counts={str(k): int(v) for k, v in df["Dataset"].value_counts().items()},
        gender_counts={str(k): int(v) for k, v in df["Gender"].value_counts().items()},
        issues=issues,
    )


def to_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    X = df.drop(columns=["Dataset"]).copy()
    y = (df["Dataset"] == 1).astype(int).to_numpy()  # 1 = "liver patient" record
    return X, y
