"""Scoring endpoints: /predict, /explain, /decision, /counterfactual, /blueprint."""

# NOTE: deliberately no ``from __future__ import annotations`` in this module.
# FastAPI resolves endpoint annotations using the decorated callable's globals,
# and slowapi's ``@limiter.limit`` wrapper does not share this module's globals.
# Postponed annotations therefore break schema resolution on some versions.

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Query, Request

from .. import db
from ..core.config import get_settings
from ..core.features import CATEGORY_OPTIONS
from ..core.model import get_predictor
from ..limiter import limiter
from ..schemas import (
    DISCLAIMER,
    Applicant,
    ApplyRequest,
    CounterfactualResponse,
    CounterfactualScenario,
    DecisionRequest,
    DecisionResponse,
    ExplainResponse,
    PredictResponse,
    ReasonItem,
    Thresholds,
)
from ..services import decision as policy
from ..services.blueprint import build_blueprint
from ..services.counterfactual import find_counterfactuals
from ..services.drift_monitor import bins_for_row
from ..services.narrative import REASON_CODES
from ..services.pipeline import base_thresholds, score_row
from ..services.reasons import top_reasons

router = APIRouter(tags=["scoring"])


def _enrich_row(applicant: Applicant) -> dict:
    """Add derived values so explanations can describe them."""
    row = applicant.as_model_row()
    income = float(row.get("person_income") or 0)
    row["loan_percent_income"] = (
        float(row["loan_amnt"]) / income if income > 0 else 0.0
    )
    return row


def _reason_code(factor: str) -> str | None:
    entry = REASON_CODES.get(factor)
    return entry["code"] if entry else None


@router.post("/predict", response_model=PredictResponse)
@limiter.limit(get_settings().rate_limit)
def predict(
    request: Request, applicant: Applicant, model: str | None = Query(default=None)
) -> PredictResponse:
    """Calibrated probability of default, band, model version and prediction id."""
    scored = score_row(applicant.as_model_row(), model_version=model)
    pd_value = scored["probability_of_default"]
    approve_max = scored["thresholds"]["approve_max_pd"]
    decline_min = scored["thresholds"]["decline_min_pd"]
    band = scored["band"]

    prediction_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    db.log_prediction(
        prediction_id=prediction_id,
        model_version=scored["model_version"],
        probability_of_default=pd_value,
        band=band,
        decision=band,
        exposure=applicant.loan_amnt,
    )
    try:
        db.log_prediction_features(prediction_id, bins_for_row(applicant.as_model_row()))
    except Exception:  # pragma: no cover - logging must never break scoring
        pass

    return PredictResponse(
        prediction_id=prediction_id,
        model_version=scored["model_version"],
        probability_of_default=pd_value,
        band=band,
        band_label=scored["band_label"],
        thresholds=Thresholds(approve_max_pd=approve_max, decline_min_pd=decline_min),
        created_at=created_at,
    )


@router.post("/explain", response_model=ExplainResponse)
@limiter.limit(get_settings().rate_limit)
def explain(
    request: Request, applicant: Applicant, model: str | None = Query(default=None)
) -> ExplainResponse:
    """The strongest plain-language reasons for this applicant's estimate."""
    pred = get_predictor(model)
    row = _enrich_row(applicant)
    pd_value = pred.predict_proba(applicant.as_model_row())
    contribs, names = pred.contributions(applicant.as_model_row())
    reasons = top_reasons(contribs, names, row, k=5)
    for reason in reasons:
        reason["code"] = _reason_code(reason.get("factor", ""))

    approve_max, decline_min = base_thresholds(pred)
    band = policy.decide(pd_value, approve_max, decline_min)
    return ExplainResponse(
        model_version=pred.version,
        probability_of_default=pd_value,
        band=band,
        reasons=[ReasonItem(**r) for r in reasons],
    )


@router.post("/decision", response_model=DecisionResponse)
@limiter.limit(get_settings().rate_limit)
def decision(request: Request, payload: DecisionRequest) -> DecisionResponse:
    """Apply the (optionally overridden) cost-based policy to one applicant."""
    scored = score_row(
        payload.applicant.as_model_row(),
        model_version=payload.model,
        apply_fairness=payload.apply_fairness,
        region=payload.region,
        use_macro_tilt=payload.use_macro_tilt,
        approve_max_pd=payload.approve_max_pd,
        decline_min_pd=payload.decline_min_pd,
        mitigation_attribute=payload.mitigation_attribute,
    )
    pd_value = scored["probability_of_default"]
    band = scored["final_band"]
    approve_max = scored["thresholds"]["approve_max_pd"]
    decline_min = scored["thresholds"]["decline_min_pd"]

    pred = get_predictor(payload.model)
    costs = policy.CostMatrix.from_dict(pred.cost_matrix or {})
    exposure = float(payload.applicant.loan_amnt)
    if band == policy.APPROVE:
        expected = costs.false_approve * pd_value * exposure
    elif band == policy.DECLINE:
        expected = costs.false_decline * (1 - pd_value) * exposure
    else:
        expected = costs.review * exposure

    return DecisionResponse(
        decision=band,
        band_label=policy.band_label(band),
        simulated=True,
        probability_of_default=pd_value,
        thresholds=Thresholds(approve_max_pd=approve_max, decline_min_pd=decline_min),
        cost_matrix=costs.as_dict(),
        expected_cost=float(expected),
        model_version=scored["model_version"],
    )


@router.post("/counterfactual", response_model=CounterfactualResponse)
@limiter.limit(get_settings().rate_limit)
def counterfactual(
    request: Request, applicant: Applicant, model: str | None = Query(default=None)
) -> CounterfactualResponse:
    """Feasible changes that could move this applicant to a better band."""
    pred = get_predictor(model)
    row = applicant.as_model_row()
    pd_value = pred.predict_proba(row)
    approve_max, decline_min = base_thresholds(pred)
    current_band = policy.decide(pd_value, approve_max, decline_min)
    target_band = (
        policy.REFER if current_band == policy.DECLINE else policy.APPROVE
    )

    scenarios = find_counterfactuals(
        raw_row=row,
        predict_fn=pred.predict_proba,
        approve_max_pd=approve_max,
        decline_min_pd=decline_min,
        current_pd=pd_value,
        loan_intent_options=CATEGORY_OPTIONS["loan_intent"],
        max_scenarios=3,
    )

    return CounterfactualResponse(
        model_version=pred.version,
        current_pd=pd_value,
        current_band=current_band,
        target_band=target_band,
        scenarios=[
            CounterfactualScenario(
                change_type=s["change_type"],
                changeability=s["changeability"],
                feature=s["feature"],
                **{"from": s["from"], "to": s["to"]},
                description=s["description"],
                new_pd=s["new_pd"],
                new_band=s["new_band"],
            )
            for s in scenarios
        ],
        disclaimer=DISCLAIMER,
    )


@router.post("/blueprint")
@limiter.limit(get_settings().rate_limit)
def blueprint(request: Request, payload: ApplyRequest) -> dict:
    """The dual-target "How to get approved" roadmap for one applicant."""
    scored = score_row(
        payload.applicant.as_model_row(),
        model_version=payload.model,
        apply_fairness=payload.apply_fairness,
        region=payload.region,
        use_macro_tilt=payload.use_macro_tilt,
        mitigation_attribute=payload.mitigation_attribute,
    )
    pred = get_predictor(payload.model)
    row = _enrich_row(payload.applicant)
    plan = build_blueprint(
        raw_row=row,
        predict_fn=pred.predict_proba,
        approve_max_pd=scored["thresholds"]["approve_max_pd"],
        decline_min_pd=scored["thresholds"]["decline_min_pd"],
        current_pd=scored["probability_of_default"],
        loan_intent_options=CATEGORY_OPTIONS["loan_intent"],
    )
    plan["scoring"] = scored
    return plan
