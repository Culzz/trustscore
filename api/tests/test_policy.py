"""Unit tests for the shared policy, reason and counterfactual logic."""
from __future__ import annotations

import numpy as np

from app.services.counterfactual import band_rank, find_counterfactuals
from app.services.decision import (
    APPROVE,
    DECLINE,
    REFER,
    CostMatrix,
    analytic_thresholds,
    decide,
    decide_array,
    grid_thresholds,
    realized_cost,
)
from app.services.reasons import top_reasons


# ---------------------------------------------------------------- decision ---
def test_analytic_thresholds_ordering():
    ta, td = analytic_thresholds(CostMatrix(1.0, 0.20, 0.05))
    assert 0 < ta < td < 1


def test_decide_bands():
    assert decide(0.01, 0.10, 0.50) == APPROVE
    assert decide(0.30, 0.10, 0.50) == REFER
    assert decide(0.90, 0.10, 0.50) == DECLINE


def test_decide_array_matches_scalar():
    p = np.array([0.01, 0.2, 0.9])
    out = decide_array(p, 0.10, 0.50)
    assert list(out) == [APPROVE, REFER, DECLINE]


def test_grid_thresholds_minimises_cost():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 500)
    amounts = rng.uniform(1000, 20000, 500)
    costs = CostMatrix(1.0, 0.20, 0.05)
    ta, td, _ = grid_thresholds(p, amounts, costs)
    assert 0 <= ta < td <= 1
    # A clearly terrible policy should cost more than the chosen one.
    good = realized_cost((p > 0.5).astype(int), amounts, decide_array(p, ta, td), costs)
    always_approve = realized_cost(
        (p > 0.5).astype(int), amounts, np.array([APPROVE] * len(p)), costs
    )
    assert good <= always_approve


# ----------------------------------------------------------------- reasons ---
def test_top_reasons_are_readable_and_ranked():
    names = ["person_income", "loan_amnt", "loan_intent_VENTURE"]
    contribs = [-0.5, 0.9, 0.3]
    row = {
        "person_income": 30000,
        "loan_amnt": 15000,
        "loan_intent": "VENTURE",
    }
    reasons = top_reasons(contribs, names, row, k=3)
    assert len(reasons) == 3
    assert reasons[0]["factor"] == "Requested loan amount"
    assert reasons[0]["direction"] == "increases"
    assert all("text" in r and "detail" in r for r in reasons)
    # Raw contribution numbers must not be exposed.
    for r in reasons:
        assert "_impact" not in r


# ---------------------------------------------------------- counterfactual ---
def test_band_rank_monotone():
    assert band_rank(APPROVE) < band_rank(REFER) < band_rank(DECLINE)


def test_counterfactual_respects_immutable_features():
    # A fake model: risk falls as the amount falls.
    def predict(row: dict) -> float:
        return min(0.99, row["loan_amnt"] / 20000.0)

    row = {"loan_amnt": 18000, "person_income": 40000, "loan_intent": "VENTURE"}
    scenarios = find_counterfactuals(
        row, predict, approve_max_pd=0.10, decline_min_pd=0.50, current_pd=0.90
    )
    assert scenarios
    for s in scenarios:
        assert s["feature"] in {"loan_amnt", "loan_intent"}
    # Reducing the amount must appear as the actionable lever.
    assert any(s["feature"] == "loan_amnt" for s in scenarios)


def test_counterfactual_empty_when_already_approved():
    def predict(row: dict) -> float:
        return 0.01

    row = {"loan_amnt": 5000, "person_income": 60000, "loan_intent": "PERSONAL"}
    assert find_counterfactuals(row, predict, 0.10, 0.50, 0.01) == []
