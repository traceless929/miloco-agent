"""Agent turn execution — AgentScope Agent + Miloco tools."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from agentscope.event import ReplyStartEvent, TextBlockDeltaEvent
from agentscope.message import UserMsg

from miloco_agent.bridge import MilocoBridgeContext
from miloco_agent.config import FeishuSettings, MilocoAgentSettings, load_settings
from miloco_agent.prompt.builder import build_system_prompt, resolve_profile
from miloco_agent.prompt.catalog import get_catalog_block
from miloco_agent.runtime.agentscope_runtime import (
    agent_exceeded_max_iters,
    build_agent,
    count_turn_stats_detailed,
    extract_reply_text,
    resolve_react_max_iters,
)
from miloco_agent.runtime.session_guard import session_flight_guard
from miloco_agent.runtime.session_store import format_history_block, session_store
from miloco_agent.trace.recorder import dump_turn_trace
from miloco_agent.trace.store import trace_store

logger = logging.getLogger(__name__)

DEFAULT_WAIT_MS = 180_000


class TurnRunner:
    """Execute one agent turn (blocking until complete or timeout)."""

    async def run_turn(
        self,
        *,
        message: str,
        session_key: str,
        lane: str | None,
        trace_id: str | None,
        timeout_ms: int | None,
        extra_system_prompt: str | None = None,
        persist_history: bool = False,
        feishu: FeishuSettings | None = None,
    ) -> dict[str, Any]:
        wait_ms = timeout_ms if timeout_ms is not None else DEFAULT_WAIT_MS
        wait_s = max(wait_ms / 1000.0, 1.0)
        run_id = str(uuid.uuid4())
        trace_store.start_turn(
            run_id,
            trace_id=trace_id,
            session_key=session_key,
            query=message,
        )

        lock = session_flight_guard.lock_for(session_key)
        async with lock:
            logger.info(
                "agent turn start run_id=%s session=%s lane=%s trace=%s",
                run_id,
                session_key,
                lane,
                trace_id,
            )
            try:
                result = await asyncio.wait_for(
                    self._execute_turn(
                        message=message,
                        session_key=session_key,
                        lane=lane,
                        extra_system_prompt=extra_system_prompt,
                        feishu=feishu,
                    ),
                    timeout=wait_s,
                )
                _finish_turn_with_trace(
                    run_id=run_id,
                    session_key=session_key,
                    trace_id=trace_id,
                    query=message,
                    result=result,
                )
                if persist_history and result["status"] == "ok":
                    reply = str(result.get("meta", {}).get("replyText") or "")
                    self._persist_history(session_key, message, reply, feishu)
                payload: dict[str, Any] = {
                    "runId": run_id,
                    "status": result["status"],
                }
                if result.get("error"):
                    payload["error"] = result["error"]
                return payload
            except TimeoutError:
                logger.warning(
                    "agent turn timeout run_id=%s session=%s wait_s=%.1f",
                    run_id,
                    session_key,
                    wait_s,
                )
                _finish_turn_with_trace(
                    run_id=run_id,
                    session_key=session_key,
                    trace_id=trace_id,
                    query=message,
                    result={
                        "status": "timeout",
                        "error": "timeout",
                        "meta": {
                            "toolCallCount": 0,
                            "llmCallCount": 0,
                            "query": message[:2048],
                        },
                    },
                )
                return {"runId": run_id, "status": "timeout"}
            except Exception as exc:  # noqa: BLE001
                logger.exception("agent turn failed run_id=%s", run_id)
                _finish_turn_with_trace(
                    run_id=run_id,
                    session_key=session_key,
                    trace_id=trace_id,
                    query=message,
                    result={
                        "status": "error",
                        "error": str(exc),
                        "meta": {
                            "toolCallCount": 0,
                            "llmCallCount": 0,
                            "query": message[:2048],
                        },
                    },
                )
                return {
                    "runId": run_id,
                    "status": "error",
                    "error": str(exc),
                }

    async def run_im_reply(
        self,
        *,
        message: str,
        session_key: str,
        lane: str | None,
        trace_id: str | None,
        timeout_ms: int | None = None,
        feishu: FeishuSettings | None = None,
    ) -> str:
        """Run a turn and return assistant text for IM channels (Feishu)."""
        result = await self.run_turn(
            message=message,
            session_key=session_key,
            lane=lane,
            trace_id=trace_id,
            timeout_ms=timeout_ms,
            persist_history=True,
            feishu=feishu,
        )
        status = result.get("status")
        if status == "timeout":
            return "处理超时，请稍后再试。"
        if status != "ok":
            return str(result.get("error") or "处理失败，请稍后再试。")
        run_id = str(result.get("runId") or "")
        if run_id:
            meta = trace_store.peek_done_meta(run_id)
            if meta:
                if meta.get("replyText"):
                    return str(meta["replyText"])
                if meta.get("replyPreview"):
                    return str(meta["replyPreview"])
        return "已完成。"

    async def run_im_reply_streaming(
        self,
        *,
        message: str,
        session_key: str,
        lane: str | None,
        trace_id: str | None,
        on_text: Callable[[str], Awaitable[None]],
        timeout_ms: int | None = None,
        feishu: FeishuSettings | None = None,
    ) -> str:
        """Run a turn with LLM token streaming; invoke on_text with growing buffer."""
        wait_ms = timeout_ms if timeout_ms is not None else DEFAULT_WAIT_MS
        wait_s = max(wait_ms / 1000.0, 1.0)
        run_id = str(uuid.uuid4())
        trace_store.start_turn(
            run_id,
            trace_id=trace_id,
            session_key=session_key,
            query=message,
        )

        lock = session_flight_guard.lock_for(session_key)
        async with lock:
            try:
                result = await asyncio.wait_for(
                    self._execute_turn_streaming(
                        message=message,
                        session_key=session_key,
                        lane=lane,
                        on_text=on_text,
                        feishu=feishu,
                    ),
                    timeout=wait_s,
                )
                _finish_turn_with_trace(
                    run_id=run_id,
                    session_key=session_key,
                    trace_id=trace_id,
                    query=message,
                    result=result,
                )
                reply = str(result.get("replyText") or "已完成。")
                if result["status"] == "ok":
                    self._persist_history(session_key, message, reply, feishu)
                if result["status"] == "timeout":
                    return "处理超时，请稍后再试。"
                if result["status"] != "ok":
                    return str(result.get("error") or "处理失败，请稍后再试。")
                return reply
            except TimeoutError:
                _finish_turn_with_trace(
                    run_id=run_id,
                    session_key=session_key,
                    trace_id=trace_id,
                    query=message,
                    result={
                        "status": "timeout",
                        "error": "timeout",
                        "meta": {"toolCallCount": 0, "llmCallCount": 0},
                    },
                )
                return "处理超时，请稍后再试。"
            except Exception as exc:  # noqa: BLE001
                logger.exception("agent streaming turn failed run_id=%s", run_id)
                _finish_turn_with_trace(
                    run_id=run_id,
                    session_key=session_key,
                    trace_id=trace_id,
                    query=message,
                    result={
                        "status": "error",
                        "error": str(exc),
                        "meta": {"toolCallCount": 0, "llmCallCount": 0},
                    },
                )
                return str(exc) or "处理失败，请稍后再试。"

    def _persist_history(
        self,
        session_key: str,
        user: str,
        assistant: str,
        feishu: FeishuSettings | None,
    ) -> None:
        if not session_key.startswith("feishu:"):
            return
        fs = feishu or load_settings().feishu
        if fs.history_turns <= 0:
            return
        session_store.append(
            session_key,
            user=user,
            assistant=assistant,
            max_turns=fs.history_turns,
            ttl_hours=fs.history_ttl_hours,
        )

    async def _prompt_context(
        self,
        *,
        message: str,
        session_key: str,
        lane: str | None,
        extra_system_prompt: str | None,
        feishu: FeishuSettings | None,
    ) -> str:
        profile = resolve_profile(session_key=session_key, lane=lane, message=message)
        catalog_block = ""
        if profile == "full":
            catalog_block = await get_catalog_block()
        history_block = ""
        if session_key.startswith("feishu:"):
            fs = feishu or load_settings().feishu
            if fs.history_turns > 0:
                turns = session_store.load(
                    session_key,
                    max_turns=fs.history_turns,
                    ttl_hours=fs.history_ttl_hours,
                )
                history_block = format_history_block(turns)
        return build_system_prompt(
            session_key=session_key,
            lane=lane,
            extra_system_prompt=extra_system_prompt,
            message=message,
            history_block=history_block or None,
            catalog_block=catalog_block or None,
        )

    async def _execute_turn_streaming(
        self,
        *,
        message: str,
        session_key: str,
        lane: str | None,
        on_text: Callable[[str], Awaitable[None]],
        feishu: FeishuSettings | None = None,
    ) -> dict[str, Any]:
        settings = load_settings()
        if not settings.llm_configured:
            stub = await self._stub_turn(message, None)
            return {**stub, "replyText": "已完成。"}

        system_prompt = await self._prompt_context(
            message=message,
            session_key=session_key,
            lane=lane,
            extra_system_prompt=None,
            feishu=feishu,
        )
        agent = build_agent(
            system_prompt=system_prompt,
            settings=settings,
            bridge_context=MilocoBridgeContext(session_key=session_key),
            stream=True,
        )
        stream_buffer = ""
        async for event in agent.reply_stream(
            UserMsg(name="user", content=message)
        ):
            if isinstance(event, ReplyStartEvent):
                stream_buffer = ""
            elif isinstance(event, TextBlockDeltaEvent):
                stream_buffer += event.delta
                await on_text(stream_buffer)

        reply_text = _last_assistant_text(agent) or stream_buffer
        stats = count_turn_stats_detailed(agent)
        if reply_text and reply_text != stream_buffer:
            await on_text(reply_text)
        return _turn_result_from_agent(
            message=message,
            reply_text=reply_text,
            agent=agent,
            stats=stats,
            include_reply_text=True,
        )

    async def _execute_turn(
        self,
        *,
        message: str,
        session_key: str,
        lane: str | None,
        extra_system_prompt: str | None,
        feishu: FeishuSettings | None = None,
    ) -> dict[str, Any]:
        settings = load_settings()
        if not settings.llm_configured:
            return await self._stub_turn(message, extra_system_prompt)

        system_prompt = await self._prompt_context(
            message=message,
            session_key=session_key,
            lane=lane,
            extra_system_prompt=extra_system_prompt,
            feishu=feishu,
        )
        agent = build_agent(
            system_prompt=system_prompt,
            settings=settings,
            bridge_context=MilocoBridgeContext(session_key=session_key),
        )
        reply = await agent.reply(UserMsg(name="user", content=message))
        reply_text = extract_reply_text(reply)
        stats = count_turn_stats_detailed(agent)
        logger.info(
            "agent turn done session=%s llm_calls=%d tool_calls=%d reply_len=%d",
            session_key,
            stats["llmCallCount"],
            stats["toolCallCount"],
            len(reply_text),
        )
        if stats.get("exceededMaxIters"):
            logger.warning(
                "agent turn exceeded max_iters session=%s iters=%d limit=%d",
                session_key,
                agent.state.cur_iter,
                agent.react_config.max_iters,
            )
        return _turn_result_from_agent(
            message=message,
            reply_text=reply_text,
            agent=agent,
            stats=stats,
        )

    async def _stub_turn(
        self,
        message: str,
        extra_system_prompt: str | None,
    ) -> dict[str, Any]:
        """P0-compatible stub when LLM is not configured (tests / dry-run)."""
        await asyncio.sleep(0.01)
        reply_preview = message[:120].replace("\n", " ")
        logger.info(
            "agent turn stub message_preview=%r extra=%s",
            reply_preview,
            bool(extra_system_prompt),
        )
        return {
            "status": "ok",
            "meta": {
                "toolCallCount": 0,
                "llmCallCount": 0,
                "query": message[:2048],
                "replyPreview": reply_preview,
                "replyText": reply_preview,
                "stub": True,
            },
        }


turn_runner = TurnRunner()


def _build_turn_meta(
    message: str,
    reply_text: str,
    stats: dict[str, object],
) -> dict[str, Any]:
    return {
        **stats,
        "query": message[:2048],
        "replyPreview": reply_text[:200],
        "replyText": reply_text,
    }


def _turn_result_from_agent(
    *,
    message: str,
    reply_text: str,
    agent: Any,
    stats: dict[str, object],
    include_reply_text: bool = False,
) -> dict[str, Any]:
    exceeded = bool(stats.get("exceededMaxIters")) or agent_exceeded_max_iters(agent)
    meta = _build_turn_meta(message, reply_text, stats)
    if exceeded:
        err = (
            f"ReAct 循环达到上限（{agent.react_config.max_iters} 轮），任务未完成。"
            f" 可在 config.json 的 agent.runtime.cron_react_max_iters 调大。"
        )
        meta["errorMsg"] = err
        payload: dict[str, Any] = {
            "status": "error",
            "error": err,
            "meta": meta,
            "agent": agent,
        }
        if include_reply_text:
            payload["replyText"] = reply_text
        return payload
    payload = {
        "status": "ok",
        "meta": meta,
        "agent": agent,
    }
    if include_reply_text:
        payload["replyText"] = reply_text
    return payload


def _finish_turn_with_trace(
    *,
    run_id: str,
    session_key: str,
    trace_id: str | None,
    query: str,
    result: dict[str, Any],
) -> None:
    meta = dict(result.get("meta") or {})
    agent = result.pop("agent", None)
    success = result.get("status") == "ok"
    jsonl_path = dump_turn_trace(
        run_id=run_id,
        session_key=session_key,
        trace_id=trace_id,
        query=query,
        success=success,
        error_msg=result.get("error"),
        agent=agent,
        meta=meta,
    )
    if jsonl_path:
        meta["jsonlPath"] = jsonl_path
    trace_store.finish_turn(
        run_id,
        success=success,
        error_msg=result.get("error"),
        error_count=int(meta.get("errorCount") or 0),
        extra_meta=meta,
    )


def _last_assistant_text(agent) -> str:
    for msg in reversed(agent.state.context):
        if getattr(msg, "role", None) == "assistant":
            text = extract_reply_text(msg)
            if text:
                return text
    return ""
