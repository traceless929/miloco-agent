#!/usr/bin/env bash
# 通过 pip + 国内 PyPI 镜像安装 uv（替代 curl https://astral.sh/uv/install.sh）
# 适用于 Docker 构建等网络环境；参考国内 uv 实践（pip 安装 + 镜像源）
set -euo pipefail

PIP_INDEX="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
UV_CONFIG_DST="${UV_CONFIG_DST:-/root/.config/uv/uv.toml}"

echo "[install-uv] pip index=${PIP_INDEX}"

# 不升级系统自带的 pip（Debian 包会触发 uninstall 失败），直接装 uv
python3 -m pip install --break-system-packages -q -i "${PIP_INDEX}" uv

if [[ -f /tmp/uv.toml ]]; then
  mkdir -p "$(dirname "${UV_CONFIG_DST}")"
  cp /tmp/uv.toml "${UV_CONFIG_DST}"
  echo "[install-uv] uv config -> ${UV_CONFIG_DST}"
fi

if command -v uv >/dev/null 2>&1; then
  echo "[install-uv] $(uv --version)"
else
  echo "[install-uv] ERROR: uv not on PATH" >&2
  exit 1
fi
