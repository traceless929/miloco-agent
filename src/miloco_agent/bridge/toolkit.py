"""Build AgentScope Toolkit: official skills + Bash + OpenClaw bridge tools."""

from __future__ import annotations

import logging
import os
from typing import Any

from agentscope.skill import LocalSkillLoader
from agentscope.tool import Toolkit
from agentscope.tool._builtin import Bash, Read, Write

from miloco_agent.bridge.cli_resolve import bash_miloco_cli_prefix
from miloco_agent.bridge.context import MilocoBridgeContext
from miloco_agent.bridge.skills import skills_available, skills_dir
from miloco_agent.bridge.tools import build_bridge_tools
from miloco_agent.config import miloco_home
from miloco_agent.tools.miloco_client import MilocoApiClient

logger = logging.getLogger(__name__)


def _miloco_cli_env() -> dict[str, str]:
    home = str(miloco_home())
    env = os.environ.copy()
    env["MILOCO_HOME"] = home
    return env


class _MilocoBash(Bash):
    """Bash with MILOCO_HOME + miloco-cli resolver (PATH 外也可执行)."""

    async def __call__(  # type: ignore[override]
        self,
        command: str,
        **kwargs: Any,
    ):
        prefix = bash_miloco_cli_prefix()
        async for chunk in super().__call__(prefix + command, **kwargs):
            yield chunk


def build_agentscope_toolkit(
    client: MilocoApiClient | None = None,
    *,
    bridge_context: MilocoBridgeContext | None = None,
) -> Toolkit:
    """Skill-first toolkit: plugins/skills + CLI + OpenClaw bridge tools."""
    _ = client  # reserved for future miloco-cli auth injection
    home = miloco_home()
    home.mkdir(parents=True, exist_ok=True)

    skills_loaders: list[LocalSkillLoader] = []
    if skills_available():
        skills_loaders.append(
            LocalSkillLoader(str(skills_dir()), scan_subdir=True),
        )
        logger.info("registered miloco skills from %s", skills_dir())
    else:
        logger.warning("skills directory not found: %s", skills_dir())

    tools = [
        _MilocoBash(cwd=str(home)),
        Read(),
        Write(),
        *build_bridge_tools(bridge_context),
    ]

    return Toolkit(
        tools=tools,
        skills_or_loaders=skills_loaders,
    )
