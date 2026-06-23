"""Feishu open_id bindings (Sidecar local store)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from miloco_agent.config import miloco_home

_BIND_FILE = "agent/feishu_bindings.json"


class FeishuBindings:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (miloco_home() / _BIND_FILE)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, str]) -> None:
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def is_allowed(self, open_id: str, *, default_open_id: str = "") -> bool:
        with self._lock:
            data = self._load()
        if open_id in data.values() or open_id in data:
            return True
        if not data and default_open_id and open_id == default_open_id:
            return True
        if not data and not default_open_id:
            return True
        return False

    def bind(self, open_id: str, label: str = "default") -> None:
        with self._lock:
            data = self._load()
            data[label] = open_id
            self._save(data)

    def list_open_ids(self) -> list[str]:
        with self._lock:
            data = self._load()
        return list(dict.fromkeys(data.values()))
