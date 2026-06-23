"""Prompt profiles aligned with OpenClaw resolveProfile + bridge injection."""

from __future__ import annotations

from typing import Literal

from miloco_agent.bridge.prompt import PromptProfile, catalog_wrapper, profile_blocks
from miloco_agent.prompt.injection import (
    build_home_profile_block,
    build_pending_suggestion_block,
)


def resolve_profile(
    *,
    session_key: str | None,
    lane: str | None = None,
    message: str | None = None,
) -> PromptProfile:
    if message and message.lstrip().startswith("[cron:"):
        return "minimal"
    key = session_key or ""
    if key.startswith("feishu:"):
        return "full"
    if "miloco-rule" in key or lane == "miloco-rule":
        return "rule"
    if "miloco-suggest" in key or lane == "miloco-suggest":
        return "suggestion"
    if key.startswith("cron:") or (lane or "").startswith("cron"):
        return "minimal"
    return "full"


def build_system_prompt(
    *,
    session_key: str | None,
    lane: str | None = None,
    extra_system_prompt: str | None = None,
    message: str | None = None,
    history_block: str | None = None,
    catalog_block: str | None = None,
) -> str:
    profile = resolve_profile(session_key=session_key, lane=lane, message=message)
    parts = profile_blocks(profile)

    if profile != "minimal":
        profile_block = build_home_profile_block()
        if profile_block:
            parts.append(profile_block)

        if profile == "full":
            pending = build_pending_suggestion_block()
            if pending:
                parts.append(pending)

        if profile == "full" and catalog_block:
            wrapped = catalog_wrapper(catalog_block)
            if wrapped:
                parts.append(wrapped)

    if history_block:
        parts.append(history_block)

    if extra_system_prompt:
        parts.append(extra_system_prompt.strip())
    return "\n\n".join(parts)
