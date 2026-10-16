"""The decision-policy layer: cost matrix, thresholds and band assignment.

The model outputs a probability of default (PD). The *policy* turns that into
Approve / Refer / Decline. Keeping the two separate is the whole point of the
project, so this module owns every policy number.

This module is pure Python + NumPy and has no heavy dependencies, so it is
imported by both the runtime API and the offline training pipeline. One
implementation, one set of numbers.

Expected-cost reasoning
-----------------------
For one applicant with default probability ``p`` and exposure ``A``:

    expected cost of approving  = p * COST_FALSE_APPROVE * A
    expected cost of declining  = (1 - p) * COST_FALSE_DECLINE * A
    expected cost of reviewing  = COST_REVIEW * A

A rational policy picks the cheapest action for each ``p``, which yields two
crossover points -- the band thresholds:

    approve -> refer  at  p = COST_REVIEW / COST_FALSE_APPROVE
    refer   -> decline at  p = 1 - COST_REVIEW / COST_FALSE_DECLINE

We also verify the analytic answer with a numeric grid search so the published
thresholds are never just a formula.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

APPROVE = "approve"
REFER = "refer"
DECLINE = "decline"

# Default business costs, in cost units per unit of loan exposure. The lender
# view can override these; these are the trained defaults recorded in metadata.
DEFAULT_FALSE_APPROVE = 1.0
DEFAULT_FALSE_DECLINE = 0.20
DEFAULT_REVIEW = 0.05


@dataclass(frozen=True)
class CostMatrix:
    """Business costs, expressed per unit of exposure (loan amount)."""

    false_approve: float = DEFAULT_FALSE_APPROVE
    false_decline: float = DEFAULT_FALSE_DECLINE
    review: float = DEFAULT_REVIEW

    def as_dict(self) -> dict:
        return {
            "false_approve": self.false_approve,
            "false_decline": self.false_decline,
            "review": self.review,
            "units": "cost per unit of loan amount (exposure)",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CostMatrix":
        return cls(
            false_approve=float(data.get("false_approve", DEFAULT_FALSE_APPROVE)),
            false_decline=float(data.get("false_decline", DEFAULT_FALSE_DECLINE)),
            review=float(data.get("review", DEFAULT_REVIEW)),
        )


def analytic_thresholds(costs: CostMatrix) -> tuple[float, float]:
    """Return (approve_max_pd, decline_min_pd) from the cost matrix."""
    t_approve = min(
        costs.review / costs.false_approve,
        costs.false_decline / (costs.false_approve + costs.false_decline),
    )
    t_decline = 1.0 - costs.review / costs.false_decline
    # Guard against a nonsensical configuration.
    if t_decline <= t_approve:
        t_decline = min(0.99, t_approve + 0.05)
    return float(t_approve), float(t_decline)


def grid_thresholds(
    p: np.ndarray,
    amounts: np.ndarray,
    costs: CostMatrix,
    n: int = 60,
) -> tuple[float, float, float]:
    """Brute-force the thresholds that minimise total *expected* cost.

    Returns (approve_max_pd, decline_min_pd, expected_cost_per_loan).
    """
    p = np.asarray(p, dtype=float)
    a = np.asarray(amounts, dtype=float)
    grid = np.linspace(0.005, 0.995, n)
    best: tuple[float | None, float | None, float] = (None, None, np.inf)
    for ta in grid:
        for td in grid:
            if td <= ta:
                continue
            approve = p <= ta
            decline = p > td
            refer = ~approve & ~decline
            cost = (
                costs.false_approve * float(np.sum(p[approve] * a[approve]))
                + costs.false_decline
                * float(np.sum((1 - p[decline]) * a[decline]))
                + costs.review * float(np.sum(a[refer]))
            )
            per_loan = cost / max(float(a.sum()), 1.0)
            if per_loan < best[2]:
                best = (float(ta), float(td), per_loan)
    return best


def decide(pd_value: float, approve_max_pd: float, decline_min_pd: float) -> str:
    """Map a single PD to a band label."""
    if pd_value <= approve_max_pd:
        return APPROVE
    if pd_value >= decline_min_pd:
        return DECLINE
    return REFER


def decide_array(
    p: np.ndarray, approve_max_pd: float, decline_min_pd: float
) -> np.ndarray:
    """Vectorised :func:`decide`, returning string labels."""
    p = np.asarray(p, dtype=float)
    out = np.full(p.shape, REFER, dtype=object)
    out[p <= approve_max_pd] = APPROVE
    out[p >= decline_min_pd] = DECLINE
    return out


def expected_cost(
    p: np.ndarray,
    amounts: np.ndarray,
    decisions: np.ndarray,
    costs: CostMatrix,
) -> float:
    """Total expected cost for a set of decisions (uses PD as the probability)."""
    p = np.asarray(p, dtype=float)
    a = np.asarray(amounts, dtype=float)
    decisions = np.asarray(decisions)
    total = 0.0
    m = decisions == APPROVE
    total += costs.false_approve * float(np.sum(p[m] * a[m]))
    m = decisions == DECLINE
    total += costs.false_decline * float(np.sum((1 - p[m]) * a[m]))
    m = decisions == REFER
    total += costs.review * float(np.sum(a[m]))
    return total


def realized_cost(
    y: np.ndarray,
    amounts: np.ndarray,
    decisions: np.ndarray,
    costs: CostMatrix,
) -> float:
    """Total *realised* cost using true outcomes (out-of-sample reporting)."""
    y = np.asarray(y, dtype=float)
    a = np.asarray(amounts, dtype=float)
    decisions = np.asarray(decisions)
    total = 0.0
    m = decisions == APPROVE
    total += costs.false_approve * float(np.sum(y[m] * a[m]))
    m = decisions == DECLINE
    total += costs.false_decline * float(np.sum((1 - y[m]) * a[m]))
    m = decisions == REFER
    total += costs.review * float(np.sum(a[m]))
    return total


def band_label(band: str) -> str:
    """Map a band to its risk wording used across the UI."""
    return {
        APPROVE: "low",
        REFER: "medium",
        DECLINE: "high",
    }.get(band, "unknown")
