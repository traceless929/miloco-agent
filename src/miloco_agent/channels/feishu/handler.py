"""Parse Feishu IM events and drive TurnRunner."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from miloco_agent.channels.feishu.bind_phrases import (
    bind_phrase_hint,
    bind_phrase_hint_md,
    is_bind_command,
)
from miloco_agent.channels.feishu.bindings import FeishuBindings
from miloco_agent.bridge.notify import bind_notify_channel_by_open_id
from miloco_agent.channels.feishu.client import FeishuClient
from miloco_agent.config import FeishuSettings, load_settings
from miloco_agent.runtime.turn_runner import turn_runner

logger = logging.getLogger(__name__)


def extract_text_message(event: dict[str, Any]) -> tuple[str, str] | None:
    """Return (open_id, text) for im.message.receive_v1 text messages."""
    message = event.get("message") or {}
    if message.get("message_type") != "text":
        return None
    sender = event.get("sender") or {}
    if sender.get("sender_type") != "user":
        return None
    sender_id = sender.get("sender_id") or {}
    open_id = sender_id.get("open_id")
    if not open_id:
        return None
    content_raw = message.get("content") or "{}"
    try:
        content = json.loads(content_raw)
    except json.JSONDecodeError:
        return None
    text = str(content.get("text") or "").strip()
    if not text:
        return None
    return str(open_id), text


async def _send_simple(api: FeishuClient, open_id: str, text: str) -> None:
    if api._settings.reply_format == "text":
        await api.send_text(open_id, text)
    else:
        await api.send_markdown(open_id, text)


def _bind_phrase_for_reply(fs: FeishuSettings) -> str:
    return bind_phrase_hint_md() if fs.reply_format != "text" else bind_phrase_hint()


async def _run_agent_reply(
    *,
    open_id: str,
    text: str,
    api: FeishuClient,
    fs: FeishuSettings,
) -> None:
    trace_id = f"feishu-{uuid.uuid4().hex[:12]}"
    session_key = f"feishu:{open_id}"
    session = None

    if fs.stream_reply:
        try:
            session = await api.start_streaming_reply(open_id)

            async def on_text(partial: str) -> None:
                if session is not None:
                    await session.update(partial)

            reply = await turn_runner.run_im_reply_streaming(
                message=text,
                session_key=session_key,
                lane="miloco-interactive",
                trace_id=trace_id,
                on_text=on_text,
                timeout_ms=90_000,
                feishu=fs,
            )
            await session.finish(reply)
            return
        except Exception:  # noqa: BLE001
            logger.exception("feishu streaming reply failed, fallback to markdown")
            if session is not None:
                try:
                    await session.finish("处理失败，请稍后再试。")
                except Exception:  # noqa: BLE001
                    pass

    reply = await turn_runner.run_im_reply(
        message=text,
        session_key=session_key,
        lane="miloco-interactive",
        trace_id=trace_id,
        timeout_ms=90_000,
        feishu=fs,
    )
    await _send_simple(api, open_id, reply)


async def handle_im_message(
    open_id: str,
    text: str,
    *,
    settings: FeishuSettings | None = None,
    client: FeishuClient | None = None,
    bindings: FeishuBindings | None = None,
) -> None:
    cfg = load_settings()
    fs = settings or cfg.feishu
    api = client or FeishuClient(fs)
    store = bindings or FeishuBindings()

    if is_bind_command(text):
        store.bind(open_id)
        bind_notify_channel_by_open_id(open_id)
        phrase = _bind_phrase_for_reply(fs)
        await _send_simple(
            api,
            open_id,
            f"已绑定 Miloco（飞书对话 + IM 通知频道）。\n"
            f"后续 Cron、告警等主动通知将发到此会话。\n"
            f"绑定口令：{phrase}",
        )
        return

    if not store.is_allowed(open_id, default_open_id=fs.default_receive_open_id):
        phrase = _bind_phrase_for_reply(fs)
        await _send_simple(
            api,
            open_id,
            f"尚未绑定 Miloco。请发送口令「{phrase}」完成绑定，"
            f"或联系管理员配置 default_receive_open_id。",
        )
        return

    await _run_agent_reply(open_id=open_id, text=text, api=api, fs=fs)
