"""Execute notify delivery plans (Feishu IM + MiOT push + speaker TTS)."""

from __future__ import annotations

import json
import logging
from typing import Any

from miloco_agent.channels.feishu.bind_phrases import bind_phrase_hint_md
from miloco_agent.channels.feishu.client import FeishuClient
from miloco_agent.config import FeishuSettings, load_settings
from miloco_agent.notify.policy import DeliveryPlan, plan_delivery
from miloco_agent.tools.devices import tool_speaker_tts
from miloco_agent.tools.miloco_client import MilocoApiClient, MilocoApiError

logger = logging.getLogger(__name__)


class NotifyService:
    def __init__(
        self,
        *,
        client: MilocoApiClient | None = None,
        feishu: FeishuClient | None = None,
        feishu_settings: FeishuSettings | None = None,
    ) -> None:
        cfg = load_settings()
        self._client = client or MilocoApiClient(cfg)
        fs = feishu_settings or cfg.feishu
        self._feishu = feishu or FeishuClient(fs)
        self._feishu_settings = fs

    async def send(
        self,
        *,
        message: str,
        level: str | None = "L3",
        room: str | None = None,
        speaker_did: str | None = None,
        speaker_online: bool = False,
        anyone_home: bool | None = None,
        open_id: str | None = None,
    ) -> dict[str, Any]:
        plan = plan_delivery(
            message=message,
            level=level,
            room=room,
            speaker_did=speaker_did,
            speaker_online=speaker_online,
            anyone_home=anyone_home,
        )
        return await self.deliver_plan(plan, open_id=open_id)

    async def deliver_plan(
        self,
        plan: DeliveryPlan,
        *,
        open_id: str | None = None,
    ) -> dict[str, Any]:
        target_open_id = open_id or self._feishu_settings.default_receive_open_id
        results: dict[str, Any] = {
            "ok": True,
            "level": plan.level,
            "channels": list(plan.channels),
            "reason": plan.reason,
            "deliveries": {},
        }

        for channel in plan.channels:
            try:
                if channel == "im":
                    results["deliveries"]["im"] = await self._send_im(
                        plan.message,
                        target_open_id,
                    )
                elif channel == "miot_push":
                    results["deliveries"]["miot_push"] = await self._send_miot_push(
                        plan.message
                    )
                elif channel == "tts":
                    if not plan.speaker_did:
                        results["deliveries"]["tts"] = {
                            "ok": False,
                            "error": "speaker_did required for TTS",
                        }
                        continue
                    raw = await tool_speaker_tts(
                        self._client,
                        did=plan.speaker_did,
                        text=plan.message,
                    )
                    results["deliveries"]["tts"] = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                logger.exception("notify channel %s failed", channel)
                results["deliveries"][channel] = {"ok": False, "error": str(exc)}
                results["ok"] = False

        if not results["deliveries"]:
            results["ok"] = False
            results["error"] = "no channel delivered"
        return results

    async def _send_im(
        self,
        message: str,
        open_id: str | None,
    ) -> dict[str, Any]:
        if not open_id:
            return {
                "ok": False,
                "needsBind": True,
                "error": "未配置通知接收人，无法 IM 通知",
                "bindHintExample": (
                    f"请发送口令「{bind_phrase_hint_md()}」绑定通知频道，"
                    "或配置 agent.feishu.default_receive_open_id"
                ),
            }
        if not self._feishu_settings.configured or not self._feishu_settings.enabled:
            return {"ok": False, "error": "feishu not configured"}
        await self._feishu.send_reply(open_id, message)
        return {"ok": True, "channel": "feishu", "open_id": open_id}

    async def _send_miot_push(self, message: str) -> dict[str, Any]:
        try:
            await self._client.send_notify(message)
            return {"ok": True, "channel": "miot_push"}
        except MilocoApiError as exc:
            return {"ok": False, "error": str(exc)}
