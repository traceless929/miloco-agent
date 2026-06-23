"""Tests for trace meta, session store, user cron, habit suggest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from miloco_agent.cron.user_registry import UserCronRegistry
from miloco_agent.prompt.builder import build_system_prompt, resolve_profile
from miloco_agent.runtime.session_store import SessionStore, format_history_block
from miloco_agent.tools.habit_suggest import run_habit_suggest
from miloco_agent.trace.store import TraceStore


def test_trace_pop_meta_fields() -> None:
    store = TraceStore()
    store.start_turn("r1", trace_id="t1", session_key="agent:main:miloco", query="hello")
    store.finish_turn(
        "r1",
        success=True,
        extra_meta={
            "llmCallCount": 2,
            "toolCallCount": 1,
            "replyText": "ok",
        },
    )
    meta = store.pop_done_meta("r1")
    assert meta is not None
    assert meta["success"] is True
    assert meta["query"] == "hello"
    assert meta["llmCallCount"] == 2
    assert meta["toolCallCount"] == 1
    assert meta["durationMs"] >= 0


def test_feishu_session_profile() -> None:
    assert resolve_profile(session_key="feishu:ou_abc") == "full"


def test_session_store_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    store = SessionStore()
    store.append(
        "feishu:u1",
        user="开灯",
        assistant="好的",
        max_turns=5,
        ttl_hours=24,
    )
    turns = store.load("feishu:u1", max_turns=5, ttl_hours=24)
    assert len(turns) == 2
    block = format_history_block(turns)
    assert "开灯" in block


def test_user_cron_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    reg = UserCronRegistry()
    job = reg.add(name="remind", cron_expr="0 9 * * *", message="喝水")
    assert reg.get(job.id) is not None
    assert reg.remove(job.id) is True


def test_habit_suggest_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    (tmp_path / "home-profile").mkdir(parents=True)
    result = run_habit_suggest({"action": "list"})
    assert result["ok"] is True
    assert "can_ask_now" in result


def test_full_prompt_includes_notify() -> None:
    text = build_system_prompt(session_key="feishu:ou_x")
    assert "miloco_im_push" in text
