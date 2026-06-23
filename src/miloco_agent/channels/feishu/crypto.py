"""Feishu event callback verify + decrypt."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def verify_signature(
    *,
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
    verification_token: str,
    encrypt_key: str = "",
) -> bool:
    if not signature:
        return False
    if encrypt_key:
        raw = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + body
        digest = hashlib.sha256(raw).hexdigest()
        return digest == signature
    if not verification_token:
        return False
    raw = f"{timestamp}{nonce}{verification_token}".encode("utf-8") + body
    digest = hashlib.sha1(raw).hexdigest()
    return digest == signature


def decrypt_event(encrypt_key: str, cipher_text: str) -> dict[str, Any]:
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    raw = base64.b64decode(cipher_text)
    iv = raw[:16]
    encrypted = raw[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    plain = decryptor.update(encrypted) + decryptor.finalize()
    pad = plain[-1]
    if pad < 1 or pad > 16:
        pad = 0
    text = plain[:-pad].decode("utf-8") if pad else plain.decode("utf-8")
    return json.loads(text)


def parse_request_body(
    body: dict[str, Any],
    *,
    encrypt_key: str,
) -> dict[str, Any]:
    if "encrypt" in body and encrypt_key:
        return decrypt_event(encrypt_key, str(body["encrypt"]))
    return body
