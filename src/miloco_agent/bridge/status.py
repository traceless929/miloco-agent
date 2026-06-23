"""Bridge layer health snapshot for admin / diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from miloco_agent.bridge.cli_resolve import resolve_miloco_cli
from miloco_agent.bridge.notify import load_notify_channel
from miloco_agent.bridge.skills import skills_available, skills_dir
from miloco_agent.channels.feishu.bind_phrases import (
    bind_instruction_short,
    bind_instruction_short_md,
    bind_phrase_hint,
)
from miloco_agent.config import load_settings, miloco_home
from miloco_agent.prompt.injection import home_profile_path

# OpenClaw plugin tools bridged in Sidecar (keep in sync with bridge/tools.py).
BRIDGE_TOOL_NAMES: tuple[str, ...] = (
    "miloco_im_push",
    "miloco_notify_bind",
    "miloco_habit_suggest",
    "cron",
    "memory_search",
)

# AgentScope built-ins used by Skill workflow.
RUNTIME_TOOL_NAMES: tuple[str, ...] = (
    "Bash",
    "Read",
    "Write",
    "Skill",
)


def list_registered_skills() -> list[dict[str, str]]:
    """Scan plugins/skills for SKILL.md frontmatter name + description."""
    root = skills_dir()
    if not root.is_dir():
        return []
    rows: list[dict[str, str]] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        name = skill_md.parent.name
        description = ""
        try:
            text = skill_md.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    front = text[3:end]
                    for line in front.splitlines():
                        if line.strip().startswith("description:"):
                            description = line.split(":", 1)[1].strip().strip('"')
                            break
        except OSError:
            pass
        rows.append(
            {
                "id": name,
                "name": name,
                "description": description[:120],
                "path": str(skill_md),
            }
        )
    return rows


def _miloco_cli_info() -> dict[str, Any]:
    return resolve_miloco_cli()


def build_bridge_status() -> dict[str, Any]:
    skills_path = skills_dir()
    skills = list_registered_skills()
    notify = load_notify_channel()
    settings = load_settings()
    profile_path = home_profile_path()
    mem_dir = miloco_home() / "memory"

    return {
        "mode": "openclaw-bridge",
        "skills": {
            "available": skills_available(),
            "directory": str(skills_path),
            "count": len(skills),
            "items": skills,
        },
        "miloco_cli": _miloco_cli_info(),
        "bridge_tools": list(BRIDGE_TOOL_NAMES),
        "runtime_tools": list(RUNTIME_TOOL_NAMES),
        "notify_channel": {
            "bound": bool(notify and notify.get("open_id")),
            "channel": (notify or {}).get("channel"),
            "open_id": (notify or {}).get("open_id"),
            "default_receive_open_id": settings.feishu.default_receive_open_id or None,
            "bind_phrase": bind_phrase_hint(),
            "bind_instruction": bind_instruction_short(),
            "bind_instruction_md": bind_instruction_short_md(),
        },
        "home_profile": {
            "profile_md_exists": profile_path.is_file(),
            "profile_md_path": str(profile_path),
        },
        "memory": {
            "directory": str(mem_dir),
            "file_count": len(list(mem_dir.glob("*-miloco-perception.md")))
            if mem_dir.is_dir()
            else 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
