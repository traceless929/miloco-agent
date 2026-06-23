"""AgentScope ToolBase wrappers for Miloco device APIs."""

from __future__ import annotations

from typing import Any

import json

from agentscope.message import TextBlock, ToolResultState
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.tool import ToolBase, ToolChunk

from miloco_agent.tools.devices import (
    tool_device_control,
    tool_device_list,
    tool_device_spec,
    tool_speaker_tts,
)
from miloco_agent.tools.miloco_client import MilocoApiClient
from miloco_agent.notify.service import NotifyService
from miloco_agent.tools.home_profile import run_home_profile_tool
from miloco_agent.tools.perception_memory import run_perception_memory_tool
from miloco_agent.tools.cron_tools import run_cron_tool
from miloco_agent.tools.habit_suggest import run_habit_suggest


def _text_chunk(text: str, *, error: bool = False) -> ToolChunk:
    return ToolChunk(
        content=[TextBlock(text=text)],
        state=ToolResultState.ERROR if error else ToolResultState.SUCCESS,
        is_last=True,
    )


class _MilocoDeviceTool(ToolBase):
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
            message="Miloco device tool auto-allowed.",
        )


class DeviceListTool(_MilocoDeviceTool):
    name = "device_list"
    description = (
        "List MiOT devices in the current home. "
        "Use before control to resolve did and check online status."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "room": {
                "type": "string",
                "description": "Optional room name filter (substring match).",
            },
            "online_only": {
                "type": "boolean",
                "description": "If true, only return online devices.",
            },
        },
        "additionalProperties": False,
    }
    is_read_only = True

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def __call__(
        self,
        room: str | None = None,
        online_only: bool = False,
    ) -> ToolChunk:
        text = await tool_device_list(
            self._client,
            room=room,
            online_only=online_only,
        )
        return _text_chunk(text)


class DeviceSpecTool(_MilocoDeviceTool):
    name = "device_spec"
    description = "Get a single device spec (services/properties/actions) by did."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "did": {"type": "string", "description": "Device ID."},
        },
        "required": ["did"],
        "additionalProperties": False,
    }
    is_read_only = True

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def __call__(self, did: str) -> ToolChunk:
        text = await tool_device_spec(self._client, did=did)
        return _text_chunk(text)


class DeviceControlTool(_MilocoDeviceTool):
    name = "device_control"
    description = (
        "Control a device: set_property, set_properties, or call_action. "
        "Prefer device_spec to find correct iid before writing."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "did": {"type": "string"},
            "control_type": {
                "type": "string",
                "enum": ["set_property", "set_properties", "call_action"],
            },
            "iid": {
                "type": "string",
                "description": "Property/action IID, e.g. prop.2.1",
            },
            "value": {"description": "Value for set_property."},
            "properties_json": {
                "type": "string",
                "description": (
                    'JSON array for set_properties, e.g. [{"iid":"prop.2.1","value":true}]'
                ),
            },
            "params_json": {
                "type": "string",
                "description": "JSON array params for call_action.",
            },
        },
        "required": ["did", "control_type"],
        "additionalProperties": False,
    }
    is_read_only = False
    is_concurrency_safe = False

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def __call__(
        self,
        did: str,
        control_type: str,
        iid: str | None = None,
        value: Any = None,
        properties_json: str | None = None,
        params_json: str | None = None,
    ) -> ToolChunk:
        text = await tool_device_control(
            self._client,
            did=did,
            control_type=control_type,
            iid=iid,
            value=value,
            properties_json=properties_json,
            params_json=params_json,
        )
        return _text_chunk(text, error='"ok": false' in text.lower())


class DeviceSpeakerTtsTool(_MilocoDeviceTool):
    name = "device_speaker_tts"
    description = (
        "Play TTS on a MiOT speaker (play-text action). "
        "Use device_list to find online speaker did in target room."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "did": {"type": "string", "description": "Speaker device ID."},
            "text": {"type": "string", "description": "Short phrase to speak."},
            "action_iid": {
                "type": "string",
                "description": "Optional play-text action IID from device_spec.",
            },
        },
        "required": ["did", "text"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def __call__(
        self,
        did: str,
        text: str,
        action_iid: str | None = None,
    ) -> ToolChunk:
        try:
            raw = await tool_speaker_tts(
                self._client,
                did=did,
                text=text,
                action_iid=action_iid,
            )
            return _text_chunk(raw, error='"ok": false' in raw.lower())
        except Exception as exc:  # noqa: BLE001
            return _text_chunk(
                json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                error=True,
            )


class NotifySendTool(_MilocoDeviceTool):
    name = "notify_send"
    description = (
        "Proactively notify household members (not IM reply). "
        "Levels: L1 danger, L2 warning, L3 daily. "
        "Routes to Feishu IM / MiOT push / speaker TTS per policy."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "level": {
                "type": "string",
                "enum": ["L1", "L2", "L3"],
                "description": "L1/L2 danger paths use IM+push (+TTS if speaker online).",
            },
            "room": {
                "type": "string",
                "description": "Incident or target room for TTS selection.",
            },
            "speaker_did": {
                "type": "string",
                "description": "Online speaker did for TTS (from device_list).",
            },
            "speaker_online": {"type": "boolean"},
            "anyone_home": {
                "type": "boolean",
                "description": "False = skip TTS when nobody home.",
            },
        },
        "required": ["message"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client
        self._notify = NotifyService(client=client)

    async def __call__(
        self,
        message: str,
        level: str = "L3",
        room: str | None = None,
        speaker_did: str | None = None,
        speaker_online: bool = False,
        anyone_home: bool | None = None,
    ) -> ToolChunk:
        result = await self._notify.send(
            message=message,
            level=level,
            room=room,
            speaker_did=speaker_did,
            speaker_online=speaker_online,
            anyone_home=anyone_home,
        )
        raw = json.dumps(result, ensure_ascii=False)
        return _text_chunk(raw, error=not result.get("ok"))


class _JsonToolBase(_MilocoDeviceTool):
    """Delegate to run_*_tool helpers."""

    _tool_name: str = ""

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def _dispatch(self, **kwargs: Any) -> ToolChunk:
        raise NotImplementedError

    async def __call__(self, **kwargs: Any) -> ToolChunk:
        try:
            raw = await self._dispatch(**kwargs)
            return _text_chunk(raw, error='"ok": false' in raw.lower())
        except Exception as exc:  # noqa: BLE001
            return _text_chunk(
                json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                error=True,
            )


class HomeProfileReadTool(_JsonToolBase):
    name = "home_profile_read"
    description = "Read rendered home profile markdown (canonical profile.md)."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    is_read_only = True

    async def _dispatch(self) -> str:
        return await run_home_profile_tool(self._client, self.name, {})


class HomeProfileListTool(_JsonToolBase):
    name = "home_profile_list"
    description = "List home profile or candidate entries (with ids for merge/replace)."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["profile", "candidates", "both"],
                "description": "Which store to list.",
            },
        },
        "additionalProperties": False,
    }
    is_read_only = True

    async def _dispatch(self, target: str = "both") -> str:
        return await run_home_profile_tool(
            self._client, self.name, {"target": target}
        )


class HomeProfileWriteTool(_JsonToolBase):
    name = "home_profile_write"
    description = (
        "Write home profile or candidates via ops JSON array "
        "(add/merge/replace/delete). Call home_profile_list first."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "ops_json": {
                "type": "string",
                "description": "JSON array of ops, e.g. [{\"op\":\"add\",...}]",
            },
            "target": {
                "type": "string",
                "enum": ["profile", "candidates"],
            },
            "user_edit": {
                "type": "boolean",
                "description": "True when user directly told this fact.",
            },
        },
        "required": ["ops_json"],
        "additionalProperties": False,
    }
    is_read_only = False

    async def _dispatch(
        self,
        ops_json: str,
        target: str = "profile",
        user_edit: bool = False,
    ) -> str:
        return await run_home_profile_tool(
            self._client,
            self.name,
            {"ops_json": ops_json, "target": target, "user_edit": user_edit},
        )


class HomeProfileCommitTool(_JsonToolBase):
    name = "home_profile_commit"
    description = "Commit profile changes and re-render profile.md."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    is_read_only = False

    async def _dispatch(self) -> str:
        return await run_home_profile_tool(self._client, self.name, {})


class PerceptionLogsTool(_JsonToolBase):
    name = "perception_logs"
    description = (
        "Fetch perception logs. Default incremental mode uses perception_cursor.json."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "incremental": {
                "type": "boolean",
                "description": "True = after cursor (digest). False = use since only.",
            },
            "since": {
                "type": "string",
                "description": "Relative window e.g. 1h, 30m (disables cursor).",
            },
            "limit": {"type": "integer"},
            "update_cursor": {
                "type": "boolean",
                "description": "Advance cursor after incremental fetch.",
            },
        },
        "additionalProperties": False,
    }
    is_read_only = True

    async def _dispatch(
        self,
        incremental: bool = True,
        since: str | None = None,
        limit: int | None = None,
        update_cursor: bool = True,
    ) -> str:
        return await run_perception_memory_tool(
            self._client,
            self.name,
            {
                "incremental": incremental,
                "since": since,
                "limit": limit,
                "update_cursor": update_cursor,
            },
        )


class MemoryPerceptionReadTool(_JsonToolBase):
    name = "memory_perception_read"
    description = "Read local perception memory markdown for a day."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "day": {
                "type": "string",
                "description": "YYYY-MM-DD; default today.",
            },
        },
        "additionalProperties": False,
    }
    is_read_only = True

    async def _dispatch(self, day: str | None = None) -> str:
        return await run_perception_memory_tool(
            self._client, self.name, {"day": day}
        )


class MemoryPerceptionAppendTool(_JsonToolBase):
    name = "memory_perception_append"
    description = "Append digest lines to today's perception memory file."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Markdown lines to append."},
        },
        "required": ["text"],
        "additionalProperties": False,
    }
    is_read_only = False

    async def _dispatch(self, text: str) -> str:
        return await run_perception_memory_tool(
            self._client, self.name, {"text": text}
        )


class HabitSuggestTool(_JsonToolBase):
    name = "habit_suggest"
    description = "Habit suggestion state: list|record|mark_asked|resolve."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "record", "mark_asked", "resolve"],
            },
            "key": {"type": "string"},
            "title": {"type": "string"},
            "subject": {"type": "string"},
            "habit": {"type": "string"},
            "suggestion": {"type": "string"},
            "evidence": {"type": "string"},
            "item_id": {"type": "string"},
            "outcome": {"type": "string", "enum": ["created", "rejected"]},
            "task_id": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }
    is_read_only = False

    async def _dispatch(self, action: str, **kwargs: Any) -> str:
        result = run_habit_suggest({"action": action, **kwargs})
        return json.dumps(result, ensure_ascii=False)


class CronAddTool(_MilocoDeviceTool):
    name = "cron_add"
    description = "Create user task cron job; returns jobId. Optionally link task_id."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "cron_expr": {"type": "string", "description": "5-field cron e.g. 0 9 * * *"},
            "message": {"type": "string"},
            "task_id": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
        "required": ["name", "cron_expr", "message"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, client: MilocoApiClient | None = None) -> None:
        self._client = client

    async def __call__(
        self,
        name: str,
        cron_expr: str,
        message: str,
        task_id: str | None = None,
        enabled: bool = True,
    ) -> ToolChunk:
        try:
            raw = await run_cron_tool(
                "cron_add",
                {
                    "name": name,
                    "cron_expr": cron_expr,
                    "message": message,
                    "task_id": task_id,
                    "enabled": enabled,
                },
            )
            from miloco_agent.cron.scheduler import reload_user_cron_jobs

            reload_user_cron_jobs()
            return _text_chunk(raw, error='"ok": false' in raw.lower())
        except Exception as exc:  # noqa: BLE001
            return _text_chunk(
                json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                error=True,
            )


class CronListTool(_MilocoDeviceTool):
    name = "cron_list"
    description = "List user cron jobs."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    is_read_only = True

    def __init__(self, client: MilocoApiClient | None = None) -> None:
        self._client = client

    async def __call__(self) -> ToolChunk:
        return _text_chunk(await run_cron_tool("cron_list", {}))


class CronRemoveTool(_MilocoDeviceTool):
    name = "cron_remove"
    description = "Remove user cron job by jobId."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, client: MilocoApiClient | None = None) -> None:
        self._client = client

    async def __call__(self, job_id: str) -> ToolChunk:
        raw = await run_cron_tool("cron_remove", {"job_id": job_id})
        from miloco_agent.cron.scheduler import reload_user_cron_jobs

        reload_user_cron_jobs()
        return _text_chunk(raw, error='"ok": false' in raw.lower())


class TaskDisableTool(_MilocoDeviceTool):
    name = "task_disable"
    description = "Disable task; applies agent_pending cron ops."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def __call__(self, task_id: str) -> ToolChunk:
        from miloco_agent.tools.cron_tools import tool_task_disable

        raw = await tool_task_disable(self._client, task_id)
        from miloco_agent.cron.scheduler import reload_user_cron_jobs

        reload_user_cron_jobs()
        return _text_chunk(raw, error='"ok": false' in raw.lower())


class TaskDeleteTool(_MilocoDeviceTool):
    name = "task_delete"
    description = "Delete task with reason; applies agent_pending cron remove ops."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "reason": {
                "type": "string",
                "enum": ["completed", "expired", "abandoned"],
            },
        },
        "required": ["task_id"],
        "additionalProperties": False,
    }
    is_read_only = False

    def __init__(self, client: MilocoApiClient) -> None:
        self._client = client

    async def __call__(
        self, task_id: str, reason: str = "completed"
    ) -> ToolChunk:
        from miloco_agent.tools.cron_tools import tool_task_delete

        raw = await tool_task_delete(self._client, task_id, reason=reason)
        from miloco_agent.cron.scheduler import reload_user_cron_jobs

        reload_user_cron_jobs()
        return _text_chunk(raw, error='"ok": false' in raw.lower())


def build_agentscope_toolkit(
    client: MilocoApiClient | None = None,
    *,
    bridge_context=None,
):
    """Delegate to OpenClaw bridge toolkit (skills + Bash + bridge tools)."""
    from miloco_agent.bridge.toolkit import (
        build_agentscope_toolkit as _build_bridge_toolkit,
    )

    return _build_bridge_toolkit(client, bridge_context=bridge_context)


def build_legacy_toolkit(client: MilocoApiClient | None = None):
    """Pre-bridge HTTP tools — kept for unit tests / gradual migration."""
    from agentscope.tool import Toolkit

    api = client or MilocoApiClient()
    return Toolkit(
        tools=[
            DeviceListTool(api),
            DeviceSpecTool(api),
            DeviceControlTool(api),
            DeviceSpeakerTtsTool(api),
            NotifySendTool(api),
            HomeProfileReadTool(api),
            HomeProfileListTool(api),
            HomeProfileWriteTool(api),
            HomeProfileCommitTool(api),
            PerceptionLogsTool(api),
            MemoryPerceptionReadTool(api),
            MemoryPerceptionAppendTool(api),
            HabitSuggestTool(api),
            CronAddTool(api),
            CronListTool(api),
            CronRemoveTool(api),
            TaskDisableTool(api),
            TaskDeleteTool(api),
        ]
    )
