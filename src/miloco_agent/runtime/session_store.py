"""Per-session conversation history for multi-turn IM (P2+-)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from miloco_agent.config import miloco_home


@dataclass
class HistoryTurn:
    role: str
    content: str
    ts: float


def _safe_key(session_key: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", session_key)[:120]
    return slug or "default"


class SessionStore:
    """Persist recent turns under $MILOCO_HOME/agent/sessions/."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._dir = miloco_home() / "agent" / "sessions"

    def _path(self, session_key: str) -> Path:
        return self._dir / f"{_safe_key(session_key)}.json"

    def _read_turns(self, session_key: str) -> list[HistoryTurn]:
        path = self._path(session_key)
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [
            HistoryTurn(
                role=str(t.get("role") or "user"),
                content=str(t.get("content") or ""),
                ts=float(t.get("ts") or 0),
            )
            for t in raw.get("turns") or []
        ]

    def load(
        self,
        session_key: str,
        *,
        max_turns: int,
        ttl_hours: float,
    ) -> list[HistoryTurn]:
        with self._lock:
            turns = self._read_turns(session_key)
        cutoff = time.time() - max(0.0, ttl_hours) * 3600.0
        turns = [t for t in turns if t.ts >= cutoff]
        if max_turns > 0:
            turns = turns[-max_turns * 2 :]
        return turns

    def append(
        self,
        session_key: str,
        *,
        user: str,
        assistant: str,
        max_turns: int,
        ttl_hours: float,
    ) -> None:
        with self._lock:
            path = self._path(session_key)
            path.parent.mkdir(parents=True, exist_ok=True)
            turns = self._read_turns(session_key)
            cutoff = time.time() - max(0.0, ttl_hours) * 3600.0
            turns = [t for t in turns if t.ts >= cutoff]
            now = time.time()
            turns.append(HistoryTurn(role="user", content=user, ts=now))
            turns.append(HistoryTurn(role="assistant", content=assistant, ts=now))
            if max_turns > 0:
                turns = turns[-max_turns * 2 :]
            payload = {
                "session_key": session_key,
                "updated_at": now,
                "turns": [
                    {"role": t.role, "content": t.content, "ts": t.ts} for t in turns
                ],
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)


def format_history_block(turns: list[HistoryTurn]) -> str:
    if not turns:
        return ""
    lines = ["## 近期对话"]
    for t in turns:
        label = "用户" if t.role == "user" else "助手"
        body = t.content.strip().replace("\n", " ")
        if len(body) > 400:
            body = body[:400] + "…"
        lines.append(f"- {label}：{body}")
    return "\n".join(lines)


session_store = SessionStore()
