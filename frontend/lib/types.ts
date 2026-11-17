export type Range = { low: number | null; high: number | null; source?: string; reference?: string; note?: string | null; text?: string };

export type Measurement = {
  key: string;
  test: string;
  panel?: string;
  value: number | null;
  unit: string;
  unit_display?: string;
  original_value?: string | null;
  original_unit?: string | null;
  reference_range?: Range | null;
  lab_flag?: string | null;
  extraction_confidence?: number;
  status?: "ok" | "uncertain" | "invalid" | "missing";
  issues?: string[];
  source_line?: string | null;
  origin?: string;
  lab_calculated?: boolean;
  confirmed_by_user?: boolean;
  assessment?: { interpretation: string; range_used: Range | null; rule: string };
  category?: { label: string; scheme: string };
  ef_band?: string;
};

export type Derived = {
  key?: string;
  name: string;
  value: number | null;
  unit: string;
  formula: string;
  note?: string | null;
  applicable?: boolean;
  label?: string;
  category?: { label: string | null; scheme: string };
};

export type Pattern = { pattern: string; evidence: string[]; explanation: string; rule: string };

export type ModuleResult = {
  module: string;
  method: string;
  measurements: Measurement[];
  derived?: Derived[];
  patterns?: Pattern[];
  missing?: { key: string; test: string }[];
  warnings?: string[];
  notes?: string[];
  disclaimer?: string;
  missing_haematinics_note?: string | null;
  research_model?: ResearchModel;
  findings?: EchoFindings;
  chart?: { name: string; value: number; low: number | null; high: number | null }[];
};

export type ResearchModel = {
  available: boolean;
  reason?: string;
  model?: string;
  model_version?: string;
  score?: number;
  score_meaning?: string;
  imputed?: string[];
  explanation?: { feature: string; value: number; shap: number; direction: string }[];
  explanation_note?: string;
  test_performance?: Record<string, number>;
  limitations?: string[];
};

export type EchoFindings = {
  valve_findings?: Record<string, string[]>;
  wall_motion?: string[];
  diastolic_function?: string[];
  pericardium?: string[];
  lv_function_text?: string[];
  impression?: string[];
  note?: string;
};

export type ReportMeta = {
  id: string;
  created_at: string;
  report_type: string;
  panels: string[];
  status: string;
  report_date: string | null;
  n_measurements: number;
  n_uncertain: number;
  n_abnormal: number;
  file_kind: string;
  file_stored: boolean;
  error?: string | null;
};

export type ReportFull = ReportMeta & {
  extraction: {
    classification: { report_type: string; panels: string[]; scores: Record<string, number>; evidence: Record<string, string[]>; confidence: number };
    measurements: Measurement[];
    validation: { n_total: number; n_ok: number; n_uncertain: number; n_invalid: number };
    report_date: { date: string; ambiguous_day_month: boolean; original: string; label: string } | null;
    demographics_suggested: { age: number | null; sex: "male" | "female" | null };
    echo_findings: EchoFindings | null;
    ecg: EcgResult | null;
    ocr: { method: string; pages: number; mean_confidence: number; preprocessing: string[]; quality_warnings: string[]; rotation_applied: number; skew_corrected_deg: number; n_lines: number };
  } | null;
  analysis: Record<string, ModuleResult | EcgResult | Record<string, unknown>> | null;
  audit: { at: string; action: string; detail: unknown }[];
};

export type EcgResult = {
  fs?: number;
  duration_s?: number;
  heart_rate_bpm: number | null;
  signal_quality: { usable: boolean; score: number; label: string; checks: Record<string, boolean>; kSQI: number; pSQI: number; basSQI: number; n_beats: number } | null;
  waveform_preview?: { points: { t: number; v: number }[]; r_peaks_s: number[] };
  rr_intervals_s?: number[];
  classification: {
    available: boolean;
    reason?: string;
    model?: string;
    model_version?: string;
    n_beats?: number;
    counts?: Record<string, number>;
    fractions?: Record<string, number>;
    mean_probabilities?: Record<string, number>;
    beats?: { index: number; time_s: number; predicted: string; probability: number; probabilities: Record<string, number> }[];
    class_descriptions?: Record<string, string>;
    test_recall_by_class?: Record<string, number>;
    test_precision_by_class?: Record<string, number>;
    explanation?: { beat: number; predicted: string; top_features: { feature: string; value: number; shap: number }[] }[] | null;
    caveat?: string;
  } | null;
  digitization?: { calibrated: boolean; fs: number | null; unit: string; rows_detected: number; row_used: number; trace_coverage: number; grid: { detected: boolean; small_box_px: number | null; confidence: number }; preview: { t: number; v: number }[]; warnings: string[]; assumptions: Record<string, number> | null };
  warnings?: string[];
  input?: Record<string, unknown>;
};
