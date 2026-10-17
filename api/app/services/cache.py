"""A tiny TTL cache for expensive, repeatable work (recourse search, PDFs).

Two backends, chosen automatically:

* **redis** when ``REDIS_URL`` is configured (shared across serverless
  instances), and
* an **in-process** dictionary otherwise (the default on Vercel, where each
  instance is short-lived anyway).

Both are best-effort: a cache miss is always safe, and a cache failure never
raises into a request. Keys are content hashes, so no personal data is stored in
the cache key itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any


def make_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TTLCache:
    def __init__(self, maxsize: int = 512, ttl_seconds: float = 300.0, namespace: str = "cache"):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self.namespace = namespace
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._redis = self._connect_redis()
        self.hits = 0
        self.misses = 0

    def _connect_redis(self):
        url = os.environ.get("REDIS_URL")
        if not url:
            return None
        try:  # pragma: no cover - needs a Redis server
            import redis

            client = redis.Redis.from_url(url, socket_timeout=1.0)
            client.ping()
            return client
        except Exception:
            return None

    def get(self, key: str) -> Any | None:
        if self._redis is not None:  # pragma: no cover - needs a Redis server
            try:
                raw = self._redis.get(f"{self.namespace}:{key}")
                if raw is not None:
                    self.hits += 1
                    return json.loads(raw)
            except Exception:
                pass
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self.misses += 1
                return None
            expires, value = item
            if expires < time.time():
                self._store.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        if self._redis is not None:  # pragma: no cover - needs a Redis server
            try:
                self._redis.setex(f"{self.namespace}:{key}", int(self.ttl), json.dumps(value, default=str))
            except Exception:
                pass
        with self._lock:
            if len(self._store) >= self.maxsize:
                # Evict the soonest to expire.
                oldest = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest, None)
            self._store[key] = (time.time() + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "namespace": self.namespace,
            "backend": "redis" if self._redis is not None else "memory",
            "size": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": (self.hits / total) if total else None,
        }


# Counterfactual / blueprint searches are the expensive repeated call.
RECOURSE_CACHE = TTLCache(maxsize=1024, ttl_seconds=600.0, namespace="trustscore:recourse")
NARRATIVE_CACHE = TTLCache(maxsize=2048, ttl_seconds=600.0, namespace="trustscore:narrative")
