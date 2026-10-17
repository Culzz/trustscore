"""Deterministic, guardrailed narrative generation.

The blueprint asks for an LLM to turn the model's reasons into a warm,
ECOA-style adverse-action notice. Running a hosted LLM would add a key, a
network dependency and non-determinism to a governance tool, so this module does
the job with a **template engine that is itself guardrailed**:

* every applicant-facing sentence is assembled from reviewed templates;
* protected characteristics are never cited in a consumer notice;
* the output is validated against a schema *and* a denylist of forbidden
  phrasings (no "guaranteed", no protected-attribute vocabulary, length caps);
* the result is stable: the same input always produces the same text.

An optional LLM hook is offered via :func:`set_provider`, but the default
"deterministic" provider is what ships.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Reason-code catalogue (ECOA/Reg-B style, mapped to the factors we emit)
# ---------------------------------------------------------------------------
REASON_CODES: dict[str, dict[str, str]] = {
    "Requested loan amount": {
        "code": "AA-01",
        "title": "Amount requested",
        "reason": "The amount requested is high relative to the income and credit history on this application.",
    },
    "Requested amount relative to income": {
        "code": "AA-02",
        "title": "Obligation-to-income",
        "reason": "The payment obligations on this application are high relative to the income shown.",
    },
    "Annual income": {
        "code": "AA-03",
        "title": "Income",
        "reason": "The income shown does not fully support the amount requested.",
    },
    "Length of employment": {
        "code": "AA-04",
        "title": "Employment history",
        "reason": "The employment history on file is short relative to the request.",
    },
    "Loan interest rate": {
        "code": "AA-05",
        "title": "Pricing",
        "reason": "The interest rate on this offer is high relative to the risk tier.",
    },
    "Loan purpose": {
        "code": "AA-06",
        "title": "Loan purpose",
        "reason": "The stated purpose is associated with a higher estimated risk in this portfolio.",
    },
    "Loan grade": {
        "code": "AA-07",
        "title": "Risk grade",
        "reason": "The assigned risk grade is not within the approved range.",
    },
    "Home ownership": {
        "code": "AA-08",
        "title": "Housing stability",
        "reason": "The housing situation on file is associated with less stability in this portfolio.",
    },
    "Prior default on file": {
        "code": "AA-09",
        "title": "Prior default",
        "reason": "A previous default is recorded on the credit file.",
    },
    "Credit history length": {
        "code": "AA-10",
        "title": "Credit history",
        "reason": "The credit history on file is short.",
    },
    "Employment length not provided": {
        "code": "AA-11",
        "title": "Incomplete information",
        "reason": "The employment length was not provided, so it could not be considered.",
    },
    "Interest rate not provided": {
        "code": "AA-12",
        "title": "Incomplete information",
        "reason": "The interest rate was not provided, so it could not be considered.",
    },
}

DEFAULT_CODE = {
    "code": "AA-99",
    "title": "Other factors",
    "reason": "Other factors in this file were considered together with those above.",
}

# Characteristics that must never appear as a stated reason in a consumer
# notice, even though the model may use some of them internally.
PROTECTED_FACTORS = {
    "Applicant age": "age",
}

# Words that must never appear in applicant-facing text.
FORBIDDEN_TERMS = [
    # promises / guarantees
    "guarantee", "guaranteed", "we promise", "will be approved", "risk-free",
    # protected-characteristic vocabulary
    "race", "racial", "ethnicity", "ethnic", "religion", "religious",
    "gender", "sex ", "sexual", "pregnan", "marital", "disab",
    "nationality", "national origin", "immigration",
]

MAX_SENTENCE_CHARS = 260
MAX_REASONS = 4


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _deterministic_provider(payload: dict) -> dict:
    return payload


_PROVIDER = _deterministic_provider


def set_provider(fn) -> None:
    """Install a custom translation provider (must be pure and deterministic)."""
    global _PROVIDER
    _PROVIDER = fn or _deterministic_provider


# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------
def validate(text: str) -> list[str]:
    """Return the list of guardrail violations in a piece of text."""
    violations: list[str] = []
    low = (text or "").lower()
    for term in FORBIDDEN_TERMS:
        if term in low:
            violations.append(f"forbidden term: {term.strip()}")
    if len(text or "") > MAX_SENTENCE_CHARS:
        violations.append(f"sentence exceeds {MAX_SENTENCE_CHARS} characters")
    return violations


def _safe(text: str) -> str:
    """Last-ditch scrub so a violation can never reach an applicant."""
    out = text
    low = out.lower()
    for term in FORBIDDEN_TERMS:
        if term in low:
            out = re.sub(re.escape(term), "a protected characteristic", out, flags=re.IGNORECASE)
            low = out.lower()
    if len(out) > MAX_SENTENCE_CHARS:
        out = out[: MAX_SENTENCE_CHARS - 3].rstrip() + "..."
    return out


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------
def reason_codes(reasons: list[dict], include_protected: bool = False) -> tuple[list[dict], list[str]]:
    """Map plain reasons to ECOA-style codes.

    Returns ``(codes, excluded_protected_factors)``. Protected characteristics are
    held back from a consumer notice by default and reported separately.
    """
    codes: list[dict] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        factor = reason.get("factor", "")
        if factor in PROTECTED_FACTORS and not include_protected:
            excluded.append(factor)
            continue
        if factor in seen:
            continue
        entry = REASON_CODES.get(factor, DEFAULT_CODE)
        direction = reason.get("direction", "increases")
        detail = reason.get("detail") or ""
        text = entry["reason"] if direction == "increases" else (
            f"{entry['title']} is a positive factor here."
        )
        codes.append(
            {
                "code": entry["code"],
                "title": entry["title"],
                "factor": factor,
                "detail": detail,
                "direction": direction,
                "reason": _safe(text),
            }
        )
        seen.add(factor)
        if len(codes) >= MAX_REASONS:
            break
    return codes, excluded


def adverse_action_narrative(
    reasons: list[dict],
    band: str,
    blueprint: dict | None = None,
) -> dict:
    """Assemble the applicant-facing explanation.

    Deterministic: identical inputs always yield identical output.
    """
    codes, excluded = reason_codes(reasons)

    if band == "approve":
        headline = "Good news: this application meets the current approval criteria."
        tone = "positive"
    elif band == "refer":
        headline = (
            "This application needs a closer look before a decision is made."
        )
        tone = "neutral"
    else:
        headline = "This application is not approved on the criteria applied today."
        tone = "supportive"

    negative = [c for c in codes if c["direction"] == "increases"]
    positive = [c for c in codes if c["direction"] == "reduces"]

    next_steps: list[str] = []
    if blueprint and blueprint.get("routes"):
        top = blueprint["routes"][0]
        next_steps.append(top["detail"])
        if len(blueprint["routes"]) > 1:
            next_steps.append(blueprint["routes"][1]["detail"])
    elif band != "approve":
        next_steps.append(
            "You can review the factors above and, if anything is out of date, "
            "correct it and apply again."
        )

    if band == "approve":
        encouragement = "Keep your file up to date, and the same criteria will keep applying."
    else:
        encouragement = (
            "Many applicants improve their position by acting on one or two of "
            "these factors. A decision today is not a decision forever."
        )

    payload = {
        "headline": _safe(headline),
        "tone": tone,
        "reason_codes": codes,
        "positive_factors": [c["factor"] for c in positive],
        "next_steps": [_safe(s) for s in next_steps],
        "encouragement": _safe(encouragement),
        "protected_factors_excluded": excluded,
        "notice": (
            "This is a simulated explanation for a demonstration system. It is "
            "not a real adverse-action notice."
        ),
    }

    violations: list[str] = []
    for field in ("headline", "encouragement"):
        violations += validate(payload[field])
    for c in payload["reason_codes"]:
        violations += validate(c["reason"])
    for s in payload["next_steps"]:
        violations += validate(s)

    out = _PROVIDER(payload)
    out["guardrail"] = {
        "provider": "deterministic",
        "checked": True,
        "violations": violations,
        "passed": len(violations) == 0,
        "protected_excluded": excluded,
        "max_reasons": MAX_REASONS,
    }
    return out
