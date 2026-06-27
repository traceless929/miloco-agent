#!/usr/bin/env bash
# Fork 专属：启动 miloco-agent Sidecar
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

VENV_DIR="${MILOCO_AGENT_VENV:-$AGENT_ROOT/.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "未找到 venv，请先运行: bash miloco-agent/scripts/miloco-agent-install.sh" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
export MILOCO_HOME="${MILOCO_HOME:-$HOME/.openclaw/miloco}"
export MILOCO_REPO

exec miloco-agent
