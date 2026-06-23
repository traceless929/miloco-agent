"""CLI entry: uv run miloco-agent"""

from __future__ import annotations

import logging
import sys

import uvicorn

from miloco_agent.config import load_settings


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.sidecar.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    uvicorn.run(
        "miloco_agent.app:app",
        host=settings.sidecar.host,
        port=settings.sidecar.port,
        log_level=settings.sidecar.log_level,
        factory=False,
    )


if __name__ == "__main__":
    main()
