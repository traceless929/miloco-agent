"""Per-session single-flight lock (aligns with AgentDispatcher drainer)."""

from __future__ import annotations

import asyncio
from collections import defaultdict


class SessionFlightGuard:
    """Ensure at most one in-flight agent turn per session_key."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock_for(self, session_key: str) -> asyncio.Lock:
        return self._locks[session_key]


session_flight_guard = SessionFlightGuard()
