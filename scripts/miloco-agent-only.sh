#!/usr/bin/env bash
# 仅启动 miloco-agent Sidecar（对接外部 Miloco Server，不启动母仓 backend）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

MILOCO_HOME="${MILOCO_HOME:-$HOME/.miloco-agent-sidecar}"
export MILOCO_HOME MILOCO_REPO MILOCO_AGENT_ROOT="${MILOCO_AGENT_ROOT:-$AGENT_ROOT}"

AGENT_PID="$MILOCO_HOME/.miloco-agent-only.pid"
LOG_DIR="$MILOCO_HOME/log"
AGENT_LOG="$LOG_DIR/miloco-agent.log"
AGENT_PORT="${MILOCO_AGENT_PORT:-18789}"

log() { printf '[miloco-agent-only] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<EOF
用法: bash miloco-agent/scripts/miloco-agent-only.sh <命令>

仅运行 Sidecar，对接已在别处运行的 Miloco Server。
须先: bash miloco-agent/scripts/setup-external-miloco.sh

命令:
  start      后台启动 Agent
  stop       停止 Agent
  restart    重启 Agent
  status     进程、端口、对外部 Server 的连通性
  logs       跟踪日志

环境变量:
  MILOCO_HOME           Sidecar 数据目录（默认 ~/.miloco-agent-sidecar）
  MILOCO_AGENT_VENV     venv 路径（默认 miloco-agent/.venv）
  MILOCO_AGENT_HOST     监听地址（跨机对接建议 0.0.0.0，见 setup-external）
  MILOCO_AGENT_PORT     端口（默认 18789）
  MILOCO_SKILLS_DIR     Skill 目录（无母仓时）

EOF
}

read_pid() { [[ -f "$1" ]] && cat "$1" || true; }
is_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

probe_external_server() {
  python3 - <<'PY' "$MILOCO_HOME/config.json" 2>/dev/null
import json, sys, urllib.request
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    print("  config.json: 缺失")
    raise SystemExit(0)
d = json.loads(p.read_text())
s = d.get("server") or {}
if s.get("url"):
    base = str(s["url"]).rstrip("/")
else:
    host = s.get("host") or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    base = f"http://{host}:{s.get('port', 1810)}"
token = s.get("token") or ""
req = urllib.request.Request(f"{base}/health", headers={"Authorization": f"Bearer {token}"} if token else {})
try:
    with urllib.request.urlopen(req, timeout=3) as r:
        print(f"  外部 Server {base}/health: OK ({r.status})")
except Exception as e:
    print(f"  外部 Server {base}/health: FAIL ({e})")
PY
}

cmd_start() {
  [[ -f "$MILOCO_HOME/config.json" ]] || die "缺少 $MILOCO_HOME/config.json，请先 setup-external-miloco.sh"
  local venv="${MILOCO_AGENT_VENV:-$AGENT_ROOT/.venv}"
  [[ -d "$venv" ]] || die "缺少 venv，请先 setup-external-miloco.sh"
  local pid
  pid="$(read_pid "$AGENT_PID")"
  if is_alive "$pid"; then
    log "已在运行 pid=$pid"
    exit 0
  fi
  mkdir -p "$LOG_DIR"
  export MILOCO_AGENT_CONFIG="${MILOCO_AGENT_CONFIG:-$MILOCO_HOME/miloco-agent.json}"
  (
    # shellcheck source=/dev/null
    source "$venv/bin/activate"
    export MILOCO_HOME MILOCO_REPO MILOCO_AGENT_ROOT
    nohup miloco-agent >>"$AGENT_LOG" 2>&1 &
    echo $! >"$AGENT_PID"
  )
  sleep 1
  log "已启动 pid=$(read_pid "$AGENT_PID") · 日志 $AGENT_LOG"
  cmd_status
}

cmd_stop() {
  local pid
  pid="$(read_pid "$AGENT_PID")"
  if is_alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    is_alive "$pid" && kill -9 "$pid" 2>/dev/null || true
    log "已停止 pid=$pid"
  fi
  rm -f "$AGENT_PID"
  pkill -f "miloco-agent" 2>/dev/null || true
}

cmd_restart() { cmd_stop; sleep 1; cmd_start; }

cmd_status() {
  log "MILOCO_HOME=$MILOCO_HOME"
  local pid pl code
  pid="$(read_pid "$AGENT_PID")"
  echo "--- Sidecar :$AGENT_PORT ---"
  is_alive "$pid" && echo "  pid: $pid ✓" || echo "  pid: -"
  pl="$(lsof -i ":$AGENT_PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  [[ -n "$pl" ]] && echo "  LISTEN: pid=$pl ✓" || echo "  LISTEN: ✗"
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "http://127.0.0.1:$AGENT_PORT/admin" 2>/dev/null || echo "000")
  [[ "$code" == "200" ]] && echo "  /admin: OK" || echo "  /admin: FAIL"
  echo "--- 外部 Miloco Server ---"
  probe_external_server
  python3 - <<PY "$MILOCO_HOME/config.json" 2>/dev/null || true
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file(): raise SystemExit(0)
d = json.loads(p.read_text())
a = d.get("agent") or {}
print(f"  webhook_url（Server 应配置）: {a.get('webhook_url', '?')}")
print(f"  auth_bearer: {'已设置' if a.get('auth_bearer') else '缺失'}")
llm = a.get("llm") or {}
print(f"  agent.llm.api_key: {'已填写' if llm.get('api_key') else '⚠ 待填写'}")
PY
}

cmd_logs() { tail -n 40 -f "$AGENT_LOG"; }

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  logs) cmd_logs ;;
  -h|--help|help) usage ;;
  *) usage; exit 1 ;;
esac
