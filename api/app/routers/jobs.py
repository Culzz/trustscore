"""Asynchronous apply flow: ``POST /apply``, ``GET /jobs/{id}``, ``WS /ws/jobs/{id}``.

The synchronous endpoints stay for compatibility and for tiny calls. This route
is the "stream the milestones" path the applicant UI uses: submit, then watch
``validated -> scored -> explained -> recourse -> complete`` arrive.

WebSockets are only available in the containerised deployment; on Vercel the
client polls ``GET /jobs/{id}`` instead and gets the same events.
"""
# NOTE: deliberately no ``from __future__ import annotations`` here. FastAPI
# evaluates endpoint annotations against the decorated callable's globals, and
# slowapi's ``@limiter.limit`` wrapper does not share this module's globals. With
# postponed annotations that turns ``ApplyRequest`` into an unresolvable string
# (NameError on Python 3.12 / older FastAPI). Eager annotations sidestep it.

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
    """Run an application and return its job record.

    With durable storage (Postgres/Redis) the job is dispatched asynchronously
    and the caller polls ``GET /jobs/{id}``. Without it -- the free-tier Vercel
    deployment -- the job runs inside this request and the completed result is
    returned inline, because a later poll may hit an instance that never saw the
    job.
    """
    job_payload = payload.model_dump()
    job_id = jobs.create_job("apply", job_payload)

    # Privacy-safe binned summary for the live drift monitor (never raw values).
    try:
        db.log_prediction_features(job_id, bins_for_row(payload.applicant.model_dump()))
    except Exception:  # pragma: no cover - logging must never break scoring
        pass

    if db.is_enabled():
        backend = jobs.dispatch(job_id, job_payload)
        job = jobs.get_job(job_id) or {}
        job["backend"] = backend
        job["durable"] = True
    else:
        # No durable store: finish in-request so the caller never depends on a
        # second instance having the job.
        job = jobs.run_inline(job_id, job_payload)
        job["backend"] = get_settings().resolved_job_backend
        job["durable"] = False
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
