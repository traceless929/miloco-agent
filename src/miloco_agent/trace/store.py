"""In-memory turn trace store (compatible with get_trace webhook + AgentMetaPoller)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Literal

TurnStatus = Literal["pending", "done"]


@dataclass
class TurnRecord:
    run_id: str
    trace_id: str | None
    session_key: str
    query: str = ""
    status: TurnStatus = "pending"
    success: bool | None = None
    error_msg: str | None = None
    error_count: int = 0
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class TraceStore:
    """Thread-safe store mimicking OpenClaw plugin trace hook semantics."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, TurnRecord] = {}

    def start_turn(
        self,
        run_id: str,
        *,
        trace_id: str | None,
        session_key: str,
        query: str = "",
    ) -> TurnRecord:
        rec = TurnRecord(
            run_id=run_id,
            trace_id=trace_id,
            session_key=session_key,
            query=query[:2048],
        )
        with self._lock:
            self._runs[run_id] = rec
        return rec

    def finish_turn(
        self,
        run_id: str,
        *,
        success: bool = True,
        error_msg: str | None = None,
        error_count: int = 0,
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None:
                return
            rec.status = "done"
            rec.success = success
            rec.error_msg = error_msg
            rec.error_count = error_count
            rec.finished_at = time.monotonic()
            if extra_meta:
                rec.meta.update(extra_meta)

    def get_status(self, run_id: str) -> Literal["done", "in_progress", "unknown"]:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None:
                return "unknown"
            if rec.status == "done":
                return "done"
            return "in_progress"

    def peek_done_meta(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None or rec.status != "done":
                return None
            return self._build_meta(rec)

    def pop_done_meta(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None or rec.status != "done":
                return None
            meta = self._build_meta(rec)
            del self._runs[run_id]
            return meta

    def _build_meta(self, rec: TurnRecord) -> dict[str, Any]:
        finished = rec.finished_at or time.monotonic()
        duration_ms = max((finished - rec.started_at) * 1000.0, 0.0)
        m = rec.meta
        llm_calls = int(m.get("llmCallCount") or m.get("llmCalls") or 0)
        tool_calls = int(m.get("toolCallCount") or m.get("toolCalls") or 0)
        return {
            "runId": rec.run_id,
            "success": rec.success,
            "errorMsg": rec.error_msg,
            "errorCount": rec.error_count or int(m.get("errorCount") or 0),
            "sessionKey": rec.session_key,
            "traceId": rec.trace_id,
            "query": rec.query or str(m.get("query") or ""),
            "durationMs": float(m.get("durationMs") or duration_ms),
            "llmCallCount": llm_calls,
            "toolCallCount": tool_calls,
            "llmTotalMs": float(m.get("llmTotalMs") or 0.0),
            "toolTotalMs": float(m.get("toolTotalMs") or 0.0),
            "toolMaxMs": float(m.get("toolMaxMs") or 0.0),
            "slowestToolName": m.get("slowestToolName"),
            "jsonlPath": m.get("jsonlPath"),
            "replyPreview": m.get("replyPreview"),
            "replyText": m.get("replyText"),
        }

    def list_recent(self, *, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            rows = sorted(
                self._runs.values(),
                key=lambda r: r.started_at,
                reverse=True,
            )[: max(limit, 1)]
            return [self._list_item(r) for r in rows]

    def _list_item(self, rec: TurnRecord) -> dict[str, Any]:
        finished = rec.finished_at or time.monotonic()
        duration_ms = max((finished - rec.started_at) * 1000.0, 0.0)
        preview = (rec.query or "")[:120]
        if rec.status == "done" and rec.meta.get("replyPreview"):
            preview = str(rec.meta["replyPreview"])[:120]
        return {
            "runId": rec.run_id,
            "traceId": rec.trace_id,
            "sessionKey": rec.session_key,
            "status": rec.status,
            "success": rec.success,
            "errorMsg": rec.error_msg,
            "queryPreview": preview,
            "durationMs": round(duration_ms, 1),
            "llmCallCount": int(rec.meta.get("llmCallCount") or 0),
            "toolCallCount": int(rec.meta.get("toolCallCount") or 0),
            "jsonlPath": rec.meta.get("jsonlPath"),
        }


trace_store = TraceStore()
