"""Fairness audit across the groups the data actually contains.

Definitions used here (stated explicitly, because fairness metrics are easy to
misread):

* A **positive prediction** is "approved" (the decision band `approve`).
* The **favourable outcome** is "repaid" (``loan_status == 0``).
* ``selection_rate``  = share of a group that is approved.
* ``tpr``             = P(approved | repaid)   -- approval rate among the creditworthy.
* ``fpr``             = P(approved | defaulted).
* ``precision``       = P(repaid | approved).

These are statistical disparities between groups. They do **not** establish legal
compliance or non-compliance. Groups smaller than ``min_group_size`` are shown
but excluded from the disparity ratios so a handful of rows cannot invent a gap.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config
from app.services.decision import APPROVE

AUDIT_ATTRIBUTES = [
    "person_home_ownership",
    "age_band",
    "income_band",
    "loan_intent",
    "cb_person_default_on_file",
]

ATTRIBUTE_LABELS = {
    "person_home_ownership": "Home ownership",
    "age_band": "Age band",
    "income_band": "Income band",
    "loan_intent": "Loan purpose",
    "cb_person_default_on_file": "Prior default on file",
}

DISCLAIMER = (
    "This dashboard reports statistical disparities between groups. It does not "
    "establish legal compliance or non-compliance, and it is not a legal opinion."
)

# Attribute used to demonstrate the equalized-odds mitigation. It must be one we
# can derive online from applicant input (see app.core.features.age_band).
MITIGATION_ATTRIBUTE = config.MITIGATION_ATTRIBUTE


def _range(values: list[float]) -> float | None:
    return float(max(values) - min(values)) if len(values) >= 2 else None


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score interval (95%) for a proportion. Robust for small n."""
    if n <= 0:
        return None
    phat = k / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    return [max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom)]


def bootstrap_disparity(
    group_codes: np.ndarray,
    approved: np.ndarray,
    repaid: np.ndarray,
    defaulted: np.ndarray,
    n_groups: int,
    n_boot: int = 400,
    seed: int = 42,
) -> dict:
    """Percentile bootstrap CIs for the disparate-impact ratio and EO gap.

    Resamples applicants (not groups) with replacement, recomputes the ratio on
    each draw, and reports the 2.5th/97.5th percentiles. Group codes below zero
    are excluded, matching the ``min_group_size`` filter in the point estimate.
    """
    n = len(group_codes)
    keep = group_codes >= 0
    if n == 0 or not keep.any() or n_groups < 2:
        return {"n_boot": 0, "disparate_impact_ratio_ci": None, "equalized_odds_difference_ci": None}

    rng = np.random.default_rng(seed)
    appr_rep = (approved.astype(float) * repaid.astype(float))
    appr_defd = (approved.astype(float) * defaulted.astype(float))
    di_draws: list[float] = []
    eo_draws: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        g = group_codes[idx]
        m = g >= 0
        if not m.any():
            continue
        gc = g[m]
        counts = np.bincount(gc, minlength=n_groups).astype(float)
        a = np.bincount(gc, weights=approved[idx][m].astype(float), minlength=n_groups)
        rep = np.bincount(gc, weights=repaid[idx][m].astype(float), minlength=n_groups)
        dfd = np.bincount(gc, weights=defaulted[idx][m].astype(float), minlength=n_groups)
        ar = np.bincount(gc, weights=appr_rep[idx][m], minlength=n_groups)
        ad = np.bincount(gc, weights=appr_defd[idx][m], minlength=n_groups)
        with np.errstate(invalid="ignore", divide="ignore"):
            sr = np.where(counts > 0, a / np.maximum(counts, 1.0), np.nan)
            tpr = np.where(rep > 0, ar / np.maximum(rep, 1.0), np.nan)
            fpr = np.where(dfd > 0, ad / np.maximum(dfd, 1.0), np.nan)
        sr_ok = sr[np.isfinite(sr)]
        if len(sr_ok) >= 2 and sr_ok.max() > 0:
            di_draws.append(float(sr_ok.min() / sr_ok.max()))
        tpr_ok = tpr[np.isfinite(tpr)]
        fpr_ok = fpr[np.isfinite(fpr)]
        if len(tpr_ok) >= 2 or len(fpr_ok) >= 2:
            eo = max(
                float(tpr_ok.max() - tpr_ok.min()) if len(tpr_ok) >= 2 else 0.0,
                float(fpr_ok.max() - fpr_ok.min()) if len(fpr_ok) >= 2 else 0.0,
            )
            eo_draws.append(eo)

    def _pct(draws: list[float]) -> list[float] | None:
        if len(draws) < 20:
            return None
        return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]

    return {
        "n_boot": n_boot,
        "method": "percentile bootstrap (resampling applicants with replacement)",
        "seed": seed,
        "disparate_impact_ratio_ci": _pct(di_draws),
        "equalized_odds_difference_ci": _pct(eo_draws),
    }


def _group_metrics(mask: np.ndarray, y: np.ndarray, approved: np.ndarray, p: np.ndarray) -> dict:
    n = int(mask.sum())
    if n == 0:
        return {
            "n": 0,
            "selection_rate": None,
            "selection_rate_ci": None,
            "tpr": None,
            "tpr_ci": None,
            "fpr": None,
            "fpr_ci": None,
            "precision": None,
            "mean_pd": None,
        }
    approved_g = approved[mask]
    y_g = y[mask]
    p_g = p[mask]

    selection_rate = float(approved_g.mean())
    repaid = y_g == 0
    defaulted = y_g == 1

    tpr = float(approved_g[repaid].mean()) if repaid.any() else None
    fpr = float(approved_g[defaulted].mean()) if defaulted.any() else None
    precision = float((y_g[approved_g] == 0).mean()) if approved_g.any() else None

    return {
        "n": n,
        "selection_rate": selection_rate,
        "selection_rate_ci": _wilson(int(approved_g.sum()), n),
        "tpr": tpr,
        "tpr_ci": _wilson(int(approved_g[repaid].sum()), int(repaid.sum())) if repaid.any() else None,
        "fpr": fpr,
        "fpr_ci": _wilson(int(approved_g[defaulted].sum()), int(defaulted.sum())) if defaulted.any() else None,
        "precision": precision,
        "mean_pd": float(p_g.mean()),
        "n_repaid": int(repaid.sum()),
        "n_defaulted": int(defaulted.sum()),
    }


def _operating_point(y: np.ndarray, approved: np.ndarray) -> tuple[float, float]:
    """Pooled (FPR, TPR) for a boolean approval vector."""
    repaid = y == 0
    defaulted = y == 1
    tpr = float(approved[repaid].mean()) if repaid.any() else 0.0
    fpr = float(approved[defaulted].mean()) if defaulted.any() else 0.0
    return fpr, tpr


def compute_fairness(
    df: pd.DataFrame,
    y_true: np.ndarray,
    p: np.ndarray,
    decisions: np.ndarray,
    model_version: str,
    min_group_size: int = 30,
    disparate_impact_floor: float | None = None,
    n_boot: int = 400,
    bootstrap_seed: int = 42,
) -> dict:
    """Build the fairness report consumed by ``GET /model`` and the dashboard."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    approved = np.asarray(decisions) == APPROVE
    floor = (
        float(disparate_impact_floor)
        if disparate_impact_floor is not None
        else float(config.DISPARATE_IMPACT_FLOOR)
    )

    # Pooled (all-applicant) operating point: the reference the mitigation aims at.
    pooled_fpr, pooled_tpr = _operating_point(y, approved)

    out: dict = {
        "model_version": model_version,
        "min_group_size": min_group_size,
        "disparate_impact_floor": floor,
        "definitions": {
            "positive_prediction": "approved (decision band = approve)",
            "favourable_outcome": "repaid (loan_status == 0)",
            "selection_rate": "share of group approved",
            "tpr": "P(approved | repaid)",
            "fpr": "P(approved | defaulted)",
            "precision": "P(repaid | approved)",
            "disparate_impact_ratio": (
                "min/max selection rate across adequately-sized groups; the "
                f"'four-fifths rule' flags a ratio below {floor:.2f}"
            ),
            "equalized_odds_difference": (
                "max(TPR gap, FPR gap) across adequately-sized groups"
            ),
        },
        "overall": {
            "n": int(len(y)),
            "selection_rate": float(approved.mean()),
            "selection_rate_ci": _wilson(int(approved.sum()), int(len(y))),
            "tpr": pooled_tpr,
            "fpr": pooled_fpr,
            "default_rate": float(y.mean()),
        },
        "uncertainty": {
            "method": "Wilson score interval for rates; percentile bootstrap for disparity ratios",
            "n_boot": n_boot,
            "bootstrap_seed": bootstrap_seed,
            "note": (
                "Intervals are sampling uncertainty only. They do not cover "
                "dataset, group-definition or metric-choice uncertainty."
            ),
        },
        "attributes": {},
        "unavailable_attributes": list(config.UNAVAILABLE_AUDIT_ATTRIBUTES),
        "disclaimer": DISCLAIMER,
    }

    repaid_all = (y == 0).astype(int)
    defaulted_all = (y == 1).astype(int)
    breaches: list[dict] = []
    for attr in AUDIT_ATTRIBUTES:
        if attr not in df.columns:
            continue
        values = df[attr].astype("string").fillna("unknown")
        labels = sorted(values.dropna().unique().tolist())
        code_of = {label: k for k, label in enumerate(labels)}
        raw_codes = np.array([code_of[v] for v in values.tolist()], dtype=int)

        groups = []
        for value in labels:
            mask = (values == value).to_numpy()
            metrics = _group_metrics(mask, y, approved, p)
            metrics["group"] = str(value)
            metrics["low_sample"] = metrics["n"] < min_group_size
            groups.append(metrics)

        # Disparity summary over adequately-sized groups only.
        big = [g for g in groups if g["n"] >= min_group_size]
        big_labels = {g["group"] for g in big}
        codes_for_boot = np.array(
            [c if labels[c] in big_labels else -1 for c in raw_codes], dtype=int
        )
        attr_seed = bootstrap_seed + (sum(ord(c) for c in attr) % 997)
        boot = bootstrap_disparity(
            group_codes=codes_for_boot,
            approved=approved.astype(int),
            repaid=repaid_all,
            defaulted=defaulted_all,
            n_groups=len(labels),
            n_boot=n_boot,
            seed=attr_seed,
        )
        selection_rates = [g["selection_rate"] for g in big if g["selection_rate"] is not None]
        tprs = [g["tpr"] for g in big if g["tpr"] is not None]
        fprs = [g["fpr"] for g in big if g["fpr"] is not None]
        di_ratio = (
            float(min(selection_rates) / max(selection_rates))
            if len(selection_rates) >= 2 and max(selection_rates) > 0
            else None
        )
        eo_difference = (
            max(_range(tprs) or 0.0, _range(fprs) or 0.0) if len(tprs) >= 2 else None
        )
        summary = {
            "selection_rate_ratio": di_ratio,
            "disparate_impact_ratio": di_ratio,
            "disparate_impact_ratio_ci": boot.get("disparate_impact_ratio_ci"),
            "disparate_impact_pass": (di_ratio is None or di_ratio >= floor),
            "demographic_parity_difference": (
                float(max(selection_rates) - min(selection_rates))
                if len(selection_rates) >= 2
                else None
            ),
            "equal_opportunity_difference": (
                float(max(tprs) - min(tprs)) if len(tprs) >= 2 else None
            ),
            "equalized_odds_difference": eo_difference,
            "equalized_odds_difference_ci": boot.get("equalized_odds_difference_ci"),
            "tpr_range": _range(tprs),
            "fpr_range": _range(fprs),
            "n_groups_considered": len(big),
            "n_groups_total": len(groups),
        }

        out["attributes"][attr] = {
            "label": ATTRIBUTE_LABELS.get(attr, attr),
            "groups": groups,
            "summary": summary,
        }

        if di_ratio is not None and di_ratio < floor:
            worst = min(
                big,
                key=lambda g: (
                    g["selection_rate"] if g["selection_rate"] is not None else 1.0
                ),
            )
            breaches.append(
                {
                    "attribute": attr,
                    "label": ATTRIBUTE_LABELS.get(attr, attr),
                    "disparate_impact_ratio": di_ratio,
                    "disparate_impact_ratio_ci": boot.get("disparate_impact_ratio_ci"),
                    "floor": floor,
                    "lowest_group": worst["group"],
                    "lowest_group_n": worst["n"],
                    "lowest_selection_rate": worst["selection_rate"],
                    "lowest_selection_rate_ci": worst["selection_rate_ci"],
                }
            )

    out["guardrail"] = {
        "disparate_impact_floor": floor,
        "passed": len(breaches) == 0,
        "n_breaches": len(breaches),
        "breaches": breaches,
        "breaching_attributes": [b["attribute"] for b in breaches],
        "mitigation_attribute": MITIGATION_ATTRIBUTE,
        "interpretation": (
            "A ratio at or above the floor for one attribute is not evidence that "
            "the system is fair overall, and it is not a legal-compliance finding. "
            "Every remaining breach is listed here and must be read together with "
            "its confidence interval and its group sizes."
        ),
    }
    return out
