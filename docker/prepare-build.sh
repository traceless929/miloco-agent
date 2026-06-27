#!/usr/bin/env bash
# 容器构建前补丁（fork 专属，不改宿主机源码树）
set -euo pipefail

patch_pnpm_workspace() {
  local ws="$1"
  [[ -f "$ws" ]] || return 0
  if grep -q '^packages:' "$ws" 2>/dev/null; then
    return 0
  fi
  echo "[prepare-build] patch ${ws} (pnpm 需要 packages 字段)"
  {
    echo "packages:"
    echo "  - ."
    cat "$ws"
  } > "${ws}.docker" && mv "${ws}.docker" "$ws"
}

patch_pnpm_workspace web/pnpm-workspace.yaml
