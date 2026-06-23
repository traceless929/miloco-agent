"""Habit suggestion state store + tool helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from miloco_agent.config import miloco_home
from miloco_agent.prompt.injection import habit_suggestions_path

_SH_TZ = timezone(timedelta(hours=8))
_STORE_VERSION = 1
_MAX_OPEN = 1
_MAX_NEW_PER_DAY = 1
_STALE_DAYS = 7
_MAX_ASKS = 3

_lock = Lock()


def _now_iso() -> str:
    return datetime.now(_SH_TZ).isoformat(timespec="seconds")


def _local_date(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    local = dt.astimezone(_SH_TZ)
    return local.strftime("%Y-%m-%d")


def _load() -> dict[str, Any]:
    path = habit_suggestions_path()
    if not path.is_file():
        return {"version": _STORE_VERSION, "entries": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": _STORE_VERSION, "entries": []}


def _save(store: dict[str, Any]) -> None:
    path = habit_suggestions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _apply_expiry(store: dict[str, Any], now_iso: str) -> None:
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    for e in store.get("entries") or []:
        if e.get("status") not in ("asked", "accepted"):
            continue
        stamp = e.get("asked_at") or e.get("resolved_at")
        if not stamp:
            continue
        asked = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if (now - asked) > timedelta(days=_STALE_DAYS):
            e["status"] = "expired"
            e["resolved_at"] = now_iso
            e["reason"] = f"{_STALE_DAYS} 天无明确回应自动过期"
            e["updated_at"] = now_iso


def run_habit_suggest(arguments: dict[str, Any]) -> dict[str, Any]:
    action: str = str(arguments.get("action") or "list")
    with _lock:
        store = _load()
        now = _now_iso()
        _apply_expiry(store, now)
        entries: list[dict[str, Any]] = store.setdefault("entries", [])

        if action == "list":
            open_q = [e for e in entries if e.get("status") == "asked"]
            asked_today = sum(
                1
                for e in entries
                if e.get("asked_at") and _local_date(str(e["asked_at"])) == _local_date(now)
            )
            can_ask = len(open_q) < _MAX_OPEN and asked_today < _MAX_NEW_PER_DAY
            _save(store)
            return {
                "ok": True,
                "can_ask_now": can_ask,
                "open_questions": open_q,
                "entries": entries,
            }

        if action == "record":
            key = str(arguments.get("key") or "")
            if not key:
                return {"ok": False, "error": "key required"}
            for e in entries:
                if e.get("key") == key and e.get("status") in ("created", "rejected"):
                    return {"ok": False, "error": "terminal entry exists"}
            existing = next((e for e in entries if e.get("key") == key), None)
            if existing:
                for field in ("title", "subject", "habit", "suggestion", "evidence", "item_id"):
                    if arguments.get(field):
                        existing[field] = arguments[field]
                existing["updated_at"] = now
            else:
                entries.append(
                    {
                        "key": key,
                        "title": str(arguments.get("title") or key),
                        "subject": str(arguments.get("subject") or ""),
                        "habit": str(arguments.get("habit") or ""),
                        "suggestion": str(arguments.get("suggestion") or ""),
                        "evidence": arguments.get("evidence"),
                        "item_id": arguments.get("item_id"),
                        "status": "pending",
                        "ask_count": 0,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            _save(store)
            return {"ok": True}

        if action == "mark_asked":
            key = str(arguments.get("key") or "")
            entry = next((e for e in entries if e.get("key") == key), None)
            if not entry:
                return {"ok": False, "error": "key not found"}
            open_q = [e for e in entries if e.get("status") == "asked"]
            if len(open_q) >= _MAX_OPEN and entry.get("status") != "asked":
                return {"ok": False, "error": "open question slot full"}
            entry["status"] = "asked"
            entry["asked_at"] = now
            entry["ask_count"] = int(entry.get("ask_count") or 0) + 1
            entry["updated_at"] = now
            _save(store)
            return {"ok": True}

        if action == "resolve":
            key = str(arguments.get("key") or "")
            outcome: Literal["created", "rejected"] | str = str(
                arguments.get("outcome") or ""
            )
            entry = next((e for e in entries if e.get("key") == key), None)
            if not entry:
                return {"ok": False, "error": "key not found"}
            if outcome == "created":
                entry["status"] = "created"
                entry["task_id"] = arguments.get("task_id")
            elif outcome == "rejected":
                entry["status"] = "rejected"
            else:
                return {"ok": False, "error": "outcome must be created|rejected"}
            entry["resolved_at"] = now
            entry["updated_at"] = now
            _save(store)
            return {"ok": True}

        return {"ok": False, "error": f"unknown action: {action}"}
