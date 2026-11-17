"use client";
import ModulePage from "@/components/ModulePage";
import { RangePositionChart, SimpleBars } from "@/components/charts";
import type { ModuleResult } from "@/lib/types";

function LipidCharts({ r }: { r: ModuleResult }) {
  const val = (k: string) => r.measurements.find((m) => m.key === k)?.value ?? r.derived?.find((d) => d.key === k)?.value ?? null;
  const main = ["total_cholesterol", "ldl", "ldl_estimated", "hdl", "vldl", "non_hdl", "triglycerides"]
    .map((k) => ({ k, v: val(k) }))
    .filter((x) => x.v != null)
    .map((x) => ({ name: { total_cholesterol: "Total", ldl: "LDL", ldl_estimated: "LDL (est.)", hdl: "HDL", vldl: "VLDL", non_hdl: "Non-HDL", triglycerides: "TG" }[x.k] as string, value: x.v as number }));
  const ldl = val("ldl") ?? val("ldl_estimated");
  const hdl = val("hdl");
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <SimpleBars title="Cholesterol distribution (mg/dL)" data={main} />
      {ldl != null && hdl != null && (
        <SimpleBars title="HDL vs LDL (mg/dL)" color="#0d9488" data={[{ name: "HDL", value: hdl }, { name: val("ldl") != null ? "LDL" : "LDL (est.)", value: ldl }]} />
      )}
      <div className="lg:col-span-2"><RangePositionChart rows={r.measurements} /></div>
    </div>
  );
}

export default function LipidPage() {
  return (
    <ModulePage
      module="lipid"
      title="Lipid profile"
      subtitle="Exact lipid measurements, transparently calculated ratios and NCEP ATP III categories. LDL is only estimated when the lab did not report it and when the equation's assumptions hold."
      panels={["LIPID"]}
      renderExtra={(r) => <LipidCharts r={r} />}
    />
  );
}
