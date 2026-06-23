"""HTTP client for Miloco Server REST APIs."""

from __future__ import annotations

from typing import Any

import httpx

from miloco_agent.config import MilocoAgentSettings, load_settings


class MilocoApiError(Exception):
    """Miloco API returned a non-zero code or HTTP error."""


class MilocoApiClient:
    """Thin async wrapper around Miloco REST API."""

    def __init__(self, settings: MilocoAgentSettings | None = None) -> None:
        self._settings = settings or load_settings()
        self._base = self._settings.miloco_api_base.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._settings.miloco_api_headers)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                headers=self.headers,
                json=json,
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        code = body.get("code", -1)
        if code != 0:
            raise MilocoApiError(
                f"{path} failed: [{code}] {body.get('message', 'unknown')}"
            )
        return body.get("data")

    async def device_list(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/miot/device_list")
        return data if isinstance(data, list) else []

    async def device_spec(self, did: str) -> dict[str, Any]:
        data = await self._request("GET", f"/api/miot/devices/{did}/spec")
        return data if isinstance(data, dict) else {}

    async def device_control(
        self,
        did: str,
        *,
        control_type: str,
        iid: str | None = None,
        value: Any = None,
        properties: list[dict[str, Any]] | None = None,
        params: list[Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": control_type}
        if iid is not None:
            payload["iid"] = iid
        if value is not None:
            payload["value"] = value
        if properties is not None:
            payload["properties"] = properties
        if params is not None:
            payload["params"] = params
        data = await self._request(
            "POST",
            f"/api/miot/devices/{did}/control",
            json=payload,
        )
        return data if isinstance(data, dict) else {"result": data}

    async def send_notify(self, text: str) -> None:
        await self._request(
            "POST",
            "/api/miot/send_notify",
            json={"notify": text},
        )

    async def home_profile_list(
        self, *, target: str = "both"
    ) -> dict[str, Any]:
        data = await self._request(
            "GET",
            "/api/home-profile/entries",
            params={"target": target},
        )
        return data if isinstance(data, dict) else {}

    async def home_profile_rendered(self) -> str:
        data = await self._request("GET", "/api/home-profile/rendered")
        if isinstance(data, dict):
            return str(data.get("markdown") or "")
        return ""

    async def home_profile_write(
        self,
        ops: list[dict[str, Any]],
        *,
        user_edit: bool = False,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "POST",
            "/api/home-profile/profile:write",
            json={"ops": ops, "user_edit": user_edit},
        )
        return data if isinstance(data, list) else []

    async def home_profile_candidate_write(
        self, ops: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "POST",
            "/api/home-profile/candidates:write",
            json={"ops": ops},
        )
        return data if isinstance(data, list) else []

    async def home_profile_commit(self) -> dict[str, Any]:
        data = await self._request("POST", "/api/home-profile/commit")
        return data if isinstance(data, dict) else {}

    async def perception_logs(
        self,
        *,
        after: str | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if after:
            params["after"] = after
        if since:
            params["since"] = since
        if limit is not None:
            params["limit"] = limit
        data = await self._request(
            "GET",
            "/api/perception/logs",
            params=params or None,
        )
        return data if isinstance(data, dict) else {}

    async def task_get(self, task_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/api/tasks/{task_id}")
        return data if isinstance(data, dict) else {}

    async def task_disable(self, task_id: str) -> dict[str, Any]:
        data = await self._request("POST", f"/api/tasks/{task_id}/disable")
        return data if isinstance(data, dict) else {}

    async def task_delete(self, task_id: str, *, reason: str = "completed") -> dict[str, Any]:
        data = await self._request(
            "DELETE",
            f"/api/tasks/{task_id}",
            params={"reason": reason},
        )
        return data if isinstance(data, dict) else {}

    async def task_link_cron(self, task_id: str, job_id: str) -> None:
        await self._request(
            "POST",
            f"/api/tasks/{task_id}/link",
            json={"kind": "cron", "ref": job_id},
        )

    async def list_tasks(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/tasks")
        return data if isinstance(data, list) else []
