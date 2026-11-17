"""Upload validation and API protection."""
from __future__ import annotations

import hashlib
import hmac
import io

from fastapi import Header, HTTPException, status
from PIL import Image

from backend.config import settings

ALLOWED = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
}
EXT_KIND = {".pdf": "pdf", ".png": "png", ".jpg": "jpg", ".jpeg": "jpg"}

Image.MAX_IMAGE_PIXELS = settings.max_image_pixels  # decompression-bomb guard


class UploadRejected(ValueError):
    pass


def sniff_kind(data: bytes) -> str | None:
    for kind, sigs in ALLOWED.items():
        if any(data.startswith(s) for s in sigs):
            return kind
    return None


def validate_upload(filename: str, data: bytes) -> dict:
    """Validate by size, extension AND magic bytes (never trust the client content-type).
    Images are fully decoded with Pillow; PDFs are opened with PyMuPDF and page-limited.
    Returns {'kind': 'pdf'|'image', 'sha256': ...}."""
    if not data:
        raise UploadRejected("Empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise UploadRejected(f"File exceeds {settings.max_upload_mb:.0f} MB limit")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in EXT_KIND:
        raise UploadRejected("Only JPG, JPEG, PNG and PDF files are accepted")
    kind = sniff_kind(data)
    if kind is None or kind != EXT_KIND[ext]:
        raise UploadRejected("File content does not match its extension")
    if kind == "pdf":
        import fitz

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as e:  # noqa: BLE001
            raise UploadRejected("Unreadable PDF") from e
        if doc.needs_pass or doc.is_encrypted:
            raise UploadRejected("Encrypted PDFs are not supported")
        if doc.page_count == 0:
            raise UploadRejected("PDF has no pages")
        if doc.page_count > settings.max_pdf_pages:
            raise UploadRejected(f"PDF has more than {settings.max_pdf_pages} pages")
        # Embedded JavaScript / launch actions are never executed: we only rasterise / read text.
        doc.close()
        out_kind = "pdf"
    else:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                if im.width < 50 or im.height < 50:
                    raise UploadRejected("Image is too small to contain a readable report")
        except Image.DecompressionBombError as e:
            raise UploadRejected("Image dimensions too large") from e
        except UploadRejected:
            raise
        except Exception as e:  # noqa: BLE001
            raise UploadRejected("Corrupted or unreadable image") from e
        out_kind = "image"
    return {"kind": out_kind, "sha256": hashlib.sha256(data).hexdigest()}


def require_api_key(x_api_key: str | None = Header(default=None)):
    """If MEDISCAN_API_KEY is configured every /api route requires the header X-API-Key."""
    if settings.api_key and not (x_api_key and hmac.compare_digest(x_api_key, settings.api_key)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
