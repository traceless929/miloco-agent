# Miloco 容器运行（Fork 专属）

在**不修改官方 `backend/` 安装逻辑**的前提下，用 Docker/Podman 跑起 Miloco Server + `miloco-agent` Sidecar。

## 前置

- Docker 或 Podman（本机 `docker` 若为 Podman 别名亦可）
- 首次构建约 15～30 分钟（编译 web + Python wheels）

## 镜像与 apt 源

- **基础镜像**：默认 `m.daocloud.io/docker.io/library/ubuntu:24.04`（避免 Docker Hub 超时），可通过 build-arg 覆盖：
  ```bash
  docker compose -f docker/docker-compose.yml build \
    --build-arg UBUNTU_IMAGE=ubuntu:24.04 miloco
  ```
- **apt 软件源**：构建时自动切换为[阿里云镜像](https://developer.aliyun.com/mirror/ubuntu-ports)
  - `amd64` → `http://mirrors.aliyun.com/ubuntu`
  - `arm64` 等 → `http://mirrors.aliyun.com/ubuntu-ports`（替代 [ports.ubuntu.com](http://ports.ubuntu.com)）
- **uv 安装**：通过 `pip` + [阿里云 PyPI](https://mirrors.aliyun.com/pypi/simple/)（`docker/install-uv.sh`），不再使用 `curl https://astral.sh/uv/install.sh`
  - 全局配置见 `docker/uv.toml`（PyPI 索引 + `python-build-standalone` 下载镜像）
  - 环境变量：`UV_DEFAULT_INDEX`、`UV_PYTHON_INSTALL_MIRROR`
- **cryptography**：镜像内固定 `42.0.8`（`cryptography>=43` 的 Rust wheel 在部分 Podman/QEMU aarch64 下会 SIGILL，导致 `miloco-backend` 反复重启）

## 快速启动

```bash
# 仓库根目录
cp docker/env.example docker/.env
# 可选：编辑 docker/.env 填入 MILOCO_OMNI_API_KEY

docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
```

Podman：

```bash
podman compose -f docker/docker-compose.yml build
podman compose -f docker/docker-compose.yml up -d
```

## 网络（host 模式）

默认 **`network_mode: host`**：容器与宿主机共用网络栈，便于摄像头 **LAN 直连 / UDP 发现 / P2P 拉流**。

| 项 | 说明 |
|----|------|
| 访问地址 | `http://127.0.0.1:1810`（面板）、`:18789`（agent） |
| `ports:` | host 模式下**无效**，已移除 |
| Server → Agent | `config.json` 内 `agent.webhook_url` 为 `http://127.0.0.1:18789/miloco/webhook`（entrypoint 每次启动同步） |
| 平台 | **Linux** 上效果最好；**macOS Podman** 的 host 在虚拟机内，`127.0.0.1:1810` 可能打不开面板，见下节 |

端口可在 `docker/.env` 修改 `MILOCO_SERVER_PORT` / `MILOCO_AGENT_PORT`（勿与宿主机其他服务冲突）。

### macOS Podman 说明

`network_mode: host` 绑定的是 **Podman 虚拟机**的网络，不是 macOS 本机 loopback：

- 容器内 / VM 内：`curl http://127.0.0.1:1810/health` 正常
- Mac 浏览器访问 `127.0.0.1:1810` 可能失败

**不等于只能本机直跑**。容器完全可行，按目标选方案：

| 目标 | 方案 | 面板 | 摄像头感知 |
|------|------|------|------------|
| 家里 Linux（NAS / 小主机） | 默认 `docker-compose.yml`（host） | ✅ | ✅ |
| Mac 调面板 + Agent | bridge 叠加 或 端口转发脚本 | ✅ | ❌ |
| Mac 容器 + 尽量碰 LAN | host + `mac-port-forward.sh` | ✅（需转发） | ⚠️ 视 VM 能否进家庭网段 |
| Mac 要完整感知 | 本机 `miloco-backend` 或 Linux 容器 | ✅ | ✅ |

#### 方案 A：Linux 上跑容器（推荐，仍是 Docker）

与摄像头同网的 **Linux 实体机 / NAS / 树莓派** 上 `docker compose up`，`network_mode: host` 在 Linux 上是真 host，**不必本机直跑 Python**。

#### 方案 B：Mac 只要面板 / 规则 / Agent

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.bridge.yml up -d
open http://127.0.0.1:1810/
```

#### 方案 C：Mac 保持 host + 本机浏览器（端口转发）

另开终端，保持运行：

```bash
bash docker/mac-port-forward.sh
```

然后在 Mac 打开 `http://127.0.0.1:1810/`。摄像头能否感知取决于 Podman VM 是否路由到你家局域网（多数家庭网下仍困难）。

#### 方案 D：Mac 本机直跑

仅当必须在 Mac 上完成**摄像头感知**且容器网络不满足时使用 `scripts/miloco-agent-install.sh` + 官方安装方式。

## 验证

```bash
curl -s http://127.0.0.1:1810/health
curl -s http://127.0.0.1:18789/health

# 面板（token 内嵌在 HTML，浏览器打开）
open http://127.0.0.1:1810/
```

## 数据目录（推荐 bind mount）

默认把 **`docker/data/`** 挂载为容器内 `/data/miloco`（`MILOCO_HOME`），与官方本地安装布局一致：

| 宿主机（`MILOCO_DATA_DIR`） | 容器内 | 说明 |
|---------------------------|--------|------|
| `config.json` | `/data/miloco/config.json` | API Key、米家、webhook |
| `models/` | `/data/miloco/models/` | ONNX 感知模型 |
| `storage/` | `/data/miloco/storage/` | SQLite 等 |
| `log/` | `/data/miloco/log/` | 日志 |

在 `docker/.env` 中配置：

```bash
# 默认：docker/data
MILOCO_DATA_DIR=./data

# 或复用已有本地安装目录
MILOCO_DATA_DIR=/Users/you/.openclaw/miloco
```

**为何不用 Docker 命名卷**：配置/模型不好直接改、与宿主机工具链割裂；本地开发用文件夹挂载更直观。

首次启动前可将模型放入 `docker/data/models/`，或依赖 entrypoint 从镜像默认目录复制。

```bash
mkdir -p docker/data/models
cp backend/miloco/src/miloco/perception/models/*.onnx docker/data/models/
```

从旧 Docker 命名卷迁移到 `docker/data/`（**用本地已有镜像**，勿拉 `alpine`）：

```bash
docker run --rm --entrypoint bash \
  -v docker_miloco-data:/from \
  -v "$(pwd)/docker/data:/to" \
  miloco-local:latest \
  -c 'cp -a /from/. /to/'
```

## 日志

```bash
docker compose -f docker/docker-compose.yml logs -f miloco
docker compose -f docker/docker-compose.yml logs -f miloco-agent
```

## 说明

| 项 | 行为 |
|----|------|
| OpenClaw | **不包含**；`agent.webhook_url` 指向本机 `miloco-agent`（`:18789`） |
| 米家账号 | 需在容器外通过 `miloco-cli account bind` 或挂载已有 `config.json` |
| 摄像头 / LAN | 已默认 **host 网络**；须与 Miloco 宿主机在同一局域网 |
| 官方代码 | 构建阶段只读源码 `build.sh`，**不向 upstream 提交 docker/** |

## 仅 Server（不启 Agent）

```bash
docker compose -f docker/docker-compose.yml up -d miloco
```

## 重建

```bash
docker compose -f docker/docker-compose.yml build --no-cache miloco
docker compose -f docker/docker-compose.yml up -d
```
