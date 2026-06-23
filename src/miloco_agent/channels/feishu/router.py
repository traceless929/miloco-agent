"""Feishu event subscription HTTP endpoint."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from miloco_agent.channels.feishu.crypto import parse_request_body, verify_signature
from miloco_agent.channels.feishu.handler import extract_text_message, handle_im_message
from miloco_agent.config import load_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/feishu/webhook")
async def feishu_webhook(request: Request, background: BackgroundTasks) -> JSONResponse:
    settings = load_settings().feishu
    if not settings.configured or not settings.enabled:
        return JSONResponse(
            status_code=503,
            content={"code": 1, "msg": "feishu not configured"},
        )

    raw_body = await request.body()
    try:
        body: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"code": 1, "msg": "invalid json"})

    signature = request.headers.get("X-Lark-Signature", "")
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    if settings.verification_token and signature:
        if not verify_signature(
            timestamp=timestamp,
            nonce=nonce,
            body=raw_body,
            signature=signature,
            verification_token=settings.verification_token,
            encrypt_key=settings.encrypt_key,
        ):
            logger.warning("feishu signature mismatch")
            return JSONResponse(status_code=401, content={"code": 1, "msg": "bad signature"})

    payload = parse_request_body(body, encrypt_key=settings.encrypt_key)

    if payload.get("type") == "url_verification" or "challenge" in payload:
        challenge = payload.get("challenge")
        logger.info("feishu url_verification challenge=%s", challenge)
        return JSONResponse(content={"challenge": challenge})

    header = payload.get("header") or {}
    event_type = header.get("event_type")
    if event_type != "im.message.receive_v1":
        return JSONResponse(content={"code": 0})

    event = payload.get("event") or {}
    parsed = extract_text_message(event)
    if parsed is None:
        return JSONResponse(content={"code": 0})

    open_id, text = parsed
    background.add_task(handle_im_message, open_id, text)
    return JSONResponse(content={"code": 0})
