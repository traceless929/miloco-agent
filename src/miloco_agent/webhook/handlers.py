"""Webhook action handlers."""

from __future__ import annotations

import logging
from typing import Any

from miloco_agent.runtime.idempotency import idempotency_cache
from miloco_agent.runtime.turn_runner import turn_runner
from miloco_agent.trace.store import trace_store

logger = logging.getLogger(__name__)


async def handle_agent(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, str) or not message:
        raise ValueError("payload.message is required")

    session_key = str(payload.get("sessionKey") or "main")
    lane = payload.get("lane")
    trace_id = payload.get("traceId")
    timeout_ms = payload.get("timeoutMs")
    extra_system_prompt = payload.get("extraSystemPrompt")
    idempotency_key = str(
        payload.get("idempotencyKey") or trace_id or session_key
    )

    cached = idempotency_cache.get(idempotency_key)
    if cached is not None:
        logger.info("idempotency hit key=%s", idempotency_key)
        return cached

    result = await turn_runner.run_turn(
        message=message,
        session_key=session_key,
        lane=str(lane) if lane is not None else None,
        trace_id=str(trace_id) if trace_id is not None else None,
        timeout_ms=int(timeout_ms) if timeout_ms is not None else None,
        extra_system_prompt=(
            str(extra_system_prompt) if extra_system_prompt is not None else None
        ),
    )
    idempotency_cache.put(idempotency_key, result)
    return result


async def handle_get_trace(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = payload.get("runId")
    if not run_id or not isinstance(run_id, str):
        return {"status": "error", "message": "runId required"}

    status = trace_store.get_status(run_id)
    if status == "in_progress":
        return {"status": "in_progress"}
    if status == "unknown":
        return {"status": "unknown"}

    meta = trace_store.pop_done_meta(run_id)
    if meta is None:
        return {"status": "unknown"}
    return {"status": "done", **meta}
