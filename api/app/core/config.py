"""Runtime settings for the API.

All settings are environment-overridable. On Vercel, set them in the project's
Environment Variables; locally, put them in a ``.env`` file (never committed).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[2]  # .../api


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "TrustScore API"
    model_version: str = "trustscore-1.0.0"
    fair_model_version: str = "trustscore-1.1.0"

    # Where the bundled artifact + metadata live.
    artifacts_dir: Path = _API_DIR / "artifacts"

    # Async jobs / live drift. With no broker everything runs in-process (the
    # Vercel default); point CELERY_BROKER_URL at Redis to use real workers.
    celery_broker_url: str | None = None
    redis_url: str | None = None
    job_backend: str = "auto"  # auto | memory | celery
    job_ttl_seconds: int = 900

    # Optional webhook for drift/adversarial alerts (the "slack hook").
    alert_webhook_url: str | None = None

    # Salt for PII hashing in the privacy gateway. Override in production.
    pii_salt: str = "trustscore-demo-salt"

    # Anonymised prediction log / counters.
    #   storage_backend: "auto" (postgres if DATABASE_URL set, else sqlite, else none)
    #                    "postgres" | "sqlite" | "none"
    # Postgres works with any provider (Supabase, Aiven, Neon, Render, ...); the
    # connection string is the only thing that changes.
    storage_backend: str = "auto"
    database_url: str | None = None
    sqlite_path: str = "predictions.db"
    log_predictions: bool = True

    # Comma-separated list of allowed browser origins.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # Rate limiting (slowapi syntax).
    rate_limit: str = "120/minute"

    # Auto docs are handy in dev; keep them but they are read-only.
    enable_docs: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def model_artifact_path(self) -> Path:
        return self.artifacts_dir / "model.joblib"

    @property
    def metadata_path(self) -> Path:
        return self.artifacts_dir / "metadata.json"

    @property
    def fair_model_artifact_path(self) -> Path:
        return self.artifacts_dir / "model_fair.joblib"

    @property
    def fair_metadata_path(self) -> Path:
        return self.artifacts_dir / "metadata_fair.json"

    @property
    def registry_path(self) -> Path:
        return self.artifacts_dir / "registry.json"

    @property
    def reference_path(self) -> Path:
        return self.artifacts_dir / "reference.json"

    @property
    def portfolio_path(self) -> Path:
        return self.artifacts_dir / "portfolio.json"

    @property
    def resolved_job_backend(self) -> str:
        backend = (self.job_backend or "auto").lower()
        if backend == "auto":
            return "celery" if (self.celery_broker_url or self.redis_url) else "memory"
        return backend


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
