"""A small, deterministic "feature store" for macro-economic context.

The blueprint asks for point-in-time macro features (prime rate, regional
unemployment) to be joined onto the applicant vector before scoring. A real
feature store (Feast/Tecton) needs infrastructure this project does not have, so
this is an **honest mock**: a seeded, reproducible generator keyed by region and
month.

It is used in two legitimate places rather than being bolted onto the model:

1. **Context display** -- the applicant and audit views show the macro backdrop
   the decision was made in.
2. **Policy tilt** -- the cost-based thresholds are nudged by the credit cycle.
   Lending policy genuinely tightens when unemployment rises; making that
   explicit is better than pretending the threshold is a constant.

Injected macro features are *not* added to the model's input vector: they were
not part of the training distribution, and adding untrained features would make
the model worse, not better. That deviation from the blueprint is deliberate and
documented.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

REGIONS = [
    {"id": "national", "label": "National"},
    {"id": "north-east", "label": "North East"},
    {"id": "south-west", "label": "South West"},
    {"id": "mid-west", "label": "Mid West"},
]

# Anchor values around the training era; the mock oscillates deterministically
# around these.
_ANCHOR = {
    "prime_rate": 8.5,
    "unemployment_rate": 5.4,
    "cpi_yoy": 3.2,
    "delinquency_rate": 2.1,
}


def _noise(region: str, month: str, field: str) -> float:
    """Deterministic pseudo-random value in [-1, 1] for (region, month, field)."""
    digest = hashlib.sha256(f"{region}|{month}|{field}".encode()).hexdigest()
    return (int(digest[:8], 16) / float(1 << 32)) * 2.0 - 1.0


def _month_key(when: datetime) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def macro_context(region: str = "national", as_of: datetime | None = None) -> dict:
    """Return the macro backdrop for a region and month. Deterministic."""
    when = as_of or datetime.now(timezone.utc)
    month = _month_key(when)
    if region not in {r["id"] for r in REGIONS}:
        region = "national"

    def value(field: str, scale: float) -> float:
        return round(_ANCHOR[field] + _noise(region, month, field) * scale, 2)

    prime = value("prime_rate", 1.5)
    unemployment = value("unemployment_rate", 1.2)
    cpi = value("cpi_yoy", 1.0)
    delinquency = value("delinquency_rate", 0.6)

    # A single 0-1 "tilt": 0 = benign cycle, 1 = stressed cycle.
    tilt = min(1.0, max(0.0, (unemployment - 3.5) / 4.0))

    return {
        "region": region,
        "region_label": next(r["label"] for r in REGIONS if r["id"] == region),
        "as_of": when.isoformat(),
        "month": month,
        "prime_rate": prime,
        "unemployment_rate": unemployment,
        "cpi_yoy": cpi,
        "delinquency_rate": delinquency,
        "cycle_tilt": round(tilt, 3),
        "source": "synthetic (mock feature store, seeded and reproducible)",
        "note": (
            "Macro context is shown for transparency and tilts policy thresholds; "
            "it is not an input to the trained model."
        ),
    }


def adjust_thresholds(
    approve_max_pd: float,
    decline_min_pd: float,
    context: dict | None,
    strength: float = 0.5,
) -> tuple[float, float, dict]:
    """Tilt the policy thresholds with the credit cycle.

    In a stressed cycle (tilt -> 1) the approve threshold tightens and the
    decline threshold loosens, i.e. policy leans conservative.
    """
    if not context:
        return approve_max_pd, decline_min_pd, {"applied": False}
    tilt = float(context.get("cycle_tilt", 0.0)) * float(strength)
    adj_approve = approve_max_pd * (1.0 - tilt)
    adj_decline = min(0.99, decline_min_pd * (1.0 + tilt * 0.5))
    if adj_decline <= adj_approve:
        adj_decline = min(0.99, adj_approve + 0.05)
    return (
        float(adj_approve),
        float(adj_decline),
        {
            "applied": True,
            "strength": strength,
            "cycle_tilt": context.get("cycle_tilt"),
            "approve_max_pd_before": float(approve_max_pd),
            "approve_max_pd_after": float(adj_approve),
            "decline_min_pd_before": float(decline_min_pd),
            "decline_min_pd_after": float(adj_decline),
        },
    )
