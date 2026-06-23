"""Build AgentScope model / agent for Miloco turns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.message import ToolCallBlock, ToolResultBlock, UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionMode
from agentscope.state import AgentState
from agentscope.tool import Toolkit
from pydantic import SecretStr

from miloco_agent.config import LlmSettings, MilocoAgentSettings, load_settings
from miloco_agent.bridge import MilocoBridgeContext, build_agentscope_toolkit
from miloco_agent.tools.miloco_client import MilocoApiClient

if TYPE_CHECKING:
    from agentscope.message import Msg

MAX_ITER_REPLY_MARK = (
    "Executed maximum iterations of reasoning-acting loop"
    "without finishing the task."
)


def resolve_react_max_iters(
    settings: MilocoAgentSettings,
    *,
    session_key: str | None = None,
) -> int:
    max_iters = max(int(settings.runtime.react_max_iters), 1)
    if session_key and session_key.startswith("cron:"):
        max_iters = max(max_iters, int(settings.runtime.cron_react_max_iters))
    return max_iters


def agent_exceeded_max_iters(agent: Agent) -> bool:
    react_config = getattr(agent, "react_config", None)
    if react_config is None:
        return False
    limit = int(react_config.max_iters)
    return limit > 0 and int(agent.state.cur_iter) >= limit


def build_chat_model(llm: LlmSettings, *, stream: bool = False) -> OpenAIChatModel:
    client_kwargs: dict[str, Any] = {}
    user_agent = llm.user_agent
    if not user_agent and "kimi.com/coding" in llm.base_url:
        user_agent = "claude-code/1.0.0"
    if user_agent:
        client_kwargs["default_headers"] = {"User-Agent": user_agent}

    return OpenAIChatModel(
        credential=OpenAICredential(
            api_key=SecretStr(llm.api_key),
            base_url=llm.base_url,
        ),
        model=llm.model,
        stream=stream,
        client_kwargs=client_kwargs or None,
    )


def build_agent(
    *,
    system_prompt: str,
    settings: MilocoAgentSettings | None = None,
    client: MilocoApiClient | None = None,
    bridge_context: MilocoBridgeContext | None = None,
    stream: bool = False,
) -> Agent:
    cfg = settings or load_settings()
    session_key = bridge_context.session_key if bridge_context else None
    max_iters = resolve_react_max_iters(cfg, session_key=session_key)
    state = AgentState()
    state.permission_context.mode = PermissionMode.BYPASS
    return Agent(
        name="miloco-agent",
        system_prompt=system_prompt,
        model=build_chat_model(cfg.llm, stream=stream),
        toolkit=build_agentscope_toolkit(
            client,
            bridge_context=bridge_context,
        ),
        state=state,
        react_config=ReActConfig(max_iters=max_iters),
    )


def count_turn_stats(agent: Agent) -> tuple[int, int]:
    detailed = count_turn_stats_detailed(agent)
    return detailed["llmCallCount"], detailed["toolCallCount"]


def count_turn_stats_detailed(agent: Agent) -> dict[str, object]:
    tool_calls = 0
    llm_calls = max(agent.state.cur_iter, 0)
    tool_names: list[str] = []
    for msg in agent.state.context:
        for block in msg.get_content_blocks():
            if isinstance(block, ToolCallBlock):
                llm_calls = max(llm_calls, 1)
                name = getattr(block, "name", None) or getattr(block, "tool_name", None)
                if name:
                    tool_names.append(str(name))
            if isinstance(block, ToolResultBlock):
                tool_calls += 1
    slowest = tool_names[-1] if tool_names else None
    exceeded = agent_exceeded_max_iters(agent)
    return {
        "llmCallCount": llm_calls,
        "toolCallCount": tool_calls,
        "llmTotalMs": 0.0,
        "toolTotalMs": 0.0,
        "toolMaxMs": 0.0,
        "slowestToolName": slowest,
        "errorCount": 1 if exceeded else 0,
        "exceededMaxIters": exceeded,
    }


def extract_reply_text(reply: Msg) -> str:
    return reply.get_text_content() or ""
