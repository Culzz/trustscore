// Shared types mirroring the FastAPI response models.

export type Band = "approve" | "refer" | "decline";
export type BandLabel = "low" | "medium" | "high";

export interface Applicant {
  person_age: number;
  person_income: number;
  person_home_ownership: "RENT" | "OWN" | "MORTGAGE" | "OTHER";
  person_emp_length: number | null;
  loan_intent:
    | "DEBTCONSOLIDATION"
    | "EDUCATION"
    | "HOMEIMPROVEMENT"
    | "MEDICAL"
    | "PERSONAL"
    | "VENTURE";
  loan_grade: "A" | "B" | "C" | "D" | "E" | "F" | "G";
  loan_amnt: number;
  loan_int_rate: number | null;
  cb_person_default_on_file: "Y" | "N";
  cb_person_cred_hist_length: number;
}

export interface Thresholds {
  approve_max_pd: number;
  decline_min_pd: number;
}

export interface PredictResponse {
  prediction_id: string;
  model_version: string;
  probability_of_default: number;
  band: Band;
  band_label: BandLabel;
  thresholds: Thresholds;
  created_at: string;
  disclaimer: string;
}

export interface ReasonItem {
  factor: string;
  detail: string;
  direction: "increases" | "reduces";
  text: string;
}

export interface ExplainResponse {
  model_version: string;
  probability_of_default: number;
  band: Band;
  reasons: ReasonItem[];
  disclaimer: string;
}

export interface DecisionResponse {
  decision: Band;
  band_label: BandLabel;
  simulated: boolean;
  probability_of_default: number;
  thresholds: Thresholds;
  cost_matrix: Record<string, unknown>;
  expected_cost: number;
  model_version: string;
  disclaimer: string;
}

export interface CounterfactualScenario {
  change_type: string;
  changeability: string;
  feature: string;
  from: number | string;
  to: number | string;
  description: string;
  new_pd: number;
  new_band: Band;
}

export interface CounterfactualResponse {
  model_version: string;
  current_pd: number;
  current_band: Band;
  target_band: Band;
  scenarios: CounterfactualScenario[];
  disclaimer: string;
}

export interface HealthResponse {
  status: string;
  model_version: string | null;
  model_loaded: boolean;
  database_configured: boolean;
  time: string;
}

export interface StatsResponse {
  enabled: boolean;
  total_predictions: number;
  mean_pd: number | null;
  high_risk_share: number | null;
  bands: Record<string, number>;
  window: string;
  note: string | null;
}

// --- GET /model payload -----------------------------------------------------
export interface ModelMetadata {
  version: string;
  trained_at: string;
  disclaimer: string;
  dataset: {
    name: string;
    source: string;
    rows: number;
    rows_in: number;
    target_rate: number;
    split_sizes: { train: number; validation: number; test: number };
    features: string[];
    seed: number;
    clean_report: Record<string, unknown>;
  };
  metrics: Record<string, MetricBlock>;
  calibration: {
    brier: number | null;
    ece: number | null;
    n_bins?: number;
    curve?: { bin_lower: number; bin_upper: number; count: number; mean_predicted: number | null; observed_rate: number | null }[];
  };
  thresholds: {
    approve_max_pd: number;
    decline_min_pd: number;
    cost_matrix: Record<string, unknown>;
    expected_cost_per_loan: number;
    test_realized_cost_per_loan: number;
    test_expected_cost_per_loan: number;
    test_approval_rate: number;
    test_band_counts: Record<string, number>;
  };
  fairness: FairnessReport;
  top_features: { feature: string; mean_abs_contribution: number }[];
  score_distribution?: { bins: { pd: number; count: number; mean_exposure: number }[]; n: number; mean_pd: number };
  policy_simulation?: { bins: { pd: number; count: number; mean_exposure: number }[]; n: number };
  drift?: { features: Record<string, { type: string; psi: number; verdict: string }>; note: string };
  metric_definitions?: Record<string, string>;
  limitations: string[];
}

export interface MetricBlock {
  roc_auc: number;
  pr_auc: number;
  brier: number;
  precision: number;
  recall: number;
  f1: number;
  confusion_matrix: Record<string, number>;
}

export interface FairnessGroup {
  group: string;
  n: number;
  selection_rate: number | null;
  tpr: number | null;
  fpr: number | null;
  precision: number | null;
  mean_pd: number | null;
  low_sample: boolean;
}

export interface FairnessAttribute {
  label: string;
  groups: FairnessGroup[];
  summary: {
    selection_rate_ratio: number | null;
    demographic_parity_difference: number | null;
    equal_opportunity_difference: number | null;
    n_groups_considered: number;
  };
}

export interface FairnessReport {
  model_version: string;
  min_group_size: number;
  definitions: Record<string, string>;
  attributes: Record<string, FairnessAttribute>;
  unavailable_attributes: string[];
  disclaimer: string;
}
