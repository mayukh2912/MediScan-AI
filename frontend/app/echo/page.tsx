"use client";
import ModulePage from "@/components/ModulePage";
import type { ModuleResult } from "@/lib/types";

function Findings({ r }: { r: ModuleResult }) {
  const f = r.findings;
  if (!f || !Object.keys(f).length) return null;
  const ef = r.measurements.find((m) => m.key === "ef");
  const Section = ({ title, items }: { title: string; items?: string[] }) =>
    items?.length ? (
      <div>
        <div className="label">{title}</div>
        {items.map((t, i) => <blockquote key={i} className="mb-2 border-l-2 border-slate-300 pl-3 text-sm leading-5 text-slate-800">{t}</blockquote>)}
      </div>
    ) : null;
  return (
    <div className="grid items-start gap-6 lg:grid-cols-3">
      <div className="card">
        <div className="card-title">Ejection fraction</div>
        {ef?.value != null ? (
          <>
            <div className="figure text-[40px] font-medium leading-none text-navy-900">{ef.value}%</div>
            <div className="mt-1 text-sm text-slate-600">{ef.ef_band}</div>
            <div className="mt-2 text-xs text-slate-400">Extraction confidence {ef.extraction_confidence?.toFixed(2)}</div>
          </>
        ) : <p className="text-sm text-slate-500">No numeric EF on the report. EF is never inferred from the wording</p>}
      </div>
      <div className="card lg:col-span-2 space-y-3">
        <div className="card-title">Original report wording</div>
        {f.valve_findings && Object.entries(f.valve_findings).map(([v, items]) => <Section key={v} title={`${v.charAt(0).toUpperCase() + v.slice(1)} valve`} items={items} />)}
        <Section title="Wall motion" items={f.wall_motion} />
        <Section title="Diastolic function" items={f.diastolic_function} />
        <Section title="LV function (as written)" items={f.lv_function_text} />
        <Section title="Pericardium" items={f.pericardium} />
        <Section title="Recorded impression" items={f.impression} />
        <p className="text-xs text-slate-400">{f.note}</p>
      </div>
    </div>
  );
}

export default function EchoPage() {
  return (
    <ModulePage
      module="echo"
      title="ECHO report analysis"
      subtitle="Structured extraction of echocardiography reports (ultrasound) – distinct from ECG electrical signals. Measurements are compared with ASE/EACVI reference values; narrative findings are quoted verbatim."
      panels={["ECHO"]}
      renderExtra={(r) => <Findings r={r} />}
    />
  );
}
