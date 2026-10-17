"""Celery worker for the hybrid asynchronous path.

This module is **optional**: it is only imported when ``JOB_BACKEND=celery`` (or
a broker URL is set), and it is only installed via ``api/requirements-async.txt``.
The Vercel deployment never touches it.

Run it alongside Redis (see ``docker-compose.yml``)::

    celery -A app.worker:celery_app worker --loglevel=info

The worker executes exactly the same ``run_application`` flow as the in-process
runner and publishes milestones to Redis, where ``WS /ws/jobs/{id}`` relays them.
"""
from __future__ import annotations

import json
import os

from celery import Celery

from .core.config import get_settings
from .services.apply_flow import run_application

_SETTINGS = get_settings()
_BROKER = _SETTINGS.celery_broker_url or _SETTINGS.redis_url or os.environ.get("REDIS_URL")

celery_app = Celery("trustscore", broker=_BROKER, backend=_BROKER)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=120,
    broker_connection_retry_on_startup=True,
)


def _publisher(job_id: str):  # pragma: no cover - needs Redis
    import redis

    client = redis.Redis.from_url(_BROKER)

    def publish(event: dict) -> None:
        client.publish(f"trustscore:jobs:{job_id}", json.dumps(event, default=str))

    return publish


@celery_app.task(name="trustscore.run_application", bind=True, max_retries=0)
def run_application_task(self, job_id: str, payload: dict) -> dict:  # pragma: no cover
    """Execute the application flow and stream milestones over Redis."""
    publish = _publisher(job_id)
    try:
        result = run_application(payload, publish)
        publish({"step": "complete", "status": "done", "label": "Decision ready", "result": result})
        return {"job_id": job_id, "status": "complete"}
    except Exception as exc:
        publish({"step": "error", "status": "error", "label": "Job failed", "error": str(exc)})
        raise
