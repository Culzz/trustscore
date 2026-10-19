"""Audit-console endpoints: registry, policy simulation, A/B, drift, alerts, PDF.

These back the dark "auditor terminal" view. They read the committed artifacts
(registry, metadata, portfolio, reference) and never touch personal data.
"""
from __future__ import annotations

import json
import urllib.request

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .. import db
from ..core import registry
from ..core.config import get_settings
from ..core.model import get_predictor, load_metadata
from ..schemas import (
    AbCompareRequest,
    AlertTestRequest,
    BiasInjectRequest,
    PolicySimulationRequest,
)
from ..services.drift_monitor import (
    MIN_WINDOW,
    evaluate_binned,
    live_drift,
    load_reference,
)
from ..services.feature_store import REGIONS, macro_context
from ..services.pipeline import base_thresholds
from ..services.portfolio import (
    ab_compare,
    available_attributes,
    bias_inject,
    load_portfolio,
    simulate,
    sweep,
)

router = APIRouter(tags=["audit"])


def _require_portfolio() -> dict:
    portfolio = load_portfolio()
    if portfolio is None:
        raise HTTPException(
            status_code=503,
            detail="Portfolio slice not found. Run training to generate it.",
        )
    return portfolio


# ---------------------------------------------------------------------------
# Registry / lineage
# ---------------------------------------------------------------------------
@router.get("/models")
def models() -> dict:
    """Model registry: versions, metrics, fairness and lineage."""
    return {
        "registry": registry.registry_summary(),
        "models": registry.list_models(),
        "lineage": registry.lineage(),
        "mitigation_attributes": registry.mitigation_attributes(),
        "variant_summaries": registry.variant_summaries(),
    }


@router.get("/registry")
def full_registry() -> dict:
    return registry.load_registry()


@router.get("/models/{version}")
def model_detail(version: str) -> dict:
    entry = registry.get_model(version)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown model version: {version}")
    return {"model": entry, "metadata": load_metadata(version)}


# ---------------------------------------------------------------------------
# Macro context (feature store)
# ---------------------------------------------------------------------------
@router.get("/context")
def context(region: str = Query(default="national")) -> dict:
    valid = {r["id"] for r in REGIONS}
    if region not in valid:
        raise HTTPException(
            status_code=400, detail=f"Unknown region. Choose one of: {sorted(valid)}"
        )
    return {"regions": REGIONS, "context": macro_context(region)}


# ---------------------------------------------------------------------------
# Portfolio & policy simulation
# ---------------------------------------------------------------------------
@router.get("/portfolio")
def portfolio_summary() -> dict:
    portfolio = _require_portfolio()
    levels = portfolio.get("levels") or {
        portfolio.get("group_attribute", "age_band"): portfolio.get("group_values") or []
    }
    return {
        "n": portfolio.get("n"),
        "set": portfolio.get("set", "validation"),
        "role": portfolio.get("role", "policy_tuning"),
        "row_key_prefix": portfolio.get("row_key_prefix"),
        "group_attribute": portfolio.get("group_attribute"),
        "attributes": available_attributes(portfolio),
        "group_values": levels,
        "fields": portfolio.get("fields"),
        "note": portfolio.get("note"),
    }


@router.get("/mitigation")
def mitigation() -> dict:
    return {
        "options": registry.mitigation_options(),
        "attributes": registry.mitigation_attributes(),
        "default_attribute": registry.default_mitigation_attribute(),
        "variant_summaries": registry.variant_summaries(),
        "disparate_impact_floor": registry.disparate_impact_floor(),
        "evaluation_protocol": registry.evaluation_protocol(),
    }


def _resolve_thresholds(payload) -> tuple[float, float, dict]:
    pred = get_predictor(payload.model)
    am, dm = base_thresholds(pred)
    if payload.approve_max_pd is not None:
        am = float(payload.approve_max_pd)
    if payload.decline_min_pd is not None:
        dm = float(payload.decline_min_pd)
    if dm <= am:
        dm = min(0.99, am + 0.01)
    costs = payload.costs.model_dump() if payload.costs else (pred.cost_matrix or None)
    return am, dm, costs


@router.post("/policy/simulate")
def policy_simulate(payload: PolicySimulationRequest) -> dict:
    """Apply a policy to the portfolio: KPIs, profitability and the guardrail."""
    portfolio = _require_portfolio()
    am, dm, costs = _resolve_thresholds(payload)
    # The attribute under audit defaults to the registry's chosen mitigation
    # variant, so the guardrail, the mitigation parameters and the group table all
    # refer to the same split.
    attribute = payload.mitigation_attribute or registry.default_mitigation_attribute()
    params = registry.mitigation_params_for(payload.model, attribute) if payload.apply_fairness else None

    try:
        result = simulate(
            portfolio,
            am,
            dm,
            costs=costs,
            apply_fairness=payload.apply_fairness,
            mitigation_params=params,
            floor=registry.disparate_impact_floor(),
            margin_rate=payload.margin_rate,
            loss_given_default=payload.loss_given_default,
            attribute=attribute,
        )

        if payload.include_sweep:
            low = max(0.005, am * 0.4)
            high = min(0.6, max(am * 2.5, 0.2))
            thresholds = [round(low + (high - low) * i / 17, 4) for i in range(18)]
            result["sweep"] = sweep(
                portfolio,
                thresholds,
                dm,
                costs=costs,
                floor=registry.disparate_impact_floor(),
                margin_rate=payload.margin_rate,
                loss_given_default=payload.loss_given_default,
                attribute=attribute,
            )

        # With mitigation on, also measure what it *cost*: the same policy without
        # it. Auditors should see the trade-off, not just the improved ratio.
        if payload.apply_fairness:
            baseline = simulate(
                portfolio,
                am,
                dm,
                costs=costs,
                apply_fairness=False,
                floor=registry.disparate_impact_floor(),
                margin_rate=payload.margin_rate,
                loss_given_default=payload.loss_given_default,
                attribute=attribute,
                with_ci=False,
            )
            result["mitigation_cost"] = {
                "cost_per_loan_delta": (
                    result["realized_cost_per_loan"] - baseline["realized_cost_per_loan"]
                ),
                "approval_rate_delta": result["approval_rate"] - baseline["approval_rate"],
                "profit_per_loan_delta": (
                    result["profit_per_loan"] - baseline["profit_per_loan"]
                ),
                "disparate_impact_ratio_base": baseline["disparate_impact_ratio"],
                "disparate_impact_ratio_mitigated": result["disparate_impact_ratio"],
                "equalized_odds_difference_base": baseline["equalized_odds_difference"],
                "equalized_odds_difference_mitigated": result["equalized_odds_difference"],
                "breaches_base": baseline["guardrail"]["n_breaches"],
                "breaches_mitigated": result["guardrail"]["n_breaches"],
                "note": (
                    "Measured on the policy tuning set (validation). The model card "
                    "quotes the same intervention measured on the held-out test split."
                ),
            }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["context"] = macro_context("national")
    breaches = result["guardrail"].get("breaches") or []
    result["intercept"] = {
        "save_policy_allowed": result["guardrail"]["passed"],
        "reason": (
            "Guardrail satisfied for the audited attribute."
            if result["guardrail"]["passed"]
            else (
                "Blocked: "
                + ", ".join(b["label"] for b in breaches)
                + " below the four-fifths floor"
                if breaches
                else "Blocked: the fairness guardrail is breached."
            )
        ),
        "floor": registry.disparate_impact_floor(),
    }
    return result


@router.post("/ab/compare")
def ab(payload: AbCompareRequest) -> dict:
    """Alpha (baseline) vs Beta (fairness-tuned) on the same portfolio."""
    portfolio = _require_portfolio()
    pred = get_predictor(payload.model_a)
    am, dm = base_thresholds(pred)
    if payload.approve_max_pd is not None:
        am = float(payload.approve_max_pd)
    if payload.decline_min_pd is not None:
        dm = float(payload.decline_min_pd)
    if dm <= am:
        dm = min(0.99, am + 0.01)
    costs = payload.costs.model_dump() if payload.costs else (pred.cost_matrix or None)
    attribute = payload.mitigation_attribute or registry.default_mitigation_attribute()
    params = registry.mitigation_params_for(payload.model_b, attribute)
    try:
        result = ab_compare(
            portfolio,
            am,
            dm,
            costs=costs,
            mitigation_params=params,
            floor=registry.disparate_impact_floor(),
            attribute=attribute,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["labels"] = {
        "alpha": (registry.get_model(payload.model_a) or {}).get("label", "Alpha"),
        "beta": (registry.get_model(payload.model_b) or {}).get("label", "Beta"),
    }
    return result


@router.post("/bias/inject")
def bias(payload: BiasInjectRequest) -> dict:
    """Skew one group's scores and show the guardrail firing, then recovery."""
    portfolio = _require_portfolio()
    pred = get_predictor(None)
    am, dm = base_thresholds(pred)
    if payload.approve_max_pd is not None:
        am = float(payload.approve_max_pd)
    if payload.decline_min_pd is not None:
        dm = float(payload.decline_min_pd)
    if dm <= am:
        dm = min(0.99, am + 0.01)
    attribute = payload.mitigation_attribute or registry.default_mitigation_attribute()
    params = registry.mitigation_params_for(None, attribute)
    try:
        return bias_inject(
            portfolio,
            payload.group,
            factor=payload.factor,
            approve_max_pd=am,
            decline_min_pd=dm,
            costs=pred.cost_matrix or None,
            mitigation_params=params,
            floor=registry.disparate_impact_floor(),
            attribute=attribute,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Live drift & adversarial alerting
# ---------------------------------------------------------------------------
def _drift_from_db() -> dict | None:
    reference = load_reference()
    if not reference:
        return None
    rows = db.recent_feature_rows(limit=800)
    if len(rows) < MIN_WINDOW:
        return None
    n_bins = {
        col: len(spec.get("expected_proportions", []))
        for col, spec in reference.get("numeric", {}).items()
    }
    bin_counts = {col: [0] * size for col, size in n_bins.items() if size}
    cat_counts: dict = {}
    for row in rows:
        for col, idx in (row.get("bins") or {}).items():
            if col in bin_counts and 0 <= int(idx) < len(bin_counts[col]):
                bin_counts[col][int(idx)] += 1
        for col, value in (row.get("cats") or {}).items():
            cats = cat_counts.setdefault(col, {})
            cats[str(value)] = cats.get(str(value), 0) + 1
    return evaluate_binned(bin_counts, cat_counts, len(rows), False, "logged submissions")


@router.get("/drift/live")
def drift_live(shift: float = Query(default=0.0, ge=-3.0, le=3.0), source: str = "auto") -> dict:
    """PSI/KS against the training reference; falls back to a simulated window."""
    if source in ("auto", "db"):
        live = _drift_from_db()
        if live is not None:
            return live
    result = live_drift(shift=shift)
    result["storage_enabled"] = db.is_enabled()
    return result


def _alert_payload(severity: str, message: str, drift: dict) -> dict:
    return {
        "type": "trustscore.drift_alert",
        "severity": severity,
        "message": message,
        "max_psi": drift.get("max_psi"),
        "max_ks": drift.get("max_ks"),
        "top_alerts": (drift.get("alerts") or [])[:5],
        "adversarial_validation": drift.get("adversarial_validation"),
        "window": drift.get("window"),
        "simulated": drift.get("simulated"),
    }


@router.post("/alerts/test")
def alerts_test(payload: AlertTestRequest) -> dict:
    """Fire the (simulated) alerting hook -- a Slack/webhook-style payload."""
    drift = live_drift(shift=payload.shift)
    alert = _alert_payload(payload.severity, payload.message, drift)
    delivered = False
    url = get_settings().alert_webhook_url
    if payload.deliver and url:
        try:  # pragma: no cover - external service
            request = urllib.request.Request(
                url,
                data=json.dumps(alert).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5):
                delivered = True
        except Exception:
            delivered = False
    return {
        "delivered": delivered,
        "webhook_configured": bool(url),
        "payload": alert,
        "note": (
            "Set ALERT_WEBHOOK_URL and pass deliver=true to actually POST the alert."
            if not url
            else "Webhook configured."
        ),
    }


# ---------------------------------------------------------------------------
# Compliance PDF
# ---------------------------------------------------------------------------
@router.get("/report.pdf")
def report_pdf() -> Response:
    """Server-side 'Compliance Alignment & Fair Lending' PDF."""
    # Imported lazily: reportlab (and its C accelerator) is only needed for this
    # endpoint. Keeping it out of the module import trims serverless cold-start
    # time and memory for the scoring endpoints.
    from ..services.report_pdf import build_compliance_report

    metadata = load_metadata()
    if not metadata:
        raise HTTPException(status_code=503, detail="Model metadata not found.")
    pdf = build_compliance_report(metadata, registry.load_registry())
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=trustscore-compliance-report.pdf"},
    )
