"""Device catalog injection via miloco-cli (5s throttle)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from miloco_agent.bridge.cli_resolve import resolve_miloco_cli
from miloco_agent.config import miloco_home

logger = logging.getLogger(__name__)

REGEN_THROTTLE_S = 5.0
_CATALOG_TIMEOUT_S = 10.0

_DEVICE_CATALOG_INTRO = """## 设备目录
下方 `# devices catalog` 是预注入的高频设备子集（≤50 台，非全量）。涉及多台设备或目录找不到目标时，必须先 `device_list` 拉全量。"""


@dataclass
class _Cache:
    text: str
    generated_at: float


_cached: _Cache | None = None
_cache_lock = asyncio.Lock()


async def _run_cli_catalog() -> str | None:
    cli = resolve_miloco_cli().get("path")
    if not cli:
        logger.debug("miloco-cli not found; skip catalog")
        return None
    env = os.environ.copy()
    env["MILOCO_HOME"] = str(miloco_home())
    try:
        proc = await asyncio.create_subprocess_exec(
            cli,
            "device",
            "catalog",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_CATALOG_TIMEOUT_S,
        )
    except TimeoutError:
        logger.warning("miloco-cli device catalog timed out")
        return None
    except OSError as exc:
        logger.warning("miloco-cli device catalog failed: %s", exc)
        return None
    if proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace")[:200]
        logger.warning("miloco-cli device catalog exit %s: %s", proc.returncode, err)
        return None
    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    return text or None


async def get_catalog_block() -> str:
    """Return markdown block with catalog, or empty string."""
    global _cached
    now = time.monotonic()
    async with _cache_lock:
        if _cached and now - _cached.generated_at < REGEN_THROTTLE_S:
            text = _cached.text
        else:
            fresh = await _run_cli_catalog()
            if fresh is not None:
                _cached = _Cache(text=fresh, generated_at=now)
                text = fresh
            else:
                text = _cached.text if _cached else ""
    if not text.strip():
        return ""
    return f"{_DEVICE_CATALOG_INTRO}\n\n```text\n{text}\n```"


def reset_catalog_cache() -> None:
    global _cached
    _cached = None
