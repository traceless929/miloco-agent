"""Read Miloco shared config without importing backend/miloco."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_MILOCO_HOME = Path.home() / ".openclaw" / "miloco"


def miloco_home() -> Path:
    if env := os.environ.get("MILOCO_HOME"):
        return Path(env).expanduser()
    return _DEFAULT_MILOCO_HOME


def config_file() -> Path:
    return miloco_home() / "config.json"


@dataclass
class AgentEndpointSettings:
    webhook_url: str = "http://127.0.0.1:18789/miloco/webhook"
    auth_bearer: str = ""


@dataclass
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 1810
    token: str = ""
    url: str = ""


@dataclass
class SidecarSettings:
    """Sidecar listen + Miloco API access."""

    host: str = "127.0.0.1"
    port: int = 18789
    log_level: str = "info"


@dataclass
class FeishuSettings:
    """Feishu bot / event subscription."""

    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""
    default_receive_open_id: str = ""
    enabled: bool = False
    # long_connection: 出站 WebSocket（推荐，无需公网 IP）
    # webhook: HTTP 公网回调（需 ngrok/域名）
    mode: str = "long_connection"
    # markdown: 交互卡片渲染 MD；text: 纯文本
    reply_format: str = "markdown"
    # 流式打字机效果（需 CardKit 权限 cardkit:card:write）
    stream_reply: bool = True
    stream_interval_s: float = 0.5
    history_turns: int = 10
    history_ttl_hours: float = 24.0

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    @property
    def use_long_connection(self) -> bool:
        return self.mode in ("long_connection", "ws", "websocket")


@dataclass
class CronSettings:
    """In-process home-profile cron (APScheduler)."""

    enabled: bool = False
    timezone: str = "Asia/Shanghai"


@dataclass
class LlmSettings:
    """OpenAI-compatible chat model for agent turns."""

    base_url: str = "https://api.xiaomimimo.com/v1"
    model: str = "xiaomi/mimo-v2.5"
    api_key: str = ""
    label: str = ""
    user_agent: str = ""


@dataclass
class AgentRuntimeSettings:
    """AgentScope ReAct loop limits."""

    react_max_iters: int = 32
    cron_react_max_iters: int = 48


@dataclass
class MilocoAgentSettings:
    agent: AgentEndpointSettings = field(default_factory=AgentEndpointSettings)
    runtime: AgentRuntimeSettings = field(default_factory=AgentRuntimeSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    sidecar: SidecarSettings = field(default_factory=SidecarSettings)
    llm: LlmSettings = field(default_factory=LlmSettings)
    feishu: FeishuSettings = field(default_factory=FeishuSettings)
    cron: CronSettings = field(default_factory=CronSettings)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def miloco_api_base(self) -> str:
        if self.server.url:
            return self.server.url.rstrip("/")
        host = self.server.host
        if host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        return f"http://{host}:{self.server.port}"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm.api_key and self.llm.base_url and self.llm.model)

    @property
    def miloco_api_headers(self) -> dict[str, str]:
        if self.server.token:
            return {"Authorization": f"Bearer {self.server.token}"}
        return {}


def _nested_get(data: dict[str, Any], key: str, default: Any) -> Any:
    val = data.get(key, default)
    return default if val is None else val


def load_settings(
    *,
    config_path: Path | None = None,
    sidecar_config_path: Path | None = None,
) -> MilocoAgentSettings:
    """Load shared config.json + optional sidecar YAML/JSON overlay."""
    path = config_path or config_file()
    raw: dict[str, Any] = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))

    agent_raw = raw.get("agent") or {}
    server_raw = raw.get("server") or {}
    model_raw = raw.get("model") or {}
    omni_raw = model_raw.get("omni") or {}
    profiles = model_raw.get("omni_profiles") or []
    agent_llm_raw = agent_raw.get("llm") or {}
    if agent_llm_raw.get("api_key"):
        llm_src = agent_llm_raw
    elif omni_raw.get("api_key"):
        llm_src = omni_raw
        key = str(omni_raw.get("api_key", ""))
        base = str(omni_raw.get("base_url", ""))
        if key.startswith("sk-kimi-") and "xiaomimimo" in base and profiles:
            llm_src = profiles[0]
    else:
        llm_src = profiles[0] if profiles else omni_raw

    feishu_raw = agent_raw.get("feishu") or raw.get("feishu") or {}
    cron_raw = agent_raw.get("cron") or raw.get("cron") or {}
    runtime_raw = agent_raw.get("runtime") or {}

    settings = MilocoAgentSettings(
        agent=AgentEndpointSettings(
            webhook_url=str(_nested_get(agent_raw, "webhook_url", AgentEndpointSettings.webhook_url)),
            auth_bearer=str(_nested_get(agent_raw, "auth_bearer", "")),
        ),
        server=ServerSettings(
            host=str(_nested_get(server_raw, "host", "127.0.0.1")),
            port=int(_nested_get(server_raw, "port", 1810)),
            token=str(_nested_get(server_raw, "token", "")),
            url=str(_nested_get(server_raw, "url", "")).rstrip("/"),
        ),
        llm=LlmSettings(
            base_url=str(_nested_get(llm_src, "base_url", LlmSettings.base_url)).rstrip("/"),
            model=str(_nested_get(llm_src, "model", LlmSettings.model)),
            api_key=str(_nested_get(llm_src, "api_key", "")),
            label=str(_nested_get(llm_src, "label", "")),
            user_agent=str(_nested_get(llm_src, "user_agent", "")),
        ),
        feishu=FeishuSettings(
            app_id=str(_nested_get(feishu_raw, "app_id", "")),
            app_secret=str(_nested_get(feishu_raw, "app_secret", "")),
            verification_token=str(_nested_get(feishu_raw, "verification_token", "")),
            encrypt_key=str(_nested_get(feishu_raw, "encrypt_key", "")),
            default_receive_open_id=str(
                _nested_get(feishu_raw, "default_receive_open_id", "")
            ),
            enabled=bool(_nested_get(feishu_raw, "enabled", False)),
            mode=str(_nested_get(feishu_raw, "mode", "long_connection")),
            reply_format=str(_nested_get(feishu_raw, "reply_format", "markdown")),
            stream_reply=bool(_nested_get(feishu_raw, "stream_reply", True)),
            stream_interval_s=float(_nested_get(feishu_raw, "stream_interval_s", 0.5)),
            history_turns=int(_nested_get(feishu_raw, "history_turns", 10)),
            history_ttl_hours=float(_nested_get(feishu_raw, "history_ttl_hours", 24.0)),
        ),
        cron=CronSettings(
            enabled=bool(_nested_get(cron_raw, "enabled", False)),
            timezone=str(_nested_get(cron_raw, "timezone", "Asia/Shanghai")),
        ),
        runtime=AgentRuntimeSettings(
            react_max_iters=int(_nested_get(runtime_raw, "react_max_iters", 32)),
            cron_react_max_iters=int(
                _nested_get(runtime_raw, "cron_react_max_iters", 48)
            ),
        ),
        raw=raw,
    )

    overlay = sidecar_config_path or _sidecar_config_path()
    if overlay and overlay.is_file():
        overlay_data = json.loads(overlay.read_text(encoding="utf-8"))
        sc = overlay_data.get("sidecar") or overlay_data
        if "host" in sc:
            settings.sidecar.host = str(sc["host"])
        if "port" in sc:
            settings.sidecar.port = int(sc["port"])
        if "log_level" in sc:
            settings.sidecar.log_level = str(sc["log_level"])

    env_host = os.environ.get("MILOCO_AGENT_HOST")
    env_port = os.environ.get("MILOCO_AGENT_PORT")
    if env_host:
        settings.sidecar.host = env_host
    if env_port:
        settings.sidecar.port = int(env_port)

    return settings


def _sidecar_config_path() -> Path | None:
    env = os.environ.get("MILOCO_AGENT_CONFIG")
    if env:
        return Path(env).expanduser()
    candidate = miloco_home() / "miloco-agent.json"
    return candidate if candidate.is_file() else None
