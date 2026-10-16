"""Metadata endpoints: /health, /model, /stats."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import db
from ..core.model import get_predictor, load_metadata
from ..schemas import HealthResponse, StatsResponse

router = APIRouter(tags=["metadata"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Service status. Never fails: reports what is and isn't wired up."""
    model_version = None
    model_loaded = False
    try:
        pred = get_predictor()
        model_version = pred.version
        model_loaded = True
    except Exception:
        model_version = load_metadata().get("version")
    return HealthResponse(
        status="ok",
        model_version=model_version,
        model_loaded=model_loaded,
        database_configured=db.is_enabled(),
        time=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/model")
def model_card_data() -> dict:
    """Model card data: version, metrics, calibration, thresholds, fairness."""
    metadata = load_metadata()
    if not metadata:
        raise HTTPException(
            status_code=503,
            detail="Model metadata not found. Run training to generate it.",
        )
    return metadata


@router.get("/stats", response_model=StatsResponse)
def stats(window_days: int = 30) -> StatsResponse:
    """Live, anonymised counters for the lender dashboard."""
    return StatsResponse(**db.get_stats(window_days=window_days))
