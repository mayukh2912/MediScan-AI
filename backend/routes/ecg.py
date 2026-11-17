from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.config import REPO_ROOT, settings
from backend.security import UploadRejected, validate_upload
from backend.services.analyzers.ecg import analyze_ecg_image, analyze_ecg_signal_file

router = APIRouter(prefix="/api/ecg", tags=["ecg"])
SAMPLE = REPO_ROOT / "backend" / "sample_data" / "mitdb_233_excerpt_60s.csv"
SAMPLE_IMG = REPO_ROOT / "backend" / "sample_data" / "ecg_strip_rendered_from_mitdb_233.png"


@router.post("/signal")
async def ecg_signal(file: UploadFile = File(...), fs: float | None = Form(None), column: str | None = Form(None),
                     mains_hz: float | None = Form(None), model: str | None = Form(None)):
    data = await file.read(int(settings.max_upload_mb * 1024 * 1024) + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(400, "File too large")
    if not (file.filename or "").lower().endswith((".csv", ".txt")):
        raise HTTPException(400, "Signal files must be .csv or .txt")
    if model not in (None, "", "xgboost", "random_forest", "cnn_1d"):
        raise HTTPException(400, "Unknown model")
    try:
        return analyze_ecg_signal_file(data, fs, column, mains_hz, model or None)
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(422, str(e)) from e


@router.post("/image")
async def ecg_image(file: UploadFile = File(...), row: int | None = Form(None), paper_speed_mm_s: float = Form(25.0),
                    gain_mm_mv: float = Form(10.0), model: str | None = Form(None)):
    data = await file.read(int(settings.max_upload_mb * 1024 * 1024) + 1)
    try:
        info = validate_upload(file.filename or "", data)
    except UploadRejected as e:
        raise HTTPException(400, str(e)) from e
    if info["kind"] == "pdf":
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
        data = doc[0].get_pixmap(dpi=200).tobytes("png")
        doc.close()
    if paper_speed_mm_s not in (12.5, 25.0, 50.0) or gain_mm_mv not in (5.0, 10.0, 20.0):
        raise HTTPException(400, "Paper speed must be 12.5/25/50 mm/s and gain 5/10/20 mm/mV")
    return analyze_ecg_image(data, row, paper_speed_mm_s, gain_mm_mv, model or None)


@router.get("/sample-signal")
def sample_signal():
    """60 s excerpt of MIT-BIH record 233 (test-set record, MLII, 360 Hz; ODC-By 1.0)."""
    return FileResponse(SAMPLE, media_type="text/csv", filename=SAMPLE.name)


@router.get("/sample-image")
def sample_image():
    return FileResponse(SAMPLE_IMG, media_type="image/png", filename=SAMPLE_IMG.name)
