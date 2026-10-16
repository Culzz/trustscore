"""Scoring endpoints: /predict, /explain, /decision, /counterfactual."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request

from .. import db
from ..core.config import get_settings
from ..core.features import CATEGORY_OPTIONS
from ..core.model import get_predictor
from ..limiter import limiter
from ..schemas import (
    DISCLAIMER,
    Applicant,
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
from ..services.counterfactual import find_counterfactuals
from ..services.reasons import top_reasons

router = APIRouter(tags=["scoring"])


def _thresholds(pred) -> tuple[float, float]:
    thr = pred.thresholds or {}
    return (
        float(thr.get("approve_max_pd", 0.10)),
        float(thr.get("decline_min_pd", 0.50)),
    )


def _enrich_row(applicant: Applicant) -> dict:
    """Add derived values so explanations can describe them."""
    row = applicant.as_model_row()
    income = float(row.get("person_income") or 0)
    row["loan_percent_income"] = (
        float(row["loan_amnt"]) / income if income > 0 else 0.0
    )
    return row


@router.post("/predict", response_model=PredictResponse)
@limiter.limit(get_settings().rate_limit)
def predict(request: Request, applicant: Applicant) -> PredictResponse:
    """Calibrated probability of default, band, model version and prediction id."""
    pred = get_predictor()
    pd_value = pred.predict_proba(applicant.as_model_row())
    approve_max, decline_min = _thresholds(pred)
    band = policy.decide(pd_value, approve_max, decline_min)

    prediction_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    db.log_prediction(
        prediction_id=prediction_id,
        model_version=pred.version,
        probability_of_default=pd_value,
        band=band,
        decision=band,
        exposure=applicant.loan_amnt,
    )
    return PredictResponse(
        prediction_id=prediction_id,
        model_version=pred.version,
        probability_of_default=pd_value,
        band=band,
        band_label=policy.band_label(band),
        thresholds=Thresholds(approve_max_pd=approve_max, decline_min_pd=decline_min),
        created_at=created_at,
    )


@router.post("/explain", response_model=ExplainResponse)
@limiter.limit(get_settings().rate_limit)
def explain(request: Request, applicant: Applicant) -> ExplainResponse:
    """The strongest plain-language reasons for this applicant's estimate."""
    pred = get_predictor()
    row = _enrich_row(applicant)
    pd_value = pred.predict_proba(applicant.as_model_row())
    contribs, names = pred.contributions(applicant.as_model_row())
    reasons = top_reasons(contribs, names, row, k=5)

    approve_max, decline_min = _thresholds(pred)
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
    pred = get_predictor()
    applicant = payload.applicant
    pd_value = pred.predict_proba(applicant.as_model_row())

    default_approve, default_decline = _thresholds(pred)
    approve_max = payload.approve_max_pd if payload.approve_max_pd is not None else default_approve
    decline_min = payload.decline_min_pd if payload.decline_min_pd is not None else default_decline
    if decline_min <= approve_max:
        # Keep the bands sane if a caller passes crossing thresholds.
        decline_min = min(0.99, approve_max + 0.01)

    band = policy.decide(pd_value, approve_max, decline_min)
    costs = policy.CostMatrix.from_dict(pred.cost_matrix or {})
    exposure = float(applicant.loan_amnt)
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
        model_version=pred.version,
    )


@router.post("/counterfactual", response_model=CounterfactualResponse)
@limiter.limit(get_settings().rate_limit)
def counterfactual(request: Request, applicant: Applicant) -> CounterfactualResponse:
    """Feasible changes that could move this applicant to a better band."""
    pred = get_predictor()
    row = applicant.as_model_row()
    pd_value = pred.predict_proba(row)
    approve_max, decline_min = _thresholds(pred)
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
