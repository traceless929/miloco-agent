"""Feishu IM outbound API."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from miloco_agent.channels.feishu.auth import FeishuAuth
from miloco_agent.channels.feishu.cards import (
    REPLY_ELEMENT_ID,
    build_markdown_card,
    card_content_string,
    card_entity_message_content,
)
from miloco_agent.config import FeishuSettings

logger = logging.getLogger(__name__)

_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
_CARD_CREATE_URL = "https://open.feishu.cn/open-apis/cardkit/v1/cards"


class FeishuClient:
    def __init__(self, settings: FeishuSettings, auth: FeishuAuth | None = None) -> None:
        self._settings = settings
        self._auth = auth or FeishuAuth(settings)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._auth.get_tenant_access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                json=json_body,
            )
            response.raise_for_status()
            body = response.json()
        if body.get("code") != 0:
            raise RuntimeError(
                f"feishu api failed: [{body.get('code')}] {body.get('msg')}"
            )
        return body.get("data") or {}

    async def send_text(self, open_id: str, text: str) -> dict[str, Any]:
        payload = {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        return await self._request(
            "POST",
            _SEND_URL,
            params={"receive_id_type": "open_id"},
            json_body=payload,
        )

    async def send_markdown(self, open_id: str, text: str) -> dict[str, Any]:
        """Send rendered Markdown via interactive card (no CardKit entity)."""
        card = build_markdown_card(text)
        payload = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": card_content_string(card),
        }
        return await self._request(
            "POST",
            _SEND_URL,
            params={"receive_id_type": "open_id"},
            json_body=payload,
        )

    async def send_reply(self, open_id: str, text: str) -> dict[str, Any]:
        if self._settings.reply_format == "text":
            return await self.send_text(open_id, text)
        return await self.send_markdown(open_id, text)

    async def create_streaming_card(self, initial_text: str = "⏳ 处理中…") -> str:
        card = build_markdown_card(initial_text, streaming=True)
        data = await self._request(
            "POST",
            _CARD_CREATE_URL,
            json_body={
                "type": "card_json",
                "data": card_content_string(card),
            },
        )
        card_id = str(data.get("card_id") or "")
        if not card_id:
            raise RuntimeError("feishu card create: missing card_id")
        return card_id

    async def send_card_entity(self, open_id: str, card_id: str) -> dict[str, Any]:
        payload = {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": card_entity_message_content(card_id),
        }
        return await self._request(
            "POST",
            _SEND_URL,
            params={"receive_id_type": "open_id"},
            json_body=payload,
        )

    async def update_streaming_content(
        self,
        card_id: str,
        content: str,
        sequence: int,
        *,
        element_id: str = REPLY_ELEMENT_ID,
    ) -> None:
        url = (
            f"https://open.feishu.cn/open-apis/cardkit/v1/cards/"
            f"{card_id}/elements/{element_id}/content"
        )
        await self._request(
            "PUT",
            url,
            json_body={"content": content, "sequence": sequence},
        )

    async def close_streaming_mode(self, card_id: str, sequence: int) -> None:
        url = f"https://open.feishu.cn/open-apis/cardkit/v1/cards/{card_id}/settings"
        settings_json = json.dumps(
            {"config": {"streaming_mode": False}},
            ensure_ascii=False,
        )
        await self._request(
            "PATCH",
            url,
            json_body={"settings": settings_json, "sequence": sequence},
        )

    async def start_streaming_reply(
        self,
        open_id: str,
        *,
        initial_text: str = "⏳ 处理中…",
    ) -> "FeishuStreamingSession":
        card_id = await self.create_streaming_card(initial_text)
        await self.send_card_entity(open_id, card_id)
        return FeishuStreamingSession(self, card_id)


class FeishuStreamingSession:
    """Throttle CardKit content updates for typewriter-style streaming."""

    def __init__(self, client: FeishuClient, card_id: str) -> None:
        self._client = client
        self.card_id = card_id
        self._sequence = 0
        self._last_update = 0.0
        self._pending: str | None = None

    async def update(self, text: str, *, force: bool = False) -> None:
        now = time.monotonic()
        interval = self._client._settings.stream_interval_s
        if not force and now - self._last_update < interval:
            self._pending = text
            return
        self._sequence += 1
        await self._client.update_streaming_content(
            self.card_id,
            text,
            self._sequence,
        )
        self._last_update = now
        self._pending = None

    async def finish(self, final_text: str) -> None:
        if self._pending and self._pending != final_text:
            await self.update(self._pending, force=True)
        if final_text:
            await self.update(final_text, force=True)
        self._sequence += 1
        try:
            await self._client.close_streaming_mode(self.card_id, self._sequence)
        except Exception:  # noqa: BLE001
            logger.exception("feishu close streaming_mode failed card_id=%s", self.card_id)
