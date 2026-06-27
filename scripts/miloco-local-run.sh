#!/usr/bin/env bash
# Fork 专属：Mac / Linux 本机跑 Miloco（摄像头 LAN 感知需本机网络，勿用 Podman bridge）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

MILOCO_HOME="${MILOCO_HOME:-$AGENT_ROOT/docker/data}"
export MILOCO_HOME MILOCO_REPO

log() { printf '[miloco-local] %s\n' "$*"; }

if [[ ! -f "$MILOCO_HOME/config.json" ]]; then
  log "未找到 $MILOCO_HOME/config.json"
  log "可先复用 docker 数据: MILOCO_HOME=$AGENT_ROOT/docker/data"
  log "或运行: bash $MILOCO_REPO/scripts/install.sh --dev"
  exit 1
fi

MODELS_DIR="$MILOCO_HOME/models"
SRC_MODELS="$MILOCO_REPO/backend/miloco/src/miloco/perception/models"
mkdir -p "$MODELS_DIR"
if [[ ! -f "$MODELS_DIR/det_4C.onnx" && -f "$SRC_MODELS/det_4C.onnx" ]]; then
  log "同步 ONNX 模型 -> $MODELS_DIR"
  cp -n "$SRC_MODELS"/*.onnx "$SRC_MODELS"/*.json "$MODELS_DIR/" 2>/dev/null || true
fi

python3 - <<PY
import json, os
from pathlib import Path
p = Path(os.environ["MILOCO_HOME"]) / "config.json"
data = json.loads(p.read_text(encoding="utf-8"))
agent = data.setdefault("agent", {})
agent["webhook_url"] = "http://127.0.0.1:18789/miloco/webhook"
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"[miloco-local] webhook -> {agent['webhook_url']}")
PY

if ! command -v uv >/dev/null 2>&1; then
  log "需要 uv，可先: pip install uv -i https://mirrors.aliyun.com/pypi/simple/"
  exit 1
fi

log "MILOCO_HOME=$MILOCO_HOME"
log "MILOCO_REPO=$MILOCO_REPO"
log "安装/同步 backend 依赖（首次较慢）..."
(cd "$MILOCO_REPO/backend" && uv sync --all-groups)

log "启动 miloco-backend :1810 （Ctrl+C 停止）"
log "另开终端启动 agent: MILOCO_HOME=$MILOCO_HOME bash miloco-agent/scripts/miloco-agent-run.sh"
cd "$MILOCO_REPO/backend"
exec uv run task dev
