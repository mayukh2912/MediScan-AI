"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Upload } from "lucide-react";
import { apiGet, getApiUrl, setApiUrl } from "@/lib/api";
import type { ReportMeta } from "@/lib/types";
import { ErrorBox, Notice, PageHeader, Spinner, StatusBadge, typeLabel } from "@/components/ui";

type Stats = { total_reports: number; by_type: Record<string, number>; analysed_by_type: Record<string, number>; recent: ReportMeta[] };
type ModelSummary = { task: string; display_name: string; model_version: string; served_model: string; headline: Record<string, number> };

const MODULES: { key: string; label: string; types: string[]; href: string }[] = [
  { key: "blood", label: "Blood and CBC", types: ["CBC", "BLOOD"], href: "/blood" },
  { key: "lft", label: "Liver function", types: ["LFT"], href: "/liver" },
  { key: "lipid", label: "Lipid profile", types: ["LIPID"], href: "/lipid" },
  { key: "echo", label: "ECHO", types: ["ECHO"], href: "/echo" },
  { key: "ecg", label: "ECG", types: ["ECG"], href: "/ecg" },
];

const METRIC: Record<string, string> = {
  roc_auc: "ROC-AUC", pr_auc: "PR-AUC", f1: "F1", macro_f1: "Macro F1", accuracy: "Accuracy", balanced_accuracy: "Balanced accuracy",
};

const STATUS: Record<string, string> = {
  analysed: "Analysed", awaiting_confirmation: "Waiting for review", needs_manual_entry: "Needs manual entry", processing: "Processing", failed: "Failed",
};

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    apiGet<Stats>("/api/stats").then(setStats).catch(setError);
    apiGet<ModelSummary[]>("/api/models").then(setModels).catch(() => {});
  }, []);

  const a = stats?.analysed_by_type || {};
  const counts = MODULES.map((m) => ({ ...m, n: m.types.reduce((s, t) => s + (a[t] || 0), 0) }));
  const maxCount = Math.max(1, ...counts.map((c) => c.n));
  const analysed = counts.reduce((s, c) => s + c.n, 0);

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Transform medical reports into understandable health insights">
        <Link href="/upload" className="btn-primary"><Upload size={16} strokeWidth={1.5} />Upload report</Link>
      </PageHeader>
      <ErrorBox error={error ? new Error(`Cannot reach the MediScan API at ${getApiUrl()}. Start the backend or enter its URL below`) : null} />
      {error ? <ApiSettings /> : null}
      {!stats && !error && <Spinner />}
      {stats && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="card">
            <div className="text-[13px] text-slate-600">Reports processed</div>
            <div className="figure mt-2 text-[40px] font-medium leading-none text-navy-900">{stats.total_reports}</div>
            <div className="mt-2 text-xs text-slate-500">{analysed} confirmed and analysed in this deployment</div>
            <ul className="mt-6 space-y-3">
              {counts.map((c) => (
                <li key={c.key}>
                  <Link href={c.href} className="group block">
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="text-slate-700 group-hover:text-slate-900">{c.label}</span>
                      <span className="figure text-slate-900">{c.n}</span>
                    </div>
                    <div className="mt-1.5 h-1 rounded-full bg-slate-100">
                      <div className="h-1 rounded-full bg-slate-400" style={{ width: `${(c.n / maxCount) * 100}%` }} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="card lg:col-span-2">
            <div className="card-title">Recent reports</div>
            {stats.recent.length === 0 ? (
              <Notice>No reports yet. Upload a CBC, LFT, lipid, ECHO or ECG report, or use manual entry on any analysis page</Notice>
            ) : (
              <div className="-mx-6 -mb-6 overflow-x-auto">
                <table className="min-w-full">
                  <thead className="border-y border-slate-900/[0.06] bg-slate-50/80"><tr>
                    <th className="th pl-6">Type</th><th className="th">Report date</th><th className="th">Uploaded</th><th className="th">Status</th><th className="th pr-6" />
                  </tr></thead>
                  <tbody className="divide-y divide-slate-900/[0.06]">
                    {stats.recent.map((r) => (
                      <tr key={r.id}>
                        <td className="td pl-6 font-medium text-slate-900">{typeLabel[r.report_type] || r.report_type}</td>
                        <td className="td figure text-[13px] text-slate-700">{r.report_date || "–"}</td>
                        <td className="td figure text-[13px] text-slate-700">{r.created_at.slice(0, 10)}</td>
                        <td className="td text-slate-700">
                          {STATUS[r.status] || r.status}
                          {r.n_uncertain > 0 && r.status !== "analysed" && <span className="ml-3"><StatusBadge status="uncertain" /></span>}
                        </td>
                        <td className="td pr-6 text-right">
                          <Link className="link" href={`/review?id=${r.id}`}>{r.status === "analysed" ? "Open" : "Review"}</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card lg:col-span-3">
            <div className="mb-4 flex items-baseline justify-between">
              <div className="card-title mb-0">Trained models</div>
              <Link href="/models" className="link inline-flex items-center gap-1 text-sm">Held-out test results <ArrowRight size={14} strokeWidth={1.5} /></Link>
            </div>
            {models.length === 0 ? <p className="text-sm text-slate-500">No model metadata found</p> : (
              <div className="grid gap-6 md:grid-cols-2">
                {models.map((m) => (
                  <div key={m.task}>
                    <div className="text-sm font-medium text-slate-900">{m.display_name}</div>
                    <div className="figure mt-0.5 text-xs text-slate-500">{m.served_model} · {m.model_version}</div>
                    <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
                      {Object.entries(m.headline).map(([k, v]) => (
                        <div key={k}>
                          <dt className="text-xs text-slate-500">{METRIC[k] || k}</dt>
                          <dd className="figure text-[15px] text-slate-900">{v.toFixed(3)}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      <p className="mt-6 text-xs text-slate-500">Counts cover reports uploaded to this deployment. No population health statistics are shown</p>
    </div>
  );
}

function ApiSettings() {
  const [url, setUrl] = useState(getApiUrl());
  return (
    <form className="card mb-6 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setApiUrl(url); window.location.reload(); }}>
      <div className="min-w-[280px] flex-1">
        <label className="label" htmlFor="apiurl">Backend API URL</label>
        <input id="apiurl" className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://your-api.onrender.com" />
        <p className="mt-2 text-xs text-slate-500">OCR and analysis run on the FastAPI backend, locally at http://localhost:8000. Saved only in this browser</p>
      </div>
      <button className="btn-primary">Save and reconnect</button>
    </form>
  );
}
