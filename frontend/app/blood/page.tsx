"use client";
import ModulePage from "@/components/ModulePage";
import { RangePositionChart } from "@/components/charts";

export default function BloodPage() {
  return (
    <ModulePage
      module="blood"
      title="Blood report analysis"
      subtitle="CBC indices and, when measured, ferritin, vitamin B12 and folate. Rule-based comparison with the laboratory's range (or a cited default). CBC values alone cannot diagnose nutritional deficiencies."
      panels={["CBC", "BLOOD", "IRON_VITAMIN"]}
      renderExtra={(r) => <RangePositionChart rows={r.measurements} />}
    />
  );
}
