"""The "How to get approved" roadmap: feasible, dual-target, self-serve recourse.

Where ``counterfactual.py`` returns a flat list of changes, this module turns the
same search into a *plan* an applicant can act on:

* **Routes** -- independent ways forward (ask for less, choose a different
  purpose, do both), each with the exact numbers and the resulting band.
* **Dual-target framing** -- "reduce the amount by $A *or* increase your
  documented income by $B", because two different applicants can reach the same
  band by different means. Income is shown as an *informational* option only: it
  is rarely within an applicant's control, so it is never the headline.
* **"Already approved" is a first-class answer** -- no fake hurdles.

Everything is computed by calling the real model, so the numbers are honest
under the current thresholds. Nothing here guarantees an outcome.
"""
from __future__ import annotations

from typing import Callable

from .counterfactual import band_rank
from .decision import APPROVE, DECLINE, REFER, decide

LOAN_AMNT_MIN = 500.0
INCOME_STEP_MAX = 5.0  # never suggest more than a 5x income increase

# The three-way actionability taxonomy the applicant sees. Immutable factors are
# never suggested; they are listed separately so the applicant can see what was
# deliberately *not* used against them.
ACTIONABILITY = {
    "changeable_by_applicant": "actionable",
    "potentially_changeable": "potentially_actionable",
    "milestone": "actionable",
}

IMMUTABLE_FIELDS = [
    {"field": "person_age", "reason": "Age cannot be changed and is never suggested."},
    {"field": "person_home_ownership", "reason": "Housing tenure is a circumstance, not an action."},
    {"field": "loan_grade", "reason": "Assigned by the lender, not chosen by the applicant."},
    {"field": "person_emp_length", "reason": "Employment history accrues over time."},
    {"field": "cb_person_default_on_file", "reason": "A past default cannot be undone."},
    {"field": "cb_person_cred_hist_length", "reason": "Credit history length accrues over time."},
    {"field": "loan_int_rate", "reason": "Set by the lender."},
    {"field": "person_income", "reason": "Informational only; never the headline suggestion."},
]

ACTIONABILITY_LEGEND = {
    "actionable": "A change the applicant can make directly before applying.",
    "potentially_actionable": "A change that depends on the applicant's real circumstances.",
    "immutable": "Cannot be changed; shown only so it is clear what was not used.",
}


def _variant(row: dict, **changes) -> dict:
    new = dict(row)
    new.update(changes)
    income = float(new.get("person_income") or 0)
    amount = float(new.get("loan_amnt") or 0)
    new["loan_percent_income"] = (amount / income) if income > 0 else 0.0
    return new


def _confidence(pd: float, threshold: float) -> str:
    gap = threshold - pd
    if gap <= 0:
        return "none"
    if gap < 0.01:
        return "borderline"
    if gap < 0.04:
        return "moderate"
    return "comfortable"


def _amount_for_target(
    row: dict,
    predict_fn: Callable[[dict], float],
    target_rank: int,
    approve_max_pd: float,
    decline_min_pd: float,
) -> dict | None:
    """Smallest amount reduction (to the nearest $100) that reaches the target band."""
    current = float(row.get("loan_amnt") or 0)
    if current <= LOAN_AMNT_MIN or target_rank >= band_rank(decide(
        float(predict_fn(row)), approve_max_pd, decline_min_pd
    )):
        return None

    def band_at(amount: float) -> tuple[float, str]:
        pd = float(predict_fn(_variant(row, loan_amnt=amount)))
        return pd, decide(pd, approve_max_pd, decline_min_pd)

    lo, hi = LOAN_AMNT_MIN, current
    best: tuple[float, float, str] | None = None
    for _ in range(24):  # ~24 iterations resolves to well under $100
        mid = max(LOAN_AMNT_MIN, round((lo + hi) / 2 / 100.0) * 100.0)
        pd, band = band_at(mid)
        if band_rank(band) <= target_rank:
            best = (mid, pd, band)
            hi = mid
        else:
            lo = mid
        if hi - lo < 50:
            break
    if best is None:
        pd, band = band_at(LOAN_AMNT_MIN)
        if band_rank(band) > target_rank:
            return None
        best = (LOAN_AMNT_MIN, pd, band)
    amount, pd, band = best
    reduction = current - amount
    return {
        "amount": float(amount),
        "reduction": float(reduction),
        "new_pd": float(pd),
        "new_band": band,
        "confidence": _confidence(pd, approve_max_pd),
    }


def _income_for_target(
    row: dict,
    predict_fn: Callable[[dict], float],
    target_rank: int,
    approve_max_pd: float,
    decline_min_pd: float,
) -> dict | None:
    """Informational: the documented income that would reach the target band."""
    current = float(row.get("person_income") or 0)
    if current <= 0:
        return None
    cap = current * INCOME_STEP_MAX
    hi = current
    found: tuple[float, float, str] | None = None
    for _ in range(8):
        hi = min(hi * 1.6, cap)
        pd = float(predict_fn(_variant(row, person_income=hi)))
        band = decide(pd, approve_max_pd, decline_min_pd)
        if band_rank(band) <= target_rank:
            found = (hi, pd, band)
            break
        if hi >= cap:
            break  # outside a plausible range; do not suggest it
    if found is None:
        return None
    lo = current
    hi_found = found[0]
    best = found
    for _ in range(24):
        mid = (lo + hi_found) / 2
        pd = float(predict_fn(_variant(row, person_income=mid)))
        band = decide(pd, approve_max_pd, decline_min_pd)
        if band_rank(band) <= target_rank:
            best = (mid, pd, band)
            hi_found = mid
        else:
            lo = mid
        if hi_found - lo < 250:
            break
    income, pd, band = best
    return {
        "income": float(round(income, -2)),
        "increase": float(round(income - current, -2)),
        "new_pd": float(pd),
        "new_band": band,
        "confidence": _confidence(pd, approve_max_pd),
        "within_control": False,
    }


def build_blueprint(
    raw_row: dict,
    predict_fn: Callable[[dict], float],
    approve_max_pd: float,
    decline_min_pd: float,
    current_pd: float,
    loan_intent_options: list[str] | None = None,
) -> dict:
    """Return a structured, dual-target recourse plan."""
    row = dict(raw_row)
    row["_approve_max_pd"] = approve_max_pd
    row["_decline_min_pd"] = decline_min_pd

    current_band = decide(current_pd, approve_max_pd, decline_min_pd)
    if current_band == APPROVE:
        return {
            "status": "already_approved",
            "current_band": current_band,
            "current_pd": float(current_pd),
            "target_band": APPROVE,
            "routes": [],
            "dual_target": None,
            "summary": (
                "No changes needed under the criteria applied today. The factors "
                "below kept this application in the approve band."
            ),
        }

    # Aim at approve, but if that is out of reach show the intermediate step.
    intent_options = loan_intent_options or []
    current_intent = raw_row.get("loan_intent")

    routes: list[dict] = []

    # --- Route 1: ask for less -------------------------------------------
    amount_plan = _amount_for_target(
        row, predict_fn, band_rank(APPROVE), approve_max_pd, decline_min_pd
    )
    if amount_plan:
        routes.append(
            {
                "id": "reduce_amount",
                "kind": "changeable_by_applicant",
                "headline": "Ask for a smaller amount",
                "detail": (
                    f"Reduce the requested amount by "
                    f"${amount_plan['reduction']:,.0f} to "
                    f"${amount_plan['amount']:,.0f}."
                ),
                "metrics": amount_plan,
            }
        )

    # --- Route 2: a different purpose ------------------------------------
    best_intent = None
    for intent in intent_options:
        if intent == current_intent:
            continue
        pd = float(predict_fn(_variant(row, loan_intent=intent)))
        band = decide(pd, approve_max_pd, decline_min_pd)
        if band_rank(band) < band_rank(current_band):
            if best_intent is None or pd < best_intent[1]:
                best_intent = (intent, pd, band)
    if best_intent:
        intent, pd, band = best_intent
        routes.append(
            {
                "id": "change_purpose",
                "kind": "potentially_changeable",
                "headline": "Choose a different loan purpose",
                "detail": (
                    f"If the funds are for {intent.replace('_', ' ').title()}, "
                    "selecting that purpose changes the estimate."
                ),
                "metrics": {
                    "intent": intent,
                    "new_pd": float(pd),
                    "new_band": band,
                    "confidence": _confidence(pd, approve_max_pd),
                },
            }
        )

    # --- Route 3: do both -------------------------------------------------
    if amount_plan and best_intent:
        combined = _variant(row, loan_amnt=amount_plan["amount"], loan_intent=best_intent[0])
        pd = float(predict_fn(combined))
        band = decide(pd, approve_max_pd, decline_min_pd)
        routes.append(
            {
                "id": "combined",
                "kind": "changeable_by_applicant",
                "headline": "Do both of the above",
                "detail": (
                    f"Reduce the amount to ${amount_plan['amount']:,.0f} and select "
                    f"{best_intent[0].replace('_', ' ').title()} as the purpose."
                ),
                "metrics": {
                    "amount": amount_plan["amount"],
                    "intent": best_intent[0],
                    "new_pd": float(pd),
                    "new_band": band,
                    "confidence": _confidence(pd, approve_max_pd),
                },
            }
        )

    # --- Route to the intermediate band (decline -> refer) ---------------
    if current_band == DECLINE and band_rank(current_band) > band_rank(REFER):
        refer_plan = _amount_for_target(
            row, predict_fn, band_rank(REFER), approve_max_pd, decline_min_pd
        )
        if refer_plan and (not amount_plan or refer_plan["reduction"] < amount_plan["reduction"]):
            routes.append(
                {
                    "id": "reach_review",
                    "kind": "milestone",
                    "headline": "Or simply reach a manual review",
                    "detail": (
                        f"Reducing the amount by ${refer_plan['reduction']:,.0f} "
                        "would move this into the review band, where a human looks "
                        "at the file."
                    ),
                    "metrics": refer_plan,
                }
            )

    # --- Dual-target framing ---------------------------------------------
    dual = None
    income_plan = _income_for_target(
        row, predict_fn, band_rank(APPROVE), approve_max_pd, decline_min_pd
    )
    options = []
    if amount_plan:
        options.append(
            {
                "change": f"Reduce the requested amount by ${amount_plan['reduction']:,.0f}",
                "new_band": amount_plan["new_band"],
                "confidence": amount_plan["confidence"],
                "within_control": True,
            }
        )
    if income_plan:
        options.append(
            {
                "change": (
                    f"Document ${income_plan['increase']:,.0f} more in annual income"
                ),
                "new_band": income_plan["new_band"],
                "confidence": income_plan["confidence"],
                "within_control": False,
            }
        )
    if len(options) >= 2:
        dual = {
            "headline": "Two independent ways to reach the approve band",
            "options": options,
            "note": (
                "These are alternatives, not requirements. The income route is "
                "shown for transparency because the model responds to it, but it "
                "is usually outside an applicant's direct control, so it is never "
                "the headline suggestion."
            ),
        }

    for route in routes:
        route["actionability"] = ACTIONABILITY.get(route["kind"], "actionable")
        route["guarantees_outcome"] = False

    routes.sort(key=lambda r: (band_rank(r["metrics"]["new_band"]), r["metrics"]["new_pd"]))
    actionable_routes = [r for r in routes if r["actionability"] == "actionable"]

    return {
        "status": "actionable" if routes else "blocked",
        "current_band": current_band,
        "current_pd": float(current_pd),
        "target_band": APPROVE,
        "pd_to_approve_threshold": float(
            max(0.0, current_pd - approve_max_pd)
        ),
        "headroom_if_approved": None,
        "routes": routes,
        "route_summary": {
            "n_routes": len(routes),
            "n_actionable": len(actionable_routes),
            "has_actionable_route": bool(actionable_routes),
        },
        "actionability_legend": ACTIONABILITY_LEGEND,
        "immutable_fields": IMMUTABLE_FIELDS,
        "dual_target": dual,
        "summary": (
            "Each route below is a change the applicant can consider. They are "
            "simulated against the current model and policy."
            if routes
            else "Under the current criteria the model finds no feasible change "
            "from the applicant-controlled fields."
        ),
        "no_route_reason": None
        if routes
        else (
            "No change to the fields an applicant controls (requested amount, loan "
            "purpose) moved this application into a better band within a plausible "
            "range. This is a statement about the simulated model, not a prediction "
            "of how any real lender would decide."
        ),
        "disclaimer": (
            "Scenarios are model-generated estimates, not promises. They do not "
            "guarantee an approval, and no real lender has agreed to them. "
            "Approval also depends on information not shown here."
        ),
    }
