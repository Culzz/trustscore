"""Training-only feature utilities.

The feature schema, engineering and preprocessing pipeline live in
``app.core.features`` (shared with the runtime API). This module adds the pieces
that only the offline pipeline needs: the split and the audit-only groupings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from app.core.features import (  # re-exported for training code
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TabularPreprocessor,
    engineer_features,
    feature_matrix,
)

from . import config

__all__ = [
    "CATEGORICAL_FEATURES",
    "MODEL_FEATURES",
    "NUMERIC_FEATURES",
    "TabularPreprocessor",
    "engineer_features",
    "feature_matrix",
    "stratified_split",
    "age_band",
    "add_audit_columns",
]


def stratified_split(
    df: pd.DataFrame, seed: int = config.SEED
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (train, validation, test) at 60/20/20, stratified on the target.

    The validation split chooses the decision thresholds; the test split is
    touched once, at the end, so the reported numbers stay honest.
    """
    train, temp = train_test_split(
        df, test_size=0.40, random_state=seed, stratify=df[config.TARGET]
    )
    val, test = train_test_split(
        temp, test_size=0.50, random_state=seed, stratify=temp[config.TARGET]
    )
    return (
        train.reset_index(drop=True),
        val.reset_index(drop=True),
        test.reset_index(drop=True),
    )


# ---------------------------------------------------------------------------
# Audit-only groupings (never model features)
# ---------------------------------------------------------------------------
def age_band(age: float) -> str:
    if pd.isna(age):
        return "unknown"
    for lo, hi, label in config.AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "unknown"


def add_audit_columns(
    df: pd.DataFrame, income_cutpoints: np.ndarray | None = None
) -> tuple[pd.DataFrame, np.ndarray]:
    """Attach the audit groupings. Returns (df, income_cutpoints).

    Income-band edges are learned from the training split and reused everywhere.
    """
    df = df.copy()
    df["age_band"] = df["person_age"].apply(age_band)
    if income_cutpoints is None:
        income_cutpoints = np.quantile(
            df["person_income"].dropna().to_numpy(), config.INCOME_BAND_QUANTILES
        )
    df["income_band"] = pd.cut(
        df["person_income"],
        bins=[-np.inf, *income_cutpoints, np.inf],
        labels=config.INCOME_BAND_LABELS,
    ).astype("string")
    return df, income_cutpoints
