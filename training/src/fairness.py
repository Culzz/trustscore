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


def compute_fairness(
    df: pd.DataFrame,
    y_true: np.ndarray,
    p: np.ndarray,
    decisions: np.ndarray,
    model_version: str,
    min_group_size: int = 30,
) -> dict:
    """Build the fairness report consumed by ``GET /model`` and the dashboard."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    approved = np.asarray(decisions) == APPROVE

    out: dict = {
        "model_version": model_version,
        "min_group_size": min_group_size,
        "definitions": {
            "positive_prediction": "approved (decision band = approve)",
            "favourable_outcome": "repaid (loan_status == 0)",
            "selection_rate": "share of group approved",
            "tpr": "P(approved | repaid)",
            "fpr": "P(approved | defaulted)",
            "precision": "P(repaid | approved)",
        },
        "attributes": {},
        "unavailable_attributes": list(config.UNAVAILABLE_AUDIT_ATTRIBUTES),
        "disclaimer": DISCLAIMER,
    }

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
        summary = {
            "selection_rate_ratio": (
                float(min(selection_rates) / max(selection_rates))
                if len(selection_rates) >= 2 and max(selection_rates) > 0
                else None
            ),
            "demographic_parity_difference": (
                float(max(selection_rates) - min(selection_rates))
                if len(selection_rates) >= 2
                else None
            ),
            "equal_opportunity_difference": (
                float(max(tprs) - min(tprs)) if len(tprs) >= 2 else None
            ),
            "n_groups_considered": len(big),
        }

        out["attributes"][attr] = {
            "label": ATTRIBUTE_LABELS.get(attr, attr),
            "groups": groups,
            "summary": summary,
        }

    return out
