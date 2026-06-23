"""Feishu tenant_access_token cache."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from miloco_agent.config import FeishuSettings

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_REFRESH_BUFFER_S = 120.0


class FeishuAuth:
    def __init__(self, settings: FeishuSettings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._token: str = ""
        self._expire_at: float = 0.0

    async def get_tenant_access_token(self) -> str:
        async with self._lock:
            now = time.monotonic()
            if self._token and now < self._expire_at:
                return self._token
            data = await self._fetch_token()
            self._token = str(data["tenant_access_token"])
            expire = float(data.get("expire", 7200))
            self._expire_at = now + max(expire - _REFRESH_BUFFER_S, 60.0)
            return self._token

    async def _fetch_token(self) -> dict[str, Any]:
        payload = {
            "app_id": self._settings.app_id,
            "app_secret": self._settings.app_secret,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(_TOKEN_URL, json=payload)
            response.raise_for_status()
            body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(
                f"feishu token failed: [{body.get('code')}] {body.get('msg')}"
            )
        return body
