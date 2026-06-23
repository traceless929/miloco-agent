"""Deterministic notify routing (aligned with miloco-notify skill)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NotifyLevel = Literal["L1", "L2", "L3"]
NotifyChannel = Literal["tts", "im", "miot_push"]


@dataclass(frozen=True)
class DeliveryPlan:
    level: NotifyLevel
    message: str
    channels: tuple[NotifyChannel, ...]
    room: str | None = None
    speaker_did: str | None = None
    reason: str = ""


def normalize_level(level: str | None) -> NotifyLevel:
    raw = (level or "L3").strip().upper()
    if raw in ("L1", "L2", "L3"):
        return raw  # type: ignore[return-value]
    if raw in ("DANGER", "CRITICAL", "HIGH"):
        return "L1"
    if raw in ("WARNING", "WARN", "MEDIUM"):
        return "L2"
    return "L3"


def plan_delivery(
    *,
    message: str,
    level: str | None = "L3",
    room: str | None = None,
    speaker_did: str | None = None,
    speaker_online: bool = False,
    anyone_home: bool | None = None,
) -> DeliveryPlan:
    """Pick channels without LLM — agent still writes copy."""
    lvl = normalize_level(level)
    channels: list[NotifyChannel] = []

    if lvl in ("L1", "L2"):
        if speaker_did and speaker_online and (anyone_home is not False):
            channels.append("tts")
        channels.extend(["im", "miot_push"])
        reason = "危险/预警：IM + 米家推送必发；有在线音箱则加 TTS"
    else:
        if speaker_did and speaker_online and (anyone_home is not False):
            channels.append("tts")
            reason = "日常：优先事发/目标房间 TTS"
        else:
            channels.append("im")
            reason = "日常：TTS 不可达，走 IM"

    # de-dup while preserving order
    seen: set[str] = set()
    ordered: list[NotifyChannel] = []
    for ch in channels:
        if ch not in seen:
            seen.add(ch)
            ordered.append(ch)

    return DeliveryPlan(
        level=lvl,
        message=message.strip(),
        channels=tuple(ordered),
        room=room,
        speaker_did=speaker_did,
        reason=reason,
    )
