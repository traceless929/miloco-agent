"""Admin API tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest
from fastapi.testclient import TestClient

from miloco_agent.admin.config_io import redact, write_agent_patch
from miloco_agent.app import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    config = {
        "server": {"host": "127.0.0.1", "port": 1810, "token": "srv"},
        "agent": {
            "auth_bearer": "admin-secret",
            "llm": {"base_url": "https://x/v1", "model": "m", "api_key": "sk-abcdefgh"},
            "feishu": {"enabled": False},
            "cron": {"enabled": False},
        },
    }
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    return TestClient(create_app())


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer admin-secret"}


def test_admin_unauthorized(client: TestClient) -> None:
    res = client.get("/admin/api/status")
    assert res.status_code == 401


def test_admin_status(client: TestClient) -> None:
    res = client.get("/admin/api/status", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "miloco-agent"
    assert "llm" in body
    assert "bridge" in body
    assert body["bridge"]["mode"] == "openclaw-bridge"


def test_admin_bridge_api(client: TestClient) -> None:
    res = client.get("/admin/api/bridge", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert "skills" in body
    assert "miloco_cli" in body
    assert "miloco_im_push" in body["bridge_tools"]
    assert "can_install" in body["miloco_cli"]


def test_admin_bind_notify(client: TestClient) -> None:
    res = client.post(
        "/admin/api/bridge/bind-notify",
        headers=_auth(),
        json={"open_id": "ou_from_admin"},
    )
    assert res.status_code == 200
    assert res.json()["open_id"] == "ou_from_admin"


def test_admin_config_redacted(client: TestClient) -> None:
    res = client.get("/admin/api/config", headers=_auth())
    assert res.status_code == 200
    key = res.json()["agent"]["llm"]["api_key"]
    assert key.startswith("********")
    assert key.endswith("efgh")


def test_admin_crons_have_summaries(client: TestClient) -> None:
    res = client.get("/admin/api/crons", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert "pipeline_intro" in body
    assert "家庭记忆管线" in body["pipeline_intro"]
    managed = body["managed"]
    assert len(managed) == 4
    digest = next(j for j in managed if j["name"] == "miloco-perception-digest")
    assert "感知日志摘要" in digest["summary"]
    assert "摄像头感知" in digest["detail"]
    assert digest["schedule_label"] == "每 15 分钟"


def test_admin_patch_and_reload(client: TestClient) -> None:
    patch_res = client.patch(
        "/admin/api/config",
        headers=_auth(),
        json={"cron": {"enabled": True, "timezone": "Asia/Shanghai"}},
    )
    assert patch_res.status_code == 200
    body = patch_res.json()
    assert body["ok"] is True
    assert body["cron_enabled"] is True

    status_res = client.get("/admin/api/status", headers=_auth())
    assert status_res.status_code == 200
    assert status_res.json()["cron"]["enabled"] is True

    reload_res = client.post("/admin/api/reload", headers=_auth())
    assert reload_res.status_code == 200
    assert reload_res.json()["ok"] is True


def test_admin_console_html(client: TestClient) -> None:
    res = client.get("/admin")
    assert res.status_code == 200
    assert "Miloco Agent" in res.text
    assert 'id="linkMilocoWeb"' in res.text
    assert 'id="connStatus"' in res.text


def test_redact_masks_secrets() -> None:
    out = redact({"api_key": "sk-12345678", "model": "x"})
    assert out["api_key"].startswith("********")
    assert out["model"] == "x"


def test_write_agent_patch_preserves_masked_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"agent": {"llm": {"api_key": "sk-realkey12"}}}),
        encoding="utf-8",
    )
    write_agent_patch({"llm": {"api_key": "********key12", "model": "new"}})
    data = json.loads(cfg.read_text())
    assert data["agent"]["llm"]["api_key"] == "sk-realkey12"
    assert data["agent"]["llm"]["model"] == "new"


def test_admin_traces_endpoint(client: TestClient) -> None:
    from miloco_agent.trace.store import trace_store

    trace_store.start_turn("run-admin-1", trace_id="t-admin", session_key="feishu:ou", query="ping")
    trace_store.finish_turn("run-admin-1", success=True)
    res = client.get("/admin/api/traces", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    assert any(t["runId"] == "run-admin-1" for t in body["traces"])


def test_admin_trace_detail_from_disk(client: TestClient) -> None:
    from miloco_agent.trace import recorder

    recorder.dump_turn_trace(
        run_id="run-detail-1",
        session_key="cron:test",
        trace_id="t1",
        query="cron smoke",
        success=True,
    )
    res = client.get("/admin/api/traces/run-detail-1", headers=_auth())
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["eventCount"] >= 2
    hooks = [e["hook"] for e in body["events"]]
    assert "turn_end" in hooks

    files_res = client.get("/admin/api/traces/files", headers=_auth())
    assert files_res.status_code == 200
    assert files_res.json()["count"] >= 1

    delete_res = client.delete("/admin/api/traces/files/run-detail-1", headers=_auth())
    assert delete_res.status_code == 200
    assert delete_res.json()["ok"] is True

    cleanup_res = client.post(
        "/admin/api/traces/files/cleanup",
        headers=_auth(),
        json={"delete_all": True},
    )
    assert cleanup_res.status_code == 200
    assert cleanup_res.json()["ok"] is True


def test_admin_user_cron_crud(client: TestClient) -> None:
    create = client.post(
        "/admin/api/crons/user",
        headers=_auth(),
        json={
            "name": "admin-test-job",
            "cron_expr": "0 9 * * *",
            "message": "admin cron smoke",
        },
    )
    assert create.status_code == 200
    job_id = create.json()["job"]["job_id"]

    patch = client.patch(
        f"/admin/api/crons/user/{job_id}",
        headers=_auth(),
        json={"enabled": False},
    )
    assert patch.status_code == 200
    assert patch.json()["job"]["enabled"] is False

    listed = client.get("/admin/api/crons", headers=_auth())
    user_jobs = listed.json()["user"]
    assert any(j["job_id"] == job_id and j["enabled"] is False for j in user_jobs)

    delete = client.delete(f"/admin/api/crons/user/{job_id}", headers=_auth())
    assert delete.status_code == 200


@pytest.mark.asyncio
async def test_fetch_server_tasks_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    from miloco_agent.admin import service
    from miloco_agent.config import MilocoAgentSettings

    class _FakeClient:
        async def list_tasks(self) -> list[dict[str, str]]:
            return [{"task_id": "t1", "description": "晨间提醒", "enabled": True}]

    monkeypatch.setattr(service, "MilocoApiClient", lambda _settings: _FakeClient())
    out = await service.fetch_server_tasks(MilocoAgentSettings())
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["tasks"][0]["task_id"] == "t1"


def test_schedule_sidecar_restart_script(monkeypatch: pytest.MonkeyPatch) -> None:
    from miloco_agent.admin import ops

    monkeypatch.setattr(ops.shutil, "which", lambda _name: None)
    called: dict[str, object] = {}

    def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN003
        called["cmd"] = cmd
        return object()

    monkeypatch.setattr(ops.subprocess, "Popen", fake_popen)
    result = ops.schedule_sidecar_restart()
    assert result["ok"] is True
    assert result["mode"] == "script"
    assert "miloco-agent-restart.sh" in str(called["cmd"])
