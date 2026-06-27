"""Locate or install miloco-cli for Skill + Bash bridge."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from miloco_agent.bridge.skills import agent_root, repo_root


def _sidecar_venv_bin() -> Path | None:
    """miloco-agent/.venv/bin"""
    candidate = agent_root() / ".venv" / "bin" / "miloco-cli"
    return candidate if candidate.is_file() else None


def _local_bin() -> Path | None:
    candidate = Path.home() / ".local" / "bin" / "miloco-cli"
    return candidate if candidate.is_file() else None


def _read_miloco_cli_version(path: str) -> str | None:
    """miloco-cli exposes ``version`` subcommand, not ``--version``."""
    try:
        proc = subprocess.run(
            [path, "version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        import json

        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get("version"):
            return str(payload["version"])
    except json.JSONDecodeError:
        pass
    return raw


def resolve_miloco_cli() -> dict[str, Any]:
    """Find miloco-cli executable; Sidecar Bash will use this even if not on PATH."""
    path = shutil.which("miloco-cli")
    source = "path"
    if not path:
        for label, candidate in (
            ("sidecar_venv", _sidecar_venv_bin()),
            ("local_bin", _local_bin()),
        ):
            if candidate:
                path = str(candidate)
                source = label
                break
    version = _read_miloco_cli_version(path) if path else None
    return {
        "available": path is not None,
        "path": path,
        "source": source if path else None,
        "on_path": bool(shutil.which("miloco-cli")),
        "version": version,
        "repo_cli": str(repo_root() / "cli"),
        "can_install": (repo_root() / "cli" / "pyproject.toml").is_file(),
    }


def bash_miloco_cli_prefix() -> str:
    """Shell snippet: MILOCO_HOME + miloco-cli on PATH for Agent Bash (/bin/sh safe)."""
    from miloco_agent.config import miloco_home

    info = resolve_miloco_cli()
    home = str(miloco_home()).replace('"', '\\"')
    lines = [f'export MILOCO_HOME="{home}"']
    cli = info.get("path")
    if cli:
        cli_dir = str(Path(str(cli)).parent).replace('"', '\\"')
        lines.append(f'export PATH="{cli_dir}:$PATH"')
    return "; ".join(lines) + "; "


def install_miloco_cli() -> dict[str, Any]:
    """Install editable miloco-cli into Sidecar venv (uv pip preferred)."""
    cli_dir = repo_root() / "cli"
    if not (cli_dir / "pyproject.toml").is_file():
        return {"ok": False, "error": f"未找到 cli 源码: {cli_dir}"}

    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "pip", "install", "-e", str(cli_dir), "--python", sys.executable]
        installer = "uv"
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-e", str(cli_dir)]
        installer = "pip"

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}

    if proc.returncode != 0 and installer == "pip":
        err = (proc.stderr or proc.stdout or "").strip()
        if "No module named pip" in err:
            try:
                bootstrap = subprocess.run(
                    [sys.executable, "-m", "ensurepip", "--upgrade"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"ok": False, "error": str(exc)}
            if bootstrap.returncode != 0:
                hint = (
                    (bootstrap.stderr or bootstrap.stdout or "").strip()[-500:]
                    or "ensurepip failed"
                )
                return {
                    "ok": False,
                    "error": f"venv 无 pip，且 ensurepip 失败: {hint}",
                }
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"ok": False, "error": str(exc)}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        if installer == "pip" and "No module named pip" in err:
            return {
                "ok": False,
                "error": "venv 无 pip；请安装 uv 后重试，或执行: bash miloco-agent/scripts/miloco-agent-install.sh",
            }
        return {"ok": False, "error": err or f"{installer} exit {proc.returncode}"}

    resolved = resolve_miloco_cli()
    return {
        "ok": True,
        "path": resolved.get("path"),
        "version": resolved.get("version"),
        "installer": installer,
        "message": "miloco-cli 已安装到 Sidecar venv，无需加入系统 PATH",
    }
