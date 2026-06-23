"""User cron + task agent_pending tool helpers."""

from __future__ import annotations

import json
from typing import Any

from miloco_agent.cron.user_registry import user_cron_registry
from miloco_agent.tools.miloco_client import MilocoApiClient, MilocoApiError


async def tool_cron_add(
    *,
    name: str,
    cron_expr: str,
    message: str,
    task_id: str | None = None,
    enabled: bool = True,
) -> str:
    job = user_cron_registry.add(
        name=name,
        cron_expr=cron_expr,
        message=message,
        task_id=task_id,
        enabled=enabled,
    )
    if task_id:
        client = MilocoApiClient()
        try:
            await client.task_link_cron(task_id, job.id)
        except MilocoApiError as exc:
            user_cron_registry.remove(job.id)
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(
        {"ok": True, "jobId": job.id, "name": job.name, "cron_expr": job.cron_expr},
        ensure_ascii=False,
    )


def tool_cron_list() -> str:
    jobs = user_cron_registry.list_jobs()
    return json.dumps(
        {
            "ok": True,
            "jobs": [
                {
                    "jobId": j.id,
                    "name": j.name,
                    "cron_expr": j.cron_expr,
                    "enabled": j.enabled,
                    "task_id": j.task_id,
                }
                for j in jobs
            ],
        },
        ensure_ascii=False,
    )


def tool_cron_remove(job_id: str) -> str:
    ok = user_cron_registry.remove(job_id)
    return json.dumps({"ok": ok, "jobId": job_id}, ensure_ascii=False)


async def tool_task_disable(client: MilocoApiClient, task_id: str) -> str:
    try:
        data = await client.task_disable(task_id)
        pending = data.get("agent_pending") or []
        applied = user_cron_registry.apply_pending(pending)
        return json.dumps(
            {"ok": True, "task_id": task_id, "data": data, "cron_ops": applied},
            ensure_ascii=False,
        )
    except MilocoApiError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


async def tool_task_delete(
    client: MilocoApiClient,
    task_id: str,
    *,
    reason: str = "completed",
) -> str:
    try:
        data = await client.task_delete(task_id, reason=reason)
        pending = data.get("agent_pending") or []
        applied = user_cron_registry.apply_pending(pending)
        return json.dumps(
            {"ok": True, "task_id": task_id, "data": data, "cron_ops": applied},
            ensure_ascii=False,
        )
    except MilocoApiError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


async def run_cron_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "cron_add":
        return await tool_cron_add(
            name=str(arguments.get("name") or ""),
            cron_expr=str(arguments.get("cron_expr") or ""),
            message=str(arguments.get("message") or ""),
            task_id=arguments.get("task_id"),
            enabled=bool(arguments.get("enabled", True)),
        )
    if name == "cron_list":
        return tool_cron_list()
    if name == "cron_remove":
        return tool_cron_remove(str(arguments.get("job_id") or ""))
    raise ValueError(f"unknown cron tool: {name}")
