"""The asynchronous application flow.

One applicant goes through a small pipeline. Each milestone is emitted as it
completes so the UI can stream progress rather than stare at a spinner:

    validated -> scored -> explained -> recourse -> complete

The same function backs both execution paths:

* the **in-process** runner (``jobs.py``) on Vercel, and
* the **Celery worker** (``api/worker.py``) on Docker/Render,

so the two never drift.
"""
from __future__ import annotations

from typing import Callable

from ..core.features import CATEGORY_OPTIONS
from . import cache
from .blueprint import build_blueprint
from .counterfactual import find_counterfactuals
from .pipeline import score_row
from .reasons import top_reasons

Emit = Callable[[dict], None]


def run_application(payload: dict, emit: Emit) -> dict:
    applicant: dict = dict(payload["applicant"])
    model_version = payload.get("model")
    apply_fairness = bool(payload.get("apply_fairness", False))
    region = payload.get("region", "national")
    use_macro_tilt = bool(payload.get("use_macro_tilt", False))

    emit({"step": "validated", "status": "done", "label": "Application validated"})

    scored = score_row(
        applicant,
        model_version=model_version,
        apply_fairness=apply_fairness,
        region=region,
        use_macro_tilt=use_macro_tilt,
    )
    emit(
        {
            "step": "scored",
            "status": "done",
            "label": "Risk estimate computed",
            "band": scored["final_band"],
            "probability_of_default": scored["probability_of_default"],
        }
    )

    # -- explanations ------------------------------------------------------
    from ..core.model import get_predictor  # local import keeps import cost low

    pred = get_predictor(model_version)
    contribs, names = pred.contributions(applicant)
    row = dict(applicant)
    income = float(row.get("person_income") or 0)
    row["loan_percent_income"] = float(row.get("loan_amnt") or 0) / income if income > 0 else 0.0
    reasons = top_reasons(contribs, names, row, k=5)

    approve_max = scored["thresholds"]["approve_max_pd"]
    decline_min = scored["thresholds"]["decline_min_pd"]

    # -- recourse (cached: the search calls the model many times) -----------
    cf_key = cache.make_key("blueprint", applicant, approve_max, decline_min, pred.version)
    blueprint = cache.RECOURSE_CACHE.get(cf_key)
    if blueprint is None:
        blueprint = build_blueprint(
            raw_row=row,
            predict_fn=pred.predict_proba,
            approve_max_pd=approve_max,
            decline_min_pd=decline_min,
            current_pd=scored["probability_of_default"],
            loan_intent_options=CATEGORY_OPTIONS["loan_intent"],
        )
        blueprint["counterfactuals"] = find_counterfactuals(
            raw_row=row,
            predict_fn=pred.predict_proba,
            approve_max_pd=approve_max,
            decline_min_pd=decline_min,
            current_pd=scored["probability_of_default"],
            loan_intent_options=CATEGORY_OPTIONS["loan_intent"],
            max_scenarios=3,
        )
        cache.RECOURSE_CACHE.set(cf_key, blueprint)
    else:
        emit({"step": "recourse", "status": "cached", "label": "Recourse plan (cached)"})

    narrative = cache.NARRATIVE_CACHE.get(cf_key)
    if narrative is None:
        from .narrative import adverse_action_narrative

        narrative = adverse_action_narrative(
            reasons, band=scored["final_band"], blueprint=blueprint
        )
        cache.NARRATIVE_CACHE.set(cf_key, narrative)

    emit({"step": "explained", "status": "done", "label": "Reasons and notice prepared"})
    emit(
        {
            "step": "recourse",
            "status": "done",
            "label": "Recourse plan ready",
            "routes": len(blueprint.get("routes", [])),
        }
    )

    result = {
        "scoring": scored,
        "reasons": reasons,
        "narrative": narrative,
        "blueprint": blueprint,
        "cache": cache.RECOURSE_CACHE.stats(),
    }
    emit({"step": "complete", "status": "done", "label": "Decision ready", "result": result})
    return result
