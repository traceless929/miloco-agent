# 对接外部 Miloco Server（仅 Sidecar）

在**不运行母仓 backend**、不 clone 完整 `xiaomi-miloco` 的情况下，单独部署 `miloco-agent` Sidecar，对接已在其他机器/Docker/官方安装中运行的 Miloco Server。

---

## 一、架构与数据流

```
┌─────────────────────────────┐         REST API          ┌──────────────────────────┐
│  miloco-agent Sidecar       │ ─────────────────────────►│  外部 Miloco Server      │
│  :18789                     │   Bearer server.token     │  :1810（任意主机/Docker）│
│  MILOCO_HOME 独立目录       │                           │  自有 MILOCO_HOME        │
└─────────────────────────────┘                           └──────────────────────────┘
         ▲                                                            │
         │  POST /miloco/webhook（agent 指令、Cron 回调）              │
         └──────────────── Bearer agent.auth_bearer ──────────────────┘
```

Sidecar 职责：

- **接收** Server 的 webhook（`agent.webhook_url` → Sidecar）
- **调用** Server REST API（设备、任务、感知查询等，需 `server.token`）
- **飞书 / Cron / LLM** 在 Sidecar 内运行（读 Sidecar 的 `config.json` 中 `agent.*`）

Omni 摄像头感知在外部 Server 执行，Sidecar **不需要**配置 `model.omni`（除非你在 Sidecar 管理台改 Server 侧配置）。

---

## 二、环境要求

### 2.1 运行 Sidecar 的机器

| 项 | 要求 |
|----|------|
| OS | Linux / macOS |
| Python | **≥ 3.11**（python3.11 或 3.12） |
| 工具 | `git`、`curl`；`uv`（脚本可自动 pip 安装） |
| 网络 | 能 **访问** 外部 Miloco `server.url` 或 `host:port`；且 **外部 Server 能访问** Sidecar 的 `webhook_url` |
| 端口 | 默认 **18789** 可用；跨机时 firewall 放行入站 |
| 内存 | 建议 ≥ 2GB（Agent + LLM 工具调用） |

### 2.2 外部 Miloco Server

| 项 | 要求 |
|----|------|
| 版本 | 与 Sidecar 契约兼容的 Miloco 2.x（支持 `agent.webhook_url`） |
| 状态 | 已启动，`GET /health` 返回 200 |
| 凭证 | 已知 `config.json` → `server.token` |
| 配置 | 需写入与 Sidecar **一致** 的 `agent.webhook_url`、`agent.auth_bearer` |

> **若外部 Server 需摄像头 LAN 感知（Omni）且用容器部署**：必须在 **Linux** 上使用 Docker/Podman 的 **`network_mode: host`**。**macOS 上的 Docker Desktop / Podman 不支持有效 host 网络**，容器内 Server 无法与家庭摄像头同网 —— Mac 上请本机直跑 Server，或把 Server 部署到 Linux 主机。详见 [docker/README.md](../docker/README.md)。

### 2.3 可选组件

| 组件 | 是否必须 | 说明 |
|------|----------|------|
| 母仓 `xiaomi-miloco` | **否** | 仅 Sidecar 时可只 clone `miloco-agent` 仓库 |
| `plugins/skills` | **推荐** | 设 `MILOCO_SKILLS_DIR` 指向 Skill 目录；可从官方仓库 shallow clone。**外部 Miloco 升级后须手动同步 Skill 文件**（见 §3.1） |
| `miloco-cli` | **否** | 无 CLI 时 Bash 设备命令不可用；`MILOCO_SKIP_CLI=1` 跳过安装 |
| `agent.llm.api_key` | **是**（对话/Cron） | 飞书、Agent 指令、Cron 需要 LLM |
| 飞书应用 | **否** | 按 [FEISHU_SETUP.md](./agent/FEISHU_SETUP.md) 配置 |

### 2.4 网络场景

| 场景 | Sidecar 监听 | `agent.webhook_url` 示例 | 注意 |
|------|--------------|---------------------------|------|
| 同机 | `127.0.0.1:18789` | `http://127.0.0.1:18789/miloco/webhook` | Server 与 Sidecar 同一台 |
| Server 在 Docker、Sidecar 在宿主机 | `0.0.0.0:18789` | `http://宿主机LAN_IP:18789/miloco/webhook` | Docker **`host` 网络（仅 Linux）** 或 `host.docker.internal`；**macOS 容器无有效 host** |
| 异机 | `0.0.0.0:18789` | `http://Sidecar机器IP:18789/miloco/webhook` | 双向防火墙、路由可达 |

Sidecar 监听地址由 `$MILOCO_HOME/miloco-agent.json` 的 `sidecar.host` 控制；`setup-external-miloco.sh` 默认 **`0.0.0.0`**（便于跨机）。

---

## 三、仅 clone 子仓（无母仓）

```bash
git clone https://github.com/traceless929/miloco-agent.git
cd miloco-agent

# Skill 文档（推荐，浅克隆官方仓库 skills 目录）
git clone --depth 1 --filter=blob:none --sparse https://github.com/XiaoMi/xiaomi-miloco.git /tmp/xiaomi-miloco
cd /tmp/xiaomi-miloco && git sparse-checkout set plugins/skills
export MILOCO_SKILLS_DIR=/tmp/xiaomi-miloco/plugins/skills
```

### 3.1 Skill 文档须手动同步（重要）

对接**外部 Miloco** 时，Sidecar 通过 `MILOCO_SKILLS_DIR` **只读加载**本地 `plugins/skills/*/SKILL.md`，**不会**随外部 Server 升级自动更新。

| 场景 | Skill 来源 | 是否自动同步 |
|------|------------|--------------|
| 全栈（母仓 `miloco-stack.sh`） | 母仓 `plugins/skills/` | `git merge upstream/main` 后随仓库更新 |
| **仅 Sidecar + 外部 Miloco** | 独立 clone 的 `MILOCO_SKILLS_DIR` | ❌ **须手动拉取**官方仓库 Skill |

**何时需要同步**：外部 Miloco Server 版本升级、官方新增/修改 Skill、Agent 工具行为与文档不一致时。

**推荐做法**（在存放 Skill 的 clone 目录执行，路径按你的 `MILOCO_SKILLS_DIR` 调整）：

```bash
# 例：MILOCO_SKILLS_DIR=/tmp/xiaomi-miloco/plugins/skills
cd /tmp/xiaomi-miloco
git fetch origin main
git checkout origin/main -- plugins/skills

# 同步后重启 Sidecar，LocalSkillLoader 会按文件 mtime 重载
bash /path/to/miloco-agent/scripts/miloco-agent-only.sh restart
```

若使用 **sparse clone**，也可在 clone 根目录 `git pull origin main`（需已 `sparse-checkout set plugins/skills`）。

**持久化建议**：将 Skill 目录放在固定路径（如 `~/miloco-skills-cache/xiaomi-miloco/plugins/skills`），写入 shell 配置或 systemd 环境的 `MILOCO_SKILLS_DIR`，升级 Miloco 后按上表执行一次 `git fetch` + 重启 Sidecar。

详见 [agent/BRIDGE.md](./agent/BRIDGE.md)「上游合并工作流」；全栈部署见 [README.md](./README.md) 第六节。

---

## 四、引导配置（推荐）

### 4.1 交互式

```bash
cd miloco-agent   # 或母仓下的 miloco-agent/

bash scripts/setup-external-miloco.sh
# 按提示输入外部 Server URL、server.token、webhook 地址等

bash scripts/miloco-agent-only.sh start
bash scripts/miloco-agent-only.sh status
```

### 4.2 非交互（脚本/自动化）

```bash
export NONINTERACTIVE=1
export MILOCO_HOME="$HOME/.miloco-agent-sidecar"
export MILOCO_SERVER_URL="http://192.168.1.10:1810"
export MILOCO_SERVER_TOKEN="你的-server-token"
export AGENT_WEBHOOK_URL="http://192.168.1.20:18789/miloco/webhook"
export MILOCO_AGENT_HOST="0.0.0.0"
export MILOCO_SKILLS_DIR="/path/to/plugins/skills"
export MILOCO_SKIP_CLI=1

bash scripts/setup-external-miloco.sh
bash scripts/miloco-agent-only.sh start
```

### 4.3 写入外部 Server 的配置

`setup-external-miloco.sh` 结束时会打印需在**外部 Miloco** 的 `config.json` 中合并的片段：

```json
{
  "agent": {
    "webhook_url": "http://<Sidecar可达地址>:18789/miloco/webhook",
    "auth_bearer": "<与 Sidecar 相同>"
  }
}
```

修改后**重启外部 Miloco Server**。  
若外部与 Sidecar 共用同一 `MILOCO_HOME`（少见），则只需维护一份 `config.json`。

---

## 五、Sidecar 独立数据目录

默认：`~/.miloco-agent-sidecar/`（与母仓 `docker/data` 分离）

```
~/.miloco-agent-sidecar/
├── config.json           # server.* 指向外部；agent.* 为 Sidecar
├── miloco-agent.json     # sidecar 监听 host/port
├── agent/                # 飞书绑定、会话等
└── log/
```

`config.json` 示例（外部 Server）：

```json
{
  "server": {
    "url": "http://192.168.1.10:1810",
    "host": "192.168.1.10",
    "port": 1810,
    "token": "外部-server-token"
  },
  "agent": {
    "webhook_url": "http://192.168.1.20:18789/miloco/webhook",
    "auth_bearer": "两边必须一致",
    "llm": {
      "base_url": "https://api.kimi.com/coding/v1",
      "model": "kimi-for-coding",
      "api_key": "你的-key"
    },
    "feishu": { "enabled": false },
    "cron": { "enabled": true, "timezone": "Asia/Shanghai" }
  }
}
```

---

## 六、仅 Agent 运维命令

```bash
bash scripts/miloco-agent-only.sh start
bash scripts/miloco-agent-only.sh stop
bash scripts/miloco-agent-only.sh restart
bash scripts/miloco-agent-only.sh status    # 含外部 Server /health 探测
bash scripts/miloco-agent-only.sh logs
```

母仓根目录兼容转发：

```bash
bash scripts/setup-external-miloco.sh
bash scripts/miloco-agent-only.sh start
```

---

## 七、验证清单

1. `miloco-agent-only.sh status` → 外部 Server `/health: OK`
2. Sidecar `/admin` 可打开 → `http://127.0.0.1:18789/admin`
3. 外部 Server 已配置相同 `webhook_url` / `auth_bearer` 并已重启
4. 在 Web 面板或飞书触发 Agent 指令，Sidecar 日志有 webhook 请求
5. （可选）管理台「桥接」页显示 Skill / 连接状态

---

## 八、常见问题

| 现象 | 处理 |
|------|------|
| 外部 Server OK，Agent 无 webhook | Server 未配 webhook 或未重启；URL 从 Server 侧不可达 |
| 401 on webhook | `auth_bearer` 不一致 |
| Skill 不可用 | 设置 `MILOCO_SKILLS_DIR` 或 clone 母仓 |
| Skill 与新版 Miloco 不一致 | **外部对接不会自动同步**；在 Skill clone 目录 `git fetch` + 更新 `plugins/skills` 后 **restart Sidecar**（见 §3.1） |
| 设备 Bash 失败 | 安装 miloco-cli：在有母仓时 `MILOCO_SKIP_CLI=0` 重装 install |
| HTTPS 外部 Server | `server.url` 写 `https://...`，Sidecar 已支持 |

---

## 九、与母仓全栈部署的区别

| | 全栈（miloco-stack.sh） | 仅 Sidecar（本文） |
|--|-------------------------|---------------------|
| Miloco Server | 本机母仓 backend 启动 | **外部**已有实例 |
| MILOCO_HOME | 通常 `docker/data` | 独立，如 `~/.miloco-agent-sidecar` |
| 母仓 clone | 需要 | **不需要** |
| `plugins/skills` | 随母仓 `git merge upstream` | **须手动同步**官方 Skill（§3.1） |
| model.omni | 与 Server 共用 config | 在外部 Server 配置 |

更多全栈说明见 [README.md](./README.md)。
