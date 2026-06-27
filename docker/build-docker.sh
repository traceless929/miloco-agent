#!/usr/bin/env bash
# Docker 专用构建：复用官方 build.sh 的 wheel/web 逻辑，跳过平台归档与自包含安装脚本
set -euo pipefail

export COPYFILE_DISABLE=1
ROOT=/src
cd "$ROOT"

# 从官方 build.sh 提取函数（去掉 main），并固定路径（source 时 BASH_SOURCE 不可靠）
sed '/^main "\$@"/d' "$ROOT/scripts/build.sh" > /tmp/build-funcs.sh
# shellcheck source=/tmp/build-funcs.sh
source /tmp/build-funcs.sh

SCRIPT_DIR="$ROOT/scripts"
PROJECT_ROOT="$ROOT"
DIST_DIR="$ROOT/dist"
PACKAGES="miloco-miot,miloco,miloco-cli,web"

should_build() {
  [[ ",$PACKAGES," == *",$1,"* ]]
}

check_prerequisites
resolve_version

log "清除 dist/ ..."
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

if should_build "web"; then build_web; fi
if should_build "miloco-miot"; then build_miloco_miot; fi
if should_build "miloco"; then build_miloco; fi
if should_build "miloco-cli"; then build_miloco_cli; fi

log "Docker wheel 构建完成"
