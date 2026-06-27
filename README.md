# miloco-agent

Miloco **Sidecar** 子仓：用 AgentScope 替换 OpenClaw Gateway，兼容官方 `agent.webhook_url` 契约。  
与 [xiaomi-miloco](https://github.com/XiaoMi/xiaomi-miloco) **母仓**配合使用，**不修改**官方 `backend/`、`cli/`、`web/` 源码。

| 仓库 | 地址 | 职责 |
|------|------|------|
| **子仓** miloco-agent | [traceless929/miloco-agent](https://github.com/traceless929/miloco-agent) | Sidecar 源码、部署脚本、Docker、文档 |
| **母仓** xiaomi-miloco | [traceless929/xiaomi-miloco](https://github.com/traceless929/xiaomi-miloco) | 官方 Miloco + `plugins/skills` + submodule 引用 |

---

## 一、母仓与子仓结构

```
xiaomi-miloco/                          ← 母仓 MILOCO_REPO
├── backend/                            ← Miloco Server（FastAPI，:1810）
├── cli/                                ← miloco-cli
├── web/                                ← 家庭 Web 面板（构建进 backend）
├── plugins/skills/                     ← 官方 Skill 文档（Sidecar 只读加载）
├── knowledge/                          ← 官方知识库
├── scripts/
│   ├── install.sh                      ← 官方安装（OpenClaw 路线）
│   └── miloco-stack.sh                 ← 转发 → 子仓一键脚本
└── miloco-agent/                       ← 本子仓（Git Submodule）
    ├── src/miloco_agent/               ← Sidecar Python 包
    ├── scripts/                        ← 安装、本机运行、一键 stack
    ├── docker/                         ← 容器编排 + docker/data 数据目录
    └── docs/                           ← 架构、飞书、管理台文档
```

### 路径与环境变量

脚本通过 `scripts/lib/paths.sh` 自动解析：

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `AGENT_ROOT` / `MILOCO_AGENT_ROOT` | 本子仓根目录 | `miloco-agent/` |
| `MILOCO_REPO` | `AGENT_ROOT/..` | 母仓 `xiaomi-miloco/` 根 |
| `MILOCO_HOME` | `miloco-agent/docker/data` | 运行时数据（config、模型、DB、日志） |
| `MILOCO_AGENT_VENV` | `miloco-agent/.venv` | Sidecar 独立 Python venv |

> **为何分两个仓？** 母仓持续 merge 小米 upstream；Sidecar、Docker、运维脚本在子仓独立演进，通过 submodule pin 版本。

---

## 二、环境要求

| 组件 | 要求 |
|------|------|
| 操作系统 | macOS / Linux（本机感知推荐 macOS 或 Linux 与摄像头同 LAN） |
| Python | **≥ 3.11**（Sidecar venv）；Backend 由 `uv` 管理 |
| 工具 | `git`、`uv`（`pip install uv` 或官方安装器） |
| 可选 | Docker / Podman（容器部署）；Mac 合盖跑需 `caffeinate` |

---

## 三、克隆与首次部署（推荐：一键脚本）

在**母仓根目录**执行：

```bash
# 1. 克隆（含子模块）
git clone --recurse-submodules https://github.com/traceless929/xiaomi-miloco.git
cd xiaomi-miloco

# 已克隆但未拉子模块：
git submodule update --init --recursive

# 2. 一键 setup：创建 config 模板、安装 Sidecar venv、同步 backend 依赖
bash miloco-agent/scripts/miloco-stack.sh setup

# 3. 编辑配置（见下一节）
${EDITOR:-vi} miloco-agent/docker/data/config.json

# 4. 启动 Server + Agent
bash miloco-agent/scripts/miloco-stack.sh start

# 5. 查看状态
bash miloco-agent/scripts/miloco-stack.sh status
```

**兼容旧路径**（母仓 `scripts/` 转发到子仓）：

```bash
bash scripts/miloco-stack.sh setup
bash scripts/miloco-stack.sh start
```

### 一键脚本命令一览

```bash
bash miloco-agent/scripts/miloco-stack.sh <命令>
```

| 命令 | 说明 |
|------|------|
| `setup` | 首次部署：init-config + venv + backend 依赖 |
| `start` | 后台启动 Miloco Server `:1810` + Agent `:18789` |
| `stop` | 停止 stack 拉起的进程 |
| `restart` | 重启 Agent；`restart --all` 重启 Server+Agent |
| `status` | 进程、端口、健康检查、配置摘要（Key 打码） |
| `logs` | 最近日志；`logs backend` / `logs agent` 跟踪单服务 |
| `caffeinate start\|stop\|status` | Mac 防睡眠（合盖持续跑） |

日志位置：`$MILOCO_HOME/log/miloco-backend.stack.log`、`miloco-agent.stack.log`。

---

## 四、配置指南（`$MILOCO_HOME/config.json`）

默认路径：`miloco-agent/docker/data/config.json`。  
`setup` / `init-config.sh` 会生成模板并自动写入 `server.token`、`agent.auth_bearer`、`agent.webhook_url`。

### 4.1 必配：Omni 感知模型（摄像头 AI）

Miloco **感知管线**使用 `model.omni`（与 Sidecar 对话 LLM 分开）：

```json
{
  "model": {
    "omni": {
      "label": "MiMo Omni",
      "base_url": "https://api.xiaomimimo.com/v1",
      "model": "xiaomi/mimo-v2.5",
      "api_key": "从 https://platform.xiaomimimo.com 获取"
    }
  }
}
```

也可在 Web 面板 **设置 → 模型配置** 中填写并保存（写入同一 `config.json`）。

> **注意**：`kimi-for-coding` 等 Coding Agent 模型**不能**用于 Omni 感知（不支持 Miloco 的 `video_url` 多模态请求）。感知请用 **MiMo** 或兼容 OpenAI 多模态协议且支持视频的模型。

### 4.2 必配：Sidecar Agent LLM（飞书 / Cron / 对话）

```json
{
  "agent": {
    "llm": {
      "base_url": "https://api.kimi.com/coding/v1",
      "model": "kimi-for-coding",
      "api_key": "你的 Kimi API Key"
    }
  }
}
```

也可在管理台 **http://127.0.0.1:18789/admin** → LLM 配置页修改。

### 4.3 可选：飞书机器人

详见 [docs/agent/FEISHU_SETUP.md](./docs/agent/FEISHU_SETUP.md)。

```json
{
  "agent": {
    "feishu": {
      "enabled": true,
      "mode": "long_connection",
      "app_id": "cli_xxx",
      "app_secret": "xxx",
      "default_receive_open_id": "ou_xxx"
    }
  }
}
```

长连接模式**无需公网 IP**。启动后日志应出现 `feishu long-connection thread started`。

### 4.4 可选：Cron 定时任务

```json
{
  "agent": {
    "cron": {
      "enabled": true,
      "timezone": "Asia/Shanghai"
    }
  }
}
```

内置任务（家庭档案 digest、巡检等）在 Sidecar 启动时自动注册；用户自定义 Cron 可在管理台配置。

### 4.5 配置检查清单

| 项 | 字段 | 用途 |
|----|------|------|
| ☐ | `model.omni.api_key` | 摄像头感知 / 性能监测 Omni |
| ☐ | `agent.llm.api_key` | 飞书、Cron、Agent 工具调用 |
| ☐ | `agent.auth_bearer` | Server → Sidecar webhook 鉴权（setup 自动生成） |
| ☐ | `server.token` | Web/API 鉴权（setup 自动生成） |
| ☐ | 米家账号 | Web `:1810` 绑定（非 config 字段，面板操作） |

---

## 五、访问地址

| 服务 | URL | 说明 |
|------|-----|------|
| Miloco Web | http://127.0.0.1:1810/ | 家庭面板、设备、性能监测 |
| Agent 管理台 | http://127.0.0.1:18789/admin | LLM / 飞书 / Cron / 桥接 / 日志 |
| Sidecar 健康 | http://127.0.0.1:18789/health | |
| Webhook | http://127.0.0.1:18789/miloco/webhook | Server 回调 Sidecar |

局域网访问：将 `127.0.0.1` 换成本机 IP；Server 默认 `0.0.0.0:1810`。

---

## 六、开发模式（前台双终端）

需要看实时日志、调试时：

```bash
export MILOCO_HOME=/path/to/xiaomi-miloco/miloco-agent/docker/data

# 终端 1 — Miloco Server（前台）
bash miloco-agent/scripts/miloco-local-run.sh

# 终端 2 — Sidecar（前台）
bash miloco-agent/scripts/miloco-agent-run.sh
```

Mac 合盖持续跑（插电）：

```bash
MILOCO_HOME=docker/data bash miloco-agent/scripts/miloco-caffeinate.sh start
# 或
bash miloco-agent/scripts/miloco-stack.sh caffeinate start
```

### Sidecar 开发

```bash
cd miloco-agent
uv sync --extra dev
uv run pytest
uv run miloco-agent          # 前台启动
```

修改 Python 代码后，`restart` 即可（venv editable 安装）：

```bash
bash miloco-agent/scripts/miloco-stack.sh restart
```

### 子仓独立提交

```bash
cd miloco-agent
git add . && git commit -m "feat: ..." && git push origin main

cd ..
git add miloco-agent          # bump submodule 指针
git commit -m "Bump miloco-agent"
git push origin main
```

---

## 七、对接外部 Miloco（仅 Sidecar）

**不使用母仓 backend**，Sidecar 单独对接已在 Docker / 远程 / 官方安装的 Miloco Server。

完整环境要求、网络拓扑、验证清单见 **[docs/EXTERNAL_MILOCO.md](./docs/EXTERNAL_MILOCO.md)**。

```bash
# 仅 clone 子仓即可（无需 xiaomi-miloco 母仓）
git clone https://github.com/traceless929/miloco-agent.git && cd miloco-agent

# 引导配置 + 安装 venv
bash scripts/setup-external-miloco.sh

# 按脚本提示，把 agent.webhook_url / auth_bearer 写到【外部】Server 的 config.json 并重启 Server

# 仅启动 Sidecar
bash scripts/miloco-agent-only.sh start
bash scripts/miloco-agent-only.sh status
```

| 脚本 | 说明 |
|------|------|
| `setup-external-miloco.sh` | 探测外部 Server、生成本地 config、安装 venv |
| `miloco-agent-only.sh` | 仅 Agent 的 start / stop / status / logs |

默认数据目录：`~/.miloco-agent-sidecar`（与母仓 `docker/data` 独立）。

---

## 八、Docker 部署（Linux / 同网摄像头）

```bash
export MILOCO_REPO=/path/to/xiaomi-miloco
bash miloco-agent/scripts/deploy-linux-docker.sh
```

构建 Server 镜像需要母仓的 `backend/`、`web/`；Agent 镜像仅本子仓。  
详见 [docker/README.md](./docker/README.md)。

---

## 九、数据目录（MILOCO_HOME）

```
docker/data/
├── config.json       # 主配置（勿提交 git）
├── models/           # ONNX 感知模型（setup 可从 backend 同步）
├── miloco.db         # 业务 SQLite（运行后生成）
├── observability.db  # 性能 trace（运行后生成）
├── log/              # 运行日志 + stack 脚本日志
├── storage/          # 其他持久化
└── trace/            # Agent 回合 jsonl（Cron 等）
```

换机器时复制整个 `docker/data/` 即可保留配置与绑定。

---

## 十、常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| Omni 错误率 100% | `model.omni` Key/地址错误或模型不支持 video | 检查 MiMo Key；见配置 4.1 |
| Agent 无响应 | Server 未起或 webhook 不通 | `miloco-stack.sh status`；确认 `agent.webhook_url` |
| 子模块目录空 | 未 init submodule | `git submodule update --init --recursive` |
| 飞书无消息 | 未开长连接或未发布应用 | [FEISHU_SETUP.md](./docs/agent/FEISHU_SETUP.md) |
| 合盖后停服 | Mac 睡眠 | 插电 + `caffeinate start` |

---

## 十一、更多文档

| 文档 | 说明 |
|------|------|
| [docs/EXTERNAL_MILOCO.md](./docs/EXTERNAL_MILOCO.md) | **仅 Sidecar 对接外部 Miloco**（环境要求、网络、脚本） |
| [docs/agent/README.md](./docs/agent/README.md) | Agent 模块索引 |
| [docs/agent/ARCHITECTURE.md](./docs/agent/ARCHITECTURE.md) | 架构与 Webhook 契约 |
| [docs/agent/ADMIN_PLATFORM.md](./docs/agent/ADMIN_PLATFORM.md) | 管理台 API |
| [docs/agent/FEISHU_SETUP.md](./docs/agent/FEISHU_SETUP.md) | 飞书接入 |
| [docs/agent/BRIDGE.md](./docs/agent/BRIDGE.md) | Skill / miloco-cli 桥接 |
| [docker/README.md](./docker/README.md) | 容器部署 |

---

## 脚本索引

| 脚本 | 用途 |
|------|------|
| **miloco-stack.sh** | 全栈 setup / start / stop（母仓 Server + Agent） |
| **setup-external-miloco.sh** | 引导对接外部 Miloco |
| **miloco-agent-only.sh** | 仅 Sidecar start / stop / status |
| init-config.sh | 仅生成/补全 config.json 与模型 |
| miloco-agent-install.sh | 安装 Sidecar venv + miloco-cli |
| miloco-agent-run.sh | 前台启动 Sidecar |
| miloco-local-run.sh | 前台启动 Miloco Server |
| miloco-caffeinate.sh | Mac 防睡眠 |
| deploy-linux-docker.sh | Linux Docker 一键部署 |
