"use client";

import { AlertTriangle, Info, Loader2, XCircle } from "lucide-react";
import type { Derived, Measurement, Pattern } from "@/lib/types";
import { fmt } from "@/lib/api";

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[28px] font-medium leading-9 tracking-[-0.01em] text-navy-900">{title}</h1>
        {subtitle && <p className="mt-2 max-w-3xl text-sm leading-5 text-slate-600">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <Loader2 className="animate-spin" size={16} strokeWidth={1.5} /> {label || "Loading"}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-flag-high/20 bg-red-50/60 px-4 py-3 text-sm text-flag-high" role="alert">
      <XCircle size={16} strokeWidth={1.5} className="mt-0.5 shrink-0" /> {msg}
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warn" }) {
  const warn = tone === "warn";
  const Icon = warn ? AlertTriangle : Info;
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm leading-5 ${warn ? "border-amber-600/20 bg-amber-50/60 text-slate-800" : "border-slate-900/[0.08] bg-slate-100/70 text-slate-700"}`}>
      <Icon size={16} strokeWidth={1.5} className={`mt-0.5 shrink-0 ${warn ? "text-flag-warn" : "text-slate-500"}`} />
      <div>{children}</div>
    </div>
  );
}

/** A label, a figure and an optional caption. No icons, no decoration. */
export function StatCard({ label, value, hint }: { label: string; value: React.ReactNode; icon?: React.ReactNode; hint?: string }) {
  return (
    <div className="card">
      <div className="text-[13px] text-slate-600">{label}</div>
      <div className="figure mt-2 text-[28px] font-medium leading-8 text-navy-900">{value}</div>
      {hint && <div className="mt-2 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

const DOT: Record<string, string> = { ok: "bg-slate-300", uncertain: "bg-flag-warn", invalid: "bg-flag-high" };
const STATUS_LABEL: Record<string, string> = { ok: "Read", uncertain: "Check", invalid: "Implausible" };

export function StatusBadge({ status }: { status?: string }) {
  const s = status || "ok";
  return (
    <span className={`badge ${s === "ok" ? "text-slate-500" : s === "invalid" ? "text-flag-high" : "text-flag-warn"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[s] || DOT.ok}`} />
      {STATUS_LABEL[s] || s}
    </span>
  );
}

/** Lab-sheet style flag: an H or L next to the words, in the flag colour; in-range values stay quiet */
export function InterpBadge({ interp }: { interp?: string }) {
  if (interp === "high" || interp === "low") {
    return (
      <span className="badge text-flag-high">
        <span className="figure inline-flex h-4 w-4 items-center justify-center rounded border border-flag-high/30 text-[11px] leading-none">{interp === "high" ? "H" : "L"}</span>
        {interp === "high" ? "Above range" : "Below range"}
      </span>
    );
  }
  return <span className="badge text-slate-500">{interp === "within_range" ? "In range" : "Not assessed"}</span>;
}

export const typeLabel: Record<string, string> = {
  CBC: "CBC", BLOOD: "Blood", LFT: "Liver (LFT)", LIPID: "Lipid", ECHO: "ECHO", ECG: "ECG", UNKNOWN: "Unknown", IRON_VITAMIN: "Iron and vitamins",
};

function rangeText(r?: { low: number | null; high: number | null } | null) {
  if (!r) return "–";
  if (r.low != null && r.high != null) return `${fmt(r.low)}–${fmt(r.high)}`;
  if (r.low != null) return `≥ ${fmt(r.low)}`;
  if (r.high != null) return `≤ ${fmt(r.high)}`;
  return "–";
}

/** Signature: the reference-range tick. Track, normal band, and a tick where the value sits. */
export function RangeMeter({ value, low, high, width = 144 }: { value: number; low: number | null; high: number | null; width?: number }) {
  if (low == null && high == null) return null;
  const lo = low ?? 0;
  const hi = high ?? lo * 2 + 1;
  const span = hi - lo || 1;
  const min = lo - span * 0.6;
  const max = hi + span * 0.6;
  const pct = (x: number) => Math.min(100, Math.max(0, ((x - min) / (max - min)) * 100));
  const out = (low != null && value < low) || (high != null && value > high);
  return (
    <div className="relative mt-2 h-3" style={{ width }} aria-hidden>
      <div className="absolute top-[5px] h-0.5 w-full rounded-full bg-slate-200" />
      <div className="absolute top-[4px] h-1 rounded-full bg-teal-200" style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }} />
      <div className={`absolute top-0 h-3 w-0.5 -translate-x-1/2 rounded-full ${out ? "bg-flag-high" : "bg-navy-900"}`} style={{ left: `${pct(value)}%` }} />
    </div>
  );
}

export function MeasurementTable({ rows, showRule = true }: { rows: Measurement[]; showRule?: boolean }) {
  if (!rows.length) return <p className="text-sm text-slate-500">No measurements</p>;
  return (
    <div className="-mx-6 overflow-x-auto">
      <table className="min-w-full">
        <thead className="border-y border-slate-900/[0.06] bg-slate-50/80">
          <tr>
            <th className="th pl-6">Test</th><th className="th">Result</th><th className="th">Range used</th>
            <th className="th">Assessment</th><th className="th pr-6">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-900/[0.06]">
          {rows.map((m) => {
            const r = m.assessment?.range_used;
            return (
              <tr key={m.key}>
                <td className="td pl-6 font-medium text-slate-900">
                  {m.test}
                  {m.category && <div className="mt-0.5 text-xs font-normal text-slate-500">{m.category.label}, {m.category.scheme}</div>}
                  {m.ef_band && <div className="mt-0.5 text-xs font-normal text-slate-500">{m.ef_band}</div>}
                </td>
                <td className="td whitespace-nowrap">
                  <span className="figure font-medium text-slate-900">{fmt(m.value)}</span> <span className="text-xs text-slate-500">{m.unit_display ?? m.unit}</span>
                  {m.value != null && r && <RangeMeter value={m.value} low={r.low} high={r.high} />}
                </td>
                <td className="td whitespace-nowrap">
                  <span className="figure text-[13px] text-slate-700">{rangeText(r)}</span>
                  {r && <div className="mt-0.5 text-xs text-slate-500">{r.source === "laboratory" ? "From the report" : "Default adult range"}</div>}
                </td>
                <td className="td">
                  <InterpBadge interp={m.assessment?.interpretation} />
                  {showRule && m.assessment?.rule && <div className="mt-1 max-w-xs text-xs leading-4 text-slate-500">{m.assessment.rule}</div>}
                </td>
                <td className="td pr-6 text-xs leading-4 text-slate-500">
                  {m.origin === "manual" ? "Entered or corrected" : m.origin === "pdf_text" ? "PDF text layer" : "OCR"}
                  {m.extraction_confidence != null && m.origin !== "manual" && <div className="figure">conf. {fmt(m.extraction_confidence)}</div>}
                  {m.lab_calculated && <div>Calculated by lab</div>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function DerivedList({ items }: { items?: Derived[] }) {
  if (!items?.length) return null;
  return (
    <div className="card">
      <div className="card-title">Derived values <span className="text-xs font-normal text-slate-500">Calculated by MediScan AI, not measured by the lab</span></div>
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((d) => (
          <div key={d.name} className={`rounded-lg bg-slate-50 p-4 ring-1 ring-slate-900/[0.06] ${d.applicable === false ? "opacity-60" : ""}`}>
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-sm font-medium text-slate-900">{d.name}</div>
              <div className="figure text-lg font-medium text-navy-900">{fmt(d.value)} <span className="font-sans text-xs font-normal text-slate-500">{d.unit}</span></div>
            </div>
            <div className="figure mt-1 text-xs text-slate-500">= {d.formula}</div>
            {d.category?.label && <div className="mt-2 text-xs text-slate-700">{d.category.label}, {d.category.scheme}</div>}
            {d.note && <div className="mt-1 text-xs leading-4 text-slate-500">{d.note}</div>}
            {d.applicable === false && <div className="mt-1 text-xs text-flag-warn">Not applicable for these values</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function PatternList({ items, empty }: { items?: Pattern[]; empty?: string }) {
  return (
    <div className="card">
      <div className="card-title">Rule-based observations</div>
      {!items?.length ? (
        <p className="text-sm text-slate-500">{empty || "No rule-based observations for these values"}</p>
      ) : (
        <ul className="divide-y divide-slate-900/[0.06]">
          {items.map((p, i) => (
            <li key={i} className="py-4 first:pt-0 last:pb-0">
              <div className="text-sm font-medium text-slate-900">{p.pattern}</div>
              <p className="mt-1 text-sm leading-5 text-slate-600">{p.explanation}</p>
              <div className="mt-2 text-xs text-slate-500"><span className="font-medium text-slate-600">Rule</span> {p.rule}</div>
              {p.evidence?.map((e, j) => <div key={j} className="figure mt-0.5 text-xs text-slate-500">{e}</div>)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MissingList({ items }: { items?: { key: string; test: string }[] }) {
  if (!items?.length) return null;
  return (
    <div className="card">
      <div className="card-title">Not on the report</div>
      <p className="text-sm text-slate-700">{items.map((m) => m.test).join(", ")}</p>
      <p className="mt-2 text-xs text-slate-500">Missing values are never estimated, except where a documented formula applies (listed under derived values)</p>
    </div>
  );
}
