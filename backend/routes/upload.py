from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from backend.config import settings
from backend.database import FERNET, Report, SessionLocal, add_audit, get_db
from backend.schemas import JobStatus, UploadResponse
from backend.security import UploadRejected, validate_upload
from backend.services import jobs
from backend.services.pipeline import process_report

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/reports/upload", response_model=UploadResponse)
async def upload_report(
    file: UploadFile = File(...),
    consent_store_file: bool = Form(False),
    allow_duplicate: bool = Form(False),
    db=Depends(get_db),
):
    data = await file.read(int(settings.max_upload_mb * 1024 * 1024) + 1)
    try:
        info = validate_upload(file.filename or "", data)
    except UploadRejected as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    dup = db.execute(select(Report.id).where(Report.file_sha256 == info["sha256"])).scalars().first()
    if dup and not allow_duplicate:
        raise HTTPException(status_code=409, detail={"message": "This file has already been uploaded.", "duplicate_of": dup})
    rep = Report(file_sha256=info["sha256"], file_kind=info["kind"], status="processing")
    db.add(rep)
    db.flush()
    if consent_store_file:  # only with explicit consent; encrypted at rest
        path = settings.storage_dir / f"{rep.id}.bin"
        path.write_bytes(FERNET.encrypt(data))
        rep.file_stored, rep.stored_path = True, str(path)
    add_audit(db, rep.id, "uploaded", {"kind": info["kind"], "stored": bool(consent_store_file)})
    db.commit()
    report_id, kind = rep.id, info["kind"]

    def task(progress):
        try:
            return process_report(report_id, data, kind, progress)
        except Exception:
            with SessionLocal() as s:
                r = s.get(Report, report_id)
                if r:
                    r.status, r.error = "failed", "Processing failed. Try a clearer scan or enter values manually."
                    s.commit()
            raise

    job_id = jobs.submit(task, report_id)
    return UploadResponse(report_id=report_id, job_id=job_id, duplicate_of=dup, file_stored=bool(consent_store_file))


@router.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    j = jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found (jobs expire after one hour)")
    return JobStatus(**{k: j.get(k) for k in JobStatus.model_fields})
