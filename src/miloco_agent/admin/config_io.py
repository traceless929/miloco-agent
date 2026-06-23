"""Read/write $MILOCO_HOME/config.json agent section."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from miloco_agent.config import config_file, load_settings

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "app_secret",
        "auth_bearer",
        "token",
        "encrypt_key",
        "verification_token",
    }
)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{'*' * 8}{value[-4:]}"


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _SECRET_KEYS and isinstance(v, str):
                out[k] = _mask_secret(v)
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def read_raw_config() -> dict[str, Any]:
    path = config_file()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def agent_view() -> dict[str, Any]:
    raw = read_raw_config()
    agent = raw.get("agent") or {}
    return redact(deepcopy(agent))


def write_agent_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge patch into config.json `agent` key; preserve secrets when masked."""
    path = config_file()
    raw = read_raw_config()
    agent = deepcopy(raw.get("agent") or {})
    current_settings = load_settings(config_path=path if path.is_file() else None)

    for section, values in patch.items():
        if not isinstance(values, dict):
            continue
        target = agent.setdefault(section, {})
        if not isinstance(target, dict):
            target = {}
            agent[section] = target
        for key, val in values.items():
            if isinstance(val, str) and val.startswith("********"):
                continue
            target[key] = val

    raw["agent"] = agent
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return redact(agent)
