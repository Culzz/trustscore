"""Loading and cleaning the raw credit-risk dataset.

The raw file is the Kaggle "Credit Risk Dataset" (laotse). It is small, but it
carries the usual real-world defects: a handful of impossible ages, employment
lengths of 123 years, and a block of missing interest rates. We fix those
explicitly and record what we did, because the model card has to state it and
the API has to reproduce it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config


@dataclass
class CleanReport:
    """A machine-readable record of every cleaning action, for the model card."""

    rows_in: int = 0
    rows_out: int = 0
    duplicate_rows_removed: int = 0
    missing_target_removed: int = 0
    age_out_of_range: int = 0
    emp_length_out_of_range: int = 0
    income_non_positive: int = 0
    loan_amnt_out_of_range: int = 0
    missing_after: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicate_rows_removed": self.duplicate_rows_removed,
            "missing_target_removed": self.missing_target_removed,
            "age_out_of_range": self.age_out_of_range,
            "emp_length_out_of_range": self.emp_length_out_of_range,
            "income_non_positive": self.income_non_positive,
            "loan_amnt_out_of_range": self.loan_amnt_out_of_range,
            "missing_after": self.missing_after,
        }


def load_raw(path: Path | str = config.RAW_CSV) -> pd.DataFrame:
    """Read the raw CSV, raising a clear error when it is missing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {path}. Download the Kaggle "
            "'Credit Risk Dataset' and place the CSV at "
            f"{config.RAW_CSV} (data/ is git-ignored)."
        )
    return pd.read_csv(path)


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, CleanReport]:
    """Return a cleaned copy of the frame plus a report of what changed.

    Deliberately conservative: we drop exact duplicates and invalid values, but
    we keep missing values as NaN so the model's imputer decides what to do with
    them rather than us silently inventing numbers here.
    """
    report = CleanReport(rows_in=len(df))
    df = df.copy()

    # Normalise column names defensively.
    df.columns = [c.strip() for c in df.columns]

    # ------------------------------------------------------------------ target
    before = len(df)
    df = df[df[config.TARGET].notna()]
    df[config.TARGET] = df[config.TARGET].astype(int)
    report.missing_target_removed = before - len(df)

    # ------------------------------------------------------------- duplicates
    before = len(df)
    df = df.drop_duplicates()
    report.duplicate_rows_removed = before - len(df)

    # ------------------------------------------------------------- numeric coercion
    numeric_cols = [
        "person_age",
        "person_income",
        "person_emp_length",
        "loan_amnt",
        "loan_int_rate",
        "cb_person_cred_hist_length",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ------------------------------------------------------------------- ranges
    # Impossible ages (the raw file contains values like 144) become missing.
    mask = df["person_age"] > config.AGE_MAX_VALID
    report.age_out_of_range = int(mask.sum())
    df.loc[mask, "person_age"] = np.nan

    # Employment length cannot exceed a working life.
    mask = df["person_emp_length"] > config.EMP_LENGTH_MAX_VALID
    report.emp_length_out_of_range = int(mask.sum())
    df.loc[mask, "person_emp_length"] = np.nan

    # Income and loan amount must be positive to be meaningful.
    mask = df["person_income"] <= 0
    report.income_non_positive = int(mask.sum())
    df.loc[mask, "person_income"] = np.nan

    mask = (df["loan_amnt"] <= 0) | (df["loan_amnt"] > 1_000_000)
    report.loan_amnt_out_of_range = int(mask.sum())
    df.loc[mask, "loan_amnt"] = np.nan

    # ------------------------------------------------------- round + categoricals
    cat_cols = [
        "person_home_ownership",
        "loan_intent",
        "loan_grade",
        "cb_person_default_on_file",
    ]
    for col in cat_cols:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().str.upper()
            df.loc[df[col].isin(["", "NAN", "NONE"]), col] = pd.NA

    df = df.reset_index(drop=True)
    report.rows_out = len(df)
    report.missing_after = {
        c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()
    }
    return df, report


def load_clean(path: Path | str = config.RAW_CSV) -> tuple[pd.DataFrame, CleanReport]:
    """Convenience: load and clean in one call."""
    return clean(load_raw(path))
