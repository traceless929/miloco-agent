"""Idempotency cache for agent webhook (aligns with dispatcher retries)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

_TTL_S = 600.0


@dataclass
class CachedAgentResult:
    data: dict[str, Any]
    created_at: float


class IdempotencyCache:
    def __init__(self, ttl_s: float = _TTL_S) -> None:
        self._ttl_s = ttl_s
        self._lock = Lock()
        self._entries: dict[str, CachedAgentResult] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now - entry.created_at > self._ttl_s:
                del self._entries[key]
                return None
            return entry.data

    def put(self, key: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._entries[key] = CachedAgentResult(data=data, created_at=time.monotonic())

    def purge_expired(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                k
                for k, v in self._entries.items()
                if now - v.created_at > self._ttl_s
            ]
            for k in expired:
                del self._entries[k]


idempotency_cache = IdempotencyCache()
