"""OpenClaw bridge layer tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from miloco_agent.bridge.cli_resolve import install_miloco_cli
from miloco_agent.bridge.context import MilocoBridgeContext
from miloco_agent.bridge.memory import memory_search
from miloco_agent.bridge.notify import bind_notify_channel, push_im, save_notify_channel
from miloco_agent.bridge.skills import skills_available, skills_dir
from miloco_agent.bridge.toolkit import build_agentscope_toolkit
from miloco_agent.bridge.tools import CronBridgeTool, MilocoHabitSuggestTool
from miloco_agent.prompt.builder import build_system_prompt


def test_skills_dir_points_to_official_tree() -> None:
    path = skills_dir()
    assert path.name == "skills"
    assert (path.parent / "openclaw").is_dir() or path.is_dir()


@pytest.mark.skipif(not skills_available(), reason="plugins/skills not present")
def test_toolkit_registers_skills() -> None:
    toolkit = build_agentscope_toolkit()
    assert toolkit is not None


def test_full_prompt_mentions_bridge_and_openclaw_tools() -> None:
    text = build_system_prompt(session_key="feishu:ou_x")
    assert "桥接" in text
    assert "miloco_im_push" in text
    assert "miloco-devices skill" in text or "miloco-devices" in text


def test_minimal_prompt_skill_first() -> None:
    text = build_system_prompt(
        session_key="cron:miloco-perception-digest",
        message="[cron:x] run",
    )
    assert "Skill" in text
    assert "miloco-cli" in text


@pytest.mark.asyncio
async def test_miloco_im_push_needs_bind_without_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    result = await push_im("hello", ctx=MilocoBridgeContext())
    assert result["ok"] is False
    assert result.get("needsBind") is True


@pytest.mark.asyncio
async def test_miloco_im_push_ok_with_default_open_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "agent": {
                    "feishu": {
                        "app_id": "x",
                        "app_secret": "y",
                        "enabled": True,
                        "default_receive_open_id": "ou_test",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "miloco_agent.bridge.notify.FeishuClient.send_reply",
        new_callable=AsyncMock,
    ) as send:
        result = await push_im("hi", ctx=MilocoBridgeContext())
    assert result["ok"] is True
    send.assert_awaited_once()


def test_notify_bind_feishu_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    ctx = MilocoBridgeContext(session_key="feishu:ou_abc")
    result = bind_notify_channel(ctx)
    assert result["ok"] is True
    saved = json.loads((tmp_path / "agent" / "notify_channel.json").read_text())
    assert saved["open_id"] == "ou_abc"


def test_memory_search_hits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "2026-06-23-miloco-perception.md").write_text(
        "- 10:00 客厅: 爸爸 喝水\n",
        encoding="utf-8",
    )
    result = memory_search("喝水", days=1)
    assert result["ok"] is True
    assert len(result["hits"]) == 1


@pytest.mark.asyncio
async def test_cron_bridge_list() -> None:
    tool = CronBridgeTool()
    chunk = await tool(action="list")
    text = chunk.content[0].text  # type: ignore[index]
    body = json.loads(text)
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_habit_suggest_bridge_name() -> None:
    tool = MilocoHabitSuggestTool()
    assert tool.name == "miloco_habit_suggest"
    chunk = await tool(action="list")
    text = chunk.content[0].text  # type: ignore[index]
    assert json.loads(text)["ok"] is True


def test_build_bridge_status_lists_skills() -> None:
    from miloco_agent.bridge.status import build_bridge_status

    status = build_bridge_status()
    assert status["mode"] == "openclaw-bridge"
    if status["skills"]["available"]:
        assert status["skills"]["count"] >= 10
        names = [s["name"] for s in status["skills"]["items"]]
        assert "miloco-devices" in names
        assert "miloco-home-profile" in names


@pytest.mark.skipif(not skills_available(), reason="plugins/skills not present")
@pytest.mark.asyncio
async def test_toolkit_skill_catalog_includes_devices() -> None:
    toolkit = build_agentscope_toolkit()
    prompt = await toolkit.get_skill_instructions()
    assert prompt is not None
    assert "miloco-devices" in prompt


def test_resolve_miloco_cli_can_install() -> None:
    from miloco_agent.bridge.cli_resolve import resolve_miloco_cli

    info = resolve_miloco_cli()
    assert info["can_install"] is True


def test_bind_notify_channel_by_open_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from miloco_agent.bridge.notify import bind_notify_channel_by_open_id, load_notify_channel

    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    result = bind_notify_channel_by_open_id("ou_admin")
    assert result["ok"] is True
    saved = load_notify_channel()
    assert saved and saved["open_id"] == "ou_admin"


def test_install_miloco_cli_prefers_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from miloco_agent.bridge import cli_resolve

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        captured.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(cli_resolve.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(cli_resolve.subprocess, "run", fake_run)
    monkeypatch.setattr(
        cli_resolve,
        "resolve_miloco_cli",
        lambda: {"path": "/venv/bin/miloco-cli", "version": None},
    )

    result = install_miloco_cli()
    assert result["ok"] is True
    assert result["installer"] == "uv"
    assert captured[0][:3] == ["/usr/bin/uv", "pip", "install"]


def test_read_miloco_cli_version_uses_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from miloco_agent.bridge.cli_resolve import _read_miloco_cli_version

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        assert cmd == ["/venv/bin/miloco-cli", "version"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"version":"2026.6.19.dev6"}',
            stderr="",
        )

    monkeypatch.setattr("miloco_agent.bridge.cli_resolve.subprocess.run", fake_run)
    assert _read_miloco_cli_version("/venv/bin/miloco-cli") == "2026.6.19.dev6"


@pytest.mark.asyncio
async def test_miloco_bash_streams_tool_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from miloco_agent.bridge.toolkit import _MilocoBash

    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    monkeypatch.setattr(
        "miloco_agent.bridge.toolkit.bash_miloco_cli_prefix",
        lambda: f'export MILOCO_HOME="{tmp_path}"; ',
    )
    bash = _MilocoBash(cwd=str(tmp_path))
    chunks = [chunk async for chunk in bash(command="echo miloco-bash-ok", description="test")]
    assert len(chunks) == 1
    text = chunks[0].content[0].text
    assert "miloco-bash-ok" in text


def test_bash_miloco_cli_prefix_works_under_sh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import subprocess

    from miloco_agent.bridge.cli_resolve import bash_miloco_cli_prefix

    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    monkeypatch.setattr(
        "miloco_agent.bridge.cli_resolve.resolve_miloco_cli",
        lambda: {
            "path": str(
                Path(__file__).resolve().parents[1]
                / ".venv"
                / "bin"
                / "miloco-cli"
            )
        },
    )
    prefix = bash_miloco_cli_prefix()
    proc = subprocess.run(
        ["/bin/sh", "-c", prefix + "miloco-cli version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "not a valid identifier" not in (proc.stderr or "")
    assert proc.returncode == 0
