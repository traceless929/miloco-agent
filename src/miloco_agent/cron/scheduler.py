"""APScheduler wrapper for home-profile + user task cron jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from miloco_agent.config import CronSettings
from miloco_agent.cron.jobs import HOME_PROFILE_JOBS, CronJob
from miloco_agent.cron.runner import run_cron_job
from miloco_agent.cron.user_registry import UserCronJob, user_cron_registry

logger = logging.getLogger(__name__)


async def run_user_cron_job(job: UserCronJob) -> dict:
    from miloco_agent.runtime.turn_runner import turn_runner

    trace_id = f"cron-{job.id}-{uuid.uuid4().hex[:8]}"
    logger.info("user cron start id=%s name=%s", job.id, job.name)
    result = await turn_runner.run_turn(
        message=job.prefixed_message(),
        session_key=job.session_key,
        lane=f"cron:{job.name}",
        trace_id=trace_id,
        timeout_ms=job.timeout_ms,
    )
    logger.info(
        "user cron done id=%s status=%s run_id=%s",
        job.id,
        result.get("status"),
        result.get("runId"),
    )
    return result


class HomeProfileCronScheduler:
    def __init__(self, settings: CronSettings) -> None:
        self._settings = settings
        self._scheduler: AsyncIOScheduler | None = None

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if not self._settings.enabled:
            logger.info("cron disabled (agent.cron.enabled=false)")
            return
        if self._scheduler is not None and self._scheduler.running:
            return

        event_loop = loop
        if event_loop is None:
            try:
                event_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("cron: no running event loop; skip scheduler start")
                return

        scheduler = AsyncIOScheduler(
            event_loop=event_loop,
            timezone=self._settings.timezone,
        )
        for job in HOME_PROFILE_JOBS:
            scheduler.add_job(
                self._execute_managed,
                CronTrigger.from_crontab(
                    job.cron_expr,
                    timezone=self._settings.timezone,
                ),
                args=[job],
                id=f"managed:{job.name}",
                name=job.description,
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info(
                "cron registered name=%s expr=%s tz=%s",
                job.name,
                job.cron_expr,
                self._settings.timezone,
            )
        for job in user_cron_registry.list_jobs(include_disabled=False):
            self._register_user_job(scheduler, job)
        scheduler.start()
        self._scheduler = scheduler
        logger.info(
            "cron scheduler started (managed=%d user=%d)",
            len(HOME_PROFILE_JOBS),
            len(user_cron_registry.list_jobs(include_disabled=False)),
        )

    def reload_user_jobs(self) -> None:
        if self._scheduler is None or not self._scheduler.running:
            return
        for job in user_cron_registry.list_jobs():
            job_id = f"user:{job.id}"
            if not job.enabled:
                try:
                    self._scheduler.remove_job(job_id)
                except Exception:  # noqa: BLE001
                    pass
                continue
            self._register_user_job(self._scheduler, job)

    def _register_user_job(
        self, scheduler: AsyncIOScheduler, job: UserCronJob
    ) -> None:
        scheduler.add_job(
            self._execute_user,
            CronTrigger.from_crontab(job.cron_expr, timezone=job.timezone),
            args=[job],
            id=f"user:{job.id}",
            name=job.name,
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info("user cron registered id=%s expr=%s", job.id, job.cron_expr)

    def shutdown(self) -> None:
        if self._scheduler is None:
            return
        self._scheduler.shutdown(wait=False)
        self._scheduler = None
        logger.info("cron scheduler stopped")

    async def _execute_managed(self, job: CronJob) -> None:
        try:
            await run_cron_job(job)
        except Exception:  # noqa: BLE001
            logger.exception("cron job failed name=%s", job.name)

    async def _execute_user(self, job: UserCronJob) -> None:
        try:
            await run_user_cron_job(job)
        except Exception:  # noqa: BLE001
            logger.exception("user cron failed id=%s", job.id)


_scheduler_singleton: HomeProfileCronScheduler | None = None


def set_cron_scheduler(scheduler: HomeProfileCronScheduler | None) -> None:
    global _scheduler_singleton
    _scheduler_singleton = scheduler


def reload_user_cron_jobs() -> None:
    if _scheduler_singleton is not None:
        _scheduler_singleton.reload_user_jobs()
