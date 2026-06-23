"""User task cron registry ($MILOCO_HOME/agent/user_cron_jobs.json)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from miloco_agent.config import miloco_home

PendingAction = Literal["disable", "enable", "remove"]


@dataclass
class UserCronJob:
    id: str
    name: str
    cron_expr: str
    message: str
    enabled: bool = True
    task_id: str | None = None
    timezone: str = "Asia/Shanghai"
    timeout_ms: int = 300_000

    @property
    def session_key(self) -> str:
        return f"cron:{self.name}"

    def prefixed_message(self) -> str:
        return f"[cron:{self.id} {self.name}] {self.message}"


@dataclass
class UserCronStore:
    version: int = 1
    jobs: list[UserCronJob] = field(default_factory=list)


class UserCronRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._path = miloco_home() / "agent" / "user_cron_jobs.json"

    def _load_unlocked(self) -> UserCronStore:
        if not self._path.is_file():
            return UserCronStore()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return UserCronStore()
        jobs = [
            UserCronJob(**{k: v for k, v in j.items() if k in UserCronJob.__dataclass_fields__})
            for j in raw.get("jobs") or []
        ]
        return UserCronStore(version=int(raw.get("version") or 1), jobs=jobs)

    def _save_unlocked(self, store: UserCronStore) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": store.version,
            "jobs": [asdict(j) for j in store.jobs],
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list_jobs(self, *, include_disabled: bool = True) -> list[UserCronJob]:
        with self._lock:
            store = self._load_unlocked()
        if include_disabled:
            return list(store.jobs)
        return [j for j in store.jobs if j.enabled]

    def get(self, job_id: str) -> UserCronJob | None:
        with self._lock:
            store = self._load_unlocked()
        for job in store.jobs:
            if job.id == job_id:
                return job
        return None

    def add(
        self,
        *,
        name: str,
        cron_expr: str,
        message: str,
        task_id: str | None = None,
        enabled: bool = True,
        timezone: str = "Asia/Shanghai",
        timeout_ms: int = 300_000,
    ) -> UserCronJob:
        job = UserCronJob(
            id=f"job-{uuid.uuid4().hex[:12]}",
            name=name,
            cron_expr=cron_expr,
            message=message,
            enabled=enabled,
            task_id=task_id,
            timezone=timezone,
            timeout_ms=timeout_ms,
        )
        with self._lock:
            store = self._load_unlocked()
            store.jobs.append(job)
            self._save_unlocked(store)
        return job

    def remove(self, job_id: str) -> bool:
        with self._lock:
            store = self._load_unlocked()
            before = len(store.jobs)
            store.jobs = [j for j in store.jobs if j.id != job_id]
            if len(store.jobs) == before:
                return False
            self._save_unlocked(store)
            return True

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        with self._lock:
            store = self._load_unlocked()
            for job in store.jobs:
                if job.id == job_id:
                    job.enabled = enabled
                    self._save_unlocked(store)
                    return True
        return False

    def update(
        self,
        job_id: str,
        *,
        name: str | None = None,
        cron_expr: str | None = None,
        message: str | None = None,
        task_id: str | None = None,
        enabled: bool | None = None,
        timezone: str | None = None,
        timeout_ms: int | None = None,
    ) -> UserCronJob | None:
        fields = {
            "name": name,
            "cron_expr": cron_expr,
            "message": message,
            "task_id": task_id,
            "enabled": enabled,
            "timezone": timezone,
            "timeout_ms": timeout_ms,
        }
        with self._lock:
            store = self._load_unlocked()
            for job in store.jobs:
                if job.id != job_id:
                    continue
                for key, value in fields.items():
                    if value is not None and key in UserCronJob.__dataclass_fields__:
                        setattr(job, key, value)
                self._save_unlocked(store)
                return job
        return None

    def apply_pending(self, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply agent_pending cron ops from task disable/delete."""
        results: list[dict[str, Any]] = []
        for op in ops:
            if op.get("kind") != "cron":
                continue
            ref = str(op.get("ref") or "")
            action = str(op.get("action") or "")
            ok = False
            if action == "remove":
                ok = self.remove(ref)
            elif action in ("disable", "enable"):
                ok = self.set_enabled(ref, action == "enable")
            results.append({"ref": ref, "action": action, "ok": ok})
        return results


user_cron_registry = UserCronRegistry()
