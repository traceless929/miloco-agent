#!/usr/bin/env bash
# 将容器内 apt 源切换为阿里云镜像（替代 archive.ubuntu.com / ports.ubuntu.com）
# 参考: https://developer.aliyun.com/mirror/ubuntu-ports
# 使用 http 以便在 ca-certificates 安装前即可 apt update（fresh 镜像无 CA 包）
set -euo pipefail

ARCH="$(dpkg --print-architecture)"
SUITE="noble"

if [[ "${ARCH}" == "amd64" || "${ARCH}" == "i386" ]]; then
  MIRROR="http://mirrors.aliyun.com/ubuntu"
else
  MIRROR="http://mirrors.aliyun.com/ubuntu-ports"
fi

echo "[apt-aliyun] arch=${ARCH} mirror=${MIRROR}"

rm -f /etc/apt/sources.list
rm -f /etc/apt/sources.list.d/ubuntu.sources

cat >/etc/apt/sources.list.d/ubuntu.sources <<EOF
Types: deb
URIs: ${MIRROR}
Suites: ${SUITE} ${SUITE}-updates ${SUITE}-backports
Components: main universe restricted multiverse

Types: deb
URIs: ${MIRROR}
Suites: ${SUITE}-security
Components: main universe restricted multiverse
EOF
