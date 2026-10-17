"""Equalized-odds post-processing (Hardt, Price & Srebro, 2016).

The audit shows the model approves some groups at different rates. This module
implements the standard *post-processing* remedy: leave the model alone and
change only the **decision rule** so that the true-positive rate and the
false-positive rate are (approximately) equal across groups.

How it works
------------
A "positive prediction" is *approved*. For a group ``g`` and a probability
threshold ``t`` (approve when ``pd <= t``):

    TPR(t) = P(approved | repaid)      FPR(t) = P(approved | defaulted)

The pooled model at its base threshold ``t*`` operates at some point
``(FPR*, TPR*)``. For each group we look for the *randomised* pair of thresholds
``(t_strict, t_permissive)`` whose achievable operating point is closest to the
pooled target, then approve with probability ``mix`` at the permissive
threshold. Randomisation is what makes the exact target reachable when no single
threshold hits it.

Randomisation must not flicker for the same applicant, so the coin flip is
**deterministic**: it is derived from a hash of a caller-supplied key (an
applicant fingerprint, or a row index during offline reporting). The same
applicant always gets the same decision.

The module is pure Python + NumPy, so training and serving share one
implementation and one set of numbers. Nothing here establishes legal
compliance; it is a statistical technique with the usual trade-offs.
"""
from __future__ import annotations

import hashlib

import numpy as np

from ..core.features import age_band

METHOD = "equalized_odds"

# Groups with fewer than this many rows fall back to the pooled threshold, so a
# handful of rows cannot drive a randomised rule.
DEFAULT_MIN_GROUP_SIZE = 50
DEFAULT_GRID = 24


# ---------------------------------------------------------------------------
# Deterministic coin flip
# ---------------------------------------------------------------------------
def _u_from_key(key: str) -> float:
    """A stable uniform(0,1) value for a key. Same key -> same value, always."""
    digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) / float(1 << 32)


def _keys_for(n: int, keys) -> list[str]:
    if keys is None:
        return [f"row:{i}" for i in range(n)]
    keys = list(keys)
    if len(keys) != n:
        raise ValueError("keys length must match scores length")
    return [str(k) for k in keys]


def row_key(row: dict) -> str:
    """Fingerprint an applicant for a reproducible mitigated decision.

    Uses only fields the applicant supplied, so the same application always
    receives the same randomised outcome.
    """
    parts = [
        str(row.get("person_age", "")),
        str(row.get("person_income", "")),
        str(row.get("loan_amnt", "")),
        str(row.get("loan_int_rate", "")),
        str(row.get("loan_grade", "")),
        str(row.get("loan_intent", "")),
        str(row.get("person_home_ownership", "")),
    ]
    return "|".join(parts)


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------
def group_labels(
    rows: list[dict], attribute: str = "age_band", income_cutpoints=None
) -> list[str]:
    """Derive the mitigation group for each raw applicant row.

    Only attributes that are derivable from the applicant's own input (or from a
    supplied categorical field) are supported, so mitigation works online.
    """
    if attribute == "age_band":
        return [age_band(r.get("person_age")) for r in rows]
    if attribute == "income_band":
        return [_income_band(r.get("person_income"), income_cutpoints) for r in rows]
    if attribute in (
        "person_home_ownership",
        "loan_intent",
        "loan_grade",
        "cb_person_default_on_file",
    ):
        return [str(r.get(attribute) or "unknown") for r in rows]
    raise ValueError(f"unsupported mitigation attribute: {attribute}")


def _income_band(income, cutpoints) -> str:
    """Recreate the audit income bands from stored quantile cut points."""
    if income is None or cutpoints is None:
        return "unknown"
    try:
        value = float(income)
    except (TypeError, ValueError):
        return "unknown"
    if value != value:
        return "unknown"
    labels = ["low", "lower-middle", "upper-middle", "high"]
    for i, edge in enumerate(cutpoints):
        if value <= float(edge):
            return labels[i]
    return labels[-1]


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------
def _operating_point(y: np.ndarray, p: np.ndarray, threshold: float) -> tuple[float, float]:
    approved = p <= threshold
    repaid = y == 0
    defaulted = y == 1
    tpr = float(approved[repaid].mean()) if repaid.any() else 0.0
    fpr = float(approved[defaulted].mean()) if defaulted.any() else 0.0
    return fpr, tpr


def _closest_segment_point(
    points: list[tuple[float, float, float]], target: tuple[float, float]
) -> tuple[float, float, float, float]:
    """Find the convex combination of two adjacent operating points nearest the target.

    ``points`` is a list of ``(threshold, fpr, tpr)`` sorted by threshold. Returns
    ``(t_strict, t_permissive, mix, distance)`` where ``mix`` is the probability of
    using the permissive (higher) threshold.
    """
    tf, tt = target
    best = (points[0][0], points[0][0], 0.0, float("inf"))
    for a, b in zip(points[:-1], points[1:]):
        t_lo, f_lo, yp_lo = a
        t_hi, f_hi, yp_hi = b
        d = np.array([f_hi - f_lo, yp_hi - yp_lo], dtype=float)
        v = np.array([tf - f_lo, tt - yp_lo], dtype=float)
        denom = float(d @ d)
        if denom <= 1e-12:
            mix = 0.0
        else:
            mix = float(np.clip((v @ d) / denom, 0.0, 1.0))
        point = np.array([f_lo, yp_lo]) + mix * d
        dist = float(np.sum((point - np.array([tf, tt])) ** 2))
        if dist < best[3]:
            best = (float(t_lo), float(t_hi), mix, dist)
    return best


def fit_equalized_odds(
    y: np.ndarray,
    p: np.ndarray,
    groups,
    base_threshold: float,
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
    n_grid: int = DEFAULT_GRID,
    attribute: str = "age_band",
) -> dict:
    """Fit the per-group randomised thresholds. Returns a JSON-serialisable dict."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    groups = np.asarray(groups, dtype=object)

    target_fpr, target_tpr = _operating_point(y, p, float(base_threshold))

    params: dict = {
        "method": METHOD,
        "attribute": attribute,
        "base_threshold": float(base_threshold),
        "target_tpr": float(target_tpr),
        "target_fpr": float(target_fpr),
        "min_group_size": int(min_group_size),
        "groups": {},
    }

    for group in sorted({str(g) for g in groups.tolist()}):
        mask = groups == group
        n = int(mask.sum())
        y_g = y[mask]
        p_g = p[mask]
        if n < min_group_size or len(np.unique(y_g)) < 2:
            params["groups"][group] = {
                "n": n,
                "fallback": True,
                "t_strict": float(base_threshold),
                "t_permissive": float(base_threshold),
                "mix": 0.0,
                "tpr": None,
                "fpr": None,
            }
            continue

        # Candidate thresholds: group score quantiles plus the extremes, so the
        # achievable set spans "approve nobody" to "approve everybody".
        qs = np.quantile(p_g, np.linspace(0.0, 1.0, n_grid))
        grid = sorted({-1.0, 1.0, *[float(q) for q in qs]})
        points = [(t, *_operating_point(y_g, p_g, t)) for t in grid]
        t_strict, t_permissive, mix, _ = _closest_segment_point(points, (target_fpr, target_tpr))

        # Report the group's realised operating point under the *deterministic*
        # midpoint, which is what the UI shows.
        achieved_fpr, achieved_tpr = _operating_point(
            y_g, p_g, t_permissive if mix >= 0.5 else t_strict
        )
        params["groups"][group] = {
            "n": n,
            "fallback": False,
            "t_strict": float(t_strict),
            "t_permissive": float(t_permissive),
            "mix": float(mix),
            "tpr": float(achieved_tpr),
            "fpr": float(achieved_fpr),
        }

    return params


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------
def apply_equalized_odds(p, groups, params: dict, keys=None) -> np.ndarray:
    """Return a boolean ``approved`` array under the fitted rule."""
    p = np.asarray(p, dtype=float)
    groups = np.asarray(groups, dtype=object)
    n = len(p)
    keys = _keys_for(n, keys)

    base = float(params.get("base_threshold", 0.5))
    approved = p <= base
    group_params = params.get("groups", {}) or {}

    for group, cfg in group_params.items():
        mask = groups == group
        if not mask.any():
            continue
        t_strict = float(cfg["t_strict"])
        t_permissive = float(cfg["t_permissive"])
        mix = float(cfg["mix"])
        idx = np.where(mask)[0]
        pg = p[idx]
        if mix <= 0.0:
            approved[idx] = pg <= t_strict
        elif mix >= 1.0:
            approved[idx] = pg <= t_permissive
        else:
            u = np.array([_u_from_key(keys[i]) for i in idx])
            approved[idx] = (pg <= t_strict) | ((pg <= t_permissive) & (u < mix))
    return approved


def apply_to_band(
    base_pd: float,
    base_band: str,
    approved: bool,
    approve: str = "approve",
    refer: str = "refer",
) -> str:
    """Reconcile the mitigated binary decision with the three-band display.

    Mitigation only touches the approve boundary, so a band can move to or from
    ``approve`` but never become ``decline`` here.
    """
    if approved and base_band != approve:
        return approve
    if not approved and base_band == approve:
        return refer
    return base_band


def summarise(params: dict) -> dict:
    """A compact, JSON-friendly summary for the API and the UI."""
    groups = params.get("groups", {}) or {}
    mixes = [g["mix"] for g in groups.values() if not g.get("fallback")]
    shuffled = sum(1 for g in groups.values() if not g.get("fallback") and 0 < g["mix"] < 1)
    return {
        "method": params.get("method", METHOD),
        "attribute": params.get("attribute", "age_band"),
        "base_threshold": params.get("base_threshold"),
        "target_tpr": params.get("target_tpr"),
        "target_fpr": params.get("target_fpr"),
        "n_groups": len(groups),
        "n_randomised_groups": shuffled,
        "mean_mix": float(np.mean(mixes)) if mixes else None,
        "groups": groups,
    }
