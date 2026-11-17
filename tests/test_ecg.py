"""ECG signal processing, digitisation and model inference."""
from pathlib import Path

import numpy as np
import pytest

from ml.ecg.image_digitizer import digitize_ecg_image
from ml.ecg.signal_processing import (
    clean_ecg, detect_r_peaks, extract_beats, heart_rate_bpm, remove_baseline_wander, remove_powerline, signal_quality,
)
from ml.model_registry import load_metadata

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "backend" / "sample_data" / "mitdb_233_excerpt_60s.csv"
SAMPLE_IMG = ROOT / "backend" / "sample_data" / "ecg_strip_rendered_from_mitdb_233.png"


def synthetic_ecg(fs=360, hr=72, seconds=20, noise=0.02, seed=0):
    """Gaussian-pulse pseudo-ECG used only to test DSP routines (not physiological data)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * seconds)) / fs
    x = np.zeros_like(t)
    rr = 60 / hr
    for b in np.arange(0.5, seconds, rr):
        x += 1.0 * np.exp(-((t - b) ** 2) / (2 * 0.01 ** 2))  # QRS
        x += 0.25 * np.exp(-((t - b - 0.25) ** 2) / (2 * 0.04 ** 2))  # T
    return t, x + noise * rng.standard_normal(len(t))


def test_baseline_and_powerline_filters():
    fs = 360
    t, x = synthetic_ecg(fs)
    drift = 0.8 * np.sin(2 * np.pi * 0.2 * t)
    hum = 0.3 * np.sin(2 * np.pi * 50 * t)
    y = remove_powerline(remove_baseline_wander(x + drift + hum, fs), fs, 50)
    ref = remove_baseline_wander(x, fs)
    assert np.corrcoef(y, ref)[0, 1] > 0.95


def test_r_peak_detection_and_hr():
    fs = 360
    _, x = synthetic_ecg(fs, hr=75)
    r = detect_r_peaks(clean_ecg(x, fs), fs)
    assert abs(heart_rate_bpm(r, fs) - 75) < 2
    assert abs(len(r) - 25) <= 1


def test_signal_quality_rejects_noise():
    fs = 360
    noise = np.random.default_rng(1).standard_normal(fs * 10)
    assert signal_quality(clean_ecg(noise, fs), fs)["usable"] is False
    flat = np.zeros(fs * 10)
    assert signal_quality(flat, fs)["usable"] is False


def test_beat_extraction_shapes():
    fs = 125
    _, x = synthetic_ecg(fs, seconds=10)
    r = detect_r_peaks(x, fs)
    beats, rr, kept = extract_beats(x, r)
    assert beats.shape[1] == 99 and rr.shape[1] == 7 and len(beats) == len(kept)
    assert np.allclose(beats.mean(1), 0, atol=1e-6)


@pytest.mark.skipif(load_metadata("ecg") is None, reason="ECG model not trained")
def test_classification_on_real_test_record():
    from ml.ecg.predict import analyze_signal

    data = np.loadtxt(SAMPLE, delimiter=",", skiprows=1)
    res = analyze_signal(data[:, 1], 360.0, mains=60)
    c = res["classification"]
    assert c["available"] and c["n_beats"] > 50
    assert set(c["counts"]) == {"N", "S", "V", "F"}
    assert 60 < res["heart_rate_bpm"] < 140


def test_digitizer_on_rendered_strip():
    d = digitize_ecg_image(SAMPLE_IMG.read_bytes())
    assert d["ok"] and d["calibrated"]
    assert abs(d["grid"]["small_box_px"] - 200 / 25.4) / (200 / 25.4) < 0.03  # rendered at 200 dpi
    assert d["fs"] == pytest.approx(25 * d["grid"]["small_box_px"])


def test_digitizer_refuses_calibration_without_grid():
    import cv2

    img = np.full((300, 1200, 3), 255, np.uint8)
    xs = np.arange(1200)
    ys = (150 - 60 * np.exp(-((xs % 200 - 100) ** 2) / 20)).astype(int)
    for x0, y0 in zip(xs, ys):
        img[y0 - 1:y0 + 2, x0] = 0
    ok, png = cv2.imencode(".png", img)
    d = digitize_ecg_image(png.tobytes())
    assert d["ok"] and d["calibrated"] is False and d["fs"] is None
