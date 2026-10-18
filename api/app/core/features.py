"""Feature schema, engineering and preprocessing.

This module is the single definition of *what the model consumes*, and it is
imported by both the runtime API and the offline training pipeline, so an
applicant scored through the API is transformed exactly the way the model was
trained.

Two deliberate decisions:

* ``loan_percent_income`` is recomputed from ``loan_amnt / person_income``
  rather than trusted from a caller, so the API can reproduce it from eleven
  form inputs alone.
* :class:`TabularPreprocessor` is self-contained (NumPy + pandas only). The
  production model therefore does **not** need scikit-learn or SciPy at
  runtime, which keeps the serverless bundle small and the cold start short.
  Its output is byte-for-byte the same layout as the classic
  ``ColumnTransformer(SimpleImputer + StandardScaler / OneHotEncoder)``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
# What a caller may supply. Everything the model needs is derived from these.
RAW_INPUT_COLUMNS = [
    "person_age",
    "person_income",
    "person_home_ownership",
    "person_emp_length",
    "loan_intent",
    "loan_grade",
    "loan_amnt",
    "loan_int_rate",
    "cb_person_default_on_file",
    "cb_person_cred_hist_length",
]

CATEGORICAL_FEATURES = [
    "person_home_ownership",
    "loan_intent",
    "loan_grade",
    "cb_person_default_on_file",
]

NUMERIC_FEATURES = [
    "person_age",
    "person_income",
    "person_emp_length",
    "loan_amnt",
    "loan_int_rate",
    "loan_percent_income",
    "cb_person_cred_hist_length",
    "emp_length_missing",
    "int_rate_missing",
]

DERIVED_FEATURES = ["loan_percent_income", "emp_length_missing", "int_rate_missing"]

MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# ---------------------------------------------------------------------------
# Audit / mitigation groupings
# ---------------------------------------------------------------------------
# These are *never* model features. They are derived at inference time so the
# fairness audit and the equalized-odds mitigation can address the same groups
# online and offline.
AGE_BANDS = [
    (18, 25, "18-25"),
    (26, 35, "26-35"),
    (36, 45, "36-45"),
    (46, 55, "46-55"),
    (56, 65, "56-65"),
    (66, 200, "66+"),
]

# The attribute used for post-processing mitigation. Age band is chosen because
# it is derivable from the applicant's own input (so mitigation works online)
# and it is one of the groups where the audit shows the largest disparity.
MITIGATION_ATTRIBUTE = "age_band"

# Row keys for the *deterministic* randomised tie-break in equalized-odds
# post-processing (see services/mitigation.py).
#
# Evaluation protocol (docs/EVALUATION.md):
#   * The auditor console experiments on the **policy tuning set** (the
#     validation split); its rows are keyed with ``TUNING_KEY_PREFIX``.
#   * The model card and the evaluation report quote the **final held-out test
#     set**, keyed with ``FINAL_EVAL_KEY_PREFIX``.
# The shipped portfolio artifact records its own prefix, so the runtime can never
# drift from the offline measurement *of the same set*.
TUNING_KEY_PREFIX = "tuning"
FINAL_EVAL_KEY_PREFIX = "test"
# The shipped portfolio is the tuning set; kept as the historical name.
PORTFOLIO_KEY_PREFIX = TUNING_KEY_PREFIX


def age_band(age) -> str:
    """Map an age to its audit band. Returns ``"unknown"`` for missing values."""
    try:
        value = float(age)
    except (TypeError, ValueError):
        return "unknown"
    if value != value:  # NaN
        return "unknown"
    for low, high, label in AGE_BANDS:
        if low <= value <= high:
            return label
    return "unknown"


CATEGORY_OPTIONS = {
    "person_home_ownership": ["RENT", "OWN", "MORTGAGE", "OTHER"],
    "loan_intent": [
        "DEBTCONSOLIDATION",
        "EDUCATION",
        "HOMEIMPROVEMENT",
        "MEDICAL",
        "PERSONAL",
        "VENTURE",
    ],
    "loan_grade": ["A", "B", "C", "D", "E", "F", "G"],
    "cb_person_default_on_file": ["Y", "N"],
}


# ---------------------------------------------------------------------------
# Engineering
# ---------------------------------------------------------------------------
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns and record missingness *before* imputation.

    "Value was not reported" is itself informative (interest rate is blank for
    the lowest-quality grades in this dataset), so the flags are computed from
    the raw missingness before any imputer runs.
    """
    df = df.copy()

    df["emp_length_missing"] = df["person_emp_length"].isna().astype(int)
    df["int_rate_missing"] = df["loan_int_rate"].isna().astype(int)

    income = df["person_income"].replace(0, np.nan)
    df["loan_percent_income"] = (df["loan_amnt"] / income).clip(lower=0, upper=5)
    return df


def _normalise_categoricals(df: pd.DataFrame, categorical=None) -> pd.DataFrame:
    """Make categorical columns string/NaN friendly."""
    cols = list(categorical) if categorical is not None else CATEGORICAL_FEATURES
    df = df.copy()
    for col in cols:
        s = df[col].astype("object")
        s[s.isna()] = np.nan
        df[col] = s
    return df


def feature_matrix(df: pd.DataFrame, features=None, categorical=None) -> pd.DataFrame:
    """Select and normalise the model input columns in a stable order."""
    cols = list(features) if features is not None else MODEL_FEATURES
    df = _normalise_categoricals(df, categorical)
    return df[cols].copy()


# ---------------------------------------------------------------------------
# Self-contained preprocessor (no scikit-learn at runtime)
# ---------------------------------------------------------------------------
class TabularPreprocessor:
    """Median-impute + standardise numerics, most-frequent-impute + one-hot cats.

    The output column order is::

        NUMERIC_FEATURES..., then for each cat feature (sorted categories)
        "cat_feature_VALUE", ...

    which is exactly what scikit-learn's ``ColumnTransformer`` produces with
    ``verbose_feature_names_out=False``, so the two are interchangeable.
    """

    def __init__(self, numeric=None, categorical=None) -> None:
        # The feature lists are per-instance so training can build a *reduced*
        # preprocessor for the feature-provenance ablation (see train.py).
        self.numeric: list[str] = (
            list(numeric) if numeric is not None else list(NUMERIC_FEATURES)
        )
        self.categorical: list[str] = (
            list(categorical) if categorical is not None else list(CATEGORICAL_FEATURES)
        )
        self.numeric_medians_: dict[str, float] = {}
        self.cat_fill_: dict[str, str] = {}
        self.cat_categories_: dict[str, list[str]] = {}
        self.scaler_mean_: np.ndarray | None = None
        self.scaler_scale_: np.ndarray | None = None
        self.feature_names_out_: list[str] = []

    def _features(self) -> list[str]:
        return self.numeric + self.categorical

    # -- fit ---------------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> "TabularPreprocessor":
        X = feature_matrix(df, self._features(), self.categorical)

        # Numerics: median then mean/std.
        self.numeric_medians_ = {}
        num = np.empty((len(X), len(self.numeric)), dtype=float)
        for j, col in enumerate(self.numeric):
            values = pd.to_numeric(X[col], errors="coerce")
            median = float(values.median())
            if not np.isfinite(median):
                median = 0.0
            self.numeric_medians_[col] = median
            num[:, j] = values.fillna(median).to_numpy(dtype=float)

        self.scaler_mean_ = num.mean(axis=0)
        scale = num.std(axis=0)
        scale[scale == 0] = 1.0
        self.scaler_scale_ = scale

        # Categories: most frequent fill, sorted unique values.
        self.cat_fill_ = {}
        self.cat_categories_ = {}
        for col in self.categorical:
            s = X[col]
            mode = s.mode()
            fill = str(mode.iloc[0]) if len(mode) else "UNKNOWN"
            self.cat_fill_[col] = fill
            categories = sorted({str(v) for v in s.dropna().unique()})
            self.cat_categories_[col] = categories

        self.feature_names_out_ = list(self.numeric) + [
            f"{col}_{value}"
            for col in self.categorical
            for value in self.cat_categories_[col]
        ]
        return self

    # -- transform ---------------------------------------------------------
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if self.scaler_mean_ is None:
            raise RuntimeError("TabularPreprocessor must be fitted before transform")
        X = feature_matrix(df, self._features(), self.categorical)

        num = np.empty((len(X), len(self.numeric)), dtype=float)
        for j, col in enumerate(self.numeric):
            values = pd.to_numeric(X[col], errors="coerce")
            num[:, j] = values.fillna(self.numeric_medians_[col]).to_numpy(dtype=float)
        num = (num - self.scaler_mean_) / self.scaler_scale_

        cat_blocks = []
        for col in self.categorical:
            categories = self.cat_categories_[col]
            index = {value: k for k, value in enumerate(categories)}
            block = np.zeros((len(X), len(categories)), dtype=float)
            for i, value in enumerate(X[col].tolist()):
                if value is None or (isinstance(value, float) and np.isnan(value)):
                    value = self.cat_fill_[col]
                k = index.get(str(value))
                if k is not None:  # unknown categories are all-zero (ignored)
                    block[i, k] = 1.0
            cat_blocks.append(block)

        if cat_blocks:
            return np.hstack([num, *cat_blocks])
        return num

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.fit(df).transform(df)

    @property
    def feature_names_out(self) -> list[str]:
        return list(self.feature_names_out_)
