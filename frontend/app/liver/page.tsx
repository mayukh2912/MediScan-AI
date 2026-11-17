"use client";
import ModulePage from "@/components/ModulePage";
import { RangePositionChart, ShapBars } from "@/components/charts";
import { Notice } from "@/components/ui";
import type { ModuleResult } from "@/lib/types";

function Research({ r }: { r: ModuleResult }) {
  const rm = r.research_model;
  if (!rm) return null;
  return (
    <div className="card">
      <div className="card-title">ML research score (XGBoost, Indian Liver Patient Dataset)</div>
      {!rm.available ? (
        <Notice>{rm.reason}</Notice>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <div className="text-[13px] text-slate-600">Research score</div><div className="figure mt-1 text-[40px] font-medium leading-none text-navy-900">{rm.score?.toFixed(2)}</div>
            <p className="mt-2 text-sm text-slate-600">{rm.score_meaning}</p>
            {rm.imputed?.length ? <p className="mt-2 text-xs text-flag-warn">Imputed {rm.imputed.join(", ")}</p> : null}
            <div className="mt-3 text-xs text-slate-500">
              Model {rm.model} · version {rm.model_version} · held-out test ROC-AUC {rm.test_performance?.roc_auc} · PR-AUC {rm.test_performance?.pr_auc} · recall {rm.test_performance?.recall}
            </div>
            <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-slate-500">
              {rm.limitations?.map((l) => <li key={l}>{l}</li>)}
            </ul>
          </div>
          {rm.explanation && (
            <ShapBars title="Why this score (SHAP, this input)" items={rm.explanation.map((e) => ({ feature: `${e.feature} = ${e.value}`, shap: e.shap }))} note={rm.explanation_note} />
          )}
        </div>
      )}
    </div>
  );
}

export default function LiverPage() {
  return (
    <ModulePage
      module="liver"
      title="Liver function analysis"
      subtitle="ALT, AST, ALP, bilirubin, proteins and documented derived ratios. An XGBoost research classifier trained on the Indian Liver Patient Dataset is shown separately and is not a diagnosis."
      panels={["LFT"]}
      needsAge
      renderExtra={(r) => (
        <div className="space-y-6">
          <Research r={r} />
          <RangePositionChart rows={r.measurements} />
        </div>
      )}
    />
  );
}
