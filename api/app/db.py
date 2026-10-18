"""Anonymised prediction logging and live counters.

Backends (chosen by ``STORAGE_BACKEND`` or auto-detected):

* **postgres** — any Postgres connection string works: Supabase, Aiven, Neon,
  Render, self-hosted. This is the production choice; Supabase and Aiven both
  have free, no-card tiers.
* **sqlite** — a local file, zero signup, perfect for development and demos on
  your own machine. Not usable on read-only serverless filesystems.
* **none** — logging disabled; the API still works, counters report as disabled.

Design choices for a serverless deployment:

* No connection pool: each call opens a short-lived connection and closes it.
* Logging is **best-effort**: if storage is missing or unreachable, the
  prediction still returns. Governance must never break the applicant flow.
* Only anonymised fields are stored: a random id, timestamp, model version, PD,
  band and loan exposure. No names, no contact details, no raw applicant row.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from .core.config import get_settings

logger = logging.getLogger("trustscore.db")


def resolve_backend() -> str:
    s = get_settings()
    if not s.log_predictions:
        return "none"
    backend = (s.storage_backend or "auto").lower()
    if backend in ("postgres", "postgresql"):
        return "postgres" if s.database_url else "none"
    if backend == "sqlite":
        return "sqlite"
    if backend == "none":
        return "none"
    # auto
    if s.database_url:
        return "postgres"
    if os.environ.get("VERCEL"):
        return "none"  # read-only filesystem
    return "sqlite" if s.sqlite_path else "none"


def is_enabled() -> bool:
    return resolve_backend() != "none"


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
@contextmanager
def _connect_postgres() -> Iterator:
    import psycopg2

    dsn = get_settings().database_url
    if not dsn:
        raise RuntimeError("database not configured")
    conn = psycopg2.connect(dsn, connect_timeout=5)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _connect_sqlite() -> Iterator:
    path = get_settings().sqlite_path
    conn = sqlite3.connect(path, timeout=5)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _connect():
    backend = resolve_backend()
    if backend == "postgres":
        return _connect_postgres()
    if backend == "sqlite":
        return _connect_sqlite()
    raise RuntimeError("storage is disabled")


_PG_DDL = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id          UUID PRIMARY KEY,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version          TEXT        NOT NULL,
    probability_of_default DOUBLE PRECISION NOT NULL,
    band                   TEXT        NOT NULL,
    decision               TEXT,
    exposure               DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS predictions_created_at_idx ON predictions (created_at);
CREATE TABLE IF NOT EXISTS prediction_features (
    prediction_id TEXT PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    features      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS prediction_features_created_at_idx
    ON prediction_features (created_at);
CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    events     TEXT NOT NULL DEFAULT '[]',
    result     TEXT,
    error      TEXT
);
CREATE INDEX IF NOT EXISTS jobs_updated_at_idx ON jobs (updated_at);
"""

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id          TEXT PRIMARY KEY,
    created_at             TEXT NOT NULL,
    model_version          TEXT NOT NULL,
    probability_of_default REAL NOT NULL,
    band                   TEXT NOT NULL,
    decision               TEXT,
    exposure               REAL
);
CREATE INDEX IF NOT EXISTS predictions_created_at_idx ON predictions (created_at);
CREATE TABLE IF NOT EXISTS prediction_features (
    prediction_id TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    features      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS prediction_features_created_at_idx
    ON prediction_features (created_at);
CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    events     TEXT NOT NULL DEFAULT '[]',
    result     TEXT,
    error      TEXT
);
CREATE INDEX IF NOT EXISTS jobs_updated_at_idx ON jobs (updated_at);
"""


def init_db() -> bool:
    """Create the table if needed. Returns True when ready."""
    backend = resolve_backend()
    if backend == "none":
        return False
    try:
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(_PG_DDL)
            else:
                cur.executescript(_SQLITE_DDL)
            cur.close()
        return True
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("init_db failed: %s", exc)
        return False


def log_prediction(
    prediction_id: str,
    model_version: str,
    probability_of_default: float,
    band: str,
    decision: str | None = None,
    exposure: float | None = None,
) -> bool:
    """Insert one anonymised row. Returns False (never raises) on failure."""
    backend = resolve_backend()
    if backend == "none":
        return False
    created = datetime.now(timezone.utc).isoformat()
    try:
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(
                    """
                    INSERT INTO predictions
                        (prediction_id, model_version, probability_of_default,
                         band, decision, exposure)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (prediction_id) DO NOTHING
                    """,
                    (prediction_id, model_version, float(probability_of_default),
                     band, decision, None if exposure is None else float(exposure)),
                )
            else:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO predictions
                        (prediction_id, created_at, model_version,
                         probability_of_default, band, decision, exposure)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (prediction_id, created, model_version,
                     float(probability_of_default), band, decision,
                     None if exposure is None else float(exposure)),
                )
            cur.close()
        return True
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("log_prediction failed: %s", exc)
        return False


def get_stats(window_days: int = 30) -> dict:
    """Live counters for the lender dashboard."""
    backend = resolve_backend()
    if backend == "none":
        return {
            "enabled": False,
            "total_predictions": 0,
            "mean_pd": None,
            "high_risk_share": None,
            "bands": {},
            "window": f"last {window_days} days",
            "note": "Prediction logging is disabled (no storage configured).",
        }
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(
                    """
                    SELECT band, COUNT(*) FROM predictions
                    WHERE created_at >= now() - (%s || ' days')::interval
                    GROUP BY band
                    """,
                    (str(int(window_days)),),
                )
                bands = {row[0]: int(row[1]) for row in cur.fetchall()}
                cur.execute(
                    """
                    SELECT COUNT(*), AVG(probability_of_default) FROM predictions
                    WHERE created_at >= now() - (%s || ' days')::interval
                    """,
                    (str(int(window_days)),),
                )
                total, mean_pd = cur.fetchone()
            else:
                cur.execute(
                    "SELECT band, COUNT(*) FROM predictions WHERE created_at >= ? GROUP BY band",
                    (cutoff,),
                )
                bands = {row[0]: int(row[1]) for row in cur.fetchall()}
                cur.execute(
                    "SELECT COUNT(*), AVG(probability_of_default) FROM predictions WHERE created_at >= ?",
                    (cutoff,),
                )
                total, mean_pd = cur.fetchone()
            cur.close()
        total = int(total or 0)
        high = int(bands.get("decline", 0))
        return {
            "enabled": True,
            "total_predictions": total,
            "mean_pd": float(mean_pd) if mean_pd is not None else None,
            "high_risk_share": (high / total) if total else None,
            "bands": bands,
            "window": f"last {window_days} days",
            "note": None,
        }
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("get_stats failed: %s", exc)
        return {
            "enabled": False,
            "total_predictions": 0,
            "mean_pd": None,
            "high_risk_share": None,
            "bands": {},
            "window": f"last {window_days} days",
            "note": f"Storage unavailable: {exc}",
        }


def log_prediction_features(prediction_id: str, features: dict) -> bool:
    """Store a privacy-safe, binned feature summary for the live drift monitor.

    Only bin indices and category codes are stored -- never the raw applicant
    values -- so drift can be measured without retaining personal data.
    """
    backend = resolve_backend()
    if backend == "none" or not features:
        return False
    import json

    payload = json.dumps(features, separators=(",", ":"))
    created = datetime.now(timezone.utc).isoformat()
    try:
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(
                    """
                    INSERT INTO prediction_features (prediction_id, features)
                    VALUES (%s, %s) ON CONFLICT (prediction_id) DO NOTHING
                    """,
                    (prediction_id, payload),
                )
            else:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO prediction_features
                        (prediction_id, created_at, features)
                    VALUES (?, ?, ?)
                    """,
                    (prediction_id, created, payload),
                )
            cur.close()
        return True
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("log_prediction_features failed: %s", exc)
        return False


def recent_feature_rows(limit: int = 500, window_days: int = 30) -> list[dict]:
    """Return recent binned feature summaries, newest first."""
    backend = resolve_backend()
    if backend == "none":
        return []
    import json

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(
                    "SELECT features FROM prediction_features "
                    "WHERE created_at >= now() - (%s || ' days')::interval "
                    "ORDER BY created_at DESC LIMIT %s",
                    (str(int(window_days)), int(limit)),
                )
            else:
                cur.execute(
                    "SELECT features FROM prediction_features WHERE created_at >= ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (cutoff, int(limit)),
                )
            rows = cur.fetchall()
            cur.close()
        return [json.loads(r[0]) for r in rows]
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("recent_feature_rows failed: %s", exc)
        return []


def clear_features() -> bool:
    backend = resolve_backend()
    if backend == "none":
        return False
    try:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM prediction_features")
            cur.close()
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("clear_features failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Durable job state
# ---------------------------------------------------------------------------
def save_job(job: dict) -> bool:
    """Upsert one job record so polling survives an instance change.

    Best-effort, like every other write here: when storage is unavailable the
    in-memory bus still works, and the console reports the job as ephemeral.
    """
    import json

    backend = resolve_backend()
    if backend == "none":
        return False
    payload = {
        "job_id": job["job_id"],
        "kind": job.get("kind", "apply"),
        "status": job.get("status", "queued"),
        "created_at": job.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "updated_at": job.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "events": json.dumps(job.get("events") or [], default=str),
        "result": (
            json.dumps(job.get("result"), default=str)
            if job.get("result") is not None
            else None
        ),
        "error": job.get("error"),
    }
    try:
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(
                    """
                    INSERT INTO jobs
                        (job_id, kind, status, created_at, updated_at, events, result, error)
                    VALUES (%(job_id)s, %(kind)s, %(status)s, %(created_at)s,
                            %(updated_at)s, %(events)s, %(result)s, %(error)s)
                    ON CONFLICT (job_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at,
                        events = EXCLUDED.events,
                        result = EXCLUDED.result,
                        error = EXCLUDED.error
                    """,
                    payload,
                )
            else:
                cur.execute(
                    """
                    INSERT INTO jobs
                        (job_id, kind, status, created_at, updated_at, events, result, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (job_id) DO UPDATE SET
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        events = excluded.events,
                        result = excluded.result,
                        error = excluded.error
                    """,
                    (
                        payload["job_id"], payload["kind"], payload["status"],
                        payload["created_at"], payload["updated_at"],
                        payload["events"], payload["result"], payload["error"],
                    ),
                )
            cur.close()
        return True
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("save_job failed: %s", exc)
        return False


def load_job(job_id: str) -> dict | None:
    """Read a job back from durable storage (used when memory has lost it)."""
    import json

    backend = resolve_backend()
    if backend == "none":
        return None
    try:
        with _connect() as conn:
            cur = conn.cursor()
            sql = (
                "SELECT job_id, kind, status, created_at, updated_at, events, result, error "
                "FROM jobs WHERE job_id = " + ("%s" if backend == "postgres" else "?")
            )
            cur.execute(sql, (job_id,))
            row = cur.fetchone()
            cur.close()
        if row is None:
            return None
        return {
            "job_id": row[0],
            "kind": row[1],
            "status": row[2],
            "created_at": row[3] if isinstance(row[3], str) else row[3].isoformat(),
            "updated_at": row[4] if isinstance(row[4], str) else row[4].isoformat(),
            "events": json.loads(row[5] or "[]"),
            "result": json.loads(row[6]) if row[6] else None,
            "error": row[7],
            "durable": True,
        }
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("load_job failed: %s", exc)
        return None


def prune_jobs(ttl_seconds: int = 3600) -> int:
    backend = resolve_backend()
    if backend == "none":
        return 0
    try:
        with _connect() as conn:
            cur = conn.cursor()
            if backend == "postgres":
                cur.execute(
                    "DELETE FROM jobs WHERE updated_at < now() - (%s || ' seconds')::interval",
                    (str(int(ttl_seconds)),),
                )
            else:
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
                ).isoformat()
                cur.execute("DELETE FROM jobs WHERE updated_at < ?", (cutoff,))
            deleted = cur.rowcount
            cur.close()
        return int(deleted or 0)
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("prune_jobs failed: %s", exc)
        return 0


def health() -> dict:
    backend = resolve_backend()
    if backend == "none":
        return {"configured": False, "reachable": False, "backend": "none",
                "note": "No storage configured"}
    try:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        return {"configured": True, "reachable": True, "backend": backend, "note": None}
    except Exception as exc:  # pragma: no cover
        return {"configured": True, "reachable": False, "backend": backend, "note": str(exc)}
