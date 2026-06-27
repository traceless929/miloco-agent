#!/usr/bin/env bash
# Fork 专属：Mac 临时防睡眠，便于本机 Miloco :1810 / :18789 在插电时合盖后继续跑
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

MILOCO_HOME="${MILOCO_HOME:-$AGENT_ROOT/docker/data}"
PID_FILE="${MILOCO_HOME}/.miloco-caffeinate.pid"

log() { printf '[miloco-caffeinate] %s\n' "$*"; }

usage() {
  cat <<EOF
用法: MILOCO_HOME=<数据目录> bash miloco-agent/scripts/miloco-caffeinate.sh <命令>

命令:
  start    后台开启防睡眠（caffeinate -dims，仅插电时 -s 生效）
  stop     关闭本脚本启动的防睡眠
  status   查看是否在运行
  restart  先 stop 再 start

EOF
}

caffeinate_bin() {
  if ! command -v caffeinate >/dev/null 2>&1; then
    log "未找到 caffeinate（仅 macOS 可用）"
    exit 1
  fi
  command -v caffeinate
}

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    cat "$PID_FILE"
  fi
}

is_our_caffeinate() {
  local pid="${1:-}"
  local comm
  [[ -n "$pid" ]] || return 1
  comm="$(ps -p "$pid" -o comm= 2>/dev/null | xargs basename 2>/dev/null || true)"
  [[ "$comm" == "caffeinate" ]]
}

is_running() {
  local pid
  pid="$(read_pid || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && is_our_caffeinate "$pid"; then
    return 0
  fi
  return 1
}

cmd_start() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    log "防睡眠脚本仅适用于 macOS"
    exit 1
  fi
  if is_running; then
    log "已在运行 (pid=$(read_pid))"
    exit 0
  fi
  mkdir -p "$MILOCO_HOME"
  rm -f "$PID_FILE"
  local bin
  bin="$(caffeinate_bin)"
  "$bin" -dims </dev/null >/dev/null 2>&1 &
  local child=$!
  echo "$child" >"$PID_FILE"
  sleep 0.2
  if ! is_running; then
    log "启动失败"
    rm -f "$PID_FILE"
    exit 1
  fi
  log "已开启防睡眠 pid=$child"
}

cmd_stop() {
  local pid
  pid="$(read_pid || true)"
  if [[ -z "$pid" ]]; then
    log "未运行（无 pid 文件）"
    exit 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 0.2
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    log "已关闭防睡眠 pid=$pid"
  else
    log "进程已不存在 pid=$pid"
  fi
  rm -f "$PID_FILE"
}

cmd_status() {
  if is_running; then
    log "运行中 pid=$(read_pid) · pid 文件 $PID_FILE"
    pmset -g assertions 2>/dev/null | grep -i "caffeinate" | head -3 || true
    exit 0
  fi
  log "未运行"
  [[ -f "$PID_FILE" ]] && rm -f "$PID_FILE"
  exit 1
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  restart) cmd_stop; cmd_start ;;
  -h|--help|help) usage ;;
  *)
    usage
    exit 1
    ;;
esac
