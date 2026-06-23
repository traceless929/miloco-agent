"""Execute a single cron job turn."""

from __future__ import annotations

import logging
import uuid

from miloco_agent.cron.jobs import CronJob

logger = logging.getLogger(__name__)


async def run_cron_job(job: CronJob) -> dict:
    from miloco_agent.runtime.turn_runner import turn_runner

    trace_id = f"cron-{job.name}-{uuid.uuid4().hex[:8]}"
    logger.info("cron job start name=%s trace=%s", job.name, trace_id)
    result = await turn_runner.run_turn(
        message=job.prefixed_message(),
        session_key=job.session_key,
        lane=job.lane,
        trace_id=trace_id,
        timeout_ms=job.timeout_ms,
    )
    logger.info(
        "cron job done name=%s status=%s run_id=%s",
        job.name,
        result.get("status"),
        result.get("runId"),
    )
    return result
