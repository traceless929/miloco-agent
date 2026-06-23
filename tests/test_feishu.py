"""Feishu channel tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from miloco_agent.app import create_app
from miloco_agent.channels.feishu.bindings import FeishuBindings
from miloco_agent.channels.feishu.crypto import parse_request_body
from miloco_agent.channels.feishu.bind_phrases import (
    escape_feishu_markdown,
    is_bind_command,
)
from miloco_agent.channels.feishu.handler import extract_text_message
from miloco_agent.channels.feishu.cards import build_markdown_card, card_content_string


def test_extract_text_message() -> None:
    event = {
        "sender": {
            "sender_type": "user",
            "sender_id": {"open_id": "ou_test"},
        },
        "message": {
            "message_type": "text",
            "content": json.dumps({"text": "列出设备"}),
        },
    }
    parsed = extract_text_message(event)
    assert parsed == ("ou_test", "列出设备")


def test_is_bind_command() -> None:
    assert is_bind_command("*#绑定#*")
    assert is_bind_command("  *#绑定miloco#*  ")
    assert not is_bind_command("绑定")
    assert not is_bind_command("绑定 Miloco")
    assert not is_bind_command("列出设备")


def test_escape_feishu_markdown_bind_phrase() -> None:
    assert escape_feishu_markdown("*#绑定#*") == r"\*#绑定#\*"
    assert escape_feishu_markdown(r"\*already\*") == r"\\\*already\\\*"


def test_bindings_mvp_allow_when_empty(tmp_path) -> None:
    store = FeishuBindings(tmp_path / "bindings.json")
    assert store.is_allowed("ou_any")
    store.bind("ou_admin")
    assert store.is_allowed("ou_admin")


def test_feishu_url_verification(client_feishu: TestClient) -> None:
    res = client_feishu.post(
        "/feishu/webhook",
        json={"challenge": "abc-123", "type": "url_verification"},
    )
    assert res.status_code == 200
    assert res.json()["challenge"] == "abc-123"


def test_feishu_not_configured(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"agent": {"feishu": {"mode": "webhook"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    app = create_app()
    client = TestClient(app)
    res = client.post("/feishu/webhook", json={"challenge": "x"})
    assert res.status_code == 503


@pytest.fixture
def client_feishu(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "agent": {
                    "auth_bearer": "t",
                    "feishu": {
                        "enabled": True,
                        "mode": "webhook",
                        "app_id": "cli_test",
                        "app_secret": "sec_test",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    return TestClient(create_app())


def test_decrypt_roundtrip() -> None:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    import base64
    import hashlib

    key = hashlib.sha256(b"test-key").digest()
    plain = b'{"challenge":"xyz"}'
    pad = 16 - len(plain) % 16
    plain_padded = plain + bytes([pad]) * pad
    iv = b"0" * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(plain_padded) + encryptor.finalize()
    blob = base64.b64encode(iv + encrypted).decode()
    parsed = parse_request_body({"encrypt": blob}, encrypt_key="test-key")
    assert parsed["challenge"] == "xyz"


def test_markdown_card_json() -> None:
    card = build_markdown_card("**加粗**\\n| a | b |\\n|---|---|\\n| 1 | 2 |")
    assert card["schema"] == "2.0"
    assert card["body"]["elements"][0]["tag"] == "markdown"
    content = card_content_string(card)
    assert '"tag": "markdown"' in content
    assert "**加粗**" in content


def test_streaming_card_config() -> None:
    card = build_markdown_card("hi", streaming=True)
    assert card["config"]["streaming_mode"] is True
    assert card["config"]["update_multi"] is True
