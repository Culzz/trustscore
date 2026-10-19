"""Async apply flow: serverless-safe fallback.

The test suite runs with ``STORAGE_BACKEND=none`` (see ``conftest.py``), which is
also the free-tier Vercel configuration. In that mode the API must finish the
job inside the POST request, because a later poll can reach a different
serverless instance that never saw the in-memory job.
"""
from __future__ import annotations


def test_apply_returns_completed_job_without_durable_store(client, strong_applicant):
    res = client.post("/apply", json={"applicant": strong_applicant})
    assert res.status_code == 202

    body = res.json()
    assert body["status"] == "complete"
    assert body["durable"] is False
    assert body["result"] is not None
    assert body["result"]["scoring"]["probability_of_default"] is not None
    assert body["result"]["scoring"]["final_band"] in ("approve", "refer", "decline")

    steps = [event["step"] for event in body["events"]]
    assert steps[0] == "validated"
    assert steps[-1] == "complete"


def test_apply_result_contains_recourse_and_narrative(client, strong_applicant):
    body = client.post("/apply", json={"applicant": strong_applicant}).json()
    result = body["result"]
    assert result["reasons"]
    assert result["narrative"]
    assert "routes" in result["blueprint"]
    assert "actionability" in result["blueprint"] or not result["blueprint"]["routes"]
