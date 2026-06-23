"""Turn trace jsonl.gz recorder (OpenClaw-compatible layout under $MILOCO_HOME/trace/agent/)."""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentscope.message import ToolCallBlock, ToolResultBlock

from miloco_agent.config import config_file, miloco_home

logger = logging.getLogger(__name__)

QUERY_LEN_MAX = 30
DAILY_DUMP_MAX = 300
BUFFER_MAX = 500
PAYLOAD_TRUNCATE = 32_768


def is_debug_enabled() -> bool:
    if (miloco_home() / ".debug_observability").is_file():
        return True
    try:
        raw = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(raw.get("debug"))


def should_dump_trace(session_key: str) -> bool:
    if session_key.startswith("cron:"):
        return True
    return is_debug_enabled()


def trace_root() -> Path:
    return miloco_home() / "trace" / "agent"


def today_dir() -> Path:
    now = datetime.now().astimezone()
    return trace_root() / now.strftime("%Y%m%d")


def sanitize_query_for_filename(query: str | None) -> str:
    if not query:
        return "system"
    cleaned = (
        query.replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )
    for ch in '/\\:*?"<>|`':
        cleaned = cleaned.replace(ch, "_")
    cleaned = " ".join(cleaned.split()).strip()[:QUERY_LEN_MAX]
    return cleaned or "system"


def _now_fields() -> dict[str, str]:
    utc = datetime.now(timezone.utc)
    local = utc.astimezone()
    return {
        "ts": utc.isoformat(),
        "local_time": local.strftime("%Y-%m-%d %H:%M:%S %z"),
    }


def _safe_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        text = value if isinstance(value, str) else str(value)
        if len(text) > PAYLOAD_TRUNCATE:
            return text[:PAYLOAD_TRUNCATE] + "…[truncated]"
        return value
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    if len(text) > PAYLOAD_TRUNCATE:
        return text[:PAYLOAD_TRUNCATE] + "…[truncated]"
    return value


def _event(
    *,
    hook: str,
    run_id: str,
    trace_id: str | None,
    session_key: str,
    payload: dict[str, Any] | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        **_now_fields(),
        "hook": hook,
        "runId": run_id,
        "traceId": trace_id,
        "sessionKey": session_key,
    }
    if tool_call_id:
        ev["toolCallId"] = tool_call_id
    if payload is not None:
        ev["payload"] = payload
    return ev


def extract_events_from_agent(
    agent: Any,
    *,
    run_id: str,
    trace_id: str | None,
    session_key: str,
    query: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        _event(
            hook="turn_start",
            run_id=run_id,
            trace_id=trace_id,
            session_key=session_key,
            payload={"query": query[:2048]},
        ),
        _event(
            hook="llm_input",
            run_id=run_id,
            trace_id=trace_id,
            session_key=session_key,
            payload={"prompt": query[:4096]},
        ),
    ]

    for msg in agent.state.context:
        role = getattr(msg, "role", None) or type(msg).__name__
        blocks = list(msg.get_content_blocks()) if hasattr(msg, "get_content_blocks") else []
        for block in blocks:
            if isinstance(block, ToolCallBlock):
                events.append(
                    _event(
                        hook="before_tool_call",
                        run_id=run_id,
                        trace_id=trace_id,
                        session_key=session_key,
                        tool_call_id=str(block.id) if block.id else None,
                        payload={
                            "toolName": block.name,
                            "params": _safe_payload(block.input),
                        },
                    )
                )
            elif isinstance(block, ToolResultBlock):
                events.append(
                    _event(
                        hook="after_tool_call",
                        run_id=run_id,
                        trace_id=trace_id,
                        session_key=session_key,
                        tool_call_id=str(block.id) if block.id else None,
                        payload={
                            "toolName": block.name,
                            "result": _safe_payload(block.output),
                        },
                    )
                )
        if role == "assistant":
            text = msg.get_text_content() if hasattr(msg, "get_text_content") else ""
            if text:
                events.append(
                    _event(
                        hook="llm_output",
                        run_id=run_id,
                        trace_id=trace_id,
                        session_key=session_key,
                        payload={"text": _safe_payload(text)},
                    )
                )

    if len(events) > BUFFER_MAX:
        events = events[:BUFFER_MAX] + [
            _event(
                hook="_truncated",
                run_id=run_id,
                trace_id=trace_id,
                session_key=session_key,
                payload={"droppedAfter": BUFFER_MAX},
            )
        ]
    return events


def dump_turn_trace(
    *,
    run_id: str,
    session_key: str,
    trace_id: str | None,
    query: str,
    success: bool,
    error_msg: str | None = None,
    agent: Any | None = None,
    duration_ms: float | None = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    if not should_dump_trace(session_key):
        return None

    if agent is not None:
        events = extract_events_from_agent(
            agent,
            run_id=run_id,
            trace_id=trace_id,
            session_key=session_key,
            query=query,
        )
    else:
        events = [
            _event(
                hook="turn_start",
                run_id=run_id,
                trace_id=trace_id,
                session_key=session_key,
                payload={"query": query[:2048]},
            )
        ]

    end_payload: dict[str, Any] = {
        "success": success,
        "error": error_msg,
        "durationMs": duration_ms,
    }
    if meta:
        end_payload.update(
            {
                k: meta[k]
                for k in (
                    "llmCallCount",
                    "toolCallCount",
                    "replyPreview",
                    "errorCount",
                )
                if k in meta
            }
        )
    events.append(
        _event(
            hook="turn_end",
            run_id=run_id,
            trace_id=trace_id,
            session_key=session_key,
            payload=end_payload,
        )
    )

    try:
        day_dir = today_dir()
        day_dir.mkdir(parents=True, exist_ok=True)
        existing = sum(1 for p in day_dir.iterdir() if p.suffix == ".gz")
        if existing >= DAILY_DUMP_MAX:
            logger.warning(
                "trace daily cap reached: %d/%d, skip dump run_id=%s",
                existing,
                DAILY_DUMP_MAX,
                run_id,
            )
            return None

        filename = f"{run_id}__{sanitize_query_for_filename(query)}.jsonl.gz"
        full_path = day_dir / filename
        body = "\n".join(json.dumps(ev, ensure_ascii=False, default=str) for ev in events) + "\n"
        full_path.write_bytes(gzip.compress(body.encode("utf-8")))
        rel = f"trace/agent/{day_dir.name}/{filename}"
        logger.info("trace dumped run_id=%s path=%s events=%d", run_id, rel, len(events))
        return rel
    except OSError as exc:
        logger.error("trace gzip write failed run_id=%s: %s", run_id, exc)
        return None


def _iter_trace_files() -> list[Path]:
    root = trace_root()
    if not root.is_dir():
        return []
    files: list[Path] = []
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for path in day_dir.glob("*.jsonl.gz"):
            files.append(path)
    return files


def find_trace_file_by_run_id(run_id: str) -> Path | None:
    root = trace_root()
    if not root.is_dir():
        return None
    needle = f"{run_id}__"
    for day_dir in sorted(root.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for path in day_dir.glob(f"{run_id}__*.jsonl.gz"):
            return path
        for path in day_dir.iterdir():
            if path.name.startswith(needle) and path.name.endswith(".jsonl.gz"):
                return path
    return None


def rel_path_for_file(path: Path) -> str:
    home = miloco_home().resolve()
    try:
        return str(path.resolve().relative_to(home))
    except ValueError:
        return str(path)


def _is_safe_trace_path(path: Path) -> bool:
    root = trace_root().resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except ValueError:
        return False
    return resolved.is_file() and resolved.name.endswith(".jsonl.gz")


def resolve_trace_path(
    *,
    run_id: str | None = None,
    rel_path: str | None = None,
) -> Path | None:
    path: Path | None = None
    if rel_path:
        candidate = (miloco_home() / rel_path).resolve()
        if _is_safe_trace_path(candidate):
            path = candidate
    if path is None and run_id:
        found = find_trace_file_by_run_id(run_id)
        if found and _is_safe_trace_path(found):
            path = found
    return path


def delete_trace_file(
    *,
    run_id: str | None = None,
    rel_path: str | None = None,
) -> dict[str, Any]:
    path = resolve_trace_path(run_id=run_id, rel_path=rel_path)
    if path is None:
        return {"ok": False, "error": "trace file not found"}
    rel = rel_path_for_file(path)
    run = run_id or path.name.split("__", 1)[0]
    try:
        size = path.stat().st_size
        path.unlink()
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "deleted": [rel],
        "count": 1,
        "freedBytes": size,
        "runId": run,
    }


def cleanup_trace_files(
    *,
    run_ids: list[str] | None = None,
    rel_paths: list[str] | None = None,
    day: str | None = None,
    older_than_days: int | None = None,
    delete_all: bool = False,
) -> dict[str, Any]:
    targets: list[Path] = []

    if delete_all:
        targets = list(_iter_trace_files())
    elif run_ids or rel_paths:
        seen: set[Path] = set()
        for rid in run_ids or []:
            path = resolve_trace_path(run_id=rid)
            if path:
                seen.add(path)
        for rel in rel_paths or []:
            path = resolve_trace_path(rel_path=rel)
            if path:
                seen.add(path)
        targets = list(seen)
    elif day:
        if not day.isdigit() or len(day) != 8:
            return {"ok": False, "error": "invalid day, expected YYYYMMDD"}
        day_dir = trace_root() / day
        if day_dir.is_dir():
            targets = [p for p in day_dir.glob("*.jsonl.gz") if _is_safe_trace_path(p)]
    elif older_than_days is not None:
        if older_than_days < 0:
            return {"ok": False, "error": "older_than_days must be >= 0"}
        import time

        cutoff = time.time() - older_than_days * 86400
        targets = [p for p in _iter_trace_files() if p.stat().st_mtime < cutoff]
    else:
        return {"ok": False, "error": "no cleanup criteria provided"}

    deleted: list[str] = []
    freed = 0
    errors: list[str] = []
    for path in targets:
        if not _is_safe_trace_path(path):
            continue
        rel = rel_path_for_file(path)
        try:
            freed += path.stat().st_size
            path.unlink()
            deleted.append(rel)
        except OSError as exc:
            errors.append(f"{rel}: {exc}")

    result: dict[str, Any] = {
        "ok": not errors or bool(deleted),
        "deleted": deleted,
        "count": len(deleted),
        "freedBytes": freed,
    }
    if errors:
        result["errors"] = errors
    return result


def read_trace_events(*, run_id: str | None = None, rel_path: str | None = None) -> dict[str, Any]:
    path: Path | None = None
    if rel_path:
        candidate = miloco_home() / rel_path
        if candidate.is_file():
            path = candidate
    if path is None and run_id:
        path = find_trace_file_by_run_id(run_id)
    if path is None or not path.is_file():
        return {"ok": False, "error": "trace file not found", "events": []}

    try:
        raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    except (OSError, gzip.BadGzipFile, UnicodeDecodeError) as exc:
        return {"ok": False, "error": str(exc), "events": []}

    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"hook": "_parse_error", "raw": line[:512]})
    return {
        "ok": True,
        "runId": run_id or path.name.split("__", 1)[0],
        "jsonlPath": rel_path_for_file(path),
        "eventCount": len(events),
        "events": events,
    }


def list_trace_files(*, day: str | None = None, limit: int = 50) -> dict[str, Any]:
    root = trace_root()
    if not root.is_dir():
        return {"ok": True, "files": [], "count": 0}

    paths: list[Path] = []
    if day:
        day_dir = root / day
        if day_dir.is_dir():
            paths = sorted(day_dir.glob("*.jsonl.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        paths = sorted(_iter_trace_files(), key=lambda p: p.stat().st_mtime, reverse=True)

    items: list[dict[str, Any]] = []
    for path in paths[: max(limit, 1)]:
        name = path.name
        run_id = name.split("__", 1)[0] if "__" in name else name.replace(".jsonl.gz", "")
        stat = path.stat()
        items.append(
            {
                "runId": run_id,
                "jsonlPath": rel_path_for_file(path),
                "day": path.parent.name,
                "sizeBytes": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return {"ok": True, "files": items, "count": len(items)}
