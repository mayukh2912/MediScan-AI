"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCheck, Eye, Plus, Trash2 } from "lucide-react";
import { apiGet, apiSend, fmt } from "@/lib/api";
import type { EcgResult, Measurement, ReportFull } from "@/lib/types";
import type { CatalogItem } from "@/components/ModulePage";
import { ErrorBox, Notice, PageHeader, Spinner, StatusBadge, typeLabel } from "@/components/ui";
import { Waveform } from "@/components/charts";

type Row = Measurement & { _value: string; _low: string; _high: string };
const MODULE_LINKS: Record<string, [string, string]> = {
  blood: ["/blood", "Blood analysis"], liver: ["/liver", "Liver analysis"], lipid: ["/lipid", "Lipid profile"],
  echo: ["/echo", "ECHO analysis"], ecg: ["/ecg", "ECG analysis"],
};

export default function ReviewPage() {
  const [id, setId] = useState<string>("");
  useEffect(() => { setId(new URLSearchParams(window.location.search).get("id") || ""); }, []);
  return id ? <Review id={id} /> : <Spinner />;
}

function Review({ id }: { id: string }) {
  const params = { id };
  const [rep, setRep] = useState<ReportFull | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [demo, setDemo] = useState<{ age: string; sex: string }>({ age: "", sex: "" });
  const [rtype, setRtype] = useState("");
  const [rdate, setRdate] = useState("");
  const [ocr, setOcr] = useState<string[] | null>(null);
  const [addKey, setAddKey] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);

  function load() {
    apiGet<ReportFull>(`/api/reports/${params.id}`).then((r) => {
      setRep(r);
      const ms = r.extraction?.measurements || [];
      setRows(ms.map((m) => ({ ...m, _value: m.value == null ? "" : String(m.value), _low: m.reference_range?.low?.toString() ?? "", _high: m.reference_range?.high?.toString() ?? "" })));
      const d = r.extraction?.demographics_suggested;
      setDemo({ age: d?.age?.toString() || "", sex: d?.sex || "" });
      setRtype(r.report_type);
      setRdate(r.report_date || "");
    }).catch(setError);
  }
  useEffect(() => {
    load();
    apiGet<CatalogItem[]>("/api/catalog").then(setCatalog).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function confirm() {
    setSaving(true);
    setError(null);
    try {
      const measurements = rows.filter((r) => r._value.trim() !== "").map((r) => ({
        key: r.key, value: Number(r._value),
        reference_range: r._low || r._high ? { low: r._low ? Number(r._low) : null, high: r._high ? Number(r._high) : null, text: r.reference_range?.text } : null,
        original_value: r.original_value, original_unit: r.original_unit, extraction_confidence: r.extraction_confidence,
        source_line: r.source_line, lab_flag: r.lab_flag, lab_calculated: r.lab_calculated,
      }));
      await apiSend(`/api/reports/${params.id}/confirm`, "PUT", {
        measurements, demographics: { age: demo.age ? Number(demo.age) : null, sex: demo.sex || null },
        report_type: rtype, report_date: rdate || null,
      });
      load();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  if (!rep) return error ? <ErrorBox error={error} /> : <Spinner />;
  const ex = rep.extraction;
  const analysed = rep.status === "analysed";
  const ecg = (rep.analysis?.ecg || ex?.ecg) as EcgResult | undefined;
  const present = new Set(rows.map((r) => r.key));

  return (
    <div>
      <PageHeader title={analysed ? "Confirmed report" : "Review extracted values"}
        subtitle={analysed ? "Values were confirmed and analysed. Open a module page for the detailed analysis." : "Check every value against the original document. Correct anything misread, remove wrong rows, add anything missed. Analysis runs only after you confirm."}>
        <button className="btn-ghost" onClick={async () => setOcr(ocr ? null : (await apiGet<{ lines: { text: string }[] }>(`/api/reports/${params.id}/ocr-text`)).lines.map((l) => l.text))}>
          <Eye size={16} strokeWidth={1.5} />{ocr ? "Hide" : "Show"} original OCR text
        </button>
      </PageHeader>
      <ErrorBox error={error} />

      {analysed && rep.analysis && (
        <div className="card mb-6">
          <div className="card-title">Analyses available</div>
          <div className="flex flex-wrap gap-2">
            {Object.keys(rep.analysis).filter((k) => !k.startsWith("_")).map((k, i) => (
              <Link key={k} href={`${MODULE_LINKS[k]?.[0]}?report=${rep.id}`} className={i === 0 ? "btn-primary" : "btn-ghost"}>{MODULE_LINKS[k]?.[1] || k}</Link>
            ))}
            <Link href="/summary" className="btn-ghost">Combined summary</Link>
          </div>
        </div>
      )}

      {ocr && (
        <div className="card mb-6">
          <div className="card-title">Original OCR text (as read, unmodified)</div>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{ocr.join("\n")}</pre>
        </div>
      )}

      {ex && (
        <div className="mb-6 grid gap-4 md:grid-cols-4">
          <div className="card">
            <label className="label" htmlFor="rtype">Report type</label>
            <select id="rtype" className="input" value={rtype} onChange={(e) => setRtype(e.target.value)} disabled={analysed}>
              {["CBC", "BLOOD", "LFT", "LIPID", "ECHO", "ECG", "UNKNOWN"].map((t) => <option key={t} value={t}>{typeLabel[t]}</option>)}
            </select>
            <p className="mt-2 text-xs text-slate-500">Detected: {ex.classification.report_type} (score-based; confidence {fmt(ex.classification.confidence)})</p>
          </div>
          <div className="card">
            <label className="label" htmlFor="rdate">Report date</label>
            <input id="rdate" type="date" className="input" value={rdate} onChange={(e) => setRdate(e.target.value)} disabled={analysed} />
            {ex.report_date?.ambiguous_day_month && <p className="mt-2 text-xs text-flag-warn">Read “{ex.report_date.original}” as day/month, please check</p>}
          </div>
          <div className="card">
            <label className="label" htmlFor="sex">Sex</label>
            <select id="sex" className="input" value={demo.sex} onChange={(e) => setDemo({ ...demo, sex: e.target.value })} disabled={analysed}>
              <option value="">Not specified</option><option value="female">Female</option><option value="male">Male</option>
            </select>
            <p className="mt-2 text-xs text-slate-500">Used only for sex-specific ranges</p>
          </div>
          <div className="card">
            <label className="label" htmlFor="age">Age</label>
            <input id="age" type="number" className="input" value={demo.age} onChange={(e) => setDemo({ ...demo, age: e.target.value })} disabled={analysed} />
            <p className="mt-2 text-xs text-slate-500">Needed for the liver research model</p>
          </div>
        </div>
      )}

      {ex?.ocr.quality_warnings.map((w) => <div key={w} className="mb-3"><Notice tone="warn">{w}</Notice></div>)}

      {ecg && (
        <div className="card mb-6">
          <div className="card-title">ECG waveform extraction</div>
          {ecg.digitization?.preview?.length ? (
            <>
              <Waveform points={ecg.digitization.preview} unit={ecg.digitization.unit} />
              <p className="text-xs text-slate-500">Rows detected: {ecg.digitization.rows_detected} · row used: {ecg.digitization.row_used + 1} · trace coverage {Math.round(ecg.digitization.trace_coverage * 100)}% · grid {ecg.digitization.grid.detected ? `detected (${fmt(ecg.digitization.grid.small_box_px)} px/mm)` : "not detected"}</p>
            </>
          ) : <p className="text-sm text-slate-500">No waveform could be digitised</p>}
          {ecg.warnings?.map((w) => <div key={w} className="mt-2"><Notice tone="warn">{w}</Notice></div>)}
          <p className="mt-2 text-xs text-slate-500">Inspect the trace above: if it does not match the printed ECG, do not rely on the ECG analysis. Use the ECG page to re-run with another row or calibration.</p>
        </div>
      )}

      {ex && (
        <div className="card">
          <div className="card-title">Measurements ({rows.length})</div>
          {rows.length === 0 && <Notice>No measurements were recognised. Add them manually below or upload a clearer scan.</Notice>}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50"><tr>
                <th className="th">Test</th><th className="th">Value (canonical unit)</th><th className="th">Lab range</th><th className="th">As read</th><th className="th">Status</th><th className="th" />
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r, i) => (
                  <tr key={r.key} className={r.status === "invalid" ? "bg-red-50/40" : r.status === "uncertain" ? "bg-amber-50/30" : ""}>
                    <td className="td font-medium text-navy-900">{r.test}<div className="text-xs font-normal text-slate-400">{r.panel}</div></td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <input aria-label={`${r.test} value`} className="input w-28" value={r._value} disabled={analysed}
                          onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, _value: e.target.value } : x)))} />
                        <span className="text-xs text-slate-500">{r.unit_display ?? r.unit}</span>
                      </div>
                    </td>
                    <td className="td">
                      <div className="flex gap-1">
                        <input aria-label="low" placeholder="low" className="input w-20 px-2" value={r._low} disabled={analysed} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, _low: e.target.value } : x)))} />
                        <input aria-label="high" placeholder="high" className="input w-20 px-2" value={r._high} disabled={analysed} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, _high: e.target.value } : x)))} />
                      </div>
                    </td>
                    <td className="td max-w-xs text-xs text-slate-500">
                      {r.original_value != null && <div><span className="font-mono">{r.original_value} {r.original_unit || ""}</span>{r.lab_flag && <span className="ml-1 badge bg-slate-100">{r.lab_flag}</span>}</div>}
                      {r.source_line && <div className="truncate" title={r.source_line}>“{r.source_line}”</div>}
                      {r.extraction_confidence != null && <div>confidence {fmt(r.extraction_confidence)}</div>}
                    </td>
                    <td className="td"><StatusBadge status={r.status} />
                      {r.issues?.map((s) => <div key={s} className="mt-1 max-w-[220px] text-xs text-slate-500">{s}</div>)}
                    </td>
                    <td className="td">{!analysed && <button aria-label={`Remove ${r.test}`} className="text-slate-400 transition-colors hover:text-flag-high" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={16} strokeWidth={1.5} /></button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!analysed && (
            <div className="mt-4 flex flex-wrap items-end gap-2">
              <div>
                <label className="label" htmlFor="add">Add a missed measurement</label>
                <select id="add" className="input w-64" value={addKey} onChange={(e) => setAddKey(e.target.value)}>
                  <option value="">Choose test…</option>
                  {catalog.filter((c) => !present.has(c.key)).map((c) => <option key={c.key} value={c.key}>{c.panel} · {c.name} ({c.unit || "ratio"})</option>)}
                </select>
              </div>
              <button className="btn-ghost" disabled={!addKey} onClick={() => {
                const c = catalog.find((x) => x.key === addKey)!;
                setRows([...rows, { key: c.key, test: c.name, panel: c.panel, value: null, unit: c.unit, status: "ok", issues: ["Added manually"], origin: "manual", _value: "", _low: "", _high: "" }]);
                setAddKey("");
              }}><Plus size={16} strokeWidth={1.5} />Add</button>
              <div className="flex-1" />
              <button className="btn-accent" onClick={confirm} disabled={saving}><CheckCheck size={16} strokeWidth={1.5} />{saving ? "Analysing" : "Confirm values and analyse"}</button>
            </div>
          )}
          {!analysed && <p className="mt-2 text-xs text-slate-500">Values are in the canonical unit shown (already converted from the report&apos;s unit where needed). Rows marked implausible must be corrected or removed before analysis.</p>}
        </div>
      )}

      <div className="card mt-6">
        <div className="card-title">Audit trail</div>
        <ul className="space-y-1 text-sm">
          {rep.audit.map((a, i) => (
            <li key={i} className="flex gap-3"><span className="w-44 shrink-0 text-xs text-slate-400">{new Date(a.at).toLocaleString()}</span>
              <span className="font-medium">{a.action}</span>
              <span className="truncate text-xs text-slate-500">{a.detail ? JSON.stringify(a.detail) : ""}</span></li>
          ))}
        </ul>
      </div>
    </div>
  );
}
