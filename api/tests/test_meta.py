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
    for key in ("version", "metrics", "calibration", "thresholds", "fairness", "limitations"):
        assert key in body
    assert 0.0 <= body["metrics"]["calibrated"]["roc_auc"] <= 1.0


def test_stats_disabled_shape(client):
    res = client.get("/stats")
    assert res.status_code == 200
    body = res.json()
    assert "enabled" in body
    assert "total_predictions" in body
