#!/usr/bin/env bash
# Fork 专属：后台重启 miloco-agent Sidecar（供管理台一键重启调用）
set -euo pipefail

# shellcheck source=lib/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/paths.sh"

export MILOCO_HOME="${MILOCO_HOME:-$HOME/.openclaw/miloco}"

pkill -f "miloco-agent" 2>/dev/null || true
sleep 1
exec env MILOCO_HOME="$MILOCO_HOME" MILOCO_REPO="$MILOCO_REPO" bash "$AGENT_ROOT/scripts/miloco-agent-run.sh"
