#!/usr/bin/env bash
# Miloco Server 容器入口：初始化 config.json 后启动 backend
set -euo pipefail

MILOCO_HOME="${MILOCO_HOME:-/data/miloco}"
CONFIG="${MILOCO_HOME}/config.json"
MODELS_DIR="${MILOCO_HOME}/models"
DEFAULT_MODELS="/opt/miloco/default-models"
mkdir -p "${MILOCO_HOME}/log" "${MILOCO_HOME}/storage" "${MODELS_DIR}"

# 必需模型：det_4C.onnx + human_body_reid_v2.onnx（见 resource_validator.py）
seed_models() {
  local required=(det_4C.onnx human_body_reid_v2.onnx)
  local missing=0 f
  for f in "${required[@]}"; do
    [[ -f "${MODELS_DIR}/${f}" ]] || missing=1
  done
  [[ "$missing" -eq 0 ]] && return 0
  if [[ ! -d "${DEFAULT_MODELS}" ]] || [[ ! -f "${DEFAULT_MODELS}/det_4C.onnx" ]]; then
    echo "[entrypoint] WARN: 默认模型目录不可用，感知引擎将处于 models_missing" >&2
    return 0
  fi
  echo "[entrypoint] seed models -> ${MODELS_DIR}"
  cp -n "${DEFAULT_MODELS}/"* "${MODELS_DIR}/" 2>/dev/null || true
}
seed_models

python3 - <<'PY'
import json
import os
import secrets
from pathlib import Path

home = Path(os.environ["MILOCO_HOME"])
cfg_path = home / "config.json"
data: dict = {}
if cfg_path.is_file():
    data = json.loads(cfg_path.read_text(encoding="utf-8"))

server = data.setdefault("server", {})
server["host"] = os.environ.get("MILOCO_SERVER_HOST", "0.0.0.0")
server["port"] = int(os.environ.get("MILOCO_SERVER_PORT", "1810"))

agent = data.setdefault("agent", {})
webhook = os.environ.get(
    "MILOCO_AGENT_WEBHOOK_URL",
    "http://127.0.0.1:18789/miloco/webhook",
)
if webhook:
    agent["webhook_url"] = webhook
if not agent.get("auth_bearer"):
    agent["auth_bearer"] = secrets.token_urlsafe(32)

model = data.setdefault("model", {})
omni = model.setdefault("omni", {})
if key := os.environ.get("MILOCO_OMNI_API_KEY"):
    omni["api_key"] = key
if base := os.environ.get("MILOCO_OMNI_BASE_URL"):
    omni["base_url"] = base
if name := os.environ.get("MILOCO_OMNI_MODEL"):
    omni["model"] = name

cfg_path.write_text(
    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(f"[entrypoint] config written: {cfg_path}")
PY

echo "[entrypoint] starting: $*"
exec "$@"
