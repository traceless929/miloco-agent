"""P4 cron scheduler tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from miloco_agent.app import create_app
from miloco_agent.config import CronSettings
from miloco_agent.cron.jobs import HOME_PROFILE_JOBS
from miloco_agent.cron.runner import run_cron_job
from miloco_agent.cron.scheduler import HomeProfileCronScheduler
from miloco_agent.prompt.builder import resolve_profile


def test_home_profile_job_count() -> None:
    assert len(HOME_PROFILE_JOBS) == 4
    names = {j.name for j in HOME_PROFILE_JOBS}
    assert names == {
        "miloco-perception-digest",
        "miloco-home-patrol",
        "miloco-home-dreaming",
        "miloco-habit-suggest",
    }
    for job in HOME_PROFILE_JOBS:
        assert job.summary.strip()
        assert job.detail.strip()


def test_cron_job_prefixed_message() -> None:
    job = HOME_PROFILE_JOBS[0]
    msg = job.prefixed_message()
    assert msg.startswith("[cron:miloco-perception-digest")
    assert "miloco-perception-digest skill" in msg


def test_resolve_profile_cron_message_prefix() -> None:
    assert (
        resolve_profile(
            session_key="agent:main:miloco",
            message="[cron:miloco-perception-digest miloco-perception-digest] 执行",
        )
        == "minimal"
    )


def test_scheduler_disabled_by_default() -> None:
    sched = HomeProfileCronScheduler(CronSettings(enabled=False))
    sched.start()
    assert not sched.running


@pytest.mark.asyncio
async def test_scheduler_starts_when_enabled() -> None:
    sched = HomeProfileCronScheduler(CronSettings(enabled=True))
    sched.start(asyncio.get_running_loop())
    try:
        assert sched.running
    finally:
        sched.shutdown()


@pytest.mark.asyncio
async def test_run_cron_job_invokes_turn_runner() -> None:
    job = HOME_PROFILE_JOBS[0]
    with patch(
        "miloco_agent.runtime.turn_runner.turn_runner.run_turn",
        new_callable=AsyncMock,
        return_value={"runId": "r1", "status": "ok"},
    ) as mock_turn:
        result = await run_cron_job(job)
        assert result["status"] == "ok"
        mock_turn.assert_awaited_once()
        kwargs = mock_turn.await_args.kwargs
        assert kwargs["session_key"] == job.session_key
        assert kwargs["message"].startswith("[cron:")


def test_app_lifespan_cron_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"agent": {"auth_bearer": "t", "cron": {"enabled": False}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    with TestClient(create_app()) as client:
        res = client.get("/health")
        assert res.status_code == 200
        sched = client.app.state.cron_scheduler
        assert not sched.running
