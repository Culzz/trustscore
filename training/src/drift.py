"""Lightweight data-drift report (Population Stability Index).

The spec suggests Evidently offline. Evidently is a heavy dependency for what we
need here, so this module computes PSI directly -- the same statistic Evidently
reports -- with no extra installs.

Important: the public dataset has no live outcome stream, so this compares the
training split (reference) against the held-out test split (current). It is an
**offline, simulated** drift check, and the report says so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

PSI_STABLE = 0.1
PSI_MODERATE = 0.25


def _psi_from_counts(ref_prop: np.ndarray, cur_prop: np.ndarray) -> float:
    eps = 1e-6
    ref_prop = np.clip(ref_prop, eps, None)
    cur_prop = np.clip(cur_prop, eps, None)
    return float(np.sum((cur_prop - ref_prop) * np.log(cur_prop / ref_prop)))


def _psi_numeric(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    reference = reference.dropna().to_numpy(dtype=float)
    current = current.dropna().to_numpy(dtype=float)
    if len(reference) == 0 or len(current) == 0:
        return 0.0
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(reference, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    return _psi_from_counts(ref_counts / ref_counts.sum(), cur_counts / cur_counts.sum())


def _psi_categorical(reference: pd.Series, current: pd.Series) -> float:
    ref = reference.astype("string").fillna("missing").value_counts(normalize=True)
    cur = current.astype("string").fillna("missing").value_counts(normalize=True)
    idx = ref.index.union(cur.index)
    return _psi_from_counts(
        ref.reindex(idx, fill_value=0).to_numpy(),
        cur.reindex(idx, fill_value=0).to_numpy(),
    )


def _verdict(psi: float) -> str:
    if psi < PSI_STABLE:
        return "stable"
    if psi < PSI_MODERATE:
        return "moderate shift"
    return "significant shift"


def build_drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    model_version: str,
) -> dict:
    features = {}
    for col in config.NUMERIC_FEATURES:
        if col in reference.columns and col in current.columns:
            psi = _psi_numeric(reference[col], current[col])
            features[col] = {"type": "numeric", "psi": psi, "verdict": _verdict(psi)}
    for col in config.CATEGORICAL_FEATURES:
        if col in reference.columns and col in current.columns:
            psi = _psi_categorical(reference[col], current[col])
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
