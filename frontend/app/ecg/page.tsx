"use client";

import { useEffect, useState } from "react";
import { FileImage, FileSpreadsheet, Play } from "lucide-react";
import { apiBlob, apiGet, apiUpload, fmt } from "@/lib/api";
import type { EcgResult, ReportFull } from "@/lib/types";
import { ErrorBox, Notice, PageHeader, Spinner, StatCard } from "@/components/ui";
import { ShapBars, SimpleBars, Waveform } from "@/components/charts";

type Tab = "signal" | "image";

export default function EcgPage() {
  const [tab, setTab] = useState<Tab>("signal");
  const [file, setFile] = useState<File | null>(null);
  const [fs, setFs] = useState("");
  const [mains, setMains] = useState("50");
  const [model, setModel] = useState("");
  const [row, setRow] = useState("");
  const [speed, setSpeed] = useState("25");
  const [gain, setGain] = useState("10");
  const [res, setRes] = useState<EcgResult | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("report");
    if (id) apiGet<ReportFull>(`/api/reports/${id}`).then((r) => r.analysis?.ecg && setRes(r.analysis.ecg as EcgResult)).catch(setError);
  }, []);

  async function run(f: File | null = file) {
    if (!f) return;
    setLoading(true); setError(null); setRes(null);
    const form = new FormData();
    form.append("file", f);
    if (model) form.append("model", model);
    try {
      if (tab === "signal") {
        if (fs) form.append("fs", fs);
        form.append("mains_hz", mains);
        setRes(await apiUpload<EcgResult>("/api/ecg/signal", form));
      } else {
        if (row) form.append("row", String(Number(row) - 1));
        form.append("paper_speed_mm_s", speed);
        form.append("gain_mm_mv", gain);
        setRes(await apiUpload<EcgResult>("/api/ecg/image", form));
      }
    } catch (e) { setError(e); } finally { setLoading(false); }
  }

  async function sample() {
    const isSig = tab === "signal";
    const blob = await apiBlob(isSig ? "/api/ecg/sample-signal" : "/api/ecg/sample-image");
    const f = new File([blob], isSig ? "mitdb_233_excerpt_60s.csv" : "ecg_strip_rendered_from_mitdb_233.png", { type: blob.type });
    setFile(f);
    if (isSig) setMains("60"); // MIT-BIH was recorded in the USA
    if (!isSig) setPreview(URL.createObjectURL(f));
    run(f);
  }

  const c = res?.classification;
  const sq = res?.signal_quality;
  return (
    <div>
      <PageHeader title="ECG analysis" subtitle="Heart electrical activity. Signal processing (filtering, R-peak detection, signal quality) and beat-level classification into AAMI classes N/S/V/F by a model trained on the MIT-BIH Arrhythmia Database with an inter-patient split. This is not a complete ECG interpretation." />
      <div className="mb-4 flex gap-2">
        <button className={tab === "signal" ? "btn-primary" : "btn-ghost"} onClick={() => { setTab("signal"); setRes(null); setFile(null); }}><FileSpreadsheet size={16} strokeWidth={1.5} />Digitised signal (CSV)</button>
        <button className={tab === "image" ? "btn-primary" : "btn-ghost"} onClick={() => { setTab("image"); setRes(null); setFile(null); }}><FileImage size={16} strokeWidth={1.5} />ECG image / scan</button>
      </div>
      <ErrorBox error={error} />
      <div className="card mb-6">
        <div className="grid gap-3 md:grid-cols-6">
          <div className="md:col-span-2">
            <label className="label" htmlFor="ecgfile">{tab === "signal" ? "CSV: one column, or time + lead columns" : "JPG/PNG/PDF of an ECG"}</label>
            <input id="ecgfile" type="file" className="input" accept={tab === "signal" ? ".csv,.txt" : ".png,.jpg,.jpeg,.pdf"}
              onChange={(e) => { const f = e.target.files?.[0] || null; setFile(f); if (f && tab === "image") setPreview(URL.createObjectURL(f)); }} />
          </div>
          {tab === "signal" ? (
            <>
              <div><label className="label" htmlFor="fs">Sampling rate (Hz)</label><input id="fs" className="input" placeholder="auto from time col." value={fs} onChange={(e) => setFs(e.target.value)} /></div>
              <div><label className="label" htmlFor="mains">Mains (Hz)</label><select id="mains" className="input" value={mains} onChange={(e) => setMains(e.target.value)}><option>50</option><option>60</option></select></div>
            </>
          ) : (
            <>
              <div><label className="label" htmlFor="speed">Paper speed</label><select id="speed" className="input" value={speed} onChange={(e) => setSpeed(e.target.value)}><option value="25">25 mm/s</option><option value="50">50 mm/s</option><option value="12.5">12.5 mm/s</option></select></div>
              <div><label className="label" htmlFor="gain">Gain</label><select id="gain" className="input" value={gain} onChange={(e) => setGain(e.target.value)}><option value="10">10 mm/mV</option><option value="5">5 mm/mV</option><option value="20">20 mm/mV</option></select></div>
            </>
          )}
          <div><label className="label" htmlFor="model">Model</label>
            <select id="model" className="input" value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">Served (default)</option><option value="xgboost">XGBoost</option><option value="random_forest">Random Forest</option><option value="cnn_1d">1-D CNN</option>
            </select></div>
          {tab === "image" && <div><label className="label" htmlFor="row">Lead row (optional)</label><input id="row" className="input" placeholder="auto" value={row} onChange={(e) => setRow(e.target.value)} /></div>}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-accent" disabled={!file || loading} onClick={() => run()}><Play size={16} strokeWidth={1.5} />Analyse</button>
          <button className="btn-ghost" disabled={loading} onClick={sample}>
            {tab === "signal" ? "Try sample: MIT-BIH record 233 (60 s, test-set patient)" : "Try sample: strip rendered from MIT-BIH 233"}
          </button>
        </div>
      </div>
      {loading && <Spinner label="Processing signal…" />}
      {res && (
        <div className="space-y-6">
          {res.warnings?.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
          {tab === "image" && preview && (
            <div className="card"><div className="card-title">Report preview</div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={preview} alt="ECG preview" className="max-h-72 w-full rounded border object-contain" /></div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Heart rate" value={res.heart_rate_bpm ? `${res.heart_rate_bpm.toFixed(0)} bpm` : "–"} hint={res.heart_rate_bpm ? "From the median RR interval" : "Not computed: quality or calibration too low"} />
            <StatCard label="Signal quality" value={sq ? sq.label.charAt(0).toUpperCase() + sq.label.slice(1) : "–"} hint={sq ? `score ${fmt(sq.score)} · ${sq.n_beats} beats` : undefined} />
            <StatCard label="Beats classified" value={c?.n_beats ?? "–"} hint={c?.model ? `${c.model} · ${c.model_version}` : undefined} />
            <StatCard label="Duration" value={res.duration_s ? `${res.duration_s}s` : "–"} hint={res.fs ? `${res.fs.toFixed(0)} Hz` : undefined} />
          </div>
          <div className="card">
            <div className="card-title">{res.digitization ? "Extracted waveform (from image)" : "Filtered signal (first 10 s) with detected R-peaks"}</div>
            {res.waveform_preview ? <Waveform points={res.waveform_preview.points} peaks={res.waveform_preview.r_peaks_s} unit="mV" /> :
              res.digitization?.preview ? <Waveform points={res.digitization.preview} unit={res.digitization.unit} /> : <p className="text-sm text-slate-500">No waveform</p>}
            {res.digitization && (
              <p className="text-xs text-slate-500">Rows detected {res.digitization.rows_detected}, row used {res.digitization.row_used + 1}, trace coverage {Math.round(res.digitization.trace_coverage * 100)}%, grid {res.digitization.grid.detected ? `${fmt(res.digitization.grid.small_box_px)} px/mm (conf. ${res.digitization.grid.confidence})` : "not detected"}.</p>
            )}
          </div>
          {sq && (
            <div className="card">
              <div className="card-title">Signal quality checks</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(sq.checks || {}).map(([k, v]) => <span key={k} className={`badge mr-4 ${v ? "text-slate-600" : "text-flag-high"}`}><span className={`h-1.5 w-1.5 rounded-full ${v ? "bg-flag-ok" : "bg-flag-high"}`} />{(k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, " ").replace(" ok", "").replace("Hr", "Heart rate").replace("Qrs", "QRS")}</span>)}
              </div>
              <p className="mt-2 text-xs text-slate-500">kSQI {fmt(sq.kSQI)} · pSQI {fmt(sq.pSQI)} · basSQI {fmt(sq.basSQI)}. Heuristic SQIs (Li &amp; Clifford 2008; Behar et al. 2013) gate the analysis</p>
            </div>
          )}
          {c && !c.available && <Notice tone="warn">Classification not performed: {c.reason}</Notice>}
          {c?.available && c.counts && (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <SimpleBars title="Predicted beats per class" data={Object.entries(c.counts).map(([k, v]) => ({ name: k, value: v }))} />
                <div className="card">
                  <div className="card-title">Class meaning and test performance</div>
                  <table className="min-w-full text-sm">
                    <thead><tr><th className="th">Class</th><th className="th">Meaning</th><th className="th">Test recall</th><th className="th">Test precision</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {Object.keys(c.counts).map((k) => (
                        <tr key={k}><td className="td font-medium">{k}</td><td className="td text-xs">{c.class_descriptions?.[k]}</td>
                          <td className="td">{fmt(c.test_recall_by_class?.[k])}</td><td className="td">{fmt(c.test_precision_by_class?.[k])}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-2 text-xs text-slate-500">Recall/precision on unseen patients (MIT-BIH DS2). Low S and F values mean predictions of those classes are unreliable</p>
                </div>
              </div>
              {c.explanation?.length ? (
                <div className="card">
                  <div className="card-title">Why: SHAP for non-normal beats (XGBoost)</div>
                  <div className="grid gap-6 md:grid-cols-2">
                    {c.explanation.slice(0, 4).map((e) => (
                      <ShapBars key={e.beat} title={`Beat #${e.beat} → ${e.predicted}`} items={e.top_features.map((t) => ({ feature: `${t.feature} = ${t.value}`, shap: t.shap }))} />
                    ))}
                  </div>
                  <p className="text-xs text-slate-500">Contributions toward the predicted class. RR features are in seconds (or ratios); amplitude features are z-scored</p>
                </div>
              ) : null}
              <div className="card">
                <div className="card-title">Per-beat predictions (first 60)</div>
                <div className="max-h-80 overflow-auto">
                  <table className="min-w-full text-sm">
                    <thead className="sticky top-0 bg-white"><tr><th className="th">#</th><th className="th">Time</th><th className="th">Predicted</th><th className="th">Probability</th><th className="th">N / S / V / F</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {c.beats?.slice(0, 60).map((b) => (
                        <tr key={b.index} className="">
                          <td className="td figure text-slate-500">{b.index}</td><td className="td figure">{b.time_s.toFixed(2)}s</td><td className={`td font-medium ${b.predicted !== "N" ? "text-navy-900" : "text-slate-600"}`}>{b.predicted}</td>
                          <td className="td">{b.probability.toFixed(2)}</td>
                          <td className="td font-mono text-xs">{Object.values(b.probabilities).map((p) => p.toFixed(2)).join(" / ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <p className="text-xs text-slate-500">{c.caveat}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
