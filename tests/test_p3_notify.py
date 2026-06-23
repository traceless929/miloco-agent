"""P3 notify policy and service tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from miloco_agent.config import MilocoAgentSettings
from miloco_agent.notify.policy import normalize_level, plan_delivery
from miloco_agent.notify.service import NotifyService
from miloco_agent.prompt.builder import build_system_prompt
from miloco_agent.tools.devices import _find_play_text_action_iid, tool_speaker_tts
from miloco_agent.tools.miloco_client import MilocoApiClient


def test_normalize_level() -> None:
    assert normalize_level("l2") == "L2"
    assert normalize_level("danger") == "L1"
    assert normalize_level(None) == "L3"


def test_plan_l1_includes_im_and_push() -> None:
    plan = plan_delivery(
        message="奶奶摔倒了", level="L1", speaker_did="sp1", speaker_online=True
    )
    assert plan.channels == ("tts", "im", "miot_push")


def test_plan_l3_im_when_no_speaker() -> None:
    plan = plan_delivery(message="该吃药了", level="L3")
    assert plan.channels == ("im",)


def test_suggestion_prompt_has_notify() -> None:
    text = build_system_prompt(session_key="agent:main:miloco-suggest")
    assert "miloco_im_push" in text or "miloco-notify" in text
    assert "事件提醒" in text


def test_find_play_text_action_iid() -> None:
    spec = {
        "services": [
            {
                "actions": [
                    {"iid": "action.3.1", "name": "play-text", "description": "TTS"},
                ]
            }
        ]
    }
    assert _find_play_text_action_iid(spec) == "action.3.1"


@pytest.mark.asyncio
async def test_notify_service_im_only() -> None:
    svc = NotifyService()
    svc._feishu_settings.default_receive_open_id = "ou_test"
    svc._feishu_settings.enabled = True
    svc._feishu_settings.app_id = "x"
    svc._feishu_settings.app_secret = "y"
    svc._feishu.send_reply = AsyncMock()  # type: ignore[method-assign]
    svc._client.send_notify = AsyncMock()  # type: ignore[method-assign]

    result = await svc.send(message="测试通知", level="L1", speaker_online=False)
    assert result["ok"] is True
    assert "im" in result["deliveries"]
    assert "miot_push" in result["deliveries"]
    svc._feishu.send_reply.assert_awaited_once()
    svc._client.send_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_speaker_tts_calls_control() -> None:
    client = MilocoApiClient(MilocoAgentSettings())
    client.device_spec = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "services": [{"actions": [{"iid": "action.1.9", "name": "play-text"}]}]
        }
    )
    client.device_control = AsyncMock(return_value={"code": 0})  # type: ignore[method-assign]

    raw = await tool_speaker_tts(client, did="did_sp", text="晚安")
    body = json.loads(raw)
    assert body["ok"] is True
    client.device_control.assert_awaited_once()
    call = client.device_control.await_args
    assert call.kwargs["control_type"] == "call_action"
    assert call.kwargs["params"] == ["晚安"]
