"use client";

import { useEffect, useState } from "react";
import { apiGet, fmt } from "@/lib/api";
import { ErrorBox, Notice, PageHeader, Spinner } from "@/components/ui";
import { Beeswarm, ConfusionMatrix, CurveChart, ImportanceBars } from "@/components/charts";

type Pt = { x: number; y: number };
type BinTest = { n: number; positive_rate_in_test: number; accuracy: number; balanced_accuracy: number; precision: number; recall: number; specificity: number; f1: number; roc_auc: number; pr_auc: number; brier: number; confusion_matrix: { labels: (string | number)[]; matrix: number[][] }; roc_curve: Pt[]; pr_curve: Pt[]; calibration: { mean_predicted: number; fraction_positive: number }[] };
type MultiTest = { n: number; accuracy: number; balanced_accuracy: number; macro_f1: number; macro_precision: number; macro_recall: number; macro_roc_auc_ovr: number; macro_pr_auc: number; per_class: Record<string, { support: number; precision: number; recall: number; f1: number; roc_auc: number | null; pr_auc: number | null }>; confusion_matrix: { labels: string[]; matrix: number[][] }; roc_curves: Record<string, Pt[]>; pr_curves: Record<string, Pt[]>; calibration_top_label: { mean_predicted: number; fraction_positive: number }[] };
type Meta = {
  task: string; display_name: string; model_version: string; served_model: string; created_at: string; split: string; served_model_selection?: string;
  dataset: Record<string, unknown> & { name: string; license: string };
  models: Record<string, { test: BinTest & MultiTest; best_params: Record<string, unknown>; cv_roc_auc_mean?: number; cv_roc_auc_std?: number; validation_macro_f1?: number; validation_macro_f1_std?: number | null }>;
  shap_global: { feature: string; mean_abs_shap: number }[]; shap_beeswarm?: Record<string, { shap: number; value_pct: number }[]>; limitations: string[]; classes?: string[];
};

export default function ModelsPage() {
  const [liver, setLiver] = useState<Meta | null>(null);
  const [ecg, setEcg] = useState<Meta | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    apiGet<Meta>("/api/models/liver").then(setLiver).catch(setError);
    apiGet<Meta>("/api/models/ecg").then(setEcg).catch(setError);
  }, []);
  return (
    <div>
      <PageHeader title="Model performance" subtitle="All numbers below were computed by the training scripts on held-out test data that was never used for training, tuning or model selection. High scores here do not establish clinical reliability." />
      <ErrorBox error={error} />
      {!liver && !ecg && !error && <Spinner />}
      {liver && <LiverSection m={liver} />}
      {ecg && <EcgSection m={ecg} />}
      <Notice>Blood, lipid and ECHO have no ML model on purpose. No public dataset with independent labels was found, so they use transparent rules (docs/DATASETS.md)</Notice>
    </div>
  );
}

function Header({ m }: { m: Meta }) {
  return (
    <div className="mb-4">
      <h2 className="text-xl font-medium text-navy-900">{m.display_name}</h2>
      <p className="text-sm text-slate-500">Version <strong>{m.model_version}</strong> · served model <strong>{m.served_model}</strong> · trained {m.created_at?.slice(0, 10)} · dataset {m.dataset.name} ({m.dataset.license})</p>
      <p className="text-xs text-slate-500">{m.split || (m.dataset.split as string)}{m.served_model_selection ? ` · ${m.served_model_selection}` : ""}</p>
    </div>
  );
}

function LiverSection({ m }: { m: Meta }) {
  const names = Object.keys(m.models);
  return (
    <section className="mb-10 space-y-6">
      <Header m={m} />
      <div className="card overflow-x-auto">
        <div className="card-title">Model comparison – held-out test set (n = {m.models[names[0]].test.n})</div>
        <table className="min-w-full text-sm">
          <thead><tr><th className="th">Model</th><th className="th">CV ROC-AUC (train, 5-fold)</th><th className="th">Test ROC-AUC</th><th className="th">PR-AUC</th><th className="th">F1</th><th className="th">Precision</th><th className="th">Recall</th><th className="th">Specificity</th><th className="th">Bal. acc.</th><th className="th">Brier</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {names.map((n) => { const t = m.models[n].test; return (
              <tr key={n} >
                <td className="td font-medium">{n}{n === m.served_model && <span className="ml-2 text-xs font-normal text-teal-700">Served</span>}</td>
                <td className="td">{fmt(m.models[n].cv_roc_auc_mean, 3)} ± {fmt(m.models[n].cv_roc_auc_std, 3)}</td>
                <td className="td">{fmt(t.roc_auc, 3)}</td><td className="td">{fmt(t.pr_auc, 3)}</td><td className="td">{fmt(t.f1, 3)}</td>
                <td className="td">{fmt(t.precision, 3)}</td><td className="td">{fmt(t.recall, 3)}</td><td className="td">{fmt(t.specificity, 3)}</td>
                <td className="td">{fmt(t.balanced_accuracy, 3)}</td><td className="td">{fmt(t.brier, 3)}</td>
              </tr>); })}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">Positive class = record labelled &quot;liver patient&quot; ({fmt(m.models[names[0]].test.positive_rate_in_test, 2)} of test set). Threshold 0.5</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card"><div className="card-title">ROC curves</div><CurveChart highlight={m.served_model} diagonal xLabel="False positive rate" yLabel="True positive rate" series={names.map((n) => ({ name: n, points: m.models[n].test.roc_curve }))} /></div>
        <div className="card"><div className="card-title">Precision–recall curves</div><CurveChart highlight={m.served_model} xLabel="Recall" yLabel="Precision" series={names.map((n) => ({ name: n, points: m.models[n].test.pr_curve }))} /></div>
        <div className="card"><div className="card-title">Calibration (reliability)</div><CurveChart highlight={m.served_model} diagonal xLabel="Mean predicted probability" yLabel="Observed fraction positive" series={names.map((n) => ({ name: n, points: m.models[n].test.calibration.map((c) => ({ x: c.mean_predicted, y: c.fraction_positive })) }))} /></div>
        <div className="card"><div className="card-title">Confusion matrices (test)</div>
          <div className="grid grid-cols-2 gap-4">{names.map((n) => <div key={n}><div className="mb-1 text-xs font-medium">{n}</div><ConfusionMatrix labels={["non-patient", "patient"]} matrix={m.models[n].test.confusion_matrix.matrix} /></div>)}</div>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card"><ImportanceBars title="Global SHAP importance (XGBoost, test set)" items={m.shap_global} /></div>
        {m.shap_beeswarm && <div className="card"><Beeswarm data={m.shap_beeswarm} /></div>}
      </div>
      <Limitations items={m.limitations} />
    </section>
  );
}

function EcgSection({ m }: { m: Meta }) {
  const names = Object.keys(m.models);
  const classes = m.classes || [];
  const served = m.models[m.served_model].test;
  return (
    <section className="mb-10 space-y-6">
      <Header m={m} />
      <div className="card overflow-x-auto">
        <div className="card-title">Model comparison – unseen patients (DS2, n = {served.n} beats)</div>
        <table className="min-w-full text-sm">
          <thead><tr><th className="th">Model</th><th className="th">Validation macro-F1 (DS1)</th><th className="th">Accuracy</th><th className="th">Balanced acc.</th><th className="th">Macro F1</th><th className="th">Macro ROC-AUC</th><th className="th">Macro PR-AUC</th>{classes.map((c) => <th key={c} className="th">F1 {c}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {names.map((n) => { const t = m.models[n].test; return (
              <tr key={n} >
                <td className="td font-medium">{n}{n === m.served_model && <span className="ml-2 text-xs font-normal text-teal-700">Served</span>}</td>
                <td className="td">{fmt(m.models[n].validation_macro_f1, 3)}{m.models[n].validation_macro_f1_std != null ? ` ± ${fmt(m.models[n].validation_macro_f1_std, 3)}` : ""}</td>
                <td className="td">{fmt(t.accuracy, 3)}</td><td className="td">{fmt(t.balanced_accuracy, 3)}</td><td className="td">{fmt(t.macro_f1, 3)}</td>
                <td className="td">{fmt(t.macro_roc_auc_ovr, 3)}</td><td className="td">{fmt(t.macro_pr_auc, 3)}</td>
                {classes.map((c) => <td key={c} className="td">{fmt(t.per_class[c].f1, 3)}</td>)}
              </tr>); })}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">Accuracy is dominated by the N class ({served.per_class.N?.support} of {served.n} beats) and is not a meaningful summary here; look at per-class recall and precision</p>
      </div>
      <div className="card overflow-x-auto">
        <div className="card-title">Per-class metrics – served model ({m.served_model})</div>
        <table className="min-w-full text-sm"><thead><tr><th className="th">Class</th><th className="th">Support</th><th className="th">Precision</th><th className="th">Recall</th><th className="th">F1</th><th className="th">ROC-AUC</th><th className="th">PR-AUC</th></tr></thead>
          <tbody className="divide-y divide-slate-100">{classes.map((c) => { const p = served.per_class[c]; return (
            <tr key={c}><td className="td font-medium">{c}</td><td className="td">{p.support}</td><td className="td">{fmt(p.precision, 3)}</td><td className="td">{fmt(p.recall, 3)}</td><td className="td">{fmt(p.f1, 3)}</td><td className="td">{fmt(p.roc_auc, 3)}</td><td className="td">{fmt(p.pr_auc, 3)}</td></tr>); })}</tbody></table>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        {names.map((n) => <div key={n} className="card"><div className="card-title">Confusion matrix – {n}</div><ConfusionMatrix labels={classes} matrix={m.models[n].test.confusion_matrix.matrix} /></div>)}
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card"><div className="card-title">One-vs-rest ROC ({m.served_model})</div><CurveChart diagonal xLabel="False positive rate" yLabel="True positive rate" series={Object.entries(served.roc_curves).map(([k, v]) => ({ name: k, points: v }))} /></div>
        <div className="card"><div className="card-title">One-vs-rest precision–recall ({m.served_model})</div><CurveChart xLabel="Recall" yLabel="Precision" series={Object.entries(served.pr_curves).map(([k, v]) => ({ name: k, points: v }))} /></div>
        <div className="card"><div className="card-title">Top-label calibration</div><CurveChart highlight={m.served_model} diagonal xLabel="Confidence" yLabel="Accuracy" series={names.map((n) => ({ name: n, points: m.models[n].test.calibration_top_label.map((c) => ({ x: c.mean_predicted, y: c.fraction_positive })) }))} /></div>
        <div className="card"><ImportanceBars title="Global SHAP importance (XGBoost, DS2 sample)" items={m.shap_global} /></div>
      </div>
      <Limitations items={m.limitations} />
    </section>
  );
}

function Limitations({ items }: { items: string[] }) {
  return (
    <div className="card"><div className="card-title">Limitations</div>
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">{items.map((l) => <li key={l}>{l}</li>)}</ul></div>
  );
}
