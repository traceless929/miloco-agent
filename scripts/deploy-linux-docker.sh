#!/usr/bin/env bash
# 在 Linux 主机（与摄像头同网）一键部署 Miloco Docker（host 网络）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

DATA_DIR="${MILOCO_DATA_DIR:-$AGENT_ROOT/docker/data}"
ENV_FILE="$AGENT_ROOT/docker/.env"
COMPOSE_FILE="$AGENT_ROOT/docker/docker-compose.yml"

log() { printf '[deploy] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

command -v docker >/dev/null 2>&1 || die "需要 docker 或 podman（带 docker compose）"

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif docker-compose version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "未找到 docker compose"
fi

mkdir -p "$DATA_DIR/models"
if [[ ! -f "$DATA_DIR/models/det_4C.onnx" ]]; then
  SRC="$MILOCO_REPO/backend/miloco/src/miloco/perception/models"
  if [[ -f "$SRC/det_4C.onnx" ]]; then
    log "复制 ONNX 模型到 $DATA_DIR/models"
    cp -n "$SRC"/*.onnx "$SRC"/*.json "$DATA_DIR/models/" 2>/dev/null || true
  else
    log "WARN: 未找到本地模型，请稍后放入 $DATA_DIR/models/"
  fi
fi

[[ -f "$ENV_FILE" ]] || cp "$AGENT_ROOT/docker/env.example" "$ENV_FILE"

export MILOCO_REPO
log "MILOCO_REPO=$MILOCO_REPO"
log "构建镜像（首次约 15～30 分钟）..."
$COMPOSE -f "$COMPOSE_FILE" build

log "启动服务（host 网络，:1810 / :18789）..."
$COMPOSE -f "$COMPOSE_FILE" up -d

sleep 5
curl -fsS "http://127.0.0.1:${MILOCO_SERVER_PORT:-1810}/health" && echo
curl -fsS "http://127.0.0.1:${MILOCO_AGENT_PORT:-18789}/health" && echo

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
log "完成。面板: http://${LAN_IP:-<本机IP>}:1810/"
log "数据目录: $DATA_DIR"
