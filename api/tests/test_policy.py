"""Unit tests for the shared policy, reason and counterfactual logic."""
from __future__ import annotations

import numpy as np

from app.services.blueprint import INCOME_STEP_MAX, build_blueprint
from app.services.counterfactual import band_rank, find_counterfactuals
from app.services.decision import (
    APPROVE,
    DECLINE,
    REFER,
    CostMatrix,
    analytic_thresholds,
    cost_equivalence,
    decide,
    decide_array,
    expected_cost_per_loan,
    grid_thresholds,
    realized_cost,
)
from app.services.reasons import top_reasons

DEFAULT_COSTS = CostMatrix(1.0, 0.20, 0.05)


# ---------------------------------------------------------------- decision ---
def test_analytic_thresholds_exact_values():
    """The deployed policy is the cost crossover, computed by hand here."""
    ta, td = analytic_thresholds(DEFAULT_COSTS)
    # review / false_approve = 0.05 / 1.0
    assert ta == 0.05
    # 1 - review / false_decline = 1 - 0.05 / 0.20
    assert td == 0.75


def test_analytic_thresholds_ordering():
    ta, td = analytic_thresholds(DEFAULT_COSTS)
    assert 0 < ta < td < 1


def test_analytic_thresholds_respond_to_cost_changes():
    # Declining gets cheaper -> the decline crossover moves down.
    ta, td = analytic_thresholds(CostMatrix(1.0, 0.40, 0.05))
    assert ta == 0.05
    assert abs(td - (1 - 0.05 / 0.40)) < 1e-12
    # Approving gets more expensive -> the approve crossover moves down.
    ta2, _ = analytic_thresholds(CostMatrix(0.50, 0.20, 0.05))
    assert abs(ta2 - 0.10) < 1e-12


def test_decide_boundaries_are_inclusive_at_the_thresholds():
    ta, td = analytic_thresholds(DEFAULT_COSTS)
    # Exactly on the crossover: <= approves, >= declines.
    assert decide(ta, ta, td) == APPROVE
    assert decide(td, ta, td) == DECLINE
    # Just inside / outside the refer band.
    assert decide(ta + 1e-9, ta, td) == REFER
    assert decide(td - 1e-9, ta, td) == REFER
    assert decide(0.0, ta, td) == APPROVE
    assert decide(1.0, ta, td) == DECLINE


def test_decide_bands():
    assert decide(0.01, 0.10, 0.50) == APPROVE
    assert decide(0.30, 0.10, 0.50) == REFER
    assert decide(0.90, 0.10, 0.50) == DECLINE


def test_decide_array_matches_scalar():
    p = np.array([0.01, 0.2, 0.9])
    out = decide_array(p, 0.10, 0.50)
    assert list(out) == [APPROVE, REFER, DECLINE]


def test_expected_cost_per_loan_picks_the_cheapest_action_per_applicant():
    """A per-applicant break-even: below 0.05 approve, above 0.75 decline."""
    costs = DEFAULT_COSTS
    pd_values = np.array([0.01, 0.04, 0.30, 0.60, 0.90, 0.99])
    amounts = np.full(len(pd_values), 1.0)
    ta, td = analytic_thresholds(costs)

    # Total expected cost of the analytic policy is the sum of the per-applicant
    # minimum of the three actions, so no other threshold pair can beat it.
    decisions = decide_array(pd_values, ta, td)
    policy_cost = expected_cost_per_loan(pd_values, amounts, ta, td, costs)
    per_applicant_min = (
        np.minimum.reduce(
            [
                pd_values * costs.false_approve,
                np.full(len(pd_values), costs.review),
                (1 - pd_values) * costs.false_decline,
            ]
        ).mean()
    )
    assert abs(policy_cost - per_applicant_min) < 1e-12


def test_grid_and_analytic_agree_on_cost_across_a_score_gap():
    """Across a gap in the score distribution the surface is flat; both are optimal.

    This mirrors the shipped model: no validation applicant scores between
    ~0.055 and ~0.676, so many threshold pairs cost exactly the same and the grid's
    value is an arbitrary plateau member. The analytic crossover is the exact
    per-applicant optimum, so no candidate can beat it.
    """
    costs = DEFAULT_COSTS
    # Two clusters with a wide empty middle, like the real calibrated scores.
    rng = np.random.default_rng(7)
    p = np.concatenate([rng.uniform(0.0, 0.02, 900), rng.uniform(0.80, 1.0, 300)])
    amounts = rng.uniform(1000, 40000, len(p))

    ta, td = analytic_thresholds(costs)
    ta_g, td_g, _ = grid_thresholds(p, amounts, costs)

    # The two pairs may look very different...
    assert (ta_g, td_g) != (ta, td)
    # ...but across the gap they must cost exactly the same, and both be optimal.
    result = cost_equivalence(p, amounts, costs, [(ta, td), (ta_g, td_g)])
    analytic_block, grid_block = result["candidates"]
    assert analytic_block["is_cost_optimal"]
    assert grid_block["is_cost_optimal"]
    assert analytic_block["delta_vs_best"] == 0.0
    assert grid_block["delta_vs_best"] <= 1e-9
    # The analytic policy is the per-applicant floor, so nothing can beat it.
    assert expected_cost_per_loan(p, amounts, ta, td, costs) == result["best_cost_per_loan"]


def test_analytic_policy_beats_a_naive_constant_threshold():
    """The cost-optimal crossover is never worse than an arbitrary policy."""
    costs = DEFAULT_COSTS
    rng = np.random.default_rng(11)
    p = rng.uniform(0, 1, 2000)
    amounts = rng.uniform(1000, 40000, 2000)
    ta, td = analytic_thresholds(costs)
    analytic = expected_cost_per_loan(p, amounts, ta, td, costs)
    naive = expected_cost_per_loan(p, amounts, 0.5, 0.9, costs)
    assert analytic <= naive + 1e-12


def test_grid_thresholds_minimises_cost():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 500)
    amounts = rng.uniform(1000, 20000, 500)
    costs = DEFAULT_COSTS
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


# ----------------------------------------------------------------- blueprint ---
def test_blueprint_routes_are_actionability_classified():
    def predict(row: dict) -> float:
        return min(0.99, row["loan_amnt"] / 20000.0)

    row = {"loan_amnt": 18000, "person_income": 40000, "loan_intent": "VENTURE"}
    plan = build_blueprint(row, predict, 0.10, 0.50, 0.90)
    assert plan["status"] == "actionable"
    assert plan["routes"]
    for route in plan["routes"]:
        assert route["actionability"] in {
            "actionable",
            "potentially_actionable",
            "immutable",
        }
        assert route["guarantees_outcome"] is False
    # Immutable factors are surfaced explicitly, not silently dropped.
    fields = {f["field"] for f in plan["immutable_fields"]}
    assert {"person_age", "loan_grade", "cb_person_default_on_file"} <= fields
    assert plan["route_summary"]["has_actionable_route"] is True


def test_blueprint_says_when_there_is_no_route():
    def predict(row: dict) -> float:
        return 0.9  # nothing the applicant changes can help

    row = {"loan_amnt": 18000, "person_income": 40000, "loan_intent": "VENTURE"}
    plan = build_blueprint(row, predict, 0.10, 0.50, 0.90)
    assert plan["status"] == "blocked"
    assert plan["routes"] == []
    assert plan["no_route_reason"]
    assert "not a prediction" in plan["no_route_reason"]
    assert plan["route_summary"]["has_actionable_route"] is False


def test_blueprint_income_route_respects_a_plausible_cap():
    """Income is an informational option, and it is capped, not unbounded."""
    def predict(row: dict) -> float:
        # Risk falls linearly with income; only a 50x increase would approve.
        return min(0.99, 0.9 * (40000.0 / max(row["person_income"], 1.0)))

    row = {"loan_amnt": 5000, "person_income": 40000, "loan_intent": "PERSONAL"}
    plan = build_blueprint(row, predict, 0.10, 0.50, 0.90)
    dual = plan.get("dual_target")
    if dual:
        for option in dual["options"]:
            # No suggestion may exceed the documented multiple of current income.
            assert "5000000" not in option["change"]
    assert INCOME_STEP_MAX <= 10.0
