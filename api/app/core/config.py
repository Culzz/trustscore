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

    # Where the bundled artifact + metadata live.
    artifacts_dir: Path = _API_DIR / "artifacts"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
