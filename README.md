# miloco-agent

Fork 专属 Sidecar：兼容 Miloco `agent.webhook_url` 契约，用于替换 OpenClaw Gateway + Plugin。

> 独立仓库 [traceless929/miloco-agent](https://github.com/traceless929/miloco-agent)，在 [xiaomi-miloco](https://github.com/traceless929/xiaomi-miloco) fork 中以 **Git Submodule** 引用。  
> 本仓包含：Sidecar 源码、`scripts/`、`docker/`、`docs/`。

## 要求

- Python **≥ 3.11**（独立 venv，不并入 `backend/` workspace）
- 已 clone 的 **xiaomi-miloco** 父仓库（`MILOCO_REPO`，含 `backend/`、`cli/`、`plugins/skills/`）
- 已运行的 Miloco Server（`miloco-cli service start` 或 Docker）

## 快速开始

```bash
# 在 xiaomi-miloco 根目录
git submodule update --init --recursive

bash miloco-agent/scripts/miloco-agent-install.sh
bash miloco-agent/scripts/miloco-agent-run.sh
# 兼容旧路径：bash scripts/miloco-agent-run.sh（转发到子仓脚本）
```

默认数据目录：`miloco-agent/docker/data/`（`MILOCO_HOME` 可覆盖）。

## 目录

| 路径 | 说明 |
|------|------|
| `src/miloco_agent/` | Sidecar 源码 |
| `scripts/` | 安装、启动、本机运行、Docker 部署 |
| `docker/` | 容器编排与镜像构建 |
| `docs/` | Fork 专属文档（架构、飞书、管理台） |

## Docker

```bash
export MILOCO_REPO=/path/to/xiaomi-miloco
bash miloco-agent/scripts/deploy-linux-docker.sh
```

详见 [docker/README.md](./docker/README.md)。

## 文档

- [docs/agent/README.md](./docs/agent/README.md)

## 环境变量

| 变量 | 说明 |
|------|------|
| `MILOCO_REPO` | xiaomi-miloco 根目录（默认：本仓上一级） |
| `MILOCO_AGENT_ROOT` | 本仓根目录（Python 桥接可选） |
| `MILOCO_HOME` | 运行时数据目录 |
| `MILOCO_SKILLS_DIR` | 覆盖 `plugins/skills` 路径 |
