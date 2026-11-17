"""ECG signal processing primitives (NumPy/SciPy only, so inference stays lightweight).

All functions take a 1-D signal in millivolts (or arbitrary units for normalised data)
and the sampling frequency ``fs`` in Hz.
"""
from __future__ import annotations

import numpy as np
from scipy import signal as sps
from scipy.stats import kurtosis, skew

TARGET_FS = 125  # beats are resampled to 125 Hz (same rate as the Kaggle heartbeat dataset)
PRE_S, POST_S = 0.30, 0.50  # beat window around the R peak (seconds)
BEAT_LEN = int(PRE_S * TARGET_FS) + int(POST_S * TARGET_FS)  # 37 + 62 = 99 samples
RR_FEATURES = ["pre_RR", "post_RR", "local_RR", "pre_RR/local_RR", "pre_RR/mean_RR", "post_RR/mean_RR", "post_RR/pre_RR"]
N_RR = len(RR_FEATURES)


def remove_baseline_wander(x: np.ndarray, fs: float, cutoff: float = 0.5) -> np.ndarray:
    """High-pass Butterworth (zero-phase) to remove respiration / movement baseline drift."""
    b, a = sps.butter(2, cutoff / (fs / 2), btype="highpass")
    return sps.filtfilt(b, a, x)


def remove_powerline(x: np.ndarray, fs: float, mains: float = 50.0, q: float = 30.0) -> np.ndarray:
    """IIR notch at the mains frequency (50 Hz in India/EU, 60 Hz in the Americas)."""
    if mains >= fs / 2:
        return x
    b, a = sps.iirnotch(mains, q, fs)
    return sps.filtfilt(b, a, x)


def lowpass(x: np.ndarray, fs: float, cutoff: float = 40.0) -> np.ndarray:
    cutoff = min(cutoff, 0.45 * fs)
    b, a = sps.butter(4, cutoff / (fs / 2), btype="lowpass")
    return sps.filtfilt(b, a, x)


def clean_ecg(x: np.ndarray, fs: float, mains: float | None = 50.0) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x - np.nanmedian(x)
    x = np.nan_to_num(x)
    x = remove_baseline_wander(x, fs)
    if mains:
        x = remove_powerline(x, fs, mains)
    return lowpass(x, fs)


def resample(x: np.ndarray, fs: float, target_fs: float = TARGET_FS) -> np.ndarray:
    if fs == target_fs:
        return x
    n = int(round(len(x) * target_fs / fs))
    return sps.resample_poly(x, int(target_fs * 1000), int(fs * 1000))[:n] if n else x


def detect_r_peaks(x: np.ndarray, fs: float) -> np.ndarray:
    """Pan-Tompkins-style detector: band-pass 5-15 Hz -> derivative -> square ->
    moving-window integration -> adaptive threshold peak picking -> refine to local max
    of |signal|. Returns sample indices."""
    x = np.asarray(x, dtype=float)
    if len(x) < fs:  # less than one second
        return np.array([], dtype=int)
    b, a = sps.butter(2, [5 / (fs / 2), min(15 / (fs / 2), 0.99)], btype="band")
    f = sps.filtfilt(b, a, x)
    d = np.gradient(f)
    e = d ** 2
    w = max(1, int(0.15 * fs))
    mwi = np.convolve(e, np.ones(w) / w, mode="same")
    thr = 0.35 * np.percentile(mwi, 99)
    peaks, _ = sps.find_peaks(mwi, height=thr, distance=int(0.25 * fs))
    # refine to the max absolute deflection in the cleaned signal near each candidate
    r = []
    half = int(0.08 * fs)
    polarity = 1.0 if np.abs(np.max(x)) >= np.abs(np.min(x)) else -1.0
    for p in peaks:
        lo, hi = max(0, p - half), min(len(x), p + half)
        seg = polarity * x[lo:hi]
        if len(seg):
            r.append(lo + int(np.argmax(seg)))
    r = np.unique(np.array(r, dtype=int))
    if len(r) > 1:  # enforce refractory period after refinement
        keep = [r[0]]
        for p in r[1:]:
            if p - keep[-1] >= int(0.25 * fs):
                keep.append(p)
        r = np.array(keep)
    return r


def rr_intervals(r_peaks: np.ndarray, fs: float) -> np.ndarray:
    return np.diff(r_peaks) / fs


def heart_rate_bpm(r_peaks: np.ndarray, fs: float) -> float | None:
    rr = rr_intervals(r_peaks, fs)
    rr = rr[(rr > 0.25) & (rr < 2.5)]
    if len(rr) < 2:
        return None
    return float(60.0 / np.median(rr))


def signal_quality(x: np.ndarray, fs: float, r_peaks: np.ndarray | None = None) -> dict:
    """Simple, documented signal quality indices (SQIs):
    * kSQI: kurtosis of the signal (clean ECG is peaky, typically > 5)
    * pSQI: power in 5-15 Hz (QRS band) / power in 5-40 Hz
    * basSQI: 1 - power(0-1 Hz)/power(0-40 Hz) (baseline stability)
    * flatline / clipping fraction
    * RR regularity plausibility (physiological 30-220 bpm)
    Thresholds are heuristics from the SQI literature (Li & Clifford 2008; Behar 2013) and
    are used to gate analysis, not to make clinical statements."""
    x = np.asarray(x, dtype=float)
    out: dict = {}
    if len(x) < 2 * fs:
        return {"usable": False, "reason": "Signal shorter than 2 seconds", "score": 0.0}
    f, pxx = sps.welch(x, fs=fs, nperseg=min(len(x), int(4 * fs)))

    def band(lo, hi):
        m = (f >= lo) & (f <= hi)
        return float(np.trapezoid(pxx[m], f[m])) if m.any() else 0.0

    total = band(0, min(40, fs / 2)) or 1e-12
    out["kSQI"] = float(kurtosis(x, fisher=False))
    out["pSQI"] = band(5, 15) / (band(5, min(40, fs / 2)) or 1e-12)
    out["basSQI"] = 1 - band(0, 1) / total
    diffs = np.abs(np.diff(x))
    out["flatline_fraction"] = float((diffs < 1e-6 * (np.ptp(x) + 1e-12)).mean())
    rng = np.ptp(x)
    out["clipping_fraction"] = float(((x >= x.max() - 0.001 * rng) | (x <= x.min() + 0.001 * rng)).mean())
    if r_peaks is None:
        r_peaks = detect_r_peaks(x, fs)
    hr = heart_rate_bpm(r_peaks, fs)
    out["n_beats"] = int(len(r_peaks))
    out["heart_rate_bpm"] = hr
    checks = {
        "kurtosis_ok": out["kSQI"] > 5,
        "qrs_power_ok": 0.4 <= out["pSQI"] <= 0.9,
        "baseline_ok": out["basSQI"] > 0.8,
        "not_flat": out["flatline_fraction"] < 0.2,
        "not_clipped": out["clipping_fraction"] < 0.05,
        "hr_plausible": hr is not None and 30 <= hr <= 220,
    }
    out["checks"] = checks
    out["score"] = float(np.mean(list(checks.values())))
    out["usable"] = bool(out["score"] >= 0.67 and checks["hr_plausible"] and checks["not_flat"])
    out["label"] = "good" if out["score"] >= 0.84 else ("acceptable" if out["usable"] else "poor")
    return out


def extract_beats(x125: np.ndarray, r125: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cut fixed windows around each R peak of a 125 Hz signal, z-normalise each window and
    compute RR features. Returns (beats [n, BEAT_LEN], rr_feats [n, 4], kept_index)."""
    pre, post = int(PRE_S * TARGET_FS), int(POST_S * TARGET_FS)
    beats, rr_feats, kept = [], [], []
    rr = np.diff(r125) / TARGET_FS
    # recording-level mean RR (unsupervised, computed from the same recording at inference too);
    # normalising by it reduces inter-patient heart-rate differences.
    plausible = rr[(rr > 0.25) & (rr < 2.5)]
    global_rr = float(plausible.mean()) if len(plausible) else 1.0
    for i, r in enumerate(r125):
        if i == 0 or i == len(r125) - 1:
            continue  # need both neighbours for pre/post RR
        lo, hi = r - pre, r + post
        if lo < 0 or hi > len(x125):
            continue
        w = x125[lo:hi].astype(float)
        sd = w.std()
        if sd < 1e-8:
            continue
        w = (w - w.mean()) / sd
        pre_rr, post_rr = rr[i - 1], rr[i]
        local = rr[max(0, i - 10): i].mean() if i > 0 else pre_rr
        beats.append(w)
        rr_feats.append([pre_rr, post_rr, local, pre_rr / local if local > 0 else 1.0,
                         pre_rr / global_rr, post_rr / global_rr, post_rr / pre_rr if pre_rr > 0 else 1.0])
        kept.append(i)
    if not beats:
        return np.zeros((0, BEAT_LEN)), np.zeros((0, N_RR)), np.array([], dtype=int)
    return np.stack(beats), np.asarray(rr_feats, dtype=float), np.asarray(kept)


def morphology_features(beats: np.ndarray) -> np.ndarray:
    """Hand-crafted per-beat features for tree models: statistics + down-sampled waveform."""
    feats = []
    for w in beats:
        r_idx = int(PRE_S * TARGET_FS)
        qrs = w[r_idx - 12: r_idx + 12]
        feats.append(np.concatenate([
            [w.max(), w.min(), w[r_idx], skew(w), kurtosis(w), np.abs(np.diff(w)).sum(),
             qrs.max() - qrs.min(), np.argmax(np.abs(qrs)) - 12,
             (np.abs(qrs) > 0.5 * np.abs(qrs).max()).sum()],
            w[::4],  # 25 down-sampled amplitude points
        ]))
    return np.asarray(feats)


FEATURE_NAMES = (
    RR_FEATURES
    + ["max", "min", "amp_at_R", "skew", "kurtosis", "total_variation", "QRS_p2p",
       "QRS_peak_offset", "QRS_width_proxy"]
    + [f"amp_t{int(i * 4 * 1000 / TARGET_FS) - int(PRE_S * 1000)}ms" for i in range((BEAT_LEN + 3) // 4)]
)


def tabular_features(beats: np.ndarray, rr_feats: np.ndarray) -> np.ndarray:
    return np.hstack([rr_feats, morphology_features(beats)])
