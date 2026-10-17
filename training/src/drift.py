"""Lightweight data-drift report (Population Stability Index) + online reference.

The spec suggests Evidently offline. Evidently is a heavy dependency for what we
need here, so this module computes PSI directly -- the same statistic Evidently
reports -- with no extra installs, using the shared runtime implementation in
``app.services.psi``.

Two jobs live here:

* :func:`build_drift_report` -- the offline report (training split vs test split).
* :func:`build_reference_distributions` -- the *reference* the live drift monitor
  compares fresh traffic against: bin edges, expected proportions and a compact
  per-row numeric sample for KS.

Important: the public dataset has no live outcome stream, so the offline report
compares the training split (reference) with the held-out test split (current).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.psi import (
    PSI_MODERATE,
    PSI_STABLE,
    ks_two_sample,
    psi_categorical,
    psi_numeric,
    verdict_psi,
)

from . import config


def _verdict(psi: float) -> str:
    return verdict_psi(psi)


def build_drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    model_version: str,
) -> dict:
    features = {}
    for col in config.NUMERIC_FEATURES:
        if col in reference.columns and col in current.columns:
            psi = psi_numeric(reference[col], current[col])
            features[col] = {"type": "numeric", "psi": psi, "verdict": _verdict(psi)}
    for col in config.CATEGORICAL_FEATURES:
        if col in reference.columns and col in current.columns:
            psi = psi_categorical(reference[col], current[col])
            features[col] = {"type": "categorical", "psi": psi, "verdict": _verdict(psi)}

    return {
        "model_version": model_version,
        "method": "Population Stability Index (decile bins for numerics)",
        "note": (
            "Offline/simulated: the public dataset has no live outcome stream, so "
            "this compares the training split (reference) with the held-out test "
            "split (current)."
        ),
        "thresholds": {"stable_below": PSI_STABLE, "moderate_below": PSI_MODERATE},
        "features": features,
    }


# ---------------------------------------------------------------------------
# Reference distributions for the live monitor
# ---------------------------------------------------------------------------
_MONITORED_NUMERIC = [
    "person_age",
    "person_income",
    "loan_amnt",
    "loan_int_rate",
    "loan_percent_income",
    "cb_person_cred_hist_length",
]
_MONITORED_CATEGORICAL = [
    "person_home_ownership",
    "loan_intent",
    "loan_grade",
    "cb_person_default_on_file",
]


def build_reference_distributions(reference: pd.DataFrame, bins: int = 10) -> dict:
    """Persist the training distribution so the API can score fresh traffic.

    For each numeric feature we store the decile edges and the expected
    proportion in each bin; for each categorical feature we store the expected
    category proportions. A small per-feature sample (2,000 values, rounded) is
    kept for the KS statistic.
    """
    numeric: dict = {}
    for col in _MONITORED_NUMERIC:
        if col not in reference.columns:
            continue
        values = reference[col].dropna().to_numpy(dtype=float)
        if len(values) == 0:
            continue
        edges = np.unique(np.quantile(values, np.linspace(0, 1, bins + 1)))
        if len(edges) < 3:
            continue
        inner = list(edges[1:-1].astype(float))
        full = np.array([-np.inf, *inner, np.inf])
        counts, _ = np.histogram(values, bins=full)
        prop = (counts / counts.sum()).astype(float).tolist()
        sample = values if len(values) <= 2000 else np.random.default_rng(config.SEED).choice(
            values, size=2000, replace=False
        )
        numeric[col] = {
            "edges": [float(e) for e in inner],
            "expected_proportions": prop,
            "sample": [round(float(v), 4) for v in sample],
            "n": int(len(values)),
        }

    categorical: dict = {}
    for col in _MONITORED_CATEGORICAL:
        if col not in reference.columns:
            continue
        vc = reference[col].astype("string").fillna("missing").value_counts(normalize=True)
        categorical[col] = {
            "expected_proportions": {str(k): float(v) for k, v in vc.items()},
            "n": int(len(reference)),
        }

    return {
        "method": "training-split reference distributions (PSI bins + KS sample)",
        "seed": config.SEED,
        "numeric": numeric,
        "categorical": categorical,
        "thresholds": {"stable_below": PSI_STABLE, "moderate_below": PSI_MODERATE},
    }


__all__ = [
    "build_drift_report",
    "build_reference_distributions",
    "ks_two_sample",
]
