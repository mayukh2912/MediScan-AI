"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ClipboardList, FileSearch, Play } from "lucide-react";
import { apiGet, apiSend } from "@/lib/api";
import type { ModuleResult, ReportFull, ReportMeta } from "@/lib/types";
import { DerivedList, ErrorBox, MeasurementTable, MissingList, Notice, PageHeader, PatternList, Spinner } from "./ui";

export type CatalogItem = { key: string; name: string; panel: string; unit: string; accepted_units: string[] };

type Props = {
  module: "blood" | "liver" | "lipid" | "echo";
  title: string;
  subtitle: string;
  panels: string[];
  needsAge?: boolean;
  renderExtra?: (r: ModuleResult) => React.ReactNode;
};

export default function ModulePage({ module, title, subtitle, panels, needsAge, renderExtra }: Props) {
  const [mode, setMode] = useState<"report" | "manual">("report");
  const [reports, setReports] = useState<ReportMeta[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [result, setResult] = useState<ModuleResult | null>(null);
  const [reportDate, setReportDate] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [values, setValues] = useState<Record<string, { value: string; unit: string; low: string; high: string }>>({});
  const [demo, setDemo] = useState<{ age: string; sex: string }>({ age: "", sex: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    apiGet<ReportMeta[]>("/api/reports?status=analysed")
      .then((rs) => {
        const mine = rs.filter((r) => r.panels.some((p) => panels.includes(p)) || panels.includes(r.report_type));
        setReports(mine);
        const q = new URLSearchParams(window.location.search).get("report");
        if (q && mine.some((r) => r.id === q)) setSelected(q);
        else if (mine.length) setSelected(mine[0].id);
        else setMode("manual");
      })
      .catch((e) => { setError(e); setReports([]); setMode("manual"); });
    apiGet<CatalogItem[]>("/api/catalog").then((c) => setCatalog(c.filter((x) => panels.includes(x.panel)))).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (mode !== "report" || !selected) return;
    setLoading(true);
    setError(null);
    apiGet<ReportFull>(`/api/reports/${selected}`)
      .then((r) => {
        setResult((r.analysis?.[module] as ModuleResult) || null);
        setReportDate(r.report_date);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [selected, mode, module]);

  const fields = useMemo(() => catalog, [catalog]);

  async function runManual(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const measurements = Object.entries(values)
        .filter(([, v]) => v.value.trim() !== "")
        .map(([key, v]) => ({
          key,
          value: Number(v.value),
          input_unit: v.unit || undefined,
          reference_range: v.low || v.high ? { low: v.low ? Number(v.low) : null, high: v.high ? Number(v.high) : null } : null,
        }));
      if (!measurements.length) throw new Error("Enter at least one value");
      const r = await apiSend<ModuleResult>(`/api/${module}/analyze`, "POST", {
        measurements,
        demographics: { age: demo.age ? Number(demo.age) : null, sex: demo.sex || null },
      });
      setResult(r);
      setReportDate(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader title={title} subtitle={subtitle}>
        <div className="flex rounded-lg bg-slate-200/70 p-0.5 text-sm">
          <button className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 transition-colors duration-150 ${mode === "report" ? "bg-white font-medium text-slate-900 shadow-[0_1px_2px_rgba(15,23,42,0.08)]" : "text-slate-600 hover:text-slate-900"}`} onClick={() => setMode("report")}>
            <FileSearch size={14} strokeWidth={1.5} />From report
          </button>
          <button className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 transition-colors duration-150 ${mode === "manual" ? "bg-white font-medium text-slate-900 shadow-[0_1px_2px_rgba(15,23,42,0.08)]" : "text-slate-600 hover:text-slate-900"}`} onClick={() => { setMode("manual"); setResult(null); }}>
            <ClipboardList size={14} strokeWidth={1.5} />Manual entry
          </button>
        </div>
      </PageHeader>
      <ErrorBox error={error} />

      {mode === "report" && (
        <div className="card mb-6">
          {reports === null ? <Spinner /> : reports.length === 0 ? (
            <Notice>No confirmed reports of this type yet. <Link className="link" href="/upload">Upload a report</Link> or use manual entry</Notice>
          ) : (
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[280px] flex-1">
                <label className="label" htmlFor="rep">Confirmed report</label>
                <select id="rep" className="input" value={selected} onChange={(e) => setSelected(e.target.value)}>
                  {reports.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.report_type} · report date {r.report_date || "not found"} · uploaded {r.created_at.slice(0, 10)} · {r.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </div>
              {reportDate && <div className="text-sm text-slate-500">Report date: <strong>{reportDate}</strong></div>}
            </div>
          )}
        </div>
      )}

      {mode === "manual" && (
        <form className="card mb-6" onSubmit={runManual}>
          <div className="card-title">Enter values as printed on the report</div>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <div>
              <label className="label" htmlFor="sex">Sex (for sex-specific ranges)</label>
              <select id="sex" className="input" value={demo.sex} onChange={(e) => setDemo({ ...demo, sex: e.target.value })}>
                <option value="">Not specified</option><option value="female">Female</option><option value="male">Male</option>
              </select>
            </div>
            {needsAge && (
              <div>
                <label className="label" htmlFor="age">Age (research model input)</label>
                <input id="age" className="input" type="number" min={0} max={120} value={demo.age} onChange={(e) => setDemo({ ...demo, age: e.target.value })} />
              </div>
            )}
          </div>
          <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
            {fields.map((f) => {
              const v = values[f.key] || { value: "", unit: "", low: "", high: "" };
              const set = (patch: Partial<typeof v>) => setValues({ ...values, [f.key]: { ...v, ...patch } });
              return (
                <div key={f.key} className="grid grid-cols-12 items-end gap-2">
                  <div className="col-span-4">
                    <label className="label" htmlFor={`f-${f.key}`}>{f.name}</label>
                    <input id={`f-${f.key}`} className="input" inputMode="decimal" value={v.value} onChange={(e) => set({ value: e.target.value })} />
                  </div>
                  <div className="col-span-3">
                    <select aria-label={`${f.name} unit`} className="input" value={v.unit || f.unit} onChange={(e) => set({ unit: e.target.value })}>
                      {(f.accepted_units.length ? f.accepted_units : [f.unit]).map((u) => <option key={u} value={u}>{u || "ratio"}</option>)}
                    </select>
                  </div>
                  <input aria-label={`${f.name} lab low`} placeholder="lab low" className="input col-span-2 px-2" value={v.low} onChange={(e) => set({ low: e.target.value })} />
                  <input aria-label={`${f.name} lab high`} placeholder="lab high" className="input col-span-3 px-2" value={v.high} onChange={(e) => set({ high: e.target.value })} />
                </div>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-slate-500">Lab low/high are optional: when supplied, the laboratory&apos;s own range is used instead of the default adult range. Nothing entered here is stored</p>
          <button className="btn-accent mt-4" disabled={loading}>Analyse</button>
        </form>
      )}

      {loading && <Spinner label="Analysing…" />}
      {!loading && mode === "report" && selected && !result && reports?.length ? (
        <Notice>This report has no {module} values</Notice>
      ) : null}
      {result && <ModuleResultView result={result} renderExtra={renderExtra} />}
    </div>
  );
}

export function ModuleResultView({ result, renderExtra }: { result: ModuleResult; renderExtra?: (r: ModuleResult) => React.ReactNode }) {
  return (
    <div className="space-y-6">
      {(result.warnings?.length || result.notes?.length) ? (
        <div className="space-y-2">
          {result.notes?.map((n, i) => <Notice key={`n${i}`}>{n}</Notice>)}
          {result.warnings?.map((w, i) => <Notice key={`w${i}`} tone="warn">{w}</Notice>)}
        </div>
      ) : null}
      <div className="card">
        <div className="card-title">Measurements <span className="text-xs font-normal text-slate-500">{result.method}</span></div>
        <MeasurementTable rows={result.measurements} />
      </div>
      {renderExtra?.(result)}
      <DerivedList items={result.derived} />
      <PatternList items={result.patterns} />
      <MissingList items={result.missing} />
      {result.missing_haematinics_note && <Notice tone="warn">{result.missing_haematinics_note}</Notice>}
      {result.disclaimer && <p className="text-xs text-slate-500">{result.disclaimer}</p>}
    </div>
  );
}
