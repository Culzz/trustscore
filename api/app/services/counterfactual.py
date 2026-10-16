"""Feasible counterfactual search with hard constraints.

Given an applicant and the current decision band, we look for small, *feasible*
changes that would move them into a better band. The rules come straight from
the project spec:

* **Changeable by the applicant:** the requested loan amount.
* **Potentially changeable:** the loan purpose (a different use of funds).
* **Immutable / never suggested:** age, home ownership, loan grade, employment
  length, prior default flag, credit history length, income and the interest
  rate -- the last two are set by circumstances or the lender, not by the
  applicant at the point of application.

Protected attributes are never suggested, even if they were present in the data.

The search is a small greedy sweep, not an optimiser: it evaluates a bounded set
of candidate rows, keeps the ones that reach the target band, and returns the
cheapest ones. Nothing here guarantees approval -- the response carries that
disclaimer.
"""
from __future__ import annotations

from typing import Callable

from .decision import APPROVE, DECLINE, REFER, decide

# Lower rank is safer.
_RANK = {APPROVE: 0, REFER: 1, DECLINE: 2}

_DEFAULT_LOAN_INTENTS = [
    "DEBTCONSOLIDATION",
    "EDUCATION",
    "HOMEIMPROVEMENT",
    "MEDICAL",
    "PERSONAL",
    "VENTURE",
]

_LOAN_AMNT_MIN = 500.0


def band_rank(band: str) -> int:
    return _RANK.get(band, 99)


def _with_loan_amount(row: dict, amount: float) -> dict:
    new = dict(row)
    new["loan_amnt"] = float(amount)
    income = float(new.get("person_income") or 0)
    new["loan_percent_income"] = (float(amount) / income) if income > 0 else 0.0
    return new


def _with_loan_intent(row: dict, intent: str) -> dict:
    new = dict(row)
    new["loan_intent"] = intent
    return new


def _amount_candidates(current: float, steps: int = 8) -> list[float]:
    """A downward sweep of feasible loan amounts."""
    current = float(current)
    if current <= _LOAN_AMNT_MIN:
        return []
    floor = max(_LOAN_AMNT_MIN, current * 0.2)
    raw = [current * f for f in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.25)]
    seen: list[float] = []
    for v in raw:
        v = round(max(v, floor), -1)
        if _LOAN_AMNT_MIN <= v < current and v not in seen:
            seen.append(v)
    seen.sort(reverse=True)
    return seen[:steps]


def find_counterfactuals(
    raw_row: dict,
    predict_fn: Callable[[dict], float],
    approve_max_pd: float,
    decline_min_pd: float,
    current_pd: float,
    loan_intent_options: list[str] | None = None,
    max_scenarios: int = 3,
) -> list[dict]:
    """Return up to ``max_scenarios`` feasible changes that improve the band."""
    current_band = decide(current_pd, approve_max_pd, decline_min_pd)
    if current_band == APPROVE:
        return []  # already in the best band; nothing to suggest

    target_band = REFER if current_band == DECLINE else APPROVE
    target_rank = band_rank(target_band)
    current_rank = band_rank(current_band)

    intent_options = loan_intent_options or _DEFAULT_LOAN_INTENTS
    current_intent = raw_row.get("loan_intent")
    current_amount = float(raw_row.get("loan_amnt") or 0)

    candidates: list[dict] = []

    # --- changeable: requested amount -------------------------------------
    for amount in _amount_candidates(current_amount):
        row = _with_loan_amount(raw_row, amount)
        pd = float(predict_fn(row))
        band = decide(pd, approve_max_pd, decline_min_pd)
        if band_rank(band) <= target_rank < current_rank or band_rank(band) < current_rank:
            reduction = current_amount - amount
            candidates.append(
                {
                    "change_type": "loan_amount",
                    "changeability": "changeable_by_applicant",
                    "feature": "loan_amnt",
                    "from": current_amount,
                    "to": amount,
                    "description": (
                        f"Reduce the requested amount by ${reduction:,.0f} "
                        f"to ${amount:,.0f}."
                    ),
                    "new_pd": pd,
                    "new_band": band,
                    "_cost": reduction,
                }
            )
            if band_rank(band) <= target_rank:
                break  # smallest sufficient reduction for this lever

    # --- potentially changeable: loan purpose ------------------------------
    for intent in intent_options:
        if intent == current_intent:
            continue
        row = _with_loan_intent(raw_row, intent)
        pd = float(predict_fn(row))
        band = decide(pd, approve_max_pd, decline_min_pd)
        if band_rank(band) < current_rank:
            candidates.append(
                {
                    "change_type": "loan_intent",
                    "changeability": "potentially_changeable",
                    "feature": "loan_intent",
                    "from": current_intent,
                    "to": intent,
                    "description": (
                        f"A different loan purpose ({intent.title()}) may lower "
                        "the estimated risk."
                    ),
                    "new_pd": pd,
                    "new_band": band,
                    "_cost": 0.0,
                }
            )

    # Best first: biggest band improvement, then cheapest change, then lowest PD.
    candidates.sort(
        key=lambda c: (band_rank(c["new_band"]), c["_cost"], c["new_pd"])
    )

    # Keep the best candidate per lever so the list is easy to read.
    seen_levers: set[str] = set()
    out: list[dict] = []
    for c in candidates:
        lever = f"{c['change_type']}:{c['to']}"
        if lever in seen_levers:
            continue
        seen_levers.add(lever)
        c.pop("_cost", None)
        out.append(c)
        if len(out) >= max_scenarios:
            break
    return out
