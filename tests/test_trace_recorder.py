"""Trace jsonl recorder tests."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from miloco_agent.trace import recorder


def _make_agent_with_tool_turn() -> MagicMock:
    from agentscope.message import ToolCallBlock, ToolResultBlock

    tool_call = ToolCallBlock(id="tc1", name="Bash", input='{"command": "echo hi"}')
    tool_result = ToolResultBlock(id="tc1", name="Bash", output="hi\n")
    user = SimpleNamespace(role="user", get_content_blocks=lambda: [], get_text_content=lambda: "cron task")
    assistant_call = SimpleNamespace(
        role="assistant",
        get_content_blocks=lambda: [tool_call],
        get_text_content=lambda: "",
    )
    assistant_reply = SimpleNamespace(
        role="assistant",
        get_content_blocks=lambda: [tool_result],
        get_text_content=lambda: "done",
    )
    agent = MagicMock()
    agent.state.context = [user, assistant_call, assistant_reply]
    return agent


def test_should_dump_cron_without_debug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    assert recorder.should_dump_trace("cron:miloco-perception-digest") is True
    assert recorder.should_dump_trace("feishu:ou_xxx") is False


def test_should_dump_when_debug_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    (tmp_path / ".debug_observability").write_text("")
    assert recorder.should_dump_trace("feishu:ou_xxx") is True


def test_dump_turn_trace_writes_gzip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    agent = _make_agent_with_tool_turn()
    rel = recorder.dump_turn_trace(
        run_id="run-cron-1",
        session_key="cron:test-job",
        trace_id="trace-1",
        query="感知摘要任务",
        success=True,
        agent=agent,
        duration_ms=120.5,
        meta={"llmCallCount": 1, "toolCallCount": 1},
    )
    assert rel is not None
    assert rel.startswith("trace/agent/")
    assert rel.endswith(".jsonl.gz")

    full = tmp_path / rel
    assert full.is_file()
    lines = gzip.decompress(full.read_bytes()).decode("utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines]
    hooks = [e["hook"] for e in events]
    assert "turn_start" in hooks
    assert "before_tool_call" in hooks
    assert "after_tool_call" in hooks
    assert "llm_output" in hooks
    assert hooks[-1] == "turn_end"


def test_read_trace_events_by_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    recorder.dump_turn_trace(
        run_id="run-read-1",
        session_key="cron:job",
        trace_id=None,
        query="q",
        success=True,
    )
    out = recorder.read_trace_events(run_id="run-read-1")
    assert out["ok"] is True
    assert out["eventCount"] >= 2
    assert out["jsonlPath"]


def test_list_trace_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    recorder.dump_turn_trace(
        run_id="run-list-1",
        session_key="cron:job",
        trace_id=None,
        query="list me",
        success=True,
    )
    listed = recorder.list_trace_files(limit=10)
    assert listed["count"] == 1
    assert listed["files"][0]["runId"] == "run-list-1"


def test_delete_trace_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    recorder.dump_turn_trace(
        run_id="run-del-1",
        session_key="cron:job",
        trace_id=None,
        query="del me",
        success=True,
    )
    out = recorder.delete_trace_file(run_id="run-del-1")
    assert out["ok"] is True
    assert out["count"] == 1
    assert recorder.find_trace_file_by_run_id("run-del-1") is None


def test_cleanup_trace_files_by_run_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    for i in range(3):
        recorder.dump_turn_trace(
            run_id=f"run-batch-{i}",
            session_key="cron:job",
            trace_id=None,
            query=f"q{i}",
            success=True,
        )
    out = recorder.cleanup_trace_files(run_ids=["run-batch-0", "run-batch-2"])
    assert out["ok"] is True
    assert out["count"] == 2
    assert recorder.find_trace_file_by_run_id("run-batch-1") is not None


def test_cleanup_rejects_unsafe_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    secret = tmp_path / "secret.jsonl.gz"
    secret.write_text("nope", encoding="utf-8")
    out = recorder.cleanup_trace_files(rel_paths=["secret.jsonl.gz"])
    assert out["count"] == 0
    assert secret.is_file()
