"""Create the demo files shipped in backend/sample_data from the raw MIT-BIH database.

* mitdb_233_excerpt_60s.csv  – 60 s of lead MLII from record 233 (a DS2 / test record), 360 Hz, mV.
* ecg_strip_rendered_from_mitdb_233.png – the first 10 s of that excerpt drawn on standard ECG
  paper (25 mm/s, 10 mm/mV) with matplotlib. It is a rendering of a real recording, used to
  demonstrate and test the image digitiser; it is not a photograph of a real paper ECG.
MIT-BIH Arrhythmia Database: Moody & Mark 2001, PhysioNet, ODC-By 1.0.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import wfdb

root = Path(__file__).resolve().parents[1]
mitdb = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "datasets" / "mitdb"
out = root / "backend" / "sample_data"
out.mkdir(parents=True, exist_ok=True)
rec = wfdb.rdrecord(str(mitdb / "233"), sampfrom=0, sampto=360 * 60)
x = rec.p_signal[:, rec.sig_name.index("MLII")]
t = np.arange(len(x)) / rec.fs
np.savetxt(out / "mitdb_233_excerpt_60s.csv", np.c_[t, x], delimiter=",", header="time,MLII", comments="", fmt="%.5f")

def render(sig, fs, path, seconds=10.0, dpi=200):
    n = int(seconds * fs)
    sig = sig[:n]
    w_mm, h_mm = seconds * 25 + 10, 40
    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w_mm); ax.set_ylim(-h_mm / 2, h_mm / 2)
    for xm in np.arange(0, w_mm + 1, 1):
        ax.axvline(xm, color="#f4b6b6" if xm % 5 else "#e06666", lw=0.3 if xm % 5 else 0.7)
    for ym in np.arange(-h_mm / 2, h_mm / 2 + 1, 1):
        ax.axhline(ym, color="#f4b6b6" if ym % 5 else "#e06666", lw=0.3 if ym % 5 else 0.7)
    tt = 5 + np.arange(len(sig)) / fs * 25
    ax.plot(tt, (sig - np.median(sig)) * 10, color="black", lw=0.9)
    ax.axis("off")
    fig.savefig(path, dpi=dpi)
    plt.close(fig)

render(x, rec.fs, out / "ecg_strip_rendered_from_mitdb_233.png")
print("written to", out)
