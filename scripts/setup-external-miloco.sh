#!/usr/bin/env bash
# 独立部署 Sidecar，对接**外部** Miloco Server（不使用母仓 backend）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

log() { printf '[setup-external] %s\n' "$*"; }
warn() { printf '[setup-external] WARN: %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
用法: bash miloco-agent/scripts/setup-external-miloco.sh [选项]

引导配置 Sidecar 对接**已运行**的外部 Miloco Server（Docker / 远程主机 / 官方安装均可）。
不依赖母仓 xiaomi-miloco 的 backend/，仅需本子仓 miloco-agent。

非交互（推荐脚本/CI）环境变量:
  MILOCO_HOME              Sidecar 本地数据目录（默认 ~/.miloco-agent-sidecar）
  MILOCO_SERVER_URL        外部 Miloco 根 URL，如 http://192.168.1.10:1810
  MILOCO_SERVER_TOKEN      外部 config.json 的 server.token（调用 REST API）
  AGENT_WEBHOOK_URL        外部 Server 应回调的地址（默认按本机 IP 推断）
  MILOCO_AGENT_HOST        Sidecar 监听地址（跨机对接时用 0.0.0.0）
  MILOCO_AGENT_PORT        Sidecar 端口（默认 18789）
  AGENT_AUTH_BEARER        与外部 Server agent.auth_bearer 一致（空则自动生成）
  MILOCO_SKILLS_DIR        Skill 文档目录（无母仓时必填或从 shallow clone 指定）
                           外部 Miloco 升级后须手动 git 同步 plugins/skills 并 restart Sidecar
  MILOCO_SKIP_CLI          1=不安装 miloco-cli（无 Bash 设备命令，Skill 仍可用）
  NONINTERACTIVE           1=不提问，缺变量则失败

交互模式: 直接运行，按提示输入。

完成后:
  bash miloco-agent/scripts/miloco-agent-only.sh start
  bash miloco-agent/scripts/miloco-agent-only.sh status

EOF
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"
}

detect_lan_ip() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true
  else
    hostname -I 2>/dev/null | awk '{print $1}' || true
  fi
}

parse_server_url() {
  python3 - <<'PY' "$1"
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1].strip())
if u.scheme not in ("http", "https"):
    raise SystemExit("URL 须以 http:// 或 https:// 开头")
host = u.hostname or ""
port = u.port or (443 if u.scheme == "https" else 80)
print(host)
print(port)
print(f"{u.scheme}://{host}:{port}")
PY
}

probe_server() {
  local base="$1" token="$2"
  local code
  if [[ -n "$token" ]]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" "$base/health" 2>/dev/null || true)
  else
    code=$(curl -s -o /dev/null -w '%{http_code}' "$base/health" 2>/dev/null || true)
  fi
  [[ "$code" == "200" ]]
}

prompt() {
  local var="$1" text="$2" default="${3:-}"
  if [[ "${NONINTERACTIVE:-0}" == "1" ]]; then
    return 0
  fi
  if [[ -n "$default" ]]; then
    read -r -p "$text [$default]: " input || true
    printf -v "$var" '%s' "${input:-$default}"
  else
    read -r -p "$text: " input || true
    printf -v "$var" '%s' "$input"
  fi
}

MILOCO_HOME="${MILOCO_HOME:-$HOME/.miloco-agent-sidecar}"
MILOCO_AGENT_HOST="${MILOCO_AGENT_HOST:-0.0.0.0}"
MILOCO_AGENT_PORT="${MILOCO_AGENT_PORT:-18789}"

main() {
  [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage && exit 0

  need_cmd python3
  need_cmd curl

  log "=== 环境检查 ==="
  log "AGENT_ROOT=$AGENT_ROOT"
  if [[ ! -f "$AGENT_ROOT/pyproject.toml" ]]; then
    die "请在 miloco-agent 子仓内运行，或设置 MILOCO_AGENT_ROOT"
  fi

  local py_ok=0
  for v in python3.12 python3.11; do
    if command -v "$v" >/dev/null 2>&1; then py_ok=1; break; fi
  done
  [[ "$py_ok" == "1" ]] || die "需要 Python >= 3.11"

  if [[ -z "${MILOCO_SERVER_URL:-}" ]]; then
    prompt MILOCO_SERVER_URL "外部 Miloco Server URL (含端口)" "http://127.0.0.1:1810"
  fi
  [[ -n "${MILOCO_SERVER_URL:-}" ]] || die "MILOCO_SERVER_URL 必填"

  local srv_host srv_port srv_base _parse
  _parse="$(parse_server_url "$MILOCO_SERVER_URL")"
  srv_host="$(echo "$_parse" | sed -n '1p')"
  srv_port="$(echo "$_parse" | sed -n '2p')"
  srv_base="$(echo "$_parse" | sed -n '3p')"

  if [[ -z "${MILOCO_SERVER_TOKEN:-}" ]]; then
    prompt MILOCO_SERVER_TOKEN "外部 server.token（REST API Bearer，可在外部 MILOCO_HOME/config.json 查看）" ""
  fi
  [[ -n "${MILOCO_SERVER_TOKEN:-}" ]] || die "MILOCO_SERVER_TOKEN 必填（外部 Server API 鉴权）"

  log "探测外部 Miloco: $srv_base/health ..."
  if probe_server "$srv_base" "$MILOCO_SERVER_TOKEN"; then
    log "外部 Server 可达 ✓"
  else
    warn "无法访问 $srv_base/health — 请确认 Server 已启动、URL/Token 正确、网络/firewall"
    [[ "${NONINTERACTIVE:-0}" == "1" ]] && die "外部 Server 探测失败"
    read -r -p "仍继续写入 Sidecar 配置? [y/N]: " cont || true
    [[ "${cont:-}" =~ ^[Yy]$ ]] || exit 1
  fi

  local lan_ip
  lan_ip="$(detect_lan_ip)"
  local default_webhook
  if [[ "$MILOCO_AGENT_HOST" == "0.0.0.0" && -n "$lan_ip" ]]; then
    default_webhook="http://${lan_ip}:${MILOCO_AGENT_PORT}/miloco/webhook"
  else
    default_webhook="http://127.0.0.1:${MILOCO_AGENT_PORT}/miloco/webhook"
  fi

  if [[ -z "${AGENT_WEBHOOK_URL:-}" ]]; then
    prompt AGENT_WEBHOOK_URL "外部 Server 应配置的 agent.webhook_url（须从 Server 侧能访问）" "$default_webhook"
  fi
  [[ -n "${AGENT_WEBHOOK_URL:-}" ]] || AGENT_WEBHOOK_URL="$default_webhook"

  if [[ -z "${AGENT_AUTH_BEARER:-}" ]]; then
    AGENT_AUTH_BEARER="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    log "已生成 agent.auth_bearer（请同步到外部 Server config.json）"
  fi

  if [[ -z "${MILOCO_SKILLS_DIR:-}" && ! -d "${MILOCO_REPO:-}/plugins/skills" ]]; then
    warn "未检测到母仓 plugins/skills"
    if [[ "${NONINTERACTIVE:-0}" != "1" ]]; then
      prompt MILOCO_SKILLS_DIR "MILOCO_SKILLS_DIR（Skill 文档目录，可 shallow clone 官方仓库后指向 plugins/skills）" ""
    fi
  fi

  mkdir -p "$MILOCO_HOME/log" "$MILOCO_HOME/agent"

  python3 - <<PY "$MILOCO_HOME/config.json" "$srv_host" "$srv_port" "$srv_base" "$MILOCO_SERVER_TOKEN" "$AGENT_WEBHOOK_URL" "$AGENT_AUTH_BEARER"
import json, sys
from pathlib import Path
cfg = Path(sys.argv[1])
host, port, base = sys.argv[2], int(sys.argv[3]), sys.argv[4]
token, webhook, bearer = sys.argv[5], sys.argv[6], sys.argv[7]
data = {
    "server": {
        "url": base,
        "host": host,
        "port": port,
        "token": token,
    },
    "agent": {
        "webhook_url": webhook,
        "auth_bearer": bearer,
        "llm": {
            "base_url": "https://api.kimi.com/coding/v1",
            "model": "kimi-for-coding",
            "api_key": "",
            "label": "Sidecar Agent LLM",
        },
        "feishu": {"enabled": False, "mode": "long_connection"},
        "cron": {"enabled": True, "timezone": "Asia/Shanghai"},
    },
}
cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"已写入 {cfg}")
PY

  # Sidecar 监听 overlay（可选 miloco-agent.json）
  python3 - <<PY "$MILOCO_HOME/miloco-agent.json" "$MILOCO_AGENT_HOST" "$MILOCO_AGENT_PORT"
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(
    json.dumps({"sidecar": {"host": sys.argv[2], "port": int(sys.argv[3]), "log_level": "info"}}, indent=2) + "\n",
    encoding="utf-8",
)
PY

  log "=== 安装 Sidecar venv ==="
  export MILOCO_HOME MILOCO_SKIP_CLI="${MILOCO_SKIP_CLI:-1}"
  bash "$AGENT_ROOT/scripts/miloco-agent-install.sh"

  local server_cfg_snippet
  server_cfg_snippet="$(cat <<EOF

# --- 请将以下片段合并到【外部 Miloco Server】的 config.json → agent 段 ---
{
  "agent": {
    "webhook_url": "${AGENT_WEBHOOK_URL}",
    "auth_bearer": "${AGENT_AUTH_BEARER}"
  }
}
# 修改后重启外部 Miloco Server。Sidecar 与 Server 的 auth_bearer 必须完全一致。
EOF
)"

  log "=== Sidecar 配置完成 ==="
  log "MILOCO_HOME=$MILOCO_HOME"
  log "Sidecar 监听: $MILOCO_AGENT_HOST:$MILOCO_AGENT_PORT"
  log "调用外部 API: $srv_base"
  log "管理台: http://127.0.0.1:${MILOCO_AGENT_PORT}/admin （本机）"
  echo "$server_cfg_snippet"
  log "下一步:"
  log "  1. 在外部 Server 写入上述 agent.webhook_url / auth_bearer 并重启 Server"
  log "  2. 编辑 $MILOCO_HOME/config.json 填入 agent.llm.api_key"
  [[ -n "${MILOCO_SKILLS_DIR:-}" ]] && log "  export MILOCO_SKILLS_DIR=$MILOCO_SKILLS_DIR"
  log "  提示: 外部 Miloco 升级后请手动同步 MILOCO_SKILLS_DIR 下 plugins/skills（git fetch + restart Sidecar），见 docs/EXTERNAL_MILOCO.md §3.1"
  log "  3. bash miloco-agent/scripts/miloco-agent-only.sh start"
}

main "$@"
