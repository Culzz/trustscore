"""Asynchronous apply flow: ``POST /apply``, ``GET /jobs/{id}``, ``WS /ws/jobs/{id}``.

The synchronous endpoints stay for compatibility and for tiny calls. This route
is the "stream the milestones" path the applicant UI uses: submit, then watch
``validated -> scored -> explained -> recourse -> complete`` arrive.

WebSockets are only available in the containerised deployment; on Vercel the
client polls ``GET /jobs/{id}`` instead and gets the same events.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from .. import db, jobs
from ..core.config import get_settings
from ..limiter import limiter
from ..schemas import ApplyRequest, JobResponse
from ..services.drift_monitor import bins_for_row

router = APIRouter(tags=["jobs"])


@router.post("/apply", response_model=JobResponse, status_code=202)
@limiter.limit(get_settings().rate_limit)
def apply(request: Request, payload: ApplyRequest) -> JobResponse:
    """Queue an application. Returns immediately with a job id."""
    job_payload = payload.model_dump()
    job_id = jobs.create_job("apply", job_payload)

    # Privacy-safe binned summary for the live drift monitor (never raw values).
    try:
        db.log_prediction_features(job_id, bins_for_row(payload.applicant.model_dump()))
    except Exception:  # pragma: no cover - logging must never break scoring
        pass

    backend = jobs.dispatch(job_id, job_payload)
    job = jobs.get_job(job_id) or {}
    job["backend"] = backend
    return JobResponse(**job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: str) -> JobResponse:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    return JobResponse(**job)


@router.websocket("/ws/jobs/{job_id}")
async def job_stream(websocket: WebSocket, job_id: str) -> None:
    """Stream milestones for a job as they happen."""
    await websocket.accept()
    try:
        async for event in jobs.subscribe(job_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:  # pragma: no cover - client went away
        pass
    except Exception as exc:  # pragma: no cover - defensive
        try:
            await websocket.send_json({"step": "error", "status": "error", "error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
