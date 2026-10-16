"""Shared rate limiter.

Kept in its own module so routers and the app object can both import it without
circular imports. The limiter is in-memory, which is the right trade-off for a
serverless demo: it blunts accidental hammering without external infrastructure.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
