"""Anti-collision Feishu bind phrases (chat access + notify channel)."""

from __future__ import annotations

import re

# 主口令：须完整发送，避免日常对话误触「绑定」
PRIMARY_BIND_PHRASE = "*#绑定#*"

# 可选别名（同样带防撞符号）
BIND_PHRASE_ALIASES: tuple[str, ...] = (
    PRIMARY_BIND_PHRASE,
    "*#绑定miloco#*",
    "*#绑定通知#*",
)

_BIND_NORMALIZED = {re.sub(r"\s+", "", p).lower() for p in BIND_PHRASE_ALIASES}


def normalize_bind_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip()).lower()


def is_bind_command(text: str) -> bool:
    """True when user sent an exact bind phrase (not substring match)."""
    return normalize_bind_text(text) in _BIND_NORMALIZED


def bind_phrase_hint() -> str:
    return PRIMARY_BIND_PHRASE


def escape_feishu_markdown(text: str) -> str:
    """Escape chars that Feishu card markdown treats as formatting."""
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        if ch in ("\\", "*", "_", "`", "[", "]", "(", ")"):
            out.append("\\")
        out.append(ch)
    return "".join(out)


def bind_phrase_hint_md() -> str:
    """Bind phrase safe to embed in Feishu interactive-card markdown."""
    return escape_feishu_markdown(PRIMARY_BIND_PHRASE)


def bind_instruction_short() -> str:
    return f"在飞书私聊机器人发送口令「{PRIMARY_BIND_PHRASE}」（须完全一致）"


def bind_instruction_short_md() -> str:
    return f"在飞书私聊机器人发送口令「{bind_phrase_hint_md()}」（须完全一致）"
