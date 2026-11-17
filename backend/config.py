"""Runtime configuration (12-factor: everything from environment variables)."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'backend' / 'mediscan.db'}")
    # Hosting providers often hand out postgres:// URLs; SQLAlchemy + psycopg 3 needs postgresql+psycopg://
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    app_name = "MediScan AI"
    database_url = _db_url()
    storage_dir = Path(os.environ.get("MEDISCAN_STORAGE_DIR", REPO_ROOT / "backend" / "storage"))
    # Fernet key for encryption at rest. If unset, a key is generated into storage_dir/.key
    # for local development. In production set MEDISCAN_ENCRYPTION_KEY explicitly.
    encryption_key = os.environ.get("MEDISCAN_ENCRYPTION_KEY")
    api_key = os.environ.get("MEDISCAN_API_KEY")  # optional shared-secret auth for the API
    cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
    # Default also allows Vercel deployments so a hosted frontend can talk to this API out of the box.
    # Set CORS_ORIGIN_REGEX="" in production to restrict to CORS_ORIGINS only.
    cors_origin_regex = os.environ.get("CORS_ORIGIN_REGEX", r"https://[a-z0-9-]+\.vercel\.app") or None
    max_upload_mb = float(os.environ.get("MAX_UPLOAD_MB", "15"))
    max_pdf_pages = int(os.environ.get("MAX_PDF_PAGES", "10"))
    max_image_pixels = int(os.environ.get("MAX_IMAGE_PIXELS", str(60_000_000)))
    ocr_lang = os.environ.get("OCR_LANG", "eng")
    job_workers = int(os.environ.get("JOB_WORKERS", "2"))
    job_max_retries = int(os.environ.get("JOB_MAX_RETRIES", "1"))
    uncertain_confidence = float(os.environ.get("UNCERTAIN_CONFIDENCE", "0.80"))
    mains_hz = float(os.environ.get("MAINS_HZ", "50"))
    enforce_https = _bool("ENFORCE_HTTPS", False)


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
