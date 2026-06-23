"""ReAct max_iters configuration tests."""

from __future__ import annotations

from miloco_agent.config import AgentRuntimeSettings, MilocoAgentSettings
from miloco_agent.runtime.agentscope_runtime import resolve_react_max_iters


def test_resolve_react_max_iters_default() -> None:
    settings = MilocoAgentSettings(runtime=AgentRuntimeSettings())
    assert resolve_react_max_iters(settings, session_key="feishu:ou") == 32
    assert resolve_react_max_iters(settings, session_key="cron:digest") == 48


def test_resolve_react_max_iters_custom() -> None:
    settings = MilocoAgentSettings(
        runtime=AgentRuntimeSettings(react_max_iters=20, cron_react_max_iters=60),
    )
    assert resolve_react_max_iters(settings, session_key="feishu:ou") == 20
    assert resolve_react_max_iters(settings, session_key="cron:digest") == 60
