"""Population Stability Index and two-sample Kolmogorov-Smirnov, in pure NumPy.

Evidently is the usual tool for this, but it is a heavy dependency for what the
project needs. These are the same statistics, computed directly, so they can run
both offline (training reports) and online (the live drift monitor) with no
extra installs and no SciPy.
"""
from __future__ import annotations

import numpy as np

PSI_STABLE = 0.1
PSI_MODERATE = 0.25

KS_STABLE = 0.10
KS_MODERATE = 0.20

_EPS = 1e-6


def psi_from_proportions(ref_prop: np.ndarray, cur_prop: np.ndarray) -> float:
    """PSI between two aligned proportion vectors."""
    ref = np.clip(np.asarray(ref_prop, dtype=float), _EPS, None)
    cur = np.clip(np.asarray(cur_prop, dtype=float), _EPS, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def psi_numeric(reference, current, bins: int = 10) -> float:
    """PSI for a numeric column using decile edges learned from ``reference``."""
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    reference = reference[~np.isnan(reference)]
    current = current[~np.isnan(current)]
    if len(reference) == 0 or len(current) == 0:
        return 0.0
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(reference, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    return psi_from_proportions(ref_counts / ref_counts.sum(), cur_counts / cur_counts.sum())


def psi_categorical(reference, current) -> float:
    """PSI between the category distributions of two columns."""
    ref = _value_counts(reference)
    cur = _value_counts(current)
    idx = ref.index.union(cur.index)
    return psi_from_proportions(
        ref.reindex(idx, fill_value=0).to_numpy(),
        cur.reindex(idx, fill_value=0).to_numpy(),
    )


def _value_counts(values):
    import pandas as pd

    return pd.Series(values).astype("string").fillna("missing").value_counts(normalize=True)


def ks_two_sample(a, b) -> tuple[float, float]:
    """Two-sample KS statistic (no p-value needed for an operational alarm)."""
    a = np.sort(np.asarray(a, dtype=float))
    b = np.sort(np.asarray(b, dtype=float))
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return 0.0, 0
    grid = np.concatenate([a, b])
    cdf_a = np.searchsorted(a, grid, side="right") / len(a)
    cdf_b = np.searchsorted(b, grid, side="right") / len(b)
    return float(np.max(np.abs(cdf_a - cdf_b))), int(min(len(a), len(b)))


def verdict_psi(psi: float) -> str:
    if psi < PSI_STABLE:
        return "stable"
    if psi < PSI_MODERATE:
        return "moderate shift"
    return "significant shift"


def verdict_ks(ks: float) -> str:
    if ks < KS_STABLE:
        return "stable"
    if ks < KS_MODERATE:
        return "moderate shift"
    return "significant shift"
