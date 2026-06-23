"""Admin service: status, crons, sessions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from miloco_agent import __version__
from miloco_agent.admin.config_io import agent_view, read_raw_config
from miloco_agent.bridge.status import build_bridge_status
from miloco_agent.config import MilocoAgentSettings, config_file, miloco_home
from miloco_agent.cron.jobs import HOME_PROFILE_JOBS
from miloco_agent.cron.labels import MANAGED_CRON_PIPELINE_INTRO, cron_schedule_label
from miloco_agent.cron.user_registry import UserCronJob, user_cron_registry
from miloco_agent.tools.miloco_client import MilocoApiClient, MilocoApiError
from miloco_agent.trace.recorder import (
    cleanup_trace_files,
    delete_trace_file,
    list_trace_files,
    read_trace_events,
)
from miloco_agent.trace.store import trace_store


def build_status(
    settings: MilocoAgentSettings,
    *,
    cron_running: bool,
) -> dict[str, Any]:
    server_ok = False
    server_detail: str | None = None
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{settings.miloco_api_base}/health")
            server_ok = r.status_code == 200
            if not server_ok:
                server_detail = f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        server_detail = str(exc)

    return {
        "service": "miloco-agent",
        "version": __version__,
        "miloco_home": str(miloco_home()),
        "config_path": str(config_file()),
        "sidecar": {
            "host": settings.sidecar.host,
            "port": settings.sidecar.port,
        },
        "server": {
            "reachable": server_ok,
            "base_url": settings.miloco_api_base,
            "detail": server_detail,
        },
        "llm": {
            "configured": settings.llm_configured,
            "model": settings.llm.model,
            "base_url": settings.llm.base_url,
        },
        "feishu": {
            "enabled": settings.feishu.enabled,
            "configured": settings.feishu.configured,
            "mode": settings.feishu.mode,
            "reply_format": settings.feishu.reply_format,
            "stream_reply": settings.feishu.stream_reply,
            "history_turns": settings.feishu.history_turns,
        },
        "cron": {
            "enabled": settings.cron.enabled,
            "running": cron_running,
            "timezone": settings.cron.timezone,
            "managed_jobs": len(HOME_PROFILE_JOBS),
            "user_jobs": len(user_cron_registry.list_jobs(include_disabled=True)),
        },
        "bridge": build_bridge_status(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def list_crons() -> dict[str, Any]:
    managed = [
        {
            "kind": "managed",
            "name": j.name,
            "cron_expr": j.cron_expr,
            "schedule_label": cron_schedule_label(j.cron_expr),
            "description": j.description,
            "summary": j.summary,
            "detail": j.detail,
            "enabled": True,
        }
        for j in HOME_PROFILE_JOBS
    ]
    user = [
        {
            "kind": "user",
            "job_id": j.id,
            "name": j.name,
            "cron_expr": j.cron_expr,
            "schedule_label": cron_schedule_label(j.cron_expr),
            "summary": _user_cron_summary(j.name, j.message),
            "detail": "",
            "enabled": j.enabled,
            "task_id": j.task_id,
        }
        for j in user_cron_registry.list_jobs(include_disabled=True)
    ]
    return {
        "pipeline_intro": MANAGED_CRON_PIPELINE_INTRO,
        "managed": managed,
        "user": user,
    }


def _user_cron_summary(name: str, message: str) -> str:
    msg = (message or "").strip()
    if msg:
        one_line = msg.replace("\n", " ").strip()
        if len(one_line) > 80:
            return one_line[:77] + "…"
        return one_line
    return f"用户任务定时：{name}"


def list_sessions() -> list[dict[str, Any]]:
    sessions_dir = miloco_home() / "agent" / "sessions"
    if not sessions_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(sessions_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        turns = data.get("turns") or []
        rows.append(
            {
                "file": path.name,
                "session_key": data.get("session_key"),
                "turns": len(turns),
                "updated_at": data.get("updated_at"),
            }
        )
    return rows


async def fetch_server_tasks(settings: MilocoAgentSettings) -> dict[str, Any]:
    client = MilocoApiClient(settings)
    try:
        tasks = await client.list_tasks()
    except MilocoApiError as exc:
        return {"ok": False, "error": str(exc), "tasks": []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "tasks": []}
    simplified = [
        {
            "task_id": t.get("task_id") or t.get("id"),
            "description": t.get("description") or "",
            "enabled": t.get("enabled"),
            "status": t.get("status"),
            "source": t.get("source"),
        }
        for t in tasks
        if isinstance(t, dict)
    ]
    return {"ok": True, "count": len(simplified), "tasks": simplified}


def list_traces(*, limit: int = 40) -> dict[str, Any]:
    items = trace_store.list_recent(limit=limit)
    return {"traces": items, "count": len(items)}


def get_trace_detail(run_id: str) -> dict[str, Any]:
    meta = trace_store.peek_done_meta(run_id)
    rel_path = str(meta["jsonlPath"]) if meta and meta.get("jsonlPath") else None
    detail = read_trace_events(run_id=run_id, rel_path=rel_path)
    if meta:
        detail["summary"] = meta
    return detail


def list_trace_dump_files(*, day: str | None = None, limit: int = 50) -> dict[str, Any]:
    return list_trace_files(day=day, limit=limit)


def delete_trace_dump_file(*, run_id: str) -> dict[str, Any]:
    return delete_trace_file(run_id=run_id)


def cleanup_trace_dump_files(
    *,
    run_ids: list[str] | None = None,
    rel_paths: list[str] | None = None,
    day: str | None = None,
    older_than_days: int | None = None,
    delete_all: bool = False,
) -> dict[str, Any]:
    return cleanup_trace_files(
        run_ids=run_ids,
        rel_paths=rel_paths,
        day=day,
        older_than_days=older_than_days,
        delete_all=delete_all,
    )


def user_cron_to_dict(job: UserCronJob) -> dict[str, Any]:
    return {
        "kind": "user",
        "job_id": job.id,
        "name": job.name,
        "cron_expr": job.cron_expr,
        "schedule_label": cron_schedule_label(job.cron_expr),
        "summary": _user_cron_summary(job.name, job.message),
        "detail": job.message,
        "enabled": job.enabled,
        "task_id": job.task_id,
        "timezone": job.timezone,
        "timeout_ms": job.timeout_ms,
    }


def create_user_cron(
    *,
    name: str,
    cron_expr: str,
    message: str,
    task_id: str | None = None,
    enabled: bool = True,
    timezone: str = "Asia/Shanghai",
    timeout_ms: int = 300_000,
) -> dict[str, Any]:
    job = user_cron_registry.add(
        name=name.strip(),
        cron_expr=cron_expr.strip(),
        message=message.strip(),
        task_id=(task_id or "").strip() or None,
        enabled=enabled,
        timezone=timezone.strip() or "Asia/Shanghai",
        timeout_ms=timeout_ms,
    )
    return user_cron_to_dict(job)


def update_user_cron(job_id: str, **fields: Any) -> dict[str, Any] | None:
    job = user_cron_registry.update(job_id, **fields)
    return user_cron_to_dict(job) if job else None


def delete_user_cron(job_id: str) -> bool:
    return user_cron_registry.remove(job_id)


def config_snapshot() -> dict[str, Any]:
    return {
        "agent": agent_view(),
        "server_host": (read_raw_config().get("server") or {}).get("host"),
        "server_port": (read_raw_config().get("server") or {}).get("port"),
    }
