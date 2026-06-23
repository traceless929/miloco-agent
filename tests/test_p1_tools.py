"""P1 unit tests for prompt, tools, and turn runner."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from miloco_agent.config import LlmSettings, MilocoAgentSettings, ServerSettings
from miloco_agent.prompt.builder import build_system_prompt, resolve_profile
from miloco_agent.runtime.turn_runner import TurnRunner
from miloco_agent.tools.devices import compact_device_row, tool_device_list
from miloco_agent.tools.miloco_client import MilocoApiClient


def test_resolve_profile_rule() -> None:
    assert resolve_profile(session_key="agent:main:miloco-rule") == "rule"
    assert resolve_profile(session_key="x", lane="miloco-rule") == "rule"


def test_resolve_profile_suggestion() -> None:
    assert resolve_profile(session_key="agent:main:miloco-suggest") == "suggestion"


def test_build_system_prompt_includes_extra() -> None:
    text = build_system_prompt(
        session_key="agent:main:miloco-rule",
        extra_system_prompt="关灯",
    )
    assert "规则触发" in text
    assert "关灯" in text


def test_build_system_prompt_suggestion_notify() -> None:
    text = build_system_prompt(session_key="agent:main:miloco-suggest")
    assert "miloco-notify" in text or "miloco_im_push" in text


def test_compact_device_row() -> None:
    row = compact_device_row(
        {"did": "1", "name": "灯", "online": True, "room_name": "客厅"}
    )
    assert row["did"] == "1"
    assert row["room"] == "客厅"


@pytest.mark.asyncio
async def test_tool_device_list_filters_room() -> None:
    client = MilocoApiClient(
        MilocoAgentSettings(server=ServerSettings(token="t"))
    )
    client.device_list = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {"did": "a", "name": "A", "online": True, "room_name": "客厅"},
            {"did": "b", "name": "B", "online": True, "room_name": "卧室"},
        ]
    )
    out = await tool_device_list(client, room="客厅")
    data = json.loads(out)
    assert data["count"] == 1
    assert data["devices"][0]["did"] == "a"


@pytest.mark.asyncio
async def test_turn_runner_stub_without_llm() -> None:
    runner = TurnRunner()
    with patch(
        "miloco_agent.runtime.turn_runner.load_settings",
        return_value=MilocoAgentSettings(),
    ):
        result = await runner.run_turn(
            message="ping",
            session_key="agent:main:miloco",
            lane=None,
            trace_id="t1",
            timeout_ms=3000,
        )
    assert result["status"] == "ok"
    assert "runId" in result


@pytest.mark.asyncio
async def test_turn_runner_llm_path_mocked() -> None:
    runner = TurnRunner()
    settings = MilocoAgentSettings(
        server=ServerSettings(token="tok"),
        llm=LlmSettings(
            base_url="https://example.com/v1",
            model="test-model",
            api_key="sk-test",
        ),
    )

    class _FakeReply:
        def get_text_content(self) -> str:
            return "done"

    fake_agent = type("A", (), {"state": type("S", (), {"context": [], "cur_iter": 1})()})()

    async def fake_reply(_msg):
        return _FakeReply()

    fake_agent.reply = fake_reply  # type: ignore[attr-defined]

    with (
        patch("miloco_agent.runtime.turn_runner.load_settings", return_value=settings),
        patch("miloco_agent.runtime.turn_runner.build_agent", return_value=fake_agent),
        patch(
            "miloco_agent.runtime.turn_runner.count_turn_stats_detailed",
            return_value={
                "llmCallCount": 1,
                "toolCallCount": 0,
                "llmTotalMs": 0.0,
                "toolTotalMs": 0.0,
                "toolMaxMs": 0.0,
                "slowestToolName": None,
                "errorCount": 0,
            },
        ),
        patch(
            "miloco_agent.runtime.turn_runner.get_catalog_block",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "miloco_agent.runtime.turn_runner.extract_reply_text",
            return_value="done",
        ),
    ):
        result = await runner.run_turn(
            message="列出设备",
            session_key="agent:main:miloco-rule",
            lane="miloco-rule",
            trace_id="t2",
            timeout_ms=5000,
        )
    assert result["status"] == "ok"
