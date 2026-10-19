"""Vercel serverless entrypoint.

Vercel's Python runtime imports this module and looks for an ASGI ``app``. The
path prefix stripping (so ``/api/predict`` resolves to ``/predict``) is handled
by middleware inside ``app.main``.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the ``app`` package importable when running as a Vercel function.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app  # noqa: E402

# Vercel looks for a module-level ASGI ``app``. Do NOT also export ``handler``:
# the runtime treats a module-level ``handler`` as a legacy
# BaseHTTPRequestHandler *class* and calls issubclass() on it, which fails for a
# FastAPI instance.
__all__ = ["app"]
