"""The asynchronous job bus behind ``POST /apply`` and ``WS /ws/jobs/{id}``.

Two execution paths, chosen by ``JOB_BACKEND`` (default ``auto``):

* **memory** (the Vercel default) -- the job runs as an ``asyncio`` task in the
  same process, emitting milestones into an in-memory store. Serverless
  functions cannot hold a WebSocket open, so on Vercel the client falls back to
  polling ``GET /jobs/{id}``.
* **celery** -- when ``CELERY_BROKER_URL`` (or ``REDIS_URL``) is set, the job is
  handed to a Celery worker (see ``api/worker.py``) and milestones are published
  over Redis pub/sub. This is the Docker/Render deployment, where WebSockets
  work.

Both paths emit the *same* events, because both call
``services.apply_flow.run_application``.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from .core.config import get_settings

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
_JOBS: dict[str, dict] = {}
_SUBSCRIBERS: dict[str, set[asyncio.Queue]] = {}
_MAX_JOBS = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prune() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    ttl = get_settings().job_ttl_seconds
    cutoff = time.time() - ttl
    for job_id, job in list(_JOBS.items()):
        if job.get("_ts", 0) < cutoff:
            _JOBS.pop(job_id, None)
            _SUBSCRIBERS.pop(job_id, None)


def create_job(kind: str, payload: dict) -> str:
    job_id = f"job_{uuid.uuid4().hex[:16]}"
    _JOBS[job_id] = {
        "job_id": job_id,
        "kind": kind,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "events": [],
        "result": None,
        "error": None,
        "backend": get_settings().resolved_job_backend,
        "_ts": time.time(),
    }
    _prune()
    return job_id


def get_job(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if job is None:
        return None
    return {k: v for k, v in job.items() if not k.startswith("_")}


def emit(job_id: str, event: dict) -> None:
    """Record a milestone and wake any subscribers."""
    job = _JOBS.get(job_id)
    if job is None:
        return
    event = {**event, "at": _now()}
    job["events"].append(event)
    job["updated_at"] = event["at"]
    job["_ts"] = time.time()
    step = event.get("step")
    if step == "complete":
        job["status"] = "complete"
        job["result"] = event.get("result", job.get("result"))
    elif step in ("error", "failed"):
        job["status"] = "error"
        job["error"] = event.get("error") or event.get("label")
    else:
        job["status"] = "running"
    for queue in list(_SUBSCRIBERS.get(job_id, ())):
        try:
            queue.put_nowait(event)
        except Exception:
            pass


def finish(job_id: str, result: dict) -> None:
    """Attach the final result, without emitting a duplicate ``complete`` event."""
    job = _JOBS.get(job_id)
    if job is None:
        return
    job["result"] = result
    events = job.get("events") or []
    last = events[-1] if events else None
    if last is not None and last.get("step") == "complete":
        last["result"] = result
        job["status"] = "complete"
        job["updated_at"] = last.get("at") or _now()
        return
    emit(
        job_id,
        {"step": "complete", "status": "done", "label": "Decision ready", "result": result},
    )


def fail(job_id: str, message: str) -> None:
    emit(job_id, {"step": "error", "status": "error", "label": "Job failed", "error": message})


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------
async def _run_memory(job_id: str, payload: dict) -> None:
    from .services.apply_flow import run_application

    def emitter(event: dict) -> None:
        emit(job_id, event)

    try:
        result = await asyncio.to_thread(run_application, payload, emitter)
        finish(job_id, result)
    except Exception as exc:  # pragma: no cover - defensive
        fail(job_id, str(exc))


def dispatch(job_id: str, payload: dict) -> str:
    """Start the job on the configured backend. Returns the backend used."""
    backend = get_settings().resolved_job_backend
    if backend == "celery":
        if _dispatch_celery(job_id, payload):
            return "celery"
    # Fall back to in-process execution.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run_memory(job_id, payload))
    except RuntimeError:  # no running loop (e.g. called from sync test)
        asyncio.run(_run_memory(job_id, payload))
    return "memory"


def _dispatch_celery(job_id: str, payload: dict) -> bool:  # pragma: no cover - needs a broker
    try:
        from .worker import run_application_task

        run_application_task.delay(job_id, payload)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------
async def subscribe(job_id: str) -> AsyncIterator[dict]:
    """Yield milestones for a job: replay first, then stream live."""
    backend = get_settings().resolved_job_backend
    if backend == "celery":
        async for event in _subscribe_redis(job_id):
            yield event
        return

    job = _JOBS.get(job_id)
    if job is None:
        yield {"step": "error", "status": "error", "label": "Unknown job", "error": "not found"}
        return

    queue: asyncio.Queue = asyncio.Queue()
    _SUBSCRIBERS.setdefault(job_id, set()).add(queue)
    try:
        for event in list(job["events"]):
            yield event
            if event.get("step") in ("complete", "error"):
                return
        while True:
            event = await queue.get()
            yield event
            if event.get("step") in ("complete", "error"):
                return
    finally:
        _SUBSCRIBERS.get(job_id, set()).discard(queue)


async def _subscribe_redis(job_id: str) -> AsyncIterator[dict]:  # pragma: no cover - needs Redis
    url = get_settings().redis_url or get_settings().celery_broker_url
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(url)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"trustscore:jobs:{job_id}")
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            event = json.loads(message["data"])
            yield event
            if event.get("step") in ("complete", "error"):
                break
    except Exception as exc:
        yield {"step": "error", "status": "error", "label": "Stream unavailable", "error": str(exc)}


async def publish_redis(job_id: str, event: dict) -> None:  # pragma: no cover - needs Redis
    """Used by the Celery worker to push milestones."""
    url = get_settings().redis_url or get_settings().celery_broker_url
    import redis.asyncio as aioredis

    client = aioredis.from_url(url)
    await client.publish(f"trustscore:jobs:{job_id}", json.dumps(event, default=str))
    await client.aclose()


def bus_stats() -> dict:
    return {
        "backend": get_settings().resolved_job_backend,
        "jobs": len(_JOBS),
        "subscribers": sum(len(v) for v in _SUBSCRIBERS.values()),
    }
