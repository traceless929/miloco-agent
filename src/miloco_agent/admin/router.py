"""Admin API + static console."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from miloco_agent.admin import config_io, service
from miloco_agent.admin.ops import schedule_sidecar_restart
from miloco_agent.bridge.cli_resolve import install_miloco_cli
from miloco_agent.bridge.notify import bind_notify_channel_by_open_id, load_notify_channel
from miloco_agent.bridge.status import build_bridge_status
from miloco_agent.config import MilocoAgentSettings, load_settings
from miloco_agent.cron.jobs import HOME_PROFILE_JOBS
from miloco_agent.cron.runner import run_cron_job
from miloco_agent.cron.scheduler import HomeProfileCronScheduler
from miloco_agent.cron.user_registry import user_cron_registry
from miloco_agent.webhook.router import verify_bearer

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/admin", tags=["admin"])


class AgentConfigPatch(BaseModel):
    feishu: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None
    cron: dict[str, Any] | None = None

    def to_patch(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.feishu is not None:
            out["feishu"] = self.feishu
        if self.llm is not None:
            out["llm"] = self.llm
        if self.cron is not None:
            out["cron"] = self.cron
        return out


class BindNotifyBody(BaseModel):
    open_id: str | None = Field(
        default=None,
        description="飞书 open_id；留空则使用 agent.feishu.default_receive_open_id",
    )


class UserCronBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cron_expr: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    task_id: str | None = None
    enabled: bool = True
    timezone: str = "Asia/Shanghai"
    timeout_ms: int = 300_000


class UserCronPatch(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    message: str | None = None
    task_id: str | None = None
    enabled: bool | None = None
    timezone: str | None = None
    timeout_ms: int | None = None


class TraceCleanupBody(BaseModel):
    run_ids: list[str] | None = None
    rel_paths: list[str] | None = None
    day: str | None = None
    older_than_days: int | None = None
    delete_all: bool = False


def _cron_scheduler(request: Request) -> HomeProfileCronScheduler | None:
    return getattr(request.app.state, "cron_scheduler", None)


def _apply_runtime_reload(request: Request) -> dict[str, Any]:
    settings = load_settings()
    request.app.state.settings = settings
    sched: HomeProfileCronScheduler | None = _cron_scheduler(request)
    restarted_cron = False
    if sched is not None:
        sched.shutdown()
        if settings.cron.enabled:
            sched.start(asyncio.get_running_loop())
            restarted_cron = sched.running
    return {
        "settings": settings,
        "cron_restarted": restarted_cron,
        "cron_enabled": settings.cron.enabled,
        "cron_running": bool(sched and sched.running),
    }


@router.get("")
async def admin_console() -> FileResponse:
    index = _STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="admin UI not found")
    return FileResponse(index, media_type="text/html; charset=utf-8")


@router.get("/api/status")
async def api_status(
    request: Request,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    settings: MilocoAgentSettings = request.app.state.settings
    sched = _cron_scheduler(request)
    return service.build_status(
        settings,
        cron_running=bool(sched and sched.running),
    )


@router.get("/api/config")
async def api_config(_: None = Depends(verify_bearer)) -> dict[str, Any]:
    return service.config_snapshot()


@router.patch("/api/config")
async def api_config_patch(
    body: AgentConfigPatch,
    request: Request,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    patch = body.to_patch()
    if not patch:
        raise HTTPException(status_code=400, detail="empty patch")
    agent = config_io.write_agent_patch(patch)
    reload_info = _apply_runtime_reload(request)
    return {
        "ok": True,
        "agent": agent,
        "cron_enabled": reload_info["cron_enabled"],
        "cron_running": reload_info["cron_running"],
        "cron_restarted": reload_info["cron_restarted"],
    }


@router.post("/api/reload")
async def api_reload(request: Request, _: None = Depends(verify_bearer)) -> dict[str, Any]:
    reload_info = _apply_runtime_reload(request)
    return {
        "ok": True,
        "cron_restarted": reload_info["cron_restarted"],
        "cron_enabled": reload_info["cron_enabled"],
        "cron_running": reload_info["cron_running"],
        "note": "飞书 app_id/secret 变更需重启 Sidecar 进程后完全生效",
    }


@router.get("/api/crons")
async def api_crons(_: None = Depends(verify_bearer)) -> dict[str, Any]:
    return service.list_crons()


@router.post("/api/crons/trigger")
async def api_trigger_cron(
    request: Request,
    payload: dict[str, Any],
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    kind = str(payload.get("kind") or "")
    if kind == "managed":
        name = str(payload.get("name") or "")
        job = next((j for j in HOME_PROFILE_JOBS if j.name == name), None)
        if job is None:
            raise HTTPException(status_code=404, detail="managed job not found")
        result = await run_cron_job(job)
        return {"ok": True, "result": result}
    if kind == "user":
        from miloco_agent.cron.scheduler import run_user_cron_job

        job_id = str(payload.get("job_id") or "")
        job = user_cron_registry.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="user job not found")
        result = await run_user_cron_job(job)
        return {"ok": True, "result": result}
    raise HTTPException(status_code=400, detail="kind must be managed|user")


@router.get("/api/bridge")
async def api_bridge(_: None = Depends(verify_bearer)) -> dict[str, Any]:
    return build_bridge_status()


@router.post("/api/bridge/install-cli")
async def api_install_cli(_: None = Depends(verify_bearer)) -> dict[str, Any]:
    result = install_miloco_cli()
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "install failed")
    return result


@router.post("/api/bridge/bind-notify")
async def api_bind_notify(
    body: BindNotifyBody,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    settings = load_settings()
    open_id = (body.open_id or "").strip() or settings.feishu.default_receive_open_id
    if not open_id:
        raise HTTPException(
            status_code=400,
            detail="需要 open_id，或在飞书配置中填写 default_receive_open_id",
        )
    return bind_notify_channel_by_open_id(open_id)


@router.get("/api/sessions")
async def api_sessions(_: None = Depends(verify_bearer)) -> dict[str, Any]:
    return {"sessions": service.list_sessions()}


@router.get("/api/server/tasks")
async def api_server_tasks(
    request: Request,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    settings: MilocoAgentSettings = request.app.state.settings
    return await service.fetch_server_tasks(settings)


@router.get("/api/traces")
async def api_traces(
    limit: int = 40,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    return service.list_traces(limit=min(max(limit, 1), 100))


@router.get("/api/traces/files")
async def api_trace_files(
    day: str | None = None,
    limit: int = 50,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    return service.list_trace_dump_files(day=day, limit=min(max(limit, 1), 200))


@router.post("/api/traces/files/cleanup")
async def api_trace_cleanup(
    body: TraceCleanupBody,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    return service.cleanup_trace_dump_files(
        run_ids=body.run_ids,
        rel_paths=body.rel_paths,
        day=body.day,
        older_than_days=body.older_than_days,
        delete_all=body.delete_all,
    )


@router.delete("/api/traces/files/{run_id}")
async def api_delete_trace_file(
    run_id: str,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    result = service.delete_trace_dump_file(run_id=run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "not found")
    return result


@router.get("/api/traces/{run_id}")
async def api_trace_detail(
    run_id: str,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    return service.get_trace_detail(run_id)


@router.post("/api/crons/user")
async def api_create_user_cron(
    body: UserCronBody,
    request: Request,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    from miloco_agent.cron.scheduler import reload_user_cron_jobs

    job = service.create_user_cron(
        name=body.name,
        cron_expr=body.cron_expr,
        message=body.message,
        task_id=body.task_id,
        enabled=body.enabled,
        timezone=body.timezone,
        timeout_ms=body.timeout_ms,
    )
    reload_info = _apply_runtime_reload(request)
    reload_user_cron_jobs()
    return {"ok": True, "job": job, "cron_running": reload_info["cron_running"]}


@router.patch("/api/crons/user/{job_id}")
async def api_update_user_cron(
    job_id: str,
    body: UserCronPatch,
    request: Request,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    from miloco_agent.cron.scheduler import reload_user_cron_jobs

    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="empty patch")
    job = service.update_user_cron(job_id, **patch)
    if job is None:
        raise HTTPException(status_code=404, detail="user job not found")
    reload_info = _apply_runtime_reload(request)
    reload_user_cron_jobs()
    return {"ok": True, "job": job, "cron_running": reload_info["cron_running"]}


@router.delete("/api/crons/user/{job_id}")
async def api_delete_user_cron(
    job_id: str,
    request: Request,
    _: None = Depends(verify_bearer),
) -> dict[str, Any]:
    from miloco_agent.cron.scheduler import reload_user_cron_jobs

    if not service.delete_user_cron(job_id):
        raise HTTPException(status_code=404, detail="user job not found")
    reload_info = _apply_runtime_reload(request)
    reload_user_cron_jobs()
    return {"ok": True, "cron_running": reload_info["cron_running"]}


@router.post("/api/ops/restart")
async def api_restart_sidecar(_: None = Depends(verify_bearer)) -> dict[str, Any]:
    return schedule_sidecar_restart()
