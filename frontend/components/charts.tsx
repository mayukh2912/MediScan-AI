"use client";

import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import type { Measurement } from "@/lib/types";

// One accent per chart: the thing that matters is teal (or the flag colour when it is out of range),
// everything else sits in neutral steps of the ink ramp.
const NAVY = "#0b2545";
const TEAL = "#0f766e";
const CYAN = "#94a3b8"; // neutral series (kept name for call sites)
const ROSE = "#b42318"; // flag / positive SHAP
const SKY = "#3b6ea8"; // negative SHAP
const GRID = "#e2e8f0";
const TICK = { fontSize: 11, fill: "#64748b", fontFamily: '"IBM Plex Mono", ui-monospace, monospace' };

/** Position of each value relative to its range: 0 = lower limit, 1 = upper limit. */
export function RangePositionChart({ rows }: { rows: Measurement[] }) {
  const data = rows
    .filter((m) => m.value != null && m.assessment?.range_used?.low != null && m.assessment?.range_used?.high != null)
    .map((m) => {
      const r = m.assessment!.range_used!;
      const pos = ((m.value as number) - (r.low as number)) / ((r.high as number) - (r.low as number));
      return { name: m.test, pos: Number(pos.toFixed(2)), interp: m.assessment!.interpretation };
    });
  if (!data.length) return null;
  return (
    <div className="card">
      <div className="card-title">Position within reference range</div>
      <p className="-mt-2 mb-4 text-xs text-slate-500">0 is the lower limit and 1 the upper limit of the range used for each test. Values outside it are in the flag colour</p>
      <ResponsiveContainer width="100%" height={Math.max(180, data.length * 34)}>
        <BarChart data={data} layout="vertical" margin={{ left: 30, right: 20 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" domain={[-1, 2]} ticks={[-1, -0.5, 0, 0.5, 1, 1.5, 2]} allowDataOverflow />
          <YAxis type="category" dataKey="name" width={120} tick={TICK} />
          <Tooltip />
          <ReferenceLine x={0} stroke="#94a3b8" />
          <ReferenceLine x={1} stroke="#94a3b8" />
          <Bar isAnimationActive={false} dataKey="pos" name="Relative position">
            {data.map((d, i) => <Cell key={i} fill={d.interp === "high" || d.interp === "low" ? ROSE : "#cbd5e1"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SimpleBars({ data, title, unit, color = "#64748b" }: { data: { name: string; value: number }[]; title: string; unit?: string; color?: string }) {
  if (!data.length) return null;
  return (
    <div className="card">
      <div className="card-title">{title}</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="name" tick={TICK} interval={0} />
          <YAxis unit={unit} tick={TICK} />
          <Tooltip />
          <Bar isAnimationActive={false} dataKey="value" fill={color} radius={[2, 2, 0, 0]} maxBarSize={56} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ShapBars({ items, title, note }: { items: { feature: string; shap: number }[]; title: string; note?: string }) {
  const data = [...items].sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap)).slice(0, 12).reverse();
  return (
    <div>
      <div className="mb-1 text-sm font-medium text-navy-900">{title}</div>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 26)}>
        <BarChart data={data} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" tick={TICK} />
          <YAxis type="category" dataKey="feature" width={170} tick={TICK} />
          <Tooltip />
          <ReferenceLine x={0} stroke="#64748b" />
          <Bar isAnimationActive={false} dataKey="shap" name="SHAP value">
            {data.map((d, i) => <Cell key={i} fill={d.shap >= 0 ? ROSE : SKY} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {note && <p className="text-xs text-slate-500">{note}</p>}
    </div>
  );
}

export function ImportanceBars({ items, title }: { items: { feature: string; mean_abs_shap: number }[]; title: string }) {
  const data = items.slice(0, 13).map((d) => ({ feature: d.feature, value: Number(d.mean_abs_shap.toFixed(4)) })).reverse();
  return (
    <div>
      <div className="mb-1 text-sm font-medium text-navy-900">{title}</div>
      <ResponsiveContainer width="100%" height={Math.max(180, data.length * 24)}>
        <BarChart data={data} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" tick={TICK} />
          <YAxis type="category" dataKey="feature" width={170} tick={TICK} />
          <Tooltip />
          <Bar isAnimationActive={false} dataKey="value" name="mean |SHAP|" fill="#64748b" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function mix(a: string, b: string, t: number) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${pa.map((v, i) => Math.round(v + (pb[i] - v) * t)).join(",")})`;
}

export function Beeswarm({ data }: { data: Record<string, { shap: number; value_pct: number }[]> }) {
  const features = Object.keys(data);
  const points = features.flatMap((f, fi) =>
    data[f].map((p, j) => ({ x: p.shap, y: features.length - fi + ((j % 7) - 3) * 0.04, pct: p.value_pct, f })),
  );
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-navy-900">SHAP summary on the test set</div>
      <ResponsiveContainer width="100%" height={features.length * 34 + 40}>
        <ScatterChart margin={{ left: 40 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis type="number" dataKey="x" name="SHAP" tick={TICK} />
          <YAxis type="number" dataKey="y" domain={[0.5, features.length + 0.5]} ticks={features.map((_, i) => features.length - i)}
            tickFormatter={(v) => features[features.length - v] || ""} width={170} tick={TICK} />
          <ZAxis range={[14, 14]} />
          <ReferenceLine x={0} stroke="#64748b" />
          <Tooltip formatter={(v: number) => v.toFixed?.(3) ?? v} />
          <Scatter isAnimationActive={false} data={points}>
            {points.map((p, i) => <Cell key={i} fill={mix(SKY, ROSE, p.pct)} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="text-xs text-slate-500">Blue is a low feature value, red a high one. Positive SHAP moves the model towards the &apos;liver patient&apos; label</p>
    </div>
  );
}

export function CurveChart({ series, xLabel, yLabel, diagonal, highlight }: {
  series: { name: string; points: { x: number; y: number }[] }[]; xLabel: string; yLabel: string; diagonal?: boolean; highlight?: string;
}) {
  // the highlighted series (served model) leads in the accent; others are neutral steps
  const neutrals = [NAVY, "#64748b", "#94a3b8", "#cbd5e1"];
  let ni = 0;
  const colorFor = (name: string) => (name === highlight ? TEAL : neutrals[ni++ % neutrals.length]);
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart margin={{ bottom: 18, left: 4 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis type="number" dataKey="x" domain={[0, 1]} tick={TICK} label={{ value: xLabel, position: "insideBottom", offset: -8, fontSize: 11 }} />
        <YAxis type="number" domain={[0, 1]} tick={TICK} label={{ value: yLabel, angle: -90, position: "insideLeft", fontSize: 11 }} />
        <Tooltip formatter={(v: number) => v.toFixed(3)} />
        <Legend wrapperStyle={{ fontSize: 12, color: "#475569" }} iconType="plainline" />
        {diagonal && <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#cbd5e1" strokeDasharray="4 4" />}
        {series.map((s, i) => (
          <Line isAnimationActive={false} key={s.name} data={s.points} dataKey="y" name={s.name} stroke={colorFor(s.name)} dot={false} strokeWidth={s.name === highlight ? 2 : 1.5} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Waveform({ points, peaks, unit }: { points: { t: number; v: number }[]; peaks?: number[]; unit: string }) {
  return (
    <div className="ecg-paper overflow-hidden rounded-lg ring-1 ring-[#ecb3b3]/60">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={points} margin={{ top: 12, left: 0, right: 12, bottom: 4 }}>
          <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ ...TICK, fill: "#9f5b5b" }} unit="s" axisLine={false} tickLine={false} />
          <YAxis tick={{ ...TICK, fill: "#9f5b5b" }} unit={unit === "mV" ? " mV" : ""} width={56} axisLine={false} tickLine={false} />
          <Tooltip formatter={(v: number) => v.toFixed(3)} labelFormatter={(l) => `${l}s`} />
          {peaks?.map((p) => <ReferenceLine key={p} x={p} stroke={TEAL} strokeOpacity={0.35} />)}
          <Line isAnimationActive={false} dataKey="v" stroke="#1e293b" dot={false} strokeWidth={1.4} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ConfusionMatrix({ labels, matrix }: { labels: (string | number)[]; matrix: number[][] }) {
  const rowSums = matrix.map((r) => r.reduce((a, b) => a + b, 0) || 1);
  return (
    <table className="text-xs">
      <thead>
        <tr><th className="p-1 pr-2 text-left font-normal text-slate-500">True / predicted</th>{labels.map((l) => <th key={l} className="p-1 font-medium">{l}</th>)}</tr>
      </thead>
      <tbody>
        {matrix.map((row, i) => (
          <tr key={i}>
            <th className="p-1 text-left font-medium">{labels[i]}</th>
            {row.map((v, j) => {
              const a = v / rowSums[i];
              return (
                <td key={j} className="figure h-10 w-14 border border-white text-center" style={{ background: `rgba(11,37,69,${0.04 + a * 0.82})`, color: a > 0.5 ? "white" : "#0b2545" }}>
                  {v}<div className="text-[11px] opacity-75">{(a * 100).toFixed(0)}%</div>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
