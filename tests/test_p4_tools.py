"""P4 home profile + perception memory tool tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from miloco_agent.config import MilocoAgentSettings
from miloco_agent.prompt.builder import build_system_prompt
from miloco_agent.tools.home_profile import (
    tool_home_profile_commit,
    tool_home_profile_list,
    tool_home_profile_read,
)
from miloco_agent.tools.miloco_client import MilocoApiClient
from miloco_agent.tools.perception_memory import (
    perception_memory_path,
    tool_memory_perception_append,
    tool_memory_perception_read,
    tool_perception_logs,
)


@pytest.mark.asyncio
async def test_home_profile_read() -> None:
    client = MilocoApiClient(MilocoAgentSettings())
    client.home_profile_rendered = AsyncMock(return_value="# 家庭档案\n\n内容")  # type: ignore[method-assign]
    raw = await tool_home_profile_read(client)
    body = json.loads(raw)
    assert body["ok"] is True
    assert "家庭档案" in body["markdown"]


@pytest.mark.asyncio
async def test_home_profile_list() -> None:
    client = MilocoApiClient(MilocoAgentSettings())
    client.home_profile_list = AsyncMock(return_value={"entries": []})  # type: ignore[method-assign]
    raw = await tool_home_profile_list(client, target="profile")
    assert json.loads(raw)["ok"] is True


@pytest.mark.asyncio
async def test_home_profile_commit() -> None:
    client = MilocoApiClient(MilocoAgentSettings())
    client.home_profile_commit = AsyncMock(return_value={"committed": True})  # type: ignore[method-assign]
    raw = await tool_home_profile_commit(client)
    assert json.loads(raw)["ok"] is True


@pytest.mark.asyncio
async def test_perception_logs_incremental_updates_cursor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    client = MilocoApiClient(MilocoAgentSettings())
    client.perception_logs = AsyncMock(  # type: ignore[method-assign]
        return_value={"logs": [{"t": "2026-06-23T10:00:00+00:00", "d": {"e": 1}}]}
    )
    raw = await tool_perception_logs(client, incremental=True)
    body = json.loads(raw)
    assert body["count"] == 1
    cursor = json.loads((tmp_path / "perception_cursor.json").read_text())
    assert cursor["cursor"] == "2026-06-23T10:00:00+00:00"


def test_memory_perception_append_and_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    fixed = date(2026, 6, 23)
    monkeypatch.setattr(
        "miloco_agent.tools.perception_memory.date",
        type("D", (), {"today": staticmethod(lambda: fixed), "fromisoformat": date.fromisoformat})(),
    )
    append_raw = tool_memory_perception_append("- 10:00 客厅: 爸爸 喝水")
    assert json.loads(append_raw)["ok"] is True
    path = perception_memory_path(fixed)
    assert path.is_file()
    read_raw = tool_memory_perception_read("2026-06-23")
    body = json.loads(read_raw)
    assert "喝水" in body["content"]


def test_minimal_prompt_skill_first() -> None:
    text = build_system_prompt(
        session_key="cron:miloco-perception-digest",
        message="[cron:x] run",
    )
    assert "Skill" in text
    assert "miloco-cli" in text
