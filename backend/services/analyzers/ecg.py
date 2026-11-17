"""ECG module glue: signal files (CSV / WFDB-like text) and ECG images."""
from __future__ import annotations

import io

import numpy as np

from backend.config import settings
from ml.ecg.image_digitizer import digitize_ecg_image
from ml.ecg.predict import analyze_signal

MAX_SAMPLES = 2_000_000


def parse_signal_csv(data: bytes, fs: float | None, column: str | None = None) -> tuple[np.ndarray, float, dict]:
    """Accept a CSV with either a single numeric column, or a header with a time column
    (seconds) plus one or more lead columns. fs must be supplied unless a time column exists."""
    import pandas as pd

    text = data.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
    if all(isinstance(c, str) and c.replace(".", "", 1).lstrip("-").isdigit() for c in df.columns):
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python", header=None)
    cols = [str(c) for c in df.columns]
    df.columns = cols
    time_col = next((c for c in cols if c.strip().lower() in ("time", "t", "time_s", "seconds", "elapsed time")), None)
    numeric = [c for c in cols if c != time_col and pd.api.types.is_numeric_dtype(df[c])]
    if not numeric:
        raise ValueError("No numeric signal column found")
    lead = column if column in numeric else next((c for c in numeric if c.upper() in ("MLII", "II", "LEAD II", "ECG")), numeric[0])
    x = df[lead].to_numpy(float)[:MAX_SAMPLES]
    if fs is None:
        if time_col is None:
            raise ValueError("Sampling rate (fs) is required when the file has no time column")
        t = df[time_col].to_numpy(float)
        dt = np.median(np.diff(t))
        if not dt or dt <= 0:
            raise ValueError("Time column is not increasing")
        fs = 1.0 / dt
    if not (50 <= fs <= 5000):
        raise ValueError("Sampling rate must be between 50 and 5000 Hz")
    if np.isnan(x).mean() > 0.05:
        raise ValueError("More than 5% of samples are missing")
    x = np.nan_to_num(x, nan=float(np.nanmedian(x)))
    return x, float(fs), {"lead": lead, "columns": numeric, "time_column": time_col}


def analyze_ecg_signal_file(data: bytes, fs: float | None, column: str | None = None, mains: float | None = None,
                            model: str | None = None) -> dict:
    x, fs, info = parse_signal_csv(data, fs, column)
    if len(x) < 3 * fs:
        raise ValueError("Signal must be at least 3 seconds long")
    res = analyze_signal(x, fs, mains=mains if mains is not None else settings.mains_hz, model=model)
    res["input"] = {"type": "digitized_signal", **info}
    res["warnings"] = []
    return res


def analyze_ecg_image(data: bytes, row: int | None = None, paper_speed: float = 25.0, gain: float = 10.0,
                      model: str | None = None) -> dict:
    dig = digitize_ecg_image(data, row=row, paper_speed_mm_s=paper_speed, gain_mm_mv=gain)
    if not dig["ok"]:
        return {"input": {"type": "ecg_image"}, "digitization": {k: v for k, v in dig.items() if k != "signal"},
                "classification": {"available": False, "reason": dig["reason"]}, "warnings": [dig["reason"]]}
    digi_public = {k: v for k, v in dig.items() if k != "signal"}
    if not dig["calibrated"]:
        return {"input": {"type": "ecg_image"}, "digitization": digi_public, "heart_rate_bpm": None,
                "signal_quality": None, "classification": {"available": False, "reason": "Uncalibrated trace"},
                "warnings": dig["warnings"]}
    sig = dig["signal"]
    if len(sig) < 3 * dig["fs"]:
        return {"input": {"type": "ecg_image"}, "digitization": digi_public, "heart_rate_bpm": None,
                "classification": {"available": False, "reason": "Trace shorter than 3 seconds"},
                "warnings": dig["warnings"] + ["Trace shorter than 3 seconds: not analysed."]}
    res = analyze_signal(sig, dig["fs"], mains=None, model=model)
    res["input"] = {"type": "ecg_image"}
    res["digitization"] = digi_public
    res["warnings"] = dig["warnings"] + [
        "The beat model was trained on digital Holter recordings; signals digitised from images are out of its "
        "training distribution, so treat any classification as experimental."]
    return res
