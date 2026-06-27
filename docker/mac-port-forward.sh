#!/usr/bin/env bash
# macOS Podman：把虚拟机内 host 网络的 1810/18789 转发到 Mac 本机 loopback
# 用法: bash docker/mac-port-forward.sh
# 前台运行，Ctrl+C 停止；另开终端访问 http://127.0.0.1:1810
set -euo pipefail

SERVER_PORT="${MILOCO_SERVER_PORT:-1810}"
AGENT_PORT="${MILOCO_AGENT_PORT:-18789}"

if ! command -v podman >/dev/null 2>&1; then
  echo "需要 podman CLI" >&2
  exit 1
fi

MACHINE="${PODMAN_MACHINE:-podman-machine-default}"
SSH_PORT="$(podman machine inspect "$MACHINE" --format '{{.SSHConfig.Port}}')"
SSH_USER="$(podman machine inspect "$MACHINE" --format '{{.SSHConfig.RemoteUsername}}')"
SSH_KEY="$(podman machine inspect "$MACHINE" --format '{{.SSHConfig.IdentityPath}}')"

if [[ -z "$SSH_PORT" || -z "$SSH_KEY" ]]; then
  echo "无法读取 podman machine SSH 配置，请先 podman machine start" >&2
  exit 1
fi

echo "[mac-port-forward] ${SERVER_PORT}, ${AGENT_PORT} -> ${MACHINE} (127.0.0.1:${SSH_PORT})"
echo "[mac-port-forward] 浏览器: http://127.0.0.1:${SERVER_PORT}/"
echo "[mac-port-forward] 按 Ctrl+C 停止"

exec ssh -N \
  -i "$SSH_KEY" \
  -p "$SSH_PORT" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -L "127.0.0.1:${SERVER_PORT}:127.0.0.1:${SERVER_PORT}" \
  -L "127.0.0.1:${AGENT_PORT}:127.0.0.1:${AGENT_PORT}" \
  "${SSH_USER}@127.0.0.1"
