"""Resolve official Miloco skill directory (plugins/skills)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def agent_root() -> Path:
    """miloco-agent submodule / package repo root."""
    if env := os.environ.get("MILOCO_AGENT_ROOT"):
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def repo_root() -> Path:
    """xiaomi-miloco fork root (plugins/skills, cli, backend)."""
    if env := os.environ.get("MILOCO_REPO"):
        return Path(env).expanduser().resolve()
    return agent_root().parent


@lru_cache(maxsize=1)
def skills_dir() -> Path:
    """Canonical skill source: plugins/skills (same tree OpenClaw sync-skills copies)."""
    if env := os.environ.get("MILOCO_SKILLS_DIR"):
        return Path(env).expanduser().resolve()
    return (repo_root() / "plugins" / "skills").resolve()


def skills_available() -> bool:
    path = skills_dir()
    return path.is_dir() and any(path.glob("*/SKILL.md"))
