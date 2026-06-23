"""Webhook contract tests — aligned with miloco.utils.agent_client expectations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from miloco_agent.app import create_app
from miloco_agent.config import MilocoAgentSettings, load_settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    config = {
        "server": {"host": "127.0.0.1", "port": 1810, "token": "test-token"},
        "agent": {
            "webhook_url": "http://127.0.0.1:18789/miloco/webhook",
            "auth_bearer": "test-bearer",
        },
    }
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))

    app = create_app()
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-bearer"}


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_webhook_agent_ok(client: TestClient) -> None:
    res = client.post(
        "/miloco/webhook",
        headers=_auth_headers(),
        json={
            "action": "agent",
            "payload": {
                "message": "ping",
                "sessionKey": "agent:main:miloco-rule",
                "lane": "miloco-rule",
                "traceId": "trace-1",
                "idempotencyKey": "trace-1",
                "timeoutMs": 5000,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    data = body["data"]
    assert data["status"] == "ok"
    assert isinstance(data["runId"], str) and data["runId"]


def test_webhook_agent_idempotency(client: TestClient) -> None:
    payload = {
        "action": "agent",
        "payload": {
            "message": "same",
            "sessionKey": "agent:main:miloco",
            "traceId": "idem-1",
            "idempotencyKey": "idem-1",
            "timeoutMs": 5000,
        },
    }
    r1 = client.post("/miloco/webhook", headers=_auth_headers(), json=payload)
    r2 = client.post("/miloco/webhook", headers=_auth_headers(), json=payload)
    assert r1.json()["data"]["runId"] == r2.json()["data"]["runId"]


def test_webhook_unauthorized(client: TestClient) -> None:
    res = client.post(
        "/miloco/webhook",
        json={"action": "agent", "payload": {"message": "x"}},
    )
    assert res.status_code == 401


def test_webhook_unknown_action(client: TestClient) -> None:
    res = client.post(
        "/miloco/webhook",
        headers=_auth_headers(),
        json={"action": "nope", "payload": {}},
    )
    assert res.status_code == 404
    body = res.json()
    assert body["code"] == 2001


def test_webhook_get_trace_flow(client: TestClient) -> None:
    agent_res = client.post(
        "/miloco/webhook",
        headers=_auth_headers(),
        json={
            "action": "agent",
            "payload": {
                "message": "trace me",
                "sessionKey": "agent:main:miloco-suggest",
                "traceId": "t-99",
                "timeoutMs": 3000,
            },
        },
    )
    run_id = agent_res.json()["data"]["runId"]

    trace_res = client.post(
        "/miloco/webhook",
        headers=_auth_headers(),
        json={"action": "get_trace", "payload": {"runId": run_id}},
    )
    assert trace_res.status_code == 200
    trace_body = trace_res.json()["data"]
    assert trace_body["status"] == "done"
    assert trace_body["success"] is True

    again = client.post(
        "/miloco/webhook",
        headers=_auth_headers(),
        json={"action": "get_trace", "payload": {"runId": run_id}},
    )
    assert again.json()["data"]["status"] == "unknown"


def test_load_settings_from_miloco_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "server": {"token": "abc", "host": "0.0.0.0", "port": 9999},
                "agent": {"auth_bearer": "sec"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    s = load_settings()
    assert isinstance(s, MilocoAgentSettings)
    assert s.server.token == "abc"
    assert s.agent.auth_bearer == "sec"
    assert s.miloco_api_base == "http://127.0.0.1:9999"
