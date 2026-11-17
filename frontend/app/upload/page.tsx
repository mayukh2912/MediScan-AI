"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileUp, Lock, ShieldCheck } from "lucide-react";
import { ApiError, apiGet, apiUpload } from "@/lib/api";
import type { ReportFull } from "@/lib/types";
import { ErrorBox, Notice, PageHeader, typeLabel } from "@/components/ui";

const ACCEPT = ".jpg,.jpeg,.png,.pdf";
const MAX_MB = 15;
type Job = { status: string; progress: number; stage: string; error?: string | null };

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const [report, setReport] = useState<ReportFull | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [duplicate, setDuplicate] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function choose(f: File | null) {
    setError(null); setJob(null); setReport(null); setReportId(null); setDuplicate(null);
    if (!f) return;
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (!["jpg", "jpeg", "png", "pdf"].includes(ext || "")) return setError(new Error("Only JPG, JPEG, PNG and PDF files are supported"));
    if (f.size > MAX_MB * 1024 * 1024) return setError(new Error(`File is larger than ${MAX_MB} MB.`));
    setFile(f);
    setPreview(URL.createObjectURL(f)); // local preview only – nothing leaves the browser until you click Process
  }

  async function submit(allowDuplicate = false) {
    if (!file) return;
    setError(null); setDuplicate(null);
    const form = new FormData();
    form.append("file", file);
    form.append("consent_store_file", String(consent));
    form.append("allow_duplicate", String(allowDuplicate));
    try {
      setJob({ status: "uploading", progress: 2, stage: "uploading" });
      const res = await apiUpload<{ report_id: string; job_id: string }>("/api/reports/upload", form);
      setReportId(res.report_id);
      poll(res.job_id, res.report_id);
    } catch (e) {
      setJob(null);
      if (e instanceof ApiError && e.status === 409) setDuplicate((e.detail as { duplicate_of: string }).duplicate_of);
      else setError(e);
    }
  }

  function poll(jobId: string, rid: string) {
    const t = setInterval(async () => {
      try {
        const j = await apiGet<Job>(`/api/jobs/${jobId}`);
        setJob(j);
        if (j.status === "succeeded" || j.status === "failed") {
          clearInterval(t);
          setReport(await apiGet<ReportFull>(`/api/reports/${rid}`));
        }
      } catch (e) {
        clearInterval(t);
        setError(e);
      }
    }, 700);
  }

  const ex = report?.extraction;
  return (
    <div>
      <PageHeader title="Upload report" subtitle="JPG, JPEG, PNG or PDF up to 15 MB. The document is processed with local OCR (Tesseract) – it is never sent to an external AI service." />
      <ErrorBox error={error} />
      {duplicate && (
        <Notice tone="warn">
          This exact file was uploaded before. <Link className="underline" href={`/review?id=${duplicate}`}>Open the existing report</Link> or{" "}
          <button className="underline" onClick={() => submit(true)}>process it again</button>.
        </Notice>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files?.[0] || null); }}
            onClick={() => input.current?.click()}
            role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed bg-white px-6 py-16 text-center transition-colors duration-150 ${drag ? "border-teal-600 bg-slate-50" : "border-slate-300 hover:border-slate-400"}`}
          >
            <FileUp className="text-slate-500" size={24} strokeWidth={1.5} />
            <div className="mt-3 font-medium text-navy-900">{file ? file.name : "Drop a report here or click to browse"}</div>
            <div className="text-xs text-slate-500">{file ? `${(file.size / 1024).toFixed(0)} KB` : "CBC · LFT · Lipid · ECHO · ECG"}</div>
            <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => choose(e.target.files?.[0] || null)} />
          </div>
          <label className="card flex cursor-pointer items-start gap-3 text-sm">
            <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>
              <span className="font-medium text-navy-900"><Lock size={16} strokeWidth={1.5} className="mr-1 inline" />Store the original file (optional)</span>
              <span className="block text-slate-500">Off by default. If enabled, the file is encrypted at rest and can be deleted at any time from Report History. Extracted values are always stored encrypted so you can review them.</span>
            </span>
          </label>
          <button className="btn-primary w-full" disabled={!file || (job !== null && job.status !== "failed" && job.status !== "succeeded")} onClick={() => submit(false)}>
            <ShieldCheck size={16} strokeWidth={1.5} />Process report
          </button>
          {job && (
            <div className="card">
              <div className="mb-2 flex justify-between text-sm"><span className="capitalize">{job.stage}</span><span>{job.progress}%</span></div>
              <div className="h-1 overflow-hidden rounded-full bg-slate-200"><div className="h-1 w-full origin-left rounded-full bg-teal-600 transition-transform duration-300 ease-out" style={{ transform: `scaleX(${job.progress / 100})` }} /></div>
              {job.status === "failed" && <p className="mt-2 text-sm text-flag-high">{job.error || "Processing failed."} You can still enter values manually on any analysis page.</p>}
            </div>
          )}
          {ex && report && (
            <div className="card space-y-3">
              <div className="card-title">Extraction complete</div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><div className="label">Detected type</div><span className="font-semibold">{typeLabel[ex.classification.report_type] || ex.classification.report_type}</span></div>
                <div><div className="label">Panels</div>{ex.classification.panels.map((p) => typeLabel[p] || p).join(", ") || "–"}</div>
                <div><div className="label">Measurements</div>{ex.measurements.length} found · {ex.validation.n_uncertain + ex.validation.n_invalid} need attention</div>
                <div><div className="label">OCR</div>{ex.ocr.method} · mean conf. {ex.ocr.mean_confidence}</div>
                <div><div className="label">Report date</div>{ex.report_date?.date || "not found"}</div>
                <div><div className="label">Preprocessing</div>{ex.ocr.preprocessing.join(", ") || "none needed"}</div>
              </div>
              {ex.ocr.quality_warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
              <button className="btn-accent w-full" onClick={() => router.push(`/review?id=${reportId}`)}>Review and confirm values</button>
              <p className="text-xs text-slate-500">No analysis runs until you have checked and confirmed the extracted values</p>
            </div>
          )}
        </div>
        <div className="card min-h-[420px]">
          <div className="card-title">Document preview</div>
          {!preview ? <p className="text-sm text-slate-500">Your document appears here, rendered locally in your browser</p> :
            file?.type === "application/pdf" || file?.name.toLowerCase().endsWith(".pdf") ? (
              <object data={preview} type="application/pdf" className="h-[600px] w-full rounded border" aria-label="PDF preview">
                <p className="text-sm">PDF preview is not supported in this browser</p>
              </object>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="Uploaded report preview" className="max-h-[700px] w-full rounded border object-contain" />
            )}
        </div>
      </div>
    </div>
  );
}
