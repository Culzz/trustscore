"""Endpoint tests for /predict, /explain, /decision and /counterfactual."""
from __future__ import annotations

import pytest


def test_predict_returns_band_and_id(client, strong_applicant):
    res = client.post("/predict", json=strong_applicant)
    assert res.status_code == 200
    body = res.json()
    assert 0.0 <= body["probability_of_default"] <= 1.0
    assert body["band"] in {"approve", "refer", "decline"}
    assert body["band_label"] in {"low", "medium", "high"}
    assert body["prediction_id"]
    assert body["model_version"]
    assert body["thresholds"]["approve_max_pd"] <= body["thresholds"]["decline_min_pd"]


def test_predict_validation_rejects_bad_input(client, strong_applicant):
    bad = dict(strong_applicant)
    bad["person_age"] = 12
    assert client.post("/predict", json=bad).status_code == 422

    missing = dict(strong_applicant)
    del missing["person_income"]
    assert client.post("/predict", json=missing).status_code == 422

    extra = dict(strong_applicant)
    extra["secret_field"] = "x"
    assert client.post("/predict", json=extra).status_code == 422


def test_explain_returns_plain_language_reasons(client, risky_applicant):
    res = client.post("/explain", json=risky_applicant)
    assert res.status_code == 200
    body = res.json()
    assert 1 <= len(body["reasons"]) <= 5
    for reason in body["reasons"]:
        assert reason["direction"] in {"increases", "reduces"}
        assert reason["text"]
        # No raw numbers leak into the applicant-facing text.
        assert not any(ch.isdigit() for ch in reason["factor"])


def test_decision_is_labelled_simulated(client, strong_applicant):
    res = client.post("/decision", json={"applicant": strong_applicant})
    assert res.status_code == 200
    body = res.json()
    assert body["simulated"] is True
    assert body["decision"] in {"approve", "refer", "decline"}
    assert "expected_cost" in body


def test_decision_threshold_override_changes_outcome(client, risky_applicant):
    default = client.post("/decision", json={"applicant": risky_applicant})
    assert default.status_code == 200
    # This applicant is deliberately extreme; the default cost policy declines.
    assert default.json()["decision"] == "decline"

    # A fully permissive policy must approve regardless of the model's score.
    permissive = client.post(
        "/decision",
        json={
            "applicant": risky_applicant,
            "approve_max_pd": 1.0,
            "decline_min_pd": 1.0,
        },
    )
    assert permissive.status_code == 200
    body = permissive.json()
    assert body["decision"] == "approve"
    assert body["thresholds"]["approve_max_pd"] == 1.0
    assert body["simulated"] is True


def test_counterfactual_structure(client, risky_applicant):
    res = client.post("/counterfactual", json=risky_applicant)
    assert res.status_code == 200
    body = res.json()
    assert body["current_band"] in {"approve", "refer", "decline"}
    for scenario in body["scenarios"]:
        assert scenario["changeability"] in {
            "changeable_by_applicant",
            "potentially_changeable",
        }
        assert scenario["new_band"] in {"approve", "refer", "decline"}
        # Protected / immutable attributes must never be suggested.
        assert scenario["feature"] in {"loan_amnt", "loan_intent"}


def test_counterfactual_none_when_already_best(client, strong_applicant):
    res = client.post("/counterfactual", json=strong_applicant)
    assert res.status_code == 200
    body = res.json()
    if body["current_band"] == "approve":
        assert body["scenarios"] == []


@pytest.mark.parametrize("field", ["person_home_ownership", "loan_intent", "loan_grade"])
def test_categorical_validation(client, strong_applicant, field):
    bad = dict(strong_applicant)
    bad[field] = "NOT_A_REAL_VALUE"
    assert client.post("/predict", json=bad).status_code == 422
