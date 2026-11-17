"""OCR pipeline: load -> (PDF text layer | rasterise) -> orientation -> deskew -> denoise ->
contrast -> Tesseract with word-level confidences -> line reconstruction.

Tesseract is used (rather than PaddleOCR) because it runs fully offline on CPU, has a small
footprint and reports per-word confidences. Nothing is sent to external services.
"""
from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass, field

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

from backend.config import settings


@dataclass
class OCRLine:
    text: str
    confidence: float  # 0..1 (mean of word confidences; 1.0 for embedded PDF text)
    page: int
    source: str  # "pdf_text" | "ocr"


@dataclass
class OCRResult:
    lines: list[OCRLine] = field(default_factory=list)
    pages: int = 0
    method: str = ""
    preprocessing: list[str] = field(default_factory=list)
    rotation_applied: int = 0
    skew_corrected_deg: float = 0.0
    mean_confidence: float = 0.0
    quality_warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["text"] = self.text
        return d


# ---------------------------------------------------------------- image preprocessing

def pil_to_gray(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img)  # respect camera orientation tags
    return np.array(img.convert("L"))


def blur_score(gray: np.ndarray) -> float:
    """Variance of the Laplacian; < ~60 is typically a blurry photo of text."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _orientation_score(gray: np.ndarray) -> float:
    small = gray if max(gray.shape) <= 1600 else cv2.resize(gray, None, fx=1600 / max(gray.shape), fy=1600 / max(gray.shape))
    d = pytesseract.image_to_data(small, config="--psm 6", output_type=pytesseract.Output.DICT)
    return float(sum(float(c) for c, w in zip(d["conf"], d["text"]) if w.strip() and float(c) > 60 and len(w) > 1))


def detect_orientation(gray: np.ndarray) -> int:
    """Tesseract OSD proposes a 0/90/180/270 rotation (degrees clockwise). When its confidence is
    low we verify by comparing OCR word confidence for the original vs the proposed rotation."""
    try:
        osd = pytesseract.image_to_osd(gray, config="--psm 0 -c min_characters_to_try=10")
    except pytesseract.TesseractError:
        return 0
    m = re.search(r"Rotate: (\d+)", osd)
    conf = re.search(r"Orientation confidence: ([\d.]+)", osd)
    if not m or int(m.group(1)) == 0:
        return 0
    rot = int(m.group(1))
    if conf and float(conf.group(1)) >= 2.0:
        return rot
    try:
        return rot if _orientation_score(rotate_bound(gray, rot)) > 1.2 * _orientation_score(gray) else 0
    except pytesseract.TesseractError:
        return 0


def rotate_bound(gray: np.ndarray, deg_cw: int) -> np.ndarray:
    k = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(deg_cw)
    return cv2.rotate(gray, k) if k is not None else gray


def estimate_skew(gray: np.ndarray) -> float:
    """Estimate small skew angle (degrees) from text line orientation via Hough lines on a
    dilated binary image. Restricted to +/-15 degrees."""
    small = gray
    scale = 1.0
    if max(gray.shape) > 2000:
        scale = 2000 / max(gray.shape)
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    bw = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3)))
    lines = cv2.HoughLinesP(bw, 1, np.pi / 720, threshold=200, minLineLength=small.shape[1] // 4, maxLineGap=20)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(a) <= 15:
            angles.append(a)
    return float(np.median(angles)) if angles else 0.0


def deskew(gray: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.3:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def enhance(gray: np.ndarray) -> np.ndarray:
    # upscale small images so glyphs are ~30px high for Tesseract
    if gray.shape[1] < 1500:
        f = 1500 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def preprocess(gray: np.ndarray, result: OCRResult) -> np.ndarray:
    rot = detect_orientation(gray)
    if rot:
        gray = rotate_bound(gray, rot)
        result.rotation_applied = rot
        result.preprocessing.append(f"rotated {rot}°")
    angle = estimate_skew(gray)
    gray = deskew(gray, angle)
    if abs(angle) >= 0.3:
        result.skew_corrected_deg = round(angle, 2)
        result.preprocessing.append(f"deskewed {angle:.1f}°")
    gray = enhance(gray)
    result.preprocessing += ["non-local-means denoise", "CLAHE contrast"]
    return gray


# ---------------------------------------------------------------- OCR

def ocr_image(gray: np.ndarray, page: int) -> list[OCRLine]:
    data = pytesseract.image_to_data(
        gray, lang=settings.ocr_lang, config="--oem 1 --psm 6 -c preserve_interword_spaces=1",
        output_type=pytesseract.Output.DICT,
    )
    groups: dict[tuple, list[tuple[int, str, float]]] = {}
    for i, word in enumerate(data["text"]):
        if not word or not word.strip():
            continue
        conf = float(data["conf"][i])
        if conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append((data["left"][i], word, conf / 100.0))
    lines = []
    for key in sorted(groups, key=lambda k: (k[0], k[1], k[2])):
        words = sorted(groups[key])
        text = " ".join(w for _, w, _ in words)
        conf = float(np.mean([c for *_, c in words]))
        lines.append(OCRLine(text=text, confidence=round(conf, 3), page=page, source="ocr"))
    return lines


def run_ocr_on_image_bytes(data: bytes) -> OCRResult:
    res = OCRResult(pages=1, method="tesseract")
    with Image.open(io.BytesIO(data)) as img:
        gray = pil_to_gray(img)
    bs = blur_score(gray)
    if bs < 60:
        res.quality_warnings.append(f"Image appears blurry (sharpness {bs:.0f}); values may be misread.")
    gray = preprocess(gray, res)
    res.lines = ocr_image(gray, page=1)
    _finalise(res)
    return res


def run_ocr_on_pdf_bytes(data: bytes) -> OCRResult:
    """Prefer the embedded text layer (exact, confidence 1.0). Pages with too little text
    (scanned PDFs) are rasterised at 300 dpi and OCR'd."""
    import fitz

    res = OCRResult(method="pdf_text")
    doc = fitz.open(stream=data, filetype="pdf")
    res.pages = doc.page_count
    used_ocr = False
    for pno, page in enumerate(doc, start=1):
        txt = page.get_text("text") or ""
        if len(re.sub(r"\s", "", txt)) >= 40:
            for line in txt.splitlines():
                if line.strip():
                    res.lines.append(OCRLine(text=line.strip(), confidence=1.0, page=pno, source="pdf_text"))
            # PDF text layers often split "label value unit" across lines; also add row-joined text
            res.lines.extend(_pdf_rows(page, pno))
        else:
            used_ocr = True
            pix = page.get_pixmap(dpi=300, colorspace=fitz.csGRAY)
            gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            gray = preprocess(gray, res)
            res.lines.extend(ocr_image(gray, page=pno))
    doc.close()
    if used_ocr:
        res.method = "pdf_text+tesseract" if any(l.source == "pdf_text" for l in res.lines) else "tesseract(pdf raster)"
    _finalise(res)
    return res


def _pdf_rows(page, pno: int) -> list[OCRLine]:
    """Re-assemble table rows from word boxes (words sharing a baseline)."""
    words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,wno
    rows: dict[int, list] = {}
    for w in words:
        key = int(round((w[1] + w[3]) / 2 / 4))  # 4pt buckets on vertical centre
        rows.setdefault(key, []).append(w)
    out = []
    for key in sorted(rows):
        ws = sorted(rows[key], key=lambda w: w[0])
        text = " ".join(w[4] for w in ws)
        if text.strip():
            out.append(OCRLine(text=text, confidence=1.0, page=pno, source="pdf_text_row"))
    return out


def _finalise(res: OCRResult):
    confs = [l.confidence for l in res.lines]
    res.mean_confidence = round(float(np.mean(confs)), 3) if confs else 0.0
    if not res.lines:
        res.quality_warnings.append("No text could be read from the document.")
    elif res.mean_confidence < 0.6:
        res.quality_warnings.append("Low OCR confidence overall; please verify every value.")


def run_ocr(data: bytes, kind: str) -> OCRResult:
    return run_ocr_on_pdf_bytes(data) if kind == "pdf" else run_ocr_on_image_bytes(data)
