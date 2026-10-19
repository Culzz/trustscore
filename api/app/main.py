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
from .middleware import PIIMaskingMiddleware
from .routers import audit, jobs, meta, scoring

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

    def __init__(self, app):
        # Starlette's ``build_middleware_stack`` passes the wrapped app as the
        # ``app=`` keyword on the versions pinned in ``api/requirements.txt``
        # (older releases passed it positionally). The parameter must therefore
        # be named ``app``; naming it ``asgi_app`` breaks the first request with
        # ``TypeError: unexpected keyword argument 'app'`` on the deployed stack.
        self.asgi_app = app

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

# Privacy gateway: strip direct identifiers from JSON bodies before routing.
app.add_middleware(PIIMaskingMiddleware, salt=settings.pii_salt)

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
app.include_router(jobs.router)
app.include_router(audit.router)


@app.on_event("startup")
def _startup() -> None:
    """Best-effort: make sure the logging tables exist. Never blocks startup."""
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
            "POST /blueprint",
            "POST /apply",
            "GET /jobs/{job_id}",
            "WS /ws/jobs/{job_id}",
            "GET /model",
            "GET /models",
            "GET /models/{version}",
            "GET /registry",
            "GET /mitigation",
            "GET /context",
            "GET /portfolio",
            "POST /policy/simulate",
            "POST /ab/compare",
            "POST /bias/inject",
            "GET /drift/live",
            "POST /alerts/test",
            "GET /report.pdf",
            "GET /health",
            "GET /stats",
            "GET /cache/stats",
        ],
        "disclaimer": "Simulated decisions only. Not a loan offer.",
    }


@app.get("/cache/stats", tags=["metadata"])
def cache_stats() -> dict:
    """Cache and job-bus counters (handy for demos and debugging)."""
    from .jobs import bus_stats
    from .services.cache import NARRATIVE_CACHE, RECOURSE_CACHE

    return {
        "recourse_cache": RECOURSE_CACHE.stats(),
        "narrative_cache": NARRATIVE_CACHE.stats(),
        "job_bus": bus_stats(),
    }
