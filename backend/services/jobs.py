"""Asynchronous job runner with status, progress and retries.

In-process ThreadPoolExecutor keeps the prototype dependency-free. The interface (submit /
get / progress callback) is deliberately small so it can be swapped for Celery/RQ/Arq with a
Redis broker when running several API replicas.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from backend.config import settings

log = logging.getLogger("mediscan.jobs")
_executor = ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="mediscan-job")
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
JOB_TTL_S = 3600


def _set(job_id: str, **kw):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kw, updated_at=time.time())


def get_job(job_id: str) -> dict | None:
    with _lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def _gc():
    now = time.time()
    with _lock:
        for k in [k for k, j in _jobs.items() if j["status"] in ("succeeded", "failed") and now - j["updated_at"] > JOB_TTL_S]:
            del _jobs[k]


def submit(fn: Callable[[Callable[[int, str], None]], dict], report_id: str | None = None) -> str:
    """fn receives a progress(percent, stage) callback and returns a result dict."""
    _gc()
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {"id": job_id, "report_id": report_id, "status": "queued", "progress": 0, "stage": "queued",
                         "attempts": 0, "error": None, "created_at": time.time(), "updated_at": time.time()}

    def progress(p: int, stage: str):
        _set(job_id, progress=int(p), stage=stage)

    def run():
        for attempt in range(1, settings.job_max_retries + 2):
            _set(job_id, status="running", attempts=attempt)
            try:
                result = fn(progress)
                _set(job_id, status="succeeded", progress=100, stage="done", result=result)
                return
            except NonRetryableError as e:
                _set(job_id, status="failed", error=str(e), stage="failed")
                return
            except Exception as e:  # noqa: BLE001
                # log only the exception type: messages may contain document content
                log.warning("job %s attempt %d failed: %s", job_id, attempt, type(e).__name__)
                if attempt > settings.job_max_retries:
                    _set(job_id, status="failed", error=f"Processing failed ({type(e).__name__}).", stage="failed")
                    return
                time.sleep(0.5 * attempt)

    _executor.submit(run)
    return job_id


class NonRetryableError(Exception):
    pass
