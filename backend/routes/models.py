from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ml.common.paths import FIGURES_DIR
from ml.model_registry import list_tasks, load_metadata

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def models():
    out = []
    for t in list_tasks():
        m = load_metadata(t)
        served = m["models"][m["served_model"]]["test"]
        out.append({"task": t, "display_name": m.get("display_name"), "model_version": m["model_version"],
                    "served_model": m["served_model"], "created_at": m.get("created_at"),
                    "headline": {k: served.get(k) for k in ("roc_auc", "pr_auc", "f1", "macro_f1", "accuracy",
                                                            "balanced_accuracy") if served.get(k) is not None}})
    return out


@router.get("/{task}")
def model_detail(task: str):
    m = load_metadata(task)
    if not m:
        raise HTTPException(404, "Unknown model task")
    return m


@router.get("/figures/{name}")
def figure(name: str):
    p = (FIGURES_DIR / name).resolve()
    if p.parent != FIGURES_DIR.resolve() or not p.exists() or p.suffix != ".png":
        raise HTTPException(404, "Figure not found")
    return FileResponse(p, media_type="image/png")
