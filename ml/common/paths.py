"""Central path definitions so training scripts, the API and tests agree on locations."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = Path(os.environ.get("MEDISCAN_DATASETS_DIR", REPO_ROOT / "datasets"))
MODELS_DIR = Path(os.environ.get("MEDISCAN_MODELS_DIR", REPO_ROOT / "models"))
METADATA_DIR = MODELS_DIR / "metadata"
REPORTS_DIR = REPO_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

for _d in (MODELS_DIR, METADATA_DIR, REPORTS_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)
