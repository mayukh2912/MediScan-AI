"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, Lock, Trash2 } from "lucide-react";
import { apiGet, apiSend, download } from "@/lib/api";
import type { ReportMeta } from "@/lib/types";
import { ErrorBox, Notice, PageHeader, Spinner, typeLabel } from "@/components/ui";

export default function HistoryPage() {
  const [rows, setRows] = useState<ReportMeta[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = () => apiGet<ReportMeta[]>("/api/reports").then(setRows).catch(setError);
  useEffect(() => { load(); }, []);

  async function del(id: string) {
    if (!window.confirm("Permanently delete this report, its extracted values and any stored file?")) return;
    await apiSend(`/api/reports/${id}`, "DELETE").catch(setError);
    load();
  }
  async function delAll() {
    if (!window.confirm("Permanently delete ALL reports and stored data? This cannot be undone.")) return;
    await apiSend(`/api/reports?confirm=true`, "DELETE").catch(setError);
    load();
  }

  return (
    <div>
      <PageHeader title="Report history" subtitle="Everything stored by this deployment. Extracted data is encrypted at rest; original files are kept only if you consented at upload.">
        <button className="btn-danger" onClick={delAll} disabled={!rows?.length}><Trash2 size={16} strokeWidth={1.5} />Delete all data</button>
      </PageHeader>
      <ErrorBox error={error} />
      {!rows ? <Spinner /> : rows.length === 0 ? <Notice>No stored reports</Notice> : (
        <div className="card overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50"><tr><th className="th">Type</th><th className="th">Report date</th><th className="th">Uploaded</th><th className="th">Status</th><th className="th">Values</th><th className="th">File</th><th className="th" /></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="td font-medium">{typeLabel[r.report_type] || r.report_type}<div className="text-xs font-normal text-slate-400">{r.panels.join(", ")}</div></td>
                  <td className="td">{r.report_date || "–"}</td>
                  <td className="td">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="td text-slate-700">{r.status.charAt(0).toUpperCase() + r.status.slice(1).replace(/_/g, " ")}</td>
                  <td className="td text-xs">{r.n_measurements} values{r.status === "analysed" ? ` · ${r.n_abnormal} outside range` : ` · ${r.n_uncertain} to check`}</td>
                  <td className="td text-xs">{r.file_stored ? <span className="inline-flex items-center gap-1.5 text-slate-700"><Lock size={14} strokeWidth={1.5} className="text-slate-500" />Stored, encrypted</span> : <span className="text-slate-500">Not stored</span>}</td>
                  <td className="td whitespace-nowrap text-right">
                    <Link href={`/review?id=${r.id}`} className="link mr-4">{r.status === "analysed" ? "Open" : "Review"}</Link>
                    {r.status === "analysed" && <button className="mr-4 text-slate-500 transition-colors hover:text-slate-900" aria-label="Download PDF" onClick={() => download(`/api/reports/${r.id}/download`, `mediscan_${r.id.slice(0, 8)}.pdf`)}><Download size={16} strokeWidth={1.5} /></button>}
                    <button className="text-slate-400 transition-colors hover:text-flag-high" aria-label="Delete report" onClick={() => del(r.id)}><Trash2 size={16} strokeWidth={1.5} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
