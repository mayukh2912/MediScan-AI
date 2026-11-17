"""ECG paper/image digitisation (OpenCV).

Steps: grid detection (colour + periodicity) -> waveform mask -> lead-row segmentation ->
column-wise trace extraction -> calibration from grid spacing -> 1-D signal.

Calibration assumes the standard 25 mm/s paper speed and 10 mm/mV gain unless the caller
supplies other values; both assumptions are returned explicitly. If no grid can be detected
reliably, the trace is returned in pixel units only and no heart rate / intervals /
classification are produced.
"""
from __future__ import annotations

import cv2
import numpy as np


def _load(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Unreadable image")
    if max(img.shape[:2]) > 3500:
        f = 3500 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return img


def _period(profile: np.ndarray, lo: int = 4, hi: int = 80) -> tuple[float | None, float]:
    p = profile - profile.mean()
    if np.allclose(p, 0):
        return None, 0.0
    ac = np.correlate(p, p, mode="full")[len(p) - 1:]
    ac = ac / (ac[0] + 1e-12)
    hi = min(hi, len(ac) - 1)
    if hi <= lo:
        return None, 0.0
    seg = ac[lo:hi]
    # first local maximum that reaches 70% of the best peak (avoids picking a harmonic)
    peaks = [i for i in range(1, len(seg) - 1) if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1]]
    if not peaks:
        return None, 0.0
    best = max(seg[i] for i in peaks)
    k = next(i for i in peaks if seg[i] >= 0.7 * best) + lo
    # refine with parabolic interpolation
    if 1 <= k < len(ac) - 1:
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        denom = a - 2 * b + c
        k = k + (0.5 * (a - c) / denom if denom != 0 else 0)
    return float(k), float(ac[int(round(k))])


def detect_grid(img: np.ndarray) -> dict:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    b, g, r = [img[:, :, i].astype(int) for i in range(3)]
    colored = ((r - g > 25) & (r - b > 10)) | ((hsv[:, :, 1] > 40) & (hsv[:, :, 2] > 120))
    if colored.mean() > 0.01:
        mask = colored.astype(np.uint8)
        kind = "coloured grid"
    else:  # grey-scale grid: light lines (not the darkest waveform pixels)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = ((gray < 235) & (gray > 120)).astype(np.uint8)
        kind = "grey grid"
    px, cx = _period(mask.sum(axis=0).astype(float))
    py, cy = _period(mask.sum(axis=1).astype(float))
    ok = px is not None and py is not None and cx > 0.3 and cy > 0.3 and abs(px - py) / max(px, py) < 0.15
    small = (px + py) / 2 if ok else None
    # If the dominant period is the large (5 mm) box, the small box is a fifth of it
    if ok and small >= 20:
        sub, csub = _period(mask.sum(axis=0).astype(float), lo=max(3, int(small / 5) - 2), hi=int(small / 5) + 3)
        if sub and csub > 0.2 and abs(sub * 5 - small) / small < 0.1:
            small = sub
    return {"detected": bool(ok), "kind": kind, "small_box_px": small,
            "confidence": round(float(min(cx, cy)) if ok else 0.0, 3), "mask": mask}


def waveform_mask(img: np.ndarray, grid_mask: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    dark_thr = min(110, int(np.percentile(gray, 3)) + 40)
    m = (gray < dark_thr) & (hsv[:, :, 1] < 120)
    m &= grid_mask == 0
    m = m.astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return m


def segment_rows(mask: np.ndarray) -> list[tuple[int, int]]:
    prof = (mask > 0).sum(axis=1).astype(float)
    k = max(5, mask.shape[0] // 60)
    sm = np.convolve(prof, np.ones(k) / k, mode="same")
    active = sm > max(1.5, 0.002 * mask.shape[1])
    rows, start = [], None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            if i - start > max(5, mask.shape[0] * 0.02):
                rows.append((start, i))
            start = None
    if start is not None and mask.shape[0] - start > max(5, mask.shape[0] * 0.02):
        rows.append((start, mask.shape[0]))
    return rows


def trace_row(mask: np.ndarray, top: int, bottom: int) -> tuple[np.ndarray, float, int, int]:
    band = mask[top:bottom] > 0
    cols = np.where(band.any(axis=0))[0]
    if len(cols) < 20:
        return np.array([]), 0.0, 0, 0
    c0, c1 = int(cols[0]), int(cols[-1])
    ys_all = np.where(band[:, c0:c1 + 1])[0]
    baseline = float(np.median(ys_all))
    y = np.full(c1 - c0 + 1, np.nan)
    for j, c in enumerate(range(c0, c1 + 1)):
        rows = np.where(band[:, c])[0]
        if len(rows):
            y[j] = rows[np.argmax(np.abs(rows - baseline))] if np.ptp(rows) > 3 else rows.mean()
    coverage = float(np.isfinite(y).mean())
    idx = np.arange(len(y))
    good = np.isfinite(y)
    y = np.interp(idx, idx[good], y[good])
    return (baseline - y), coverage, c0, c1  # invert: image y grows downwards


def digitize_ecg_image(data: bytes, row: int | None = None, paper_speed_mm_s: float = 25.0,
                       gain_mm_mv: float = 10.0) -> dict:
    img = _load(data)
    grid = detect_grid(img)
    mask = waveform_mask(img, grid["mask"])
    rows = segment_rows(mask)
    warnings = []
    if not rows:
        return {"ok": False, "reason": "No waveform could be found in the image.", "grid": _grid_public(grid)}
    # choose the requested row or the one with the widest horizontal extent (often the rhythm strip)
    extents = []
    for t, b in rows:
        cols = np.where((mask[t:b] > 0).any(axis=0))[0]
        extents.append(int(cols[-1] - cols[0]) if len(cols) else 0)
    chosen = row if row is not None and 0 <= row < len(rows) else int(np.argmax(extents))
    sig_px, coverage, c0, c1 = trace_row(mask, *rows[chosen])
    if len(sig_px) == 0:
        return {"ok": False, "reason": "Selected row has no traceable waveform.", "grid": _grid_public(grid)}
    if coverage < 0.85:
        warnings.append(f"Only {coverage:.0%} of columns contained trace pixels; gaps were interpolated.")
    calibrated = grid["detected"] and grid["small_box_px"] and grid["confidence"] >= 0.35
    if calibrated:
        px_per_mm = grid["small_box_px"]
        fs = px_per_mm * paper_speed_mm_s
        signal = sig_px / (px_per_mm * gain_mm_mv)
        unit = "mV"
        warnings.append(f"Calibration assumes {paper_speed_mm_s:g} mm/s and {gain_mm_mv:g} mm/mV; confirm these "
                        "match the values printed on the ECG.")
    else:
        fs, signal, unit = None, sig_px, "px"
        warnings.append("ECG grid could not be detected reliably: time and amplitude calibration is unavailable, so "
                        "heart rate, intervals and beat classification are not computed.")
    step = max(1, len(signal) // 1500)
    return {
        "ok": True,
        "calibrated": bool(calibrated),
        "fs": fs, "unit": unit,
        "signal": signal,
        "rows_detected": len(rows),
        "row_used": chosen,
        "row_bounds": [list(map(int, r)) for r in rows],
        "x_range_px": [c0, c1],
        "trace_coverage": round(coverage, 3),
        "grid": _grid_public(grid),
        "assumptions": {"paper_speed_mm_s": paper_speed_mm_s, "gain_mm_mv": gain_mm_mv} if calibrated else None,
        "preview": [{"t": round(i / fs, 3) if fs else i, "v": round(float(signal[i]), 4)} for i in range(0, len(signal), step)],
        "warnings": warnings,
    }


def _grid_public(grid: dict) -> dict:
    return {k: v for k, v in grid.items() if k != "mask"}
