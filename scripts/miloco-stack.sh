#!/usr/bin/env bash
# 一键安装 / 启动 / 停止 / 重启 / 状态 — Miloco Server + miloco-agent Sidecar
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

MILOCO_HOME="${MILOCO_HOME:-$AGENT_ROOT/docker/data}"
export MILOCO_HOME MILOCO_REPO MILOCO_AGENT_ROOT="${MILOCO_AGENT_ROOT:-$AGENT_ROOT}"

BACKEND_PID="$MILOCO_HOME/.miloco-stack.backend.pid"
AGENT_PID="$MILOCO_HOME/.miloco-stack.agent.pid"
LOG_DIR="$MILOCO_HOME/log"
BACKEND_LOG="$LOG_DIR/miloco-backend.stack.log"
AGENT_LOG="$LOG_DIR/miloco-agent.stack.log"

SERVER_PORT="${MILOCO_SERVER_PORT:-1810}"
AGENT_PORT="${MILOCO_AGENT_PORT:-18789}"

log() { printf '[miloco-stack] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<EOF
用法: MILOCO_HOME=<数据目录> bash miloco-agent/scripts/miloco-stack.sh <命令>

在 xiaomi-miloco 根目录也可: bash scripts/miloco-stack.sh <命令>（转发脚本）

命令:
  setup      首次部署：init-config + 安装 Sidecar venv + backend 依赖
  start      后台启动 Miloco Server (:${SERVER_PORT}) + Agent (:${AGENT_PORT})
  stop       停止 stack 启动的后端与 Agent
  restart    重启 Agent（加 --all 则重启 Server + Agent）
  status     进程、端口、HTTP 健康检查、配置摘要
  logs       查看最近日志（backend | agent | all）
  caffeinate start|stop|status   Mac 防睡眠（合盖持续跑）

环境变量:
  MILOCO_HOME       数据目录（默认 miloco-agent/docker/data）
  MILOCO_REPO       母仓 xiaomi-miloco 根（默认子仓上一级）
  MILOCO_AGENT_VENV Sidecar venv（默认 miloco-agent/.venv）

EOF
}

read_pid() {
  local f="$1"
  [[ -f "$f" ]] && cat "$f" || true
}

is_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_listen() {
  lsof -i ":$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true
}

http_code() {
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "http://127.0.0.1:$1/" 2>/dev/null) || true
  echo "${code:-000}"
}

health_ok() {
  curl -fsS --connect-timeout 2 "http://127.0.0.1:$1/health" >/dev/null 2>&1
}

cmd_setup() {
  log "MILOCO_REPO=$MILOCO_REPO"
  log "MILOCO_HOME=$MILOCO_HOME"
  bash "$AGENT_ROOT/scripts/init-config.sh"
  bash "$AGENT_ROOT/scripts/miloco-agent-install.sh"
  if ! command -v uv >/dev/null 2>&1; then
    die "需要 uv，请先安装: pip install uv"
  fi
  log "同步 backend 依赖（首次较慢）..."
  (cd "$MILOCO_REPO/backend" && uv sync --all-groups)
  log "setup 完成。请编辑 $MILOCO_HOME/config.json 填入 API Key 后执行: bash miloco-agent/scripts/miloco-stack.sh start"
}

start_backend() {
  if is_alive "$(read_pid "$BACKEND_PID")" || [[ -n "$(port_listen "$SERVER_PORT")" ]]; then
    log "Backend :$SERVER_PORT 已在运行，跳过"
    return 0
  fi
  mkdir -p "$LOG_DIR"
  if ! command -v uv >/dev/null 2>&1; then
    die "未找到 uv，请先 bash miloco-agent/scripts/miloco-stack.sh setup"
  fi
  log "启动 Miloco Backend :$SERVER_PORT -> $BACKEND_LOG"
  (
    cd "$MILOCO_REPO/backend"
    export MILOCO_HOME
    nohup uv run task dev >>"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID"
  )
  sleep 2
}

start_agent() {
  if is_alive "$(read_pid "$AGENT_PID")" || [[ -n "$(port_listen "$AGENT_PORT")" ]]; then
    log "Agent :$AGENT_PORT 已在运行，跳过"
    return 0
  fi
  local venv="${MILOCO_AGENT_VENV:-$AGENT_ROOT/.venv}"
  [[ -d "$venv" ]] || die "未找到 venv，请先: bash miloco-agent/scripts/miloco-stack.sh setup"
  mkdir -p "$LOG_DIR"
  log "启动 miloco-agent :$AGENT_PORT -> $AGENT_LOG"
  (
    # shellcheck source=/dev/null
    source "$venv/bin/activate"
    export MILOCO_HOME MILOCO_REPO MILOCO_AGENT_ROOT
    nohup miloco-agent >>"$AGENT_LOG" 2>&1 &
    echo $! >"$AGENT_PID"
  )
  sleep 1
}

cmd_start() {
  [[ -f "$MILOCO_HOME/config.json" ]] || die "缺少 config.json，请先: bash miloco-agent/scripts/miloco-stack.sh setup"
  python3 - <<PY
import json, os, sys
from pathlib import Path
p = Path(os.environ["MILOCO_HOME"]) / "config.json"
data = json.loads(p.read_text(encoding="utf-8"))
agent = data.setdefault("agent", {})
agent["webhook_url"] = "http://127.0.0.1:${AGENT_PORT}/miloco/webhook"
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
  start_backend
  local i=0
  while ! health_ok "$SERVER_PORT" && [[ $i -lt 90 ]]; do
    sleep 2
    i=$((i + 1))
  done
  if ! health_ok "$SERVER_PORT"; then
    log "WARN: Backend 健康检查未通过，仍尝试启动 Agent（见 $BACKEND_LOG）"
  fi
  start_agent
  cmd_status
}

stop_one() {
  local pid_file="$1" name="$2"
  local pid
  pid="$(read_pid "$pid_file")"
  if is_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    is_alive "$pid" && kill -9 "$pid" 2>/dev/null || true
    log "已停止 $name pid=$pid"
  fi
  rm -f "$pid_file"
}

cmd_stop() {
  stop_one "$AGENT_PID" "Agent"
  stop_one "$BACKEND_PID" "Backend"
  pkill -f "uv run task dev" 2>/dev/null || true
  pkill -f "miloco-agent" 2>/dev/null || true
  log "已停止"
}

cmd_restart() {
  if [[ "${1:-}" == "--all" ]]; then
    cmd_stop
    sleep 2
    cmd_start
  else
    stop_one "$AGENT_PID" "Agent"
    pkill -f "miloco-agent" 2>/dev/null || true
    sleep 1
    start_agent
    cmd_status
  fi
}

config_summary() {
  python3 - <<'PY' "$MILOCO_HOME/config.json" 2>/dev/null || echo "  (无法读取 config.json)"
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    print("  config.json 不存在")
    raise SystemExit(0)
d = json.loads(p.read_text(encoding="utf-8"))
omni = (d.get("model") or {}).get("omni") or {}
llm = (d.get("agent") or {}).get("llm") or {}
feishu = (d.get("agent") or {}).get("feishu") or {}

def mask(s):
    s = s or ""
    if len(s) <= 8:
        return "（未设置）" if not s else "***"
    return s[:4] + "****" + s[-4:]

print(f"  omni: {omni.get('model', '?')} @ {omni.get('base_url', '?')}")
print(f"  omni.api_key: {mask(omni.get('api_key'))}")
print(f"  agent.llm: {llm.get('model', '?')} @ {llm.get('base_url', '?')}")
print(f"  agent.llm.api_key: {mask(llm.get('api_key'))}")
print(f"  feishu: {'开启' if feishu.get('enabled') else '关闭'}")
PY
}

cmd_status() {
  local bp ap
  bp="$(read_pid "$BACKEND_PID")"
  ap="$(read_pid "$AGENT_PID")"
  log "MILOCO_HOME=$MILOCO_HOME"
  log "MILOCO_REPO=$MILOCO_REPO"
  echo "--- Backend :$SERVER_PORT ---"
  if is_alive "$bp"; then echo "  pid(file): $bp ✓"; else echo "  pid(file): -"; fi
  local pl
  pl="$(port_listen "$SERVER_PORT")"
  [[ -n "$pl" ]] && echo "  port LISTEN: pid=$pl ✓" || echo "  port LISTEN: ✗"
  if health_ok "$SERVER_PORT"; then echo "  /health: OK"; else echo "  /health: FAIL (HTTP $(http_code "$SERVER_PORT"))"; fi
  echo "  Web: http://127.0.0.1:$SERVER_PORT/"
  echo "--- Agent :$AGENT_PORT ---"
  if is_alive "$ap"; then echo "  pid(file): $ap ✓"; else echo "  pid(file): -"; fi
  pl="$(port_listen "$AGENT_PORT")"
  [[ -n "$pl" ]] && echo "  port LISTEN: pid=$pl ✓" || echo "  port LISTEN: ✗"
  if [[ "$(http_code "$AGENT_PORT")" == "200" ]]; then echo "  /admin: OK"; else echo "  /admin: FAIL"; fi
  echo "  管理台: http://127.0.0.1:$AGENT_PORT/admin"
  echo "--- 配置 ---"
  config_summary
}

cmd_logs() {
  local target="${1:-all}"
  case "$target" in
    backend) tail -n 40 -f "$BACKEND_LOG" ;;
    agent) tail -n 40 -f "$AGENT_LOG" ;;
    all|*)
      echo "=== backend ($BACKEND_LOG) ==="
      tail -n 20 "$BACKEND_LOG" 2>/dev/null || echo "(无日志)"
      echo "=== agent ($AGENT_LOG) ==="
      tail -n 20 "$AGENT_LOG" 2>/dev/null || echo "(无日志)"
      ;;
  esac
}

cmd_caffeinate() {
  bash "$AGENT_ROOT/scripts/miloco-caffeinate.sh" "${1:-status}"
}

case "${1:-}" in
  setup|install) cmd_setup ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart "${2:-}" ;;
  status) cmd_status ;;
  logs) cmd_logs "${2:-all}" ;;
  caffeinate) cmd_caffeinate "${2:-status}" ;;
  -h|--help|help) usage ;;
  *)
    usage
    exit 1
    ;;
esac
