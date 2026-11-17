"""Feature engineering for the liver model. Lives in its own module so pickled pipelines
can be re-imported at inference time."""
from __future__ import annotations

import numpy as np
import pandas as pd

RAW_FEATURES = [
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
]

DERIVED_FEATURES = ["Indirect_Bilirubin", "Globulin", "AST_ALT_Ratio", "Is_Male"]

NUMERIC_MODEL_FEATURES = [c for c in RAW_FEATURES if c != "Gender"] + DERIVED_FEATURES

FRIENDLY_NAMES = {
    "Age": "Age",
    "Total_Bilirubin": "Total bilirubin",
    "Direct_Bilirubin": "Direct bilirubin",
    "Alkaline_Phosphotase": "ALP",
    "Alamine_Aminotransferase": "ALT",
    "Aspartate_Aminotransferase": "AST",
    "Total_Protiens": "Total protein",
    "Albumin": "Albumin",
    "Albumin_and_Globulin_Ratio": "A/G ratio",
    "Indirect_Bilirubin": "Indirect bilirubin (derived)",
    "Globulin": "Globulin (derived)",
    "AST_ALT_Ratio": "AST/ALT ratio (derived)",
    "Is_Male": "Sex = male",
}


def add_derived_features(X: pd.DataFrame) -> pd.DataFrame:
    """Deterministic, documented derivations:
    * Indirect bilirubin = total - direct (clipped at 0)
    * Globulin = total protein - albumin
    * AST/ALT ratio (De Ritis ratio)
    * Is_Male = 1 if Gender == Male
    No target information is used, so this is leakage-free.
    """
    X = X.copy()
    X["Indirect_Bilirubin"] = (X["Total_Bilirubin"] - X["Direct_Bilirubin"]).clip(lower=0)
    X["Globulin"] = X["Total_Protiens"] - X["Albumin"]
    alt = X["Alamine_Aminotransferase"].replace(0, np.nan)
    X["AST_ALT_Ratio"] = X["Aspartate_Aminotransferase"] / alt
    X["Is_Male"] = (X["Gender"].astype(str).str.lower() == "male").astype(float)
    return X[NUMERIC_MODEL_FEATURES]


def log1p_safe(X):
    return np.log1p(np.clip(X, 0, None))
