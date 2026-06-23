"""Admin operational helpers (Sidecar restart)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from miloco_agent.bridge.skills import repo_root
from miloco_agent.config import miloco_home


def schedule_sidecar_restart() -> dict[str, Any]:
    """Restart Sidecar out-of-process (current HTTP handler will be terminated)."""
    supervisor = os.environ.get("MILOCO_AGENT_SUPERVISOR", "miloco-agent").strip()
    if shutil.which("supervisorctl") and supervisor:
        try:
            proc = subprocess.run(
                ["supervisorctl", "restart", supervisor],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}
        if proc.returncode == 0:
            return {
                "ok": True,
                "mode": "supervisor",
                "message": f"已通过 supervisorctl 重启 {supervisor}",
            }

    script = repo_root() / "scripts" / "miloco-agent-restart.sh"
    if not script.is_file():
        return {"ok": False, "error": f"未找到重启脚本: {script}"}
    env = os.environ.copy()
    env["MILOCO_HOME"] = str(miloco_home())
    subprocess.Popen(
        ["bash", str(script)],
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "ok": True,
        "mode": "script",
        "message": "Sidecar 正在后台重启，约 3 秒后刷新页面",
    }
