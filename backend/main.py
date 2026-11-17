"""MediScan AI – FastAPI application entry point.

Run locally:  uvicorn backend.main:app --reload --port 8000   (from the repository root)
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from backend.config import settings
from backend.database import init_db
from backend.routes import analysis, ecg, models, reports, upload
from backend.security import require_api_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mediscan")

app = FastAPI(
    title="MediScan AI API",
    version="1.0.0",
    description="Educational research prototype for medical report extraction and analysis. Not a medical device.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def private_network_access(request: Request, call_next):
    """Chromium's Private Network Access: a page on https://*.vercel.app calling an API on
    localhost sends a preflight with Access-Control-Request-Private-Network; answer it so a
    locally-running backend works with the hosted frontend."""
    resp = await call_next(request)
    if request.method == "OPTIONS" and request.headers.get("access-control-request-private-network"):
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if settings.enforce_https and request.headers.get("x-forwarded-proto", request.url.scheme) == "http":
        return RedirectResponse(str(request.url.replace(scheme="https")), status_code=307)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    if settings.enforce_https:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Never echo exception messages: they may contain document content.
    log.error("Unhandled %s on %s", type(exc).__name__, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error"})


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    from ml.model_registry import list_tasks

    return {"status": "ok", "models": list_tasks(), "disclaimer": "Educational research prototype – not for clinical use."}


for r in (upload.router, reports.router, analysis.router, ecg.router, models.router):
    app.include_router(r, dependencies=[Depends(require_api_key)])
