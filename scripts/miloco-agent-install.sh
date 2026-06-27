#!/usr/bin/env bash
# Fork 专属：安装 miloco-agent Sidecar（独立 Python 3.11+ venv，不修改 backend/）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

AGENT_DIR="$AGENT_ROOT"
VENV_DIR="${MILOCO_AGENT_VENV:-$AGENT_ROOT/.venv}"

if [[ ! -f "$AGENT_DIR/pyproject.toml" ]]; then
  echo "[miloco-agent-install] 未找到 $AGENT_DIR/pyproject.toml" >&2
  exit 1
fi

need_python() {
  if command -v python3.12 >/dev/null 2>&1; then echo python3.12; return; fi
  if command -v python3.11 >/dev/null 2>&1; then echo python3.11; return; fi
  echo "需要 Python >= 3.11（python3.11 或 python3.12）" >&2
  exit 1
}

PY="$(need_python)"
echo "[miloco-agent-install] 使用 $("$PY" --version)"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PY" -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

PIP_INDEX="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"

if ! command -v uv >/dev/null 2>&1; then
  echo "[miloco-agent-install] 未检测到 uv，通过 pip 安装（index=${PIP_INDEX}）"
  pip install -U pip -i "$PIP_INDEX"
  pip install uv -i "$PIP_INDEX"
  UV_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/uv"
  mkdir -p "$UV_CONFIG_DIR"
  if [[ -f "$AGENT_ROOT/docker/uv.toml" ]]; then
    cp "$AGENT_ROOT/docker/uv.toml" "$UV_CONFIG_DIR/uv.toml"
  fi
fi

uv pip install -e "$AGENT_DIR[dev]"
if [[ "${MILOCO_SKIP_CLI:-0}" != "1" && -f "$MILOCO_REPO/cli/pyproject.toml" ]]; then
  uv pip install -e "$MILOCO_REPO/cli"
elif [[ "${MILOCO_SKIP_CLI:-0}" != "1" ]]; then
  echo "[miloco-agent-install] 未找到 $MILOCO_REPO/cli，跳过 miloco-cli（可设 MILOCO_SKIP_CLI=1 抑制此提示）" >&2
fi

MILOCO_HOME="${MILOCO_HOME:-$HOME/.openclaw/miloco}"
CONFIG="$MILOCO_HOME/config.json"
mkdir -p "$MILOCO_HOME"

if [[ ! -f "$CONFIG" ]]; then
  echo "[miloco-agent-install] 警告: $CONFIG 不存在，请先安装 Miloco Server" >&2
fi

BEARER=""
if [[ -f "$CONFIG" ]]; then
  BEARER="$("$PY" - <<'PY' "$CONFIG"
import json, secrets, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
agent = data.setdefault("agent", {})
if not agent.get("auth_bearer"):
    agent["auth_bearer"] = secrets.token_urlsafe(32)
agent["webhook_url"] = agent.get("webhook_url") or "http://127.0.0.1:18789/miloco/webhook"
p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(agent["auth_bearer"])
PY
)"
else
  BEARER="$(openssl rand -base64 32 | tr -d '/+=' | head -c 43)"
fi

echo "[miloco-agent-install] 完成"
echo "  venv: $VENV_DIR"
echo "  webhook: http://127.0.0.1:18789/miloco/webhook"
echo "  auth_bearer: ${BEARER:-（见 config.json）}"
echo "  启动: bash miloco-agent/scripts/miloco-agent-run.sh"
