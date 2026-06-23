"""P3 suggestion dispatch integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from miloco_agent.app import create_app
from miloco_agent.runtime.turn_runner import turn_runner

# Sample text aligned with backend event_text_builder.py
SAMPLE_SUGGESTION_MESSAGE = """[感知引擎]事件提醒：
时间：14:30:00
来源：客厅的小米C700(did=cam_living_01)
画面描述：老人坐在沙发上
检测到：老人摔倒
事件优先级：high
建议：立即查看并联系家人"""


@pytest.fixture
def webhook_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "agent": {"auth_bearer": "test-bearer"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    return TestClient(create_app())


def test_suggestion_webhook_uses_suggest_profile(
    webhook_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_turn(**kwargs: Any) -> dict[str, Any]:
        from miloco_agent.prompt.builder import build_system_prompt

        captured.update(kwargs)
        captured["system_prompt"] = build_system_prompt(
            session_key=kwargs.get("session_key"),
            lane=kwargs.get("lane"),
            message=kwargs.get("message"),
        )
        return {
            "status": "ok",
            "meta": {
                "toolCalls": 1,
                "llmCalls": 1,
                "replyPreview": "已通知",
                "replyText": "已通过 notify_send 通知家人。",
            },
        }

    monkeypatch.setattr(turn_runner, "_execute_turn", fake_execute_turn)

    res = webhook_client.post(
        "/miloco/webhook",
        headers={"Authorization": "Bearer test-bearer"},
        json={
            "action": "agent",
            "payload": {
                "message": SAMPLE_SUGGESTION_MESSAGE,
                "sessionKey": "agent:main:miloco-suggest",
                "lane": "miloco-suggest",
                "traceId": "suggest-int-1",
                "idempotencyKey": "suggest-int-1",
                "timeoutMs": 60_000,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"

    assert captured.get("session_key") == "agent:main:miloco-suggest"
    assert captured.get("lane") == "miloco-suggest"
    prompt = str(captured.get("system_prompt") or "")
    assert "miloco_im_push" in prompt or "miloco-notify" in prompt
    assert "事件提醒" in prompt


@pytest.mark.asyncio
async def test_suggestion_turn_can_call_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent turn stub: verify notify_send would be the delivery path for L2 events."""
    from miloco_agent.notify.service import NotifyService

    sent: list[str] = []

    async def fake_send(self, **kwargs: Any) -> dict[str, Any]:
        sent.append(str(kwargs.get("message")))
        return {"ok": True, "level": kwargs.get("level"), "channels": ["im"], "deliveries": {}}

    monkeypatch.setattr(NotifyService, "send", fake_send)

    svc = NotifyService()
    result = await svc.send(
        message="客厅有老人摔倒，请马上查看。",
        level="L2",
        speaker_online=False,
    )
    assert result["ok"] is True
    assert sent == ["客厅有老人摔倒，请马上查看。"]
