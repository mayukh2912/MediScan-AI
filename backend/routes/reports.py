from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from backend.database import AuditEvent, Report, decrypt_json, get_db
from backend.schemas import ConfirmRequest
from backend.services.pipeline import confirm_report
from backend.services.report_generator import build_summary, summary_pdf

router = APIRouter(prefix="/api", tags=["reports"])


def _meta(r: Report) -> dict:
    return {"id": r.id, "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "report_type": r.report_type, "panels": [p for p in r.panels.split(",") if p], "status": r.status,
            "report_date": r.report_date, "n_measurements": r.n_measurements, "n_uncertain": r.n_uncertain,
            "n_abnormal": r.n_abnormal, "file_kind": r.file_kind, "file_stored": r.file_stored, "error": r.error}


def _get(db, rid: str) -> Report:
    r = db.get(Report, rid)
    if not r:
        raise HTTPException(404, "Report not found")
    return r


@router.get("/reports")
def list_reports(type: str | None = None, status: str | None = None, db=Depends(get_db)):
    q = select(Report).order_by(Report.created_at.desc())
    if type:
        q = q.where(Report.report_type == type)
    if status:
        q = q.where(Report.status == status)
    return [_meta(r) for r in db.execute(q).scalars()]


@router.get("/reports/{rid}")
def get_report(rid: str, db=Depends(get_db)):
    r = _get(db, rid)
    extraction = decrypt_json(r.extraction_blob)
    audit = db.execute(select(AuditEvent).where(AuditEvent.report_id == rid).order_by(AuditEvent.at)).scalars()
    return {**_meta(r), "extraction": extraction, "analysis": decrypt_json(r.analysis_blob),
            "audit": [{"at": a.at.isoformat(), "action": a.action, "detail": decrypt_json(a.detail_blob)} for a in audit]}


@router.get("/reports/{rid}/ocr-text")
def get_ocr_text(rid: str, db=Depends(get_db)):
    """Original OCR output, returned only on explicit request (never logged)."""
    r = _get(db, rid)
    return decrypt_json(r.ocr_blob) or {"lines": []}


@router.put("/reports/{rid}/confirm")
def confirm(rid: str, body: ConfirmRequest, db=Depends(get_db)):
    r = _get(db, rid)
    if r.status in ("processing",):
        raise HTTPException(409, "Report is still processing")
    items = [m.model_dump() for m in body.measurements]
    for m in items:
        if m.get("reference_range"):
            m["reference_range"] = {k: v for k, v in m["reference_range"].items()}
    try:
        analysis = confirm_report(db, r, items, body.demographics.model_dump(), body.report_type, body.panels,
                                  body.report_date)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {**_meta(r), "analysis": analysis}


@router.delete("/reports/{rid}")
def delete_report(rid: str, db=Depends(get_db)):
    r = _get(db, rid)
    if r.stored_path and os.path.exists(r.stored_path):
        os.remove(r.stored_path)
    db.delete(r)
    db.commit()
    return {"deleted": rid}


@router.delete("/reports")
def delete_all(confirm: bool = Query(False), db=Depends(get_db)):
    if not confirm:
        raise HTTPException(400, "Pass ?confirm=true to delete all stored data")
    n = 0
    for r in db.execute(select(Report)).scalars():
        if r.stored_path and os.path.exists(r.stored_path):
            os.remove(r.stored_path)
        db.delete(r)
        n += 1
    db.commit()
    return {"deleted": n}


@router.get("/reports/{rid}/download")
def download_report(rid: str, db=Depends(get_db)):
    r = _get(db, rid)
    if r.status != "analysed":
        raise HTTPException(409, "Report has not been analysed yet")
    s = build_summary([{"id": r.id, "report_type": r.report_type, "report_date": r.report_date,
                        "created_at": r.created_at.isoformat(), "analysis": decrypt_json(r.analysis_blob)}])
    return Response(summary_pdf(s), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="mediscan_{rid[:8]}.pdf"'})


def _analysed(db, ids: list[str] | None):
    q = select(Report).where(Report.status == "analysed").order_by(Report.created_at)
    if ids:
        q = q.where(Report.id.in_(ids))
    return [{"id": r.id, "report_type": r.report_type, "report_date": r.report_date, "created_at": r.created_at.isoformat(),
             "analysis": decrypt_json(r.analysis_blob)} for r in db.execute(q).scalars()]


@router.get("/summary")
def summary(ids: str | None = None, db=Depends(get_db)):
    return build_summary(_analysed(db, ids.split(",") if ids else None))


@router.get("/summary/pdf")
def summary_pdf_route(ids: str | None = None, db=Depends(get_db)):
    s = build_summary(_analysed(db, ids.split(",") if ids else None))
    return Response(summary_pdf(s), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="mediscan_summary.pdf"'})


@router.get("/summary/json")
def summary_json(ids: str | None = None, db=Depends(get_db)):
    s = build_summary(_analysed(db, ids.split(",") if ids else None))
    return Response(json.dumps(s, indent=2, default=str), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="mediscan_summary.json"'})


@router.get("/stats")
def stats(db=Depends(get_db)):
    """Counts of reports processed in THIS deployment (no health statistics)."""
    rows = db.execute(select(Report.report_type, Report.status, func.count()).group_by(Report.report_type, Report.status)).all()
    by_type: dict[str, int] = {}
    analysed_by_type: dict[str, int] = {}
    total = 0
    for t, st, n in rows:
        total += n
        by_type[t] = by_type.get(t, 0) + n
        if st == "analysed":
            analysed_by_type[t] = analysed_by_type.get(t, 0) + n
    recent = [_meta(r) for r in db.execute(select(Report).order_by(Report.created_at.desc()).limit(8)).scalars()]
    return {"total_reports": total, "by_type": by_type, "analysed_by_type": analysed_by_type, "recent": recent}
