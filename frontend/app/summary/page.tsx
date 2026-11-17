"use client";

import { useEffect, useState } from "react";
import { Download, FileJson } from "lucide-react";
import { apiGet, download, fmt } from "@/lib/api";
import { ErrorBox, InterpBadge, Notice, PageHeader, Spinner } from "@/components/ui";

type Summary = {
  generated_at: string; n_reports: number;
  modules: Record<string, { report_id: string; report_date: string | null }[]>;
  abnormal_values: { module: string; test: string; value: number; unit: string; interpretation: string; range_used: { low: number | null; high: number | null; source: string } | null; report_date: string | null }[];
  uncertain_values: { module: string; test: string; issues: string[] }[];
  missing_measurements: { module: string; test: string }[];
  model_outputs: { module: string; model: string; version: string; output: string; meaning: string }[];
  model_limitations: string[];
  report_dates: { report_id: string; type: string; report_date: string | null; uploaded: string }[];
  overall_score_note: string; disclaimer: string;
};

export default function SummaryPage() {
  const [s, setS] = useState<Summary | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { apiGet<Summary>("/api/summary").then(setS).catch(setError); }, []);
  return (
    <div>
      <PageHeader title="Combined health summary" subtitle="Brings together every confirmed analysis. It lists what was measured and what fell outside the range used – it does not combine them into a score.">
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => download("/api/summary/json", "mediscan_summary.json")}><FileJson size={16} strokeWidth={1.5} />JSON</button>
          <button className="btn-primary" onClick={() => download("/api/summary/pdf", "mediscan_summary.pdf")}><Download size={16} strokeWidth={1.5} />Download PDF</button>
        </div>
      </PageHeader>
      <ErrorBox error={error} />
      {!s && !error && <Spinner />}
      {s && s.n_reports === 0 && <Notice>No confirmed reports yet</Notice>}
      {s && s.n_reports > 0 && (
        <div className="space-y-6">
          <div className="card">
            <div className="card-title">Reports included ({s.n_reports})</div>
            <table className="min-w-full text-sm"><thead><tr><th className="th">Type</th><th className="th">Report date</th><th className="th">Uploaded</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{s.report_dates.map((d) => <tr key={d.report_id}><td className="td">{d.type}</td><td className="td">{d.report_date || "not found on report"}</td><td className="td">{d.uploaded.slice(0, 10)}</td></tr>)}</tbody></table>
          </div>
          <div className="card">
            <div className="card-title">Values outside the range used ({s.abnormal_values.length})</div>
            {s.abnormal_values.length === 0 ? <p className="text-sm text-slate-500">None</p> : (
              <table className="min-w-full text-sm"><thead><tr><th className="th">Module</th><th className="th">Test</th><th className="th">Value</th><th className="th">Range used</th><th className="th">Flag</th><th className="th">Report date</th></tr></thead>
                <tbody className="divide-y divide-slate-100">{s.abnormal_values.map((a, i) => (
                  <tr key={i}><td className="td">{a.module}</td><td className="td font-medium">{a.test}</td><td className="td">{fmt(a.value)} {a.unit}</td>
                    <td className="td text-xs">{a.range_used ? `${a.range_used.low ?? "–"} – ${a.range_used.high ?? "–"} (${a.range_used.source})` : "–"}</td>
                    <td className="td"><InterpBadge interp={a.interpretation} /></td>
                    <td className="td">{a.report_date || "–"}</td></tr>))}</tbody></table>
            )}
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <div className="card-title">Model outputs (research only)</div>
              {s.model_outputs.length === 0 ? <p className="text-sm text-slate-500">None</p> : s.model_outputs.map((m, i) => (
                <div key={i} className="mb-3 rounded-lg bg-slate-50 p-3 text-sm"><div className="font-medium">{m.module}: {m.output}</div><div className="text-xs text-slate-500">{m.model} · {m.version}</div><div className="mt-1 text-xs text-slate-600">{m.meaning}</div></div>
              ))}
            </div>
            <div className="card">
              <div className="card-title">Uncertain values</div>
              {s.uncertain_values.length === 0 ? <p className="text-sm text-slate-500">None, every value was confirmed by the user</p> :
                s.uncertain_values.map((u, i) => <div key={i} className="text-sm">{u.module} · {u.test}: <span className="text-xs text-slate-500">{u.issues.join("; ")}</span></div>)}
              <div className="card-title mt-4">Missing measurements</div>
              <div className="flex flex-wrap gap-2">{s.missing_measurements.map((m, i) => <span key={i} className="badge bg-slate-100 text-slate-600">{m.module}: {m.test}</span>)}</div>
            </div>
          </div>
          {s.model_limitations.length > 0 && (
            <div className="card"><div className="card-title">Model limitations</div>
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">{s.model_limitations.map((l) => <li key={l}>{l}</li>)}</ul></div>
          )}
          <Notice>{s.overall_score_note}</Notice>
          <p className="text-xs text-slate-500">{s.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
