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
  intervals?: {
    method: string;
    n_boot: number;
    roc_auc?: { ci_low: number; ci_high: number };
    pr_auc?: { ci_low: number; ci_high: number };
    brier?: { ci_low: number; ci_high: number };
  };
}

export interface FairnessGroup {
  group: string;
  n: number;
  selection_rate: number | null;
  selection_rate_ci?: [number, number] | null;
  tpr: number | null;
  tpr_ci?: [number, number] | null;
  fpr: number | null;
  fpr_ci?: [number, number] | null;
  precision: number | null;
  mean_pd: number | null;
  low_sample: boolean;
}

export interface FairnessAttribute {
  label: string;
  groups: FairnessGroup[];
  summary: {
    selection_rate_ratio: number | null;
    disparate_impact_ratio?: number | null;
    disparate_impact_ratio_ci?: [number, number] | null;
    disparate_impact_pass?: boolean;
    demographic_parity_difference: number | null;
    equal_opportunity_difference: number | null;
    equalized_odds_difference?: number | null;
    equalized_odds_difference_ci?: [number, number] | null;
    tpr_range?: number | null;
    fpr_range?: number | null;
    n_groups_considered: number;
    n_groups_total?: number;
  };
}

export interface FairnessGuardrailBlock {
  disparate_impact_floor: number;
  passed: boolean;
  n_breaches: number;
  breaches: {
    attribute: string;
    label: string;
    disparate_impact_ratio: number;
    floor: number;
    lowest_group: string;
    lowest_selection_rate: number | null;
  }[];
  mitigation_attribute?: string;
}

export interface FairnessReport {
  model_version: string;
  min_group_size: number;
  disparate_impact_floor?: number;
  overall?: {
    n: number;
    selection_rate: number;
    tpr: number;
    fpr: number;
    default_rate: number;
  };
  definitions: Record<string, string>;
  attributes: Record<string, FairnessAttribute>;
  guardrail?: FairnessGuardrailBlock;
  unavailable_attributes: string[];
  disclaimer: string;
}

// --- Advanced platform types -------------------------------------------------
export type StepStatus = "pending" | "running" | "done" | "error" | "cached";

export interface JobEvent {
  step: string;
  status: string;
  label?: string;
  at?: string;
  band?: Band;
  probability_of_default?: number;
  routes?: number;
  error?: string;
}

export interface JobResponse {
  job_id: string;
  kind: string;
  status: string;
  created_at: string;
  updated_at: string;
  backend?: string | null;
  events: JobEvent[];
  result?: ApplicationResult | null;
  error?: string | null;
}

export interface RouteMetrics {
  amount?: number;
  reduction?: number;
  intent?: string;
  new_pd: number;
  new_band: Band;
  confidence: string;
}

export interface BlueprintRoute {
  id: string;
  kind: string;
  actionability?: string;
  guarantees_outcome?: boolean;
  headline: string;
  detail: string;
  metrics: RouteMetrics;
}

export interface DualTargetOption {
  change: string;
  new_band: Band;
  confidence: string;
  within_control: boolean;
}

export interface Blueprint {
  status: string;
  current_band: Band;
  current_pd: number;
  target_band: Band;
  pd_to_approve_threshold?: number;
  routes: BlueprintRoute[];
  route_summary?: {
    n_routes: number;
    n_actionable: number;
    has_actionable_route: boolean;
  };
  actionability_legend?: Record<string, string>;
  immutable_fields?: { field: string; reason: string }[];
  dual_target: { headline: string; options: DualTargetOption[]; note: string } | null;
  summary: string;
  no_route_reason?: string | null;
  disclaimer?: string;
  counterfactuals?: CounterfactualScenario[];
}

export interface ReasonCode {
  code: string;
  title: string;
  factor: string;
  detail: string;
  direction: "increases" | "reduces";
  reason: string;
}

export interface Narrative {
  headline: string;
  tone: string;
  reason_codes: ReasonCode[];
  positive_factors: string[];
  next_steps: string[];
  encouragement: string;
  protected_factors_excluded: string[];
  notice: string;
  guardrail: {
    provider: string;
    checked: boolean;
    violations: string[];
    passed: boolean;
    protected_excluded: string[];
    max_reasons: number;
  };
}

export interface ScoringBlock {
  model_version: string;
  probability_of_default: number;
  thresholds: Thresholds;
  band: Band;
  band_label: BandLabel;
  final_band: Band;
  final_band_label: BandLabel;
  mitigation: {
    requested: boolean;
    applied: boolean;
    changed_band: boolean;
    attribute: string | null;
    method: string;
  };
  group: string;
  context: MacroContext;
  macro_tilt: Record<string, unknown>;
}

export interface ApplicationResult {
  scoring: ScoringBlock;
  reasons: ReasonItem[];
  narrative: Narrative;
  blueprint: Blueprint;
  cache?: Record<string, unknown>;
}

export interface MacroContext {
  region: string;
  region_label: string;
  as_of: string;
  month: string;
  prime_rate: number;
  unemployment_rate: number;
  cpi_yoy: number;
  delinquency_rate: number;
  cycle_tilt: number;
  source: string;
  note: string;
}

export interface GuardrailResult {
  disparate_impact_floor: number;
  passed: boolean;
  n_breaches: number;
  breaches: {
    attribute: string;
    label: string;
    lowest_group: string;
    lowest_group_n?: number;
    lowest_selection_rate: number | null;
    disparate_impact_ratio_ci?: [number, number] | null;
  }[];
}

export interface SimulationResult {
  n: number;
  evaluation_set?: string;
  evaluation_role?: string;
  approve_max_pd: number;
  decline_min_pd: number;
  apply_fairness: boolean;
  approval_rate: number;
  band_counts: Record<string, number>;
  band_shares: Record<string, number>;
  expected_cost_per_loan: number;
  realized_cost_per_loan: number;
  profit_per_loan: number;
  profit_total: number;
  disparate_impact_ratio: number | null;
  equalized_odds_difference: number | null;
  uncertainty?: {
    n_boot: number;
    method: string;
    disparate_impact_ratio_ci: [number, number] | null;
    equalized_odds_difference_ci: [number, number] | null;
  } | null;
  fairness_table: {
    group: string;
    n: number;
    selection_rate: number;
    selection_rate_ci?: [number, number] | null;
    tpr: number | null;
    tpr_ci?: [number, number] | null;
    fpr: number | null;
    fpr_ci?: [number, number] | null;
    mean_exposure: number;
    low_sample: boolean;
  }[];
  group_attribute: string;
  guardrail: GuardrailResult;
  mitigation_note?: string | null;
  mitigation_cost?: {
    cost_per_loan_delta: number;
    approval_rate_delta: number;
    profit_per_loan_delta: number;
    disparate_impact_ratio_base: number | null;
    disparate_impact_ratio_mitigated: number | null;
    equalized_odds_difference_base: number | null;
    equalized_odds_difference_mitigated: number | null;
    breaches_base: number;
    breaches_mitigated: number;
    note: string;
  } | null;
  sweep?: {
    points: {
      approve_max_pd: number;
      approval_rate: number;
      expected_cost_per_loan: number;
      profit_per_loan: number;
      disparate_impact_ratio: number | null;
      guardrail_passed: boolean;
    }[];
  };
  context?: MacroContext;
  intercept?: { save_policy_allowed: boolean; reason: string; floor: number };
}

export interface AbCompareResult {
  alpha: SimulationResult;
  beta: SimulationResult;
  delta: Record<string, number | null>;
  labels?: { alpha: string; beta: string };
}

export interface MitigationAttribute {
  id: string;
  label: string;
  impact?: {
    disparate_impact_ratio_base?: number;
  } & Record<string, number | string | null>;
}

export interface MitigationInfo {
  options: { id: string; label: string; attribute?: string; description?: string }[];
  attributes: MitigationAttribute[];
  default_attribute: string;
  variant_summaries: Record<
    string,
    {
      label: string;
      summary?: Record<string, unknown>;
      impact?: Record<string, number | string | null>;
    }
  >;
  disparate_impact_floor: number;
}

export interface RegistryModel {
  version: string;
  label: string;
  role: string;
  artifact: string;
  metadata: string;
  trained_at?: string;
  metrics?: Record<string, number | null>;
  thresholds?: Thresholds;
  fairness?: {
    guardrail_passed?: boolean;
    n_breaches?: number;
    disparate_impact_ratio?: number | null;
    equalized_odds_difference?: number | null;
    attribute?: string;
  };
  mitigation?: Record<string, unknown>;
}

export interface ModelsResponse {
  registry: {
    default: string;
    fair: string;
    group_attribute: string;
    disparate_impact_floor: number;
    mitigation_attributes: MitigationAttribute[];
    n_models: number;
    generated_at?: string;
  };
  models: RegistryModel[];
  lineage: {
    version: string;
    role: string;
    parent?: string;
    trained_at?: string;
    note?: string;
  }[];
  mitigation_attributes: MitigationAttribute[];
  variant_summaries: Record<
    string,
    {
      label: string;
      summary?: Record<string, unknown>;
      impact?: Record<string, number | string | null>;
    }
  >;
}

export interface DriftResult {
  available: boolean;
  enough_data?: boolean;
  n?: number;
  window?: string;
  simulated?: boolean;
  alert: boolean;
  severity?: string;
  max_psi?: number;
  max_ks?: number | null;
  features?: Record<
    string,
    { type: string; psi: number; psi_verdict?: string; ks?: number | null; ks_verdict?: string }
  >;
  alerts?: { feature: string; statistic: string; value: number }[];
  adversarial_validation?: { proxy_auc: number; note: string };
  thresholds?: Record<string, number>;
  note?: string;
  storage_enabled?: boolean;
}

export interface BiasInjectResult {
  injection: { group: string; factor: number; note: string };
  clean: { disparate_impact_ratio: number | null; guardrail_passed: boolean };
  biased: {
    disparate_impact_ratio: number | null;
    equalized_odds_difference: number | null;
    guardrail: GuardrailResult;
    fairness_table: SimulationResult["fairness_table"];
  };
  recovered: {
    disparate_impact_ratio: number | null;
    equalized_odds_difference: number | null;
    guardrail: GuardrailResult;
    fairness_table: SimulationResult["fairness_table"];
  };
}
