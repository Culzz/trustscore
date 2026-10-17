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


def _group_metrics(mask: np.ndarray, y: np.ndarray, approved: np.ndarray, p: np.ndarray) -> dict:
    n = int(mask.sum())
    if n == 0:
        return {
            "n": 0,
            "selection_rate": None,
            "tpr": None,
            "fpr": None,
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
        "tpr": tpr,
        "fpr": fpr,
        "precision": precision,
        "mean_pd": float(p_g.mean()),
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
            "tpr": pooled_tpr,
            "fpr": pooled_fpr,
            "default_rate": float(y.mean()),
        },
        "attributes": {},
        "unavailable_attributes": list(config.UNAVAILABLE_AUDIT_ATTRIBUTES),
        "disclaimer": DISCLAIMER,
    }

    breaches: list[dict] = []
    for attr in AUDIT_ATTRIBUTES:
        if attr not in df.columns:
            continue
        values = df[attr].astype("string").fillna("unknown")
        groups = []
        for value in sorted(values.dropna().unique().tolist()):
            mask = (values == value).to_numpy()
            metrics = _group_metrics(mask, y, approved, p)
            metrics["group"] = str(value)
            metrics["low_sample"] = metrics["n"] < min_group_size
            groups.append(metrics)

        # Disparity summary over adequately-sized groups only.
        big = [g for g in groups if g["n"] >= min_group_size]
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
            "tpr_range": _range(tprs),
            "fpr_range": _range(fprs),
            "n_groups_considered": len(big),
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
                    "floor": floor,
                    "lowest_group": worst["group"],
                    "lowest_selection_rate": worst["selection_rate"],
                }
            )

    out["guardrail"] = {
        "disparate_impact_floor": floor,
        "passed": len(breaches) == 0,
        "n_breaches": len(breaches),
        "breaches": breaches,
        "mitigation_attribute": MITIGATION_ATTRIBUTE,
    }
    return out
