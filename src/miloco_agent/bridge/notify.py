"""Notify channel bind + miloco_im_push (OpenClaw notify.ts compatible)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from miloco_agent.bridge.context import MilocoBridgeContext
from miloco_agent.channels.feishu.bind_phrases import bind_phrase_hint_md
from miloco_agent.channels.feishu.client import FeishuClient
from miloco_agent.config import FeishuSettings, load_settings

BindReason = Literal["not_configured", "configured_but_invalid"]

BIND_HINT_EXAMPLE: dict[BindReason, str] = {
    "not_configured": (
        "您尚未设置 Miloco 通知频道，本条消息已临时发送到最近活跃的对话。"
        f"在飞书私聊机器人发送口令「{bind_phrase_hint_md()}」可将当前对话设为固定通知频道，"
        "后续提醒、定时任务、告警等通知都将发送至此。"
    ),
    "configured_but_invalid": (
        "您原先绑定的 Miloco 通知频道已失效，本条消息已临时发送到最近活跃的对话。"
        f"请重新发送口令「{bind_phrase_hint_md()}」绑定。"
    ),
}


def _notify_channel_path() -> Path:
    from miloco_agent.config import miloco_home

    return miloco_home() / "agent" / "notify_channel.json"


def load_notify_channel() -> dict[str, Any] | None:
    path = _notify_channel_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_notify_channel(
    *,
    open_id: str,
    channel: str = "feishu",
    session_key: str | None = None,
) -> dict[str, Any]:
    path = _notify_channel_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "channel": channel,
        "open_id": open_id,
        "session_key": session_key or f"feishu:{open_id}",
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return payload


def resolve_im_target(
    ctx: MilocoBridgeContext | None,
    *,
    feishu: FeishuSettings | None = None,
) -> tuple[str | None, bool, BindReason | None]:
    """Return (open_id, needs_bind, bind_reason)."""
    fs = feishu or load_settings().feishu
    bound = load_notify_channel()
    if bound and bound.get("open_id"):
        return str(bound["open_id"]), False, None

    fallback = (ctx.feishu_open_id if ctx else None) or fs.default_receive_open_id
    if fallback:
        reason: BindReason = "not_configured"
        return fallback, True, reason

    return None, True, "not_configured"


async def push_im(
    message: str,
    *,
    bind_hint: str | None = None,
    ctx: MilocoBridgeContext | None = None,
    feishu: FeishuClient | None = None,
    feishu_settings: FeishuSettings | None = None,
) -> dict[str, Any]:
    """OpenClaw-compatible miloco_im_push result shape."""
    fs = feishu_settings or load_settings().feishu
    client = feishu or FeishuClient(fs)
    open_id, needs_bind, bind_reason = resolve_im_target(ctx, feishu=fs)

    if not open_id:
        return {
            "ok": False,
            "needsBind": True,
            "bindReason": bind_reason or "not_configured",
            "bindHintExample": BIND_HINT_EXAMPLE["not_configured"],
            "error": "未配置通知接收人，请先绑定或设置 default_receive_open_id",
        }

    body = message
    if bind_hint:
        body = f"{message}\n\n{bind_hint}"

    if not fs.configured or not fs.enabled:
        return {"ok": False, "error": "feishu not configured"}

    try:
        await client.send_reply(open_id, body)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    result: dict[str, Any] = {
        "ok": True,
        "channel": "feishu",
        "open_id": open_id,
    }
    if needs_bind:
        result["needsBind"] = True
        result["bindReason"] = bind_reason
        result["bindHintExample"] = BIND_HINT_EXAMPLE.get(
            bind_reason or "not_configured",
            BIND_HINT_EXAMPLE["not_configured"],
        )
    return result


def bind_notify_channel(ctx: MilocoBridgeContext | None) -> dict[str, Any]:
    open_id = ctx.feishu_open_id if ctx else None
    if not open_id:
        return {
            "ok": False,
            "error": "当前 session 无有效的飞书 open_id，无法绑定为通知频道",
        }
    return bind_notify_channel_by_open_id(open_id)


def bind_notify_channel_by_open_id(open_id: str) -> dict[str, Any]:
    saved = save_notify_channel(
        open_id=open_id.strip(),
        channel="feishu",
        session_key=f"feishu:{open_id.strip()}",
    )
    return {"ok": True, "channel": saved["channel"], "open_id": saved["open_id"]}
