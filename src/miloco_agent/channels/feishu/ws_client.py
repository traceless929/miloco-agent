"""Feishu long-connection (WebSocket) client via lark-oapi SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageMessageReadV1, P2ImMessageReceiveV1
from lark_oapi.core.enum import LogLevel

from miloco_agent.channels.feishu.handler import handle_im_message
from miloco_agent.config import FeishuSettings

logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_main_loop: asyncio.AbstractEventLoop | None = None


def extract_from_lark_event(data: P2ImMessageReceiveV1) -> tuple[str, str] | None:
    event = data.event
    if event is None or event.message is None or event.sender is None:
        return None
    if event.sender.sender_type != "user":
        return None
    if event.message.message_type != "text":
        return None
    sender_id = event.sender.sender_id
    open_id = sender_id.open_id if sender_id else None
    if not open_id:
        return None
    try:
        content = json.loads(event.message.content or "{}")
    except json.JSONDecodeError:
        return None
    text = str(content.get("text") or "").strip()
    if not text:
        return None
    return str(open_id), text


def _on_p2_im_message_message_read_v1(_data: P2ImMessageMessageReadV1) -> None:
    """No-op: read receipts are informational only."""


def _on_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    parsed = extract_from_lark_event(data)
    if parsed is None:
        return
    open_id, text = parsed
    loop = _main_loop
    if loop is None or not loop.is_running():
        logger.warning("feishu ws: main event loop not ready, drop message")
        return

    async def _run() -> None:
        try:
            await handle_im_message(open_id, text)
        except Exception:  # noqa: BLE001
            logger.exception("feishu ws: handle message failed open_id=%s", open_id)

    asyncio.run_coroutine_threadsafe(_run(), loop)


def _ws_thread_main(settings: FeishuSettings) -> None:
    logger.info("feishu long-connection starting app_id=%s", settings.app_id)
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_p2_im_message_receive_v1)
        .register_p2_im_message_message_read_v1(_on_p2_im_message_message_read_v1)
        .build()
    )
    cli = lark.ws.Client(
        settings.app_id,
        settings.app_secret,
        event_handler=handler,
        log_level=LogLevel.INFO,
    )
    cli.start()


def start_feishu_long_connection(
    loop: asyncio.AbstractEventLoop,
    settings: FeishuSettings,
) -> None:
    """Start lark-oapi WebSocket client in a daemon thread."""
    global _thread, _main_loop
    if not settings.configured or not settings.enabled or not settings.use_long_connection:
        return
    if _thread is not None and _thread.is_alive():
        logger.info("feishu long-connection already running")
        return
    _main_loop = loop
    _thread = threading.Thread(
        target=_ws_thread_main,
        args=(settings,),
        name="feishu-ws",
        daemon=True,
    )
    _thread.start()
    logger.info("feishu long-connection thread started")
