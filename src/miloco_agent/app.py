"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from miloco_agent import __version__
from miloco_agent.admin.router import router as admin_router
from miloco_agent.channels.feishu.router import router as feishu_router
from miloco_agent.channels.feishu.ws_client import start_feishu_long_connection
from miloco_agent.config import load_settings
from miloco_agent.cron.scheduler import HomeProfileCronScheduler, set_cron_scheduler
from miloco_agent.webhook.router import router as webhook_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = load_settings()
    start_feishu_long_connection(asyncio.get_running_loop(), settings.feishu)
    cron_scheduler = HomeProfileCronScheduler(settings.cron)
    cron_scheduler.start(asyncio.get_running_loop())
    set_cron_scheduler(cron_scheduler)
    app.state.cron_scheduler = cron_scheduler
    yield
    set_cron_scheduler(None)
    cron_scheduler.shutdown()


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(
        title="miloco-agent",
        version=__version__,
        description="Miloco Agent Sidecar (OpenClaw webhook compatible)",
        lifespan=_lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "miloco-agent"}

    app.include_router(webhook_router)
    app.include_router(admin_router)
    if not settings.feishu.use_long_connection:
        app.include_router(feishu_router)
    app.state.settings = settings
    return app


app = create_app()
