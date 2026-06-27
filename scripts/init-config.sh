#!/usr/bin/env bash
# 初始化 $MILOCO_HOME/config.json（不存在时创建模板并生成 token）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

MILOCO_HOME="${MILOCO_HOME:-$AGENT_ROOT/docker/data}"
CONFIG="$MILOCO_HOME/config.json"

log() { printf '[init-config] %s\n' "$*"; }

mkdir -p "$MILOCO_HOME/models" "$MILOCO_HOME/log"

if [[ -f "$CONFIG" ]]; then
  log "已存在 $CONFIG，跳过创建（仅补全缺失的 agent.webhook / auth_bearer）"
fi

python3 - <<'PY' "$CONFIG" "$MILOCO_HOME"
import json, secrets, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
home = Path(sys.argv[2])

default = {
    "server": {
        "host": "0.0.0.0",
        "port": 1810,
        "token": secrets.token_urlsafe(16),
    },
    "agent": {
        "webhook_url": "http://127.0.0.1:18789/miloco/webhook",
        "auth_bearer": secrets.token_urlsafe(32),
        "llm": {
            "base_url": "https://api.kimi.com/coding/v1",
            "model": "kimi-for-coding",
            "api_key": "",
            "label": "Sidecar Agent LLM（飞书/Cron 对话）",
        },
        "feishu": {
            "enabled": False,
            "mode": "long_connection",
            "app_id": "",
            "app_secret": "",
            "history_turns": 10,
            "reply_format": "markdown",
            "stream_reply": True,
            "default_receive_open_id": "",
        },
        "cron": {"enabled": True, "timezone": "Asia/Shanghai"},
    },
    "model": {
        "omni": {
            "label": "MiMo Omni（摄像头感知，必填）",
            "base_url": "https://api.xiaomimimo.com/v1",
            "model": "xiaomi/mimo-v2.5",
            "api_key": "",
        },
        "omni_profiles": [],
    },
}

if cfg_path.is_file():
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
else:
    data = default
    cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[init-config] 已创建 {cfg_path}")

agent = data.setdefault("agent", {})
if not agent.get("auth_bearer"):
    agent["auth_bearer"] = secrets.token_urlsafe(32)
agent["webhook_url"] = agent.get("webhook_url") or "http://127.0.0.1:18789/miloco/webhook"
cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

omni_key = (data.get("model") or {}).get("omni", {}).get("api_key") or ""
llm_key = agent.get("llm", {}).get("api_key") or ""
print(f"[init-config] MILOCO_HOME={home}")
print(f"[init-config] config={cfg_path}")
print(f"[init-config] server.token={'已设置' if data.get('server', {}).get('token') else '缺失'}")
print(f"[init-config] agent.auth_bearer={'已设置' if agent.get('auth_bearer') else '缺失'}")
print(f"[init-config] model.omni.api_key={'已填写' if omni_key else '⚠ 待填写（感知必需）'}")
print(f"[init-config] agent.llm.api_key={'已填写' if llm_key else '⚠ 待填写（Agent 对话必需）'}")
PY

SRC_MODELS="$MILOCO_REPO/backend/miloco/src/miloco/perception/models"
DEST="$MILOCO_HOME/models"
if [[ ! -f "$DEST/det_4C.onnx" && -f "$SRC_MODELS/det_4C.onnx" ]]; then
  log "同步 ONNX 模型 -> $DEST"
  cp -n "$SRC_MODELS"/*.onnx "$SRC_MODELS"/*.json "$DEST/" 2>/dev/null || true
fi

log "下一步：编辑 $CONFIG 填入 model.omni 与 agent.llm 的 api_key"
log "管理台: http://127.0.0.1:18789/admin  ·  Web 面板: http://127.0.0.1:1810/"
