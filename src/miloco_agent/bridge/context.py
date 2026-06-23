"""Per-turn context for OpenClaw-compatible bridge tools."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MilocoBridgeContext:
    """Session-scoped data for notify / bind bridges."""

    session_key: str | None = None

    @property
    def feishu_open_id(self) -> str | None:
        key = self.session_key or ""
        if key.startswith("feishu:"):
            return key.split(":", 1)[1] or None
        return None
