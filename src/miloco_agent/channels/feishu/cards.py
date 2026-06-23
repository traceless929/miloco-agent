"""Feishu interactive card JSON builders."""

from __future__ import annotations

import json
from typing import Any

REPLY_ELEMENT_ID = "miloco_reply_md"


def build_markdown_card(
    text: str,
    *,
    streaming: bool = False,
    element_id: str = REPLY_ELEMENT_ID,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if streaming:
        config = {
            "streaming_mode": True,
            "update_multi": True,
        }
    return {
        "schema": "2.0",
        "config": config,
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "element_id": element_id,
                    "content": text,
                }
            ]
        },
    }


def card_content_string(card: dict[str, Any]) -> str:
    return json.dumps(card, ensure_ascii=False)


def card_entity_message_content(card_id: str) -> str:
    return json.dumps(
        {"type": "card", "data": {"card_id": card_id}},
        ensure_ascii=False,
    )
