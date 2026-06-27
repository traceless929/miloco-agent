#!/usr/bin/env bash
# miloco-agent 容器入口：与 Server 共享 MILOCO_HOME / config.json
set -euo pipefail

MILOCO_HOME="${MILOCO_HOME:-/data/miloco}"
export MILOCO_HOME
export MILOCO_AGENT_HOST="${MILOCO_AGENT_HOST:-0.0.0.0}"
export MILOCO_AGENT_PORT="${MILOCO_AGENT_PORT:-18789}"

# 等待 config.json（miloco 服务 entrypoint 创建）
for i in $(seq 1 60); do
  if [[ -f "${MILOCO_HOME}/config.json" ]]; then
    break
  fi
  sleep 1
done

echo "[entrypoint-agent] starting miloco-agent on ${MILOCO_AGENT_HOST}:${MILOCO_AGENT_PORT}"
exec "$@"
