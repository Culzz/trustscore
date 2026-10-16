"""FastAPI application entrypoint.

The same app object is used for local ``uvicorn`` and for the Vercel serverless
function (see ``api/index.py``). Routes are declared at the root
(``/predict``, ``/explain``, ...). When the app is served behind Vercel's
``/api/*`` rewrite, :class:`StripApiPrefix` removes the prefix so the same routes
resolve unchanged.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from . import db
from .core.config import get_settings
from .limiter import limiter
from .routers import meta, scoring

logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.model_version,
    description=(
        "Explainable, fairness-aware credit *decision simulation*. "
        "Not a real lending tool. See /model for the model card."
    ),
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)


class StripApiPrefix:
    """ASGI middleware that removes a leading ``/api`` segment.

    Lets one route table serve both ``/predict`` (local, Render) and
    ``/api/predict`` (Vercel rewrite) without duplication.
    """

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/api":
                scope = {**scope, "path": "/"}
            elif path.startswith("/api/"):
                new_path = path[len("/api") :]
                scope = {**scope, "path": new_path}
                if scope.get("raw_path"):
                    scope = {**scope, "raw_path": new_path.encode()}
        await self.asgi_app(scope, receive, send)


app.add_middleware(StripApiPrefix)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):  # pragma: no cover - exercised in prod
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please slow down."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(scoring.router)


@app.on_event("startup")
def _startup() -> None:
    """Best-effort: make sure the logging table exists. Never blocks startup."""
    db.init_db()


@app.get("/", tags=["metadata"])
def root() -> dict:
    return {
        "service": settings.app_name,
        "model_version": settings.model_version,
        "docs": "/docs",
        "endpoints": [
            "POST /predict",
            "POST /explain",
            "POST /decision",
            "POST /counterfactual",
            "GET /model",
            "GET /health",
            "GET /stats",
        ],
        "disclaimer": "Simulated decisions only. Not a loan offer.",
    }
