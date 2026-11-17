"""Heartbeat dataset construction.

Two supported sources:

1. ``kaggle``: shayanfazeli/heartbeat ``mitbih_train.csv`` / ``mitbih_test.csv``
   Schema (verified against the dataset card): 187 columns of a single beat sampled at 125 Hz,
   normalised to [0, 1] and zero-padded, plus a final integer label column
   (0=N, 1=S, 2=V, 3=F, 4=Q). The CSVs contain NO record/patient identifier and
   no RR context, so a patient-aware split is impossible: beats from the same patient appear
   in both train and test. Metrics on that split are therefore optimistic ("intra-patient").

2. ``mitdb`` (default, used for the shipped model): the raw PhysioNet MIT-BIH Arrhythmia
   Database (the same source the Kaggle CSVs were derived from). This keeps record IDs so we
   can use the standard de Chazal et al. (2004) inter-patient split DS1 (train) / DS2 (test)
   and exclude the four paced records, as recommended by AAMI EC57.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml.ecg.signal_processing import TARGET_FS, clean_ecg, extract_beats, resample

AAMI_MAP = {
    "N": "N", "L": "N", "R": "N", "e": "N", "j": "N",
    "A": "S", "a": "S", "J": "S", "S": "S",
    "V": "V", "E": "V",
    "F": "F",
    "/": "Q", "f": "Q", "Q": "Q",
}
# Q (unclassifiable / paced) is excluded: after removing paced records only ~15 Q beats remain,
# far too few to train or evaluate. The served model supports N, S, V, F only.
CLASSES = ["N", "S", "V", "F"]
CLASS_DESCRIPTIONS = {
    "N": "Normal / bundle-branch-block / escape beat (AAMI class N)",
    "S": "Supraventricular ectopic beat (AAMI class S)",
    "V": "Ventricular ectopic beat (AAMI class V)",
    "F": "Fusion of ventricular and normal beat (AAMI class F)",
}
PACED = {"102", "104", "107", "217"}
DS1 = ["101", "106", "108", "109", "112", "114", "115", "116", "118", "119", "122", "124",
       "201", "203", "205", "207", "208", "209", "215", "220", "223", "230"]
DS2 = ["100", "103", "105", "111", "113", "117", "121", "123", "200", "202", "210", "212",
       "213", "214", "219", "221", "222", "228", "231", "232", "233", "234"]


def load_record_beats(mitdb_dir: str | Path, record: str) -> dict:
    import wfdb  # imported lazily: only needed for training

    path = str(Path(mitdb_dir) / record)
    rec = wfdb.rdrecord(path)
    ann = wfdb.rdann(path, "atr")
    names = [n.upper() for n in rec.sig_name]
    ch = names.index("MLII") if "MLII" in names else 0
    fs = rec.fs
    x = clean_ecg(rec.p_signal[:, ch], fs, mains=60.0)  # MIT-BIH was recorded in the USA (60 Hz)
    x125 = resample(x, fs, TARGET_FS)
    # keep only beat annotations that map to AAMI classes
    sym = np.array(ann.symbol)
    samp = np.array(ann.sample)
    is_beat = np.isin(sym, list(AAMI_MAP))
    sym, samp = sym[is_beat], samp[is_beat]
    r125 = np.round(samp * TARGET_FS / fs).astype(int)
    beats, rr, kept = extract_beats(x125, r125)
    labels = np.array([AAMI_MAP[s] for s in sym[kept]])
    return {"beats": beats, "rr": rr, "labels": labels, "record": record}


def build_mitdb(mitdb_dir: str | Path, records: list[str]) -> dict:
    B, R, L, G = [], [], [], []
    for rec in records:
        if rec in PACED:
            continue
        d = load_record_beats(mitdb_dir, rec)
        keep = np.isin(d["labels"], CLASSES)
        B.append(d["beats"][keep]); R.append(d["rr"][keep]); L.append(d["labels"][keep])
        G.append(np.full(keep.sum(), rec))
    labels = np.concatenate(L)
    return {
        "beats": np.concatenate(B).astype(np.float32),
        "rr": np.concatenate(R).astype(np.float32),
        "y": np.array([CLASSES.index(c) for c in labels]),
        "groups": np.concatenate(G),
    }


def load_kaggle_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load and validate the Kaggle heartbeat CSV schema."""
    df = pd.read_csv(path, header=None)
    if df.shape[1] != 188:
        raise ValueError(f"Expected 188 columns (187 samples + label), got {df.shape[1]}")
    X = df.iloc[:, :187].to_numpy(np.float32)
    y = df.iloc[:, 187].astype(int).to_numpy()
    if X.min() < -1e-6 or X.max() > 1 + 1e-6:
        raise ValueError("Kaggle heartbeat samples are expected to be normalised to [0, 1]")
    if not set(np.unique(y)) <= {0, 1, 2, 3, 4}:
        raise ValueError("Unexpected label values")
    return X, y
