"""OpenClaw-compatible tool names for AgentScope (Sidecar bridge layer)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk

from miloco_agent.bridge.context import MilocoBridgeContext
from miloco_agent.bridge.memory import memory_search
from miloco_agent.bridge.notify import bind_notify_channel, push_im
from miloco_agent.tools.habit_suggest import run_habit_suggest


def _chunk(data: dict[str, Any] | str, *, error: bool = False) -> ToolChunk:
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return ToolChunk(
        content=[TextBlock(text=text)],
        state=ToolResultState.ERROR if error else ToolResultState.SUCCESS,
        is_last=True,
    )


class _BridgeTool(ToolBase):
    is_mcp = False
    is_concurrency_safe = True
    is_external_tool = False
    is_state_injected = False

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        _ = tool_input, context
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Miloco bridge tool auto-allowed.",
        )


class MilocoImPushTool(_BridgeTool):
    """OpenClaw plugin: miloco_im_push."""

    name = "miloco_im_push"
    description = (
        "给主人推送一条 IM 通知。通常只传 message 调用即可。\n"
        "配合 miloco-notify skill 使用。若返回 ok=false 且 needsBind=true，"
        "必须立刻再次调用：message 不变，补上 bindHint（把 bindHintExample 翻译成用户语言）。"
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "要发给主人的通知正文"},
            "bindHint": {
                "type": "string",
                "description": "仅当上次 needsBind=true 时传：绑定引导语",
            },
        },
        "required": ["message"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, ctx: MilocoBridgeContext | None = None) -> None:
        self._ctx = ctx

    async def __call__(self, message: str, bindHint: str | None = None) -> ToolChunk:
        result = await push_im(message, bind_hint=bindHint, ctx=self._ctx)
        return _chunk(result, error=not result.get("ok"))


class MilocoNotifyBindTool(_BridgeTool):
    """OpenClaw plugin: miloco_notify_bind."""

    name = "miloco_notify_bind"
    description = "绑定通知渠道。Sidecar 将当前飞书会话 open_id 写入 notify_channel。"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, ctx: MilocoBridgeContext | None = None) -> None:
        self._ctx = ctx

    async def __call__(self) -> ToolChunk:
        result = bind_notify_channel(self._ctx)
        return _chunk(result, error=not result.get("ok"))


class MilocoHabitSuggestTool(_BridgeTool):
    """OpenClaw plugin: miloco_habit_suggest."""

    name = "miloco_habit_suggest"
    description = (
        "习惯建议候选库（防骚扰状态机）。配合 miloco-habit-suggest skill。"
        "action: list | record | mark_asked | resolve。"
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "record", "mark_asked", "resolve"],
            },
            "key": {"type": "string"},
            "subject": {"type": "string"},
            "habit": {"type": "string"},
            "suggestion": {"type": "string"},
            "title": {"type": "string"},
            "evidence": {"type": "string"},
            "item_id": {"type": "string"},
            "outcome": {
                "type": "string",
                "enum": ["accepted", "rejected", "created"],
            },
            "task_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }
    is_read_only = False

    async def __call__(self, action: str, **kwargs: Any) -> ToolChunk:
        payload = {"action": action, **kwargs}
        result = run_habit_suggest(payload)
        return _chunk(result, error=not result.get("ok", True))


class CronBridgeTool(_BridgeTool):
    """OpenClaw cron tool — user task jobs in Sidecar user_cron_registry."""

    name = "cron"
    description = (
        "OpenClaw-compatible cron 管理（Sidecar 桥接）。"
        "action: add | remove | list | disable | enable。"
        "add 时传 name、cron 或 at、message；remove/disable/enable 传 jobId。"
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "list", "disable", "enable"],
            },
            "name": {"type": "string"},
            "cron": {"type": "string", "description": "5-field cron expression"},
            "at": {"type": "string", "description": "ISO datetime for one-shot (converted to cron)"},
            "message": {"type": "string"},
            "jobId": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }
    is_read_only = False
    is_concurrency_safe = False

    async def __call__(
        self,
        action: str,
        name: str | None = None,
        cron: str | None = None,
        at: str | None = None,
        message: str | None = None,
        jobId: str | None = None,
        enabled: bool | None = None,
    ) -> ToolChunk:
        from miloco_agent.cron.scheduler import reload_user_cron_jobs
        from miloco_agent.cron.user_registry import user_cron_registry
        from miloco_agent.tools.cron_tools import tool_cron_add, tool_cron_list, tool_cron_remove

        if action == "list":
            return _chunk(json.loads(tool_cron_list()))

        if action == "remove":
            if not jobId:
                return _chunk({"ok": False, "error": "jobId required"}, error=True)
            raw = tool_cron_remove(jobId)
            reload_user_cron_jobs()
            body = json.loads(raw)
            return _chunk(body, error=not body.get("ok"))

        if action in ("disable", "enable"):
            if not jobId:
                return _chunk({"ok": False, "error": "jobId required"}, error=True)
            ok = user_cron_registry.set_enabled(jobId, action == "enable")
            reload_user_cron_jobs()
            return _chunk({"ok": ok, "jobId": jobId, "enabled": action == "enable"}, error=not ok)

        if action == "add":
            cron_expr = cron or _at_to_cron(at)
            if not name or not cron_expr or not message:
                return _chunk(
                    {"ok": False, "error": "name, cron|at, message required"},
                    error=True,
                )
            raw = await tool_cron_add(
                name=name,
                cron_expr=cron_expr,
                message=message,
                enabled=enabled if enabled is not None else True,
            )
            reload_user_cron_jobs()
            body = json.loads(raw)
            return _chunk(body, error=not body.get("ok"))

        return _chunk({"ok": False, "error": f"unknown action: {action}"}, error=True)


class MemorySearchTool(_BridgeTool):
    """OpenClaw memory_search — search local perception memory files."""

    name = "memory_search"
    description = "检索感知记忆（$MILOCO_HOME/memory/*-miloco-perception.md）。"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "days": {"type": "integer", "description": "Search last N days (default 7)."},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    is_read_only = True

    async def __call__(self, query: str, days: int = 7) -> ToolChunk:
        result = memory_search(query, days=days)
        return _chunk(result, error=not result.get("ok", True))


def _at_to_cron(at: str | None) -> str | None:
    if not at:
        return None
    try:
        dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        local = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        return f"{local.minute} {local.hour} {local.day} {local.month} *"
    except ValueError:
        return None


def build_bridge_tools(ctx: MilocoBridgeContext | None = None) -> list[ToolBase]:
    return [
        MilocoImPushTool(ctx),
        MilocoNotifyBindTool(ctx),
        MilocoHabitSuggestTool(),
        CronBridgeTool(),
        MemorySearchTool(),
    ]
