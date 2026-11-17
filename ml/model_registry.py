"""Minimal file-based model registry.

Each trained model writes ``models/metadata/<task>.json`` describing the served model,
its version, dataset hash, evaluation metrics and limitations. The API reads only from
here, so the UI can never show a metric that was not produced by a training run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ml.common.paths import METADATA_DIR, MODELS_DIR


def save_metadata(task: str, metadata: dict[str, Any]) -> Path:
    metadata = dict(metadata)
    metadata.setdefault("task", task)
    metadata.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    path = METADATA_DIR / f"{task}.json"
    path.write_text(json.dumps(metadata, indent=2, default=float))
    return path


def load_metadata(task: str) -> dict[str, Any] | None:
    path = METADATA_DIR / f"{task}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_tasks() -> list[str]:
    return sorted(p.stem for p in METADATA_DIR.glob("*.json"))


def model_path(task: str, filename: str) -> Path:
    d = MODELS_DIR / task
    d.mkdir(parents=True, exist_ok=True)
    return d / filename
