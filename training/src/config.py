"""Central configuration for the TrustScore training pipeline.

Keeping paths, the model version and every tunable policy number in one place
means the training run and the API contract never drift apart silently.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# training/src/config.py -> repo root is parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Raw Kaggle "Credit Risk Dataset" (laotse). Never committed (see .gitignore).
RAW_CSV = RAW_DIR / "credit_risk_dataset.csv"

# Where the artifacts that the API bundles are written.
API_ARTIFACTS_DIR = REPO_ROOT / "api" / "artifacts"
MODEL_ARTIFACT = API_ARTIFACTS_DIR / "model.joblib"
METADATA_JSON = API_ARTIFACTS_DIR / "metadata.json"

# Human-readable reports (committed).
REPORTS_DIR = REPO_ROOT / "reports"
FAIRNESS_JSON = REPORTS_DIR / "fairness_v1.json"
DRIFT_JSON = REPORTS_DIR / "drift_v1.json"
METRICS_JSON = REPORTS_DIR / "metrics_v1.json"
MODEL_CARD_MD = REPORTS_DIR / "MODEL_CARD.md"
MODEL_CARD_JSON = REPORTS_DIR / "model_card_v1.json"
CALIBRATION_JSON = REPORTS_DIR / "calibration_v1.json"

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 42
MODEL_VERSION = "trustscore-1.0.0"

# ---------------------------------------------------------------------------
# Target + raw schema
# ---------------------------------------------------------------------------
TARGET = "loan_status"  # 1 = default, 0 = repaid

# The feature schema lives in the shared runtime module (app.core.features) and
# is imported here so training and serving can never disagree about it.
from app.core.features import (  # noqa: E402  (import after path setup)
    CATEGORICAL_FEATURES,
    DERIVED_FEATURES,
    NUMERIC_FEATURES,
    RAW_INPUT_COLUMNS,
)

# ---------------------------------------------------------------------------
# Data-quality bounds (documented in the model card)
# ---------------------------------------------------------------------------
AGE_MAX_VALID = 100  # values above this are data-entry errors (e.g. 144)
EMP_LENGTH_MAX_VALID = 60
LOAN_AMNT_MIN = 500
LOAN_AMNT_MAX = 40_000
INCOME_MIN = 1_000

# ---------------------------------------------------------------------------
# Decision policy / cost matrix (business costs, in "cost units").
# The lender view can override these; these are the trained defaults.
# ---------------------------------------------------------------------------
# Expected monetary loss on a defaulted loan (loss given default proxy).
COST_FALSE_APPROVE = 1.0
# Lost margin when we wrongly decline a good applicant.
COST_FALSE_DECLINE = 0.20
# Cost of routing to a human reviewer.
COST_REVIEW = 0.05

# Bands are the *defaults exposed in metadata*; the API recomputes them from the
# cost matrix so they always agree with expected-cost logic.
DEFAULT_APPROVE_MAX_PD = 0.10
DEFAULT_DECLINE_MIN_PD = 0.50

# ---------------------------------------------------------------------------
# Fairness audit
# ---------------------------------------------------------------------------
# age_band and income_band are computed ONLY for the audit; they are never model
# features (so the model does not consume a protected-style grouping).
AGE_BANDS = [
    (18, 25, "18-25"),
    (26, 35, "26-35"),
    (36, 45, "36-45"),
    (46, 55, "46-55"),
    (56, 65, "56-65"),
    (66, 200, "66+"),
]

# income quantile cut points (learned on the training split) used for audit bands
INCOME_BAND_QUANTILES = [0.33, 0.66, 0.90]
INCOME_BAND_LABELS = ["low", "lower-middle", "upper-middle", "high"]

# Attributes the dataset does not contain. Reported explicitly as "not available"
# so the audit never implies coverage it does not have.
UNAVAILABLE_AUDIT_ATTRIBUTES = [
    "gender",
    "race/ethnicity",
    "geography/region",
    "marital status",
    "disability status",
]

# ---------------------------------------------------------------------------
# Counterfactual search
# ---------------------------------------------------------------------------
# changeable_by_applicant: the applicant can act on this before applying.
# potentially_changeable: sometimes within the applicant's control.
# immutable: never suggested (and protected attributes are excluded entirely).
CHANGEABLE_FEATURES = ["loan_amnt"]
POTENTIALLY_CHANGEABLE_FEATURES = ["loan_intent"]
IMMUTABLE_FEATURES = [
    "person_age",
    "person_home_ownership",
    "loan_grade",
    "person_emp_length",
    "cb_person_default_on_file",
    "cb_person_cred_hist_length",
    "person_income",
    "loan_int_rate",
]
# Lenders price the rate and grade; a consumer cannot set them, and we never
# suggest a protected attribute even if it were present in the data.
NEVER_SUGGEST = ["person_age", "gender", "race", "region"]

LOAN_INTENT_OPTIONS = [
    "DEBTCONSOLIDATION",
    "EDUCATION",
    "HOMEIMPROVEMENT",
    "MEDICAL",
    "PERSONAL",
    "VENTURE",
]
