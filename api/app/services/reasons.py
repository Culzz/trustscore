"""Turn model contributions into plain-language reasons.

The model's SHAP-style contributions arrive aligned with the *transformed*
feature names (for example ``person_home_ownership_RENT`` or ``loan_amnt``).
This module maps each name back to a human factor and a direction, then returns
the strongest few as short sentences.

Applicants never see a raw contribution number. The API exposes only the factor,
a humanised value and a direction ("increases" / "reduces"); the numeric impact
stays inside this module.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REASON_MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "reason_map.json"

# How each numeric feature's value should read in a sentence.
_NUMERIC_FORMAT = {
    "person_age": "{:.0f} years old",
    "person_income": "income of ${:,.0f}",
    "person_emp_length": "{:.1f} years of employment",
    "loan_amnt": "requested amount of ${:,.0f}",
    "loan_int_rate": "interest rate of {:.2f}%",
    "loan_percent_income": "{:.0%} of income",
    "cb_person_cred_hist_length": "{:.0f} year credit history",
}


@lru_cache(maxsize=1)
def reason_map() -> dict:
    with _REASON_MAP_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _base_and_value(transformed_name: str) -> tuple[str, str | None]:
    """Split ``person_home_ownership_RENT`` -> ('person_home_ownership','RENT')."""
    cats = reason_map()["categorical"]
    for base in cats:
        if transformed_name == base:
            return base, None
        if transformed_name.startswith(base + "_"):
            return base, transformed_name[len(base) + 1 :]
    return transformed_name, None


def _format_numeric(name: str, raw_row: dict) -> str:
    value = raw_row.get(name)
    if value is None:
        return "not provided"
    if name in ("emp_length_missing", "int_rate_missing"):
        return "not provided"
    if name in _NUMERIC_FORMAT:
        try:
            return _NUMERIC_FORMAT[name].format(float(value))
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def top_reasons(
    contributions: list[float],
    feature_names: list[str],
    raw_row: dict,
    k: int = 5,
) -> list[dict]:
    """Return the ``k`` strongest reasons for one prediction.

    ``contributions`` must exclude the model bias term (LightGBM appends it as
    the final column; the caller drops it).
    """
    rmap = reason_map()
    numeric = rmap["numeric"]
    categorical = rmap["categorical"]

    scored: list[dict] = []
    for name, contrib in zip(feature_names, contributions):
        contrib = float(contrib)
        if abs(contrib) < 1e-9:
            continue
        base, value = _base_and_value(name)
        direction = "increases" if contrib > 0 else "reduces"

        if value is None and base in numeric:
            label = numeric[base]["label"]
            detail = _format_numeric(base, raw_row)
            text = f"{label} ({detail}) {direction} the estimated risk."
            factor = label
        elif value is not None and base in categorical:
            label = categorical[base]["label"]
            value_label = categorical[base]["values"].get(value, value)
            detail = value_label
            text = f"{label} — {value_label} — {direction} the estimated risk."
            factor = label
        else:
            # Unknown feature: degrade gracefully rather than crash the request.
            factor = base.replace("_", " ").title()
            detail = value or ""
            text = f"{factor} {direction} the estimated risk."

        scored.append(
            {
                "factor": factor,
                "detail": detail,
                "direction": direction,
                "text": text,
                "_impact": abs(contrib),  # internal ordering only; not serialised
            }
        )

    scored.sort(key=lambda r: r["_impact"], reverse=True)
    for r in scored:
        r.pop("_impact", None)
    return scored[:k]
