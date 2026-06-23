"""Perception logs + local perception memory files ($MILOCO_HOME/memory)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from miloco_agent.config import miloco_home
from miloco_agent.tools.miloco_client import MilocoApiClient, MilocoApiError


def _cursor_file() -> Path:
    return miloco_home() / "perception_cursor.json"


def _load_cursor() -> str | None:
    path = _cursor_file()
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    cursor = obj.get("cursor")
    if cursor:
        return str(cursor)
    cursor_ms = obj.get("cursor_ms")
    if cursor_ms is not None:
        return datetime.fromtimestamp(
            int(cursor_ms) / 1000,
            tz=timezone.utc,
        ).isoformat()
    return None


def _save_cursor(cursor_iso: str) -> None:
    path = _cursor_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"cursor": cursor_iso}, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def perception_memory_path(day: date | None = None) -> Path:
    d = day or date.today()
    return miloco_home() / "memory" / f"{d.isoformat()}-miloco-perception.md"


def _format_logs_jsonl(logs: list[dict[str, Any]]) -> str:
    if not logs:
        return "No logs found"
    lines: list[str] = []
    for item in logs:
        t = item.get("t", "")
        d = item.get("d", "")
        lines.append(f"{t}: {json.dumps(d, ensure_ascii=False)}")
    return "\n".join(lines)


async def tool_perception_logs(
    client: MilocoApiClient,
    *,
    incremental: bool = True,
    since: str | None = None,
    limit: int | None = None,
    update_cursor: bool = True,
) -> str:
    params_after: str | None = None
    params_since = since
    if incremental and not since:
        params_after = _load_cursor()
    data = await client.perception_logs(
        after=params_after,
        since=params_since,
        limit=limit,
    )
    logs = data.get("logs") if isinstance(data, dict) else []
    if not isinstance(logs, list):
        logs = []
    if incremental and not since and update_cursor and logs:
        last_t = logs[-1].get("t")
        if last_t:
            _save_cursor(str(last_t))
    return json.dumps(
        {
            "ok": True,
            "count": len(logs),
            "jsonl": _format_logs_jsonl(logs),
            "logs": logs,
        },
        ensure_ascii=False,
    )


def tool_memory_perception_read(day: str | None = None) -> str:
    if day:
        path = perception_memory_path(date.fromisoformat(day))
    else:
        path = perception_memory_path()
    if not path.is_file():
        return json.dumps(
            {"ok": True, "path": str(path), "content": "", "empty": True},
            ensure_ascii=False,
        )
    content = path.read_text(encoding="utf-8")
    return json.dumps(
        {
            "ok": True,
            "path": str(path),
            "content": content,
            "empty": not content.strip(),
        },
        ensure_ascii=False,
    )


def tool_memory_perception_append(text: str) -> str:
    body = text.strip()
    if not body:
        raise ValueError("text is required")
    path = perception_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.is_file() and path.stat().st_size > 0:
        prefix = "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(prefix + body + "\n")
    return json.dumps(
        {"ok": True, "path": str(path), "appended_chars": len(body)},
        ensure_ascii=False,
    )


async def run_perception_memory_tool(
    client: MilocoApiClient,
    name: str,
    arguments: dict[str, Any],
) -> str:
    try:
        if name == "perception_logs":
            return await tool_perception_logs(
                client,
                incremental=bool(arguments.get("incremental", True)),
                since=arguments.get("since"),
                limit=arguments.get("limit"),
                update_cursor=bool(arguments.get("update_cursor", True)),
            )
        if name == "memory_perception_read":
            return tool_memory_perception_read(arguments.get("day"))
        if name == "memory_perception_append":
            return tool_memory_perception_append(str(arguments.get("text") or ""))
        raise ValueError(f"unknown perception memory tool: {name}")
    except MilocoApiError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
