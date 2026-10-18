"""Endpoint tests for /health, /model and /stats."""
from __future__ import annotations


def test_root_lists_endpoints(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert "POST /predict" in body["endpoints"]


def test_health_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_version"]


def test_api_prefix_is_stripped(client):
    # Vercel serves the app behind /api/*; the same route must resolve.
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_model_metadata(client):
    res = client.get("/model")
    assert res.status_code == 200
    body = res.json()
    for key in (
        "version",
        "metrics",
        "calibration",
        "thresholds",
        "fairness",
        "limitations",
        "evaluation_protocol",
        "ablation",
        "robustness",
    ):
        assert key in body
    assert 0.0 <= body["metrics"]["calibrated"]["roc_auc"] <= 1.0


def test_deployed_thresholds_are_the_analytic_crossover(client):
    """The published thresholds must be the cost crossover, not the grid point."""
    body = client.get("/model").json()
    thr = body["thresholds"]
    assert thr["selected_by"] == "analytic_cost_minimisation"
    assert thr["approve_max_pd"] == thr["analytic_approve_max_pd"]
    assert thr["decline_min_pd"] == thr["analytic_decline_min_pd"]
    # ...and the grid search must have verified it as cost-optimal.
    grid = thr["grid_verification"]
    assert grid["analytic_is_cost_optimal"] is True
    assert grid["cost_delta_vs_analytic"] == 0.0


def test_model_metadata_has_uncertainty_intervals(client):
    body = client.get("/model").json()
    intervals = body["metrics"]["calibrated"].get("intervals")
    assert intervals is not None
    for metric in ("roc_auc", "pr_auc", "brier"):
        assert intervals[metric]["ci_low"] <= intervals[metric]["ci_high"]


def test_evaluation_protocol_separates_tuning_from_final(client):
    body = client.get("/model").json()
    proto = body["evaluation_protocol"]
    assert proto["policy_tuning_set"]["name"] == "validation"
    assert proto["final_evaluation_set"]["name"] == "test"
    # The final test rows must never be shipped as an inspectable portfolio.
    assert proto["final_evaluation_set"]["shipped_as_portfolio"] is False
    assert proto["policy_tuning_set"]["shipped_as_portfolio"] is True


def test_fairness_reports_uncertainty_and_all_breaches(client):
    fairness = client.get("/model").json()["fairness"]
    summary = fairness["attributes"]["age_band"]["summary"]
    assert summary.get("disparate_impact_ratio_ci") is not None
    assert summary.get("n_groups_total", 0) >= summary.get("n_groups_considered", 0)
    guardrail = fairness["guardrail"]
    assert set(guardrail["breaching_attributes"]) == {
        b["attribute"] for b in guardrail["breaches"]
    }
    assert guardrail.get("interpretation")


def test_portfolio_is_the_tuning_set_not_the_test_set(client):
    res = client.get("/portfolio")
    assert res.status_code == 200
    body = res.json()
    assert body["set"] == "validation"
    assert body["role"] == "policy_tuning"


def test_policy_simulate_reports_its_set_and_uncertainty(client):
    res = client.post(
        "/policy/simulate",
        json={"approve_max_pd": 0.05, "decline_min_pd": 0.75, "include_sweep": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation_set"] == "validation"
    assert body["evaluation_role"] == "policy_tuning"
    assert body["uncertainty"]["n_boot"] > 0
    assert body["fairness_table"]
    assert "selection_rate_ci" in body["fairness_table"][0]


def test_policy_simulate_reports_the_cost_of_mitigation(client):
    res = client.post(
        "/policy/simulate",
        json={"apply_fairness": True, "include_sweep": False},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mitigation_cost"] is not None
    assert "cost_per_loan_delta" in body["mitigation_cost"]
    assert "note" in body["mitigation_cost"]


def test_stats_disabled_shape(client):
    res = client.get("/stats")
    assert res.status_code == 200
    body = res.json()
    assert "enabled" in body
    assert "total_predictions" in body
