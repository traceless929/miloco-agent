# Miloco Agent（替换 OpenClaw）

> **Fork 专属** · 独立 Sidecar，**不修改** Miloco 官方 `backend/` / `cli/` / `web/`。

## 文档

完整 **部署 / 配置 / 一键启动** 手册见子仓根目录 **[../README.md](../README.md)**（推荐从此读起）。

| 文档 | 说明 |
|------|------|
| [../README.md](../README.md) | 母仓/子仓结构、全栈部署、`miloco-stack.sh` |
| [../docs/EXTERNAL_MILOCO.md](../docs/EXTERNAL_MILOCO.md) | **仅 Sidecar 对接外部 Miloco** |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 架构设计：边界、Webhook 契约、Session、AgentScope |
| [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) | 分期开发计划 P0～P5、验收标准、合并策略 |
| [FEISHU_SETUP.md](./FEISHU_SETUP.md) | 飞书机器人接入与排错 |
| [ADMIN_PLATFORM.md](./ADMIN_PLATFORM.md) | Agent 管理配置台（:18789/admin） |
| [BRIDGE.md](./BRIDGE.md) | OpenClaw 生态桥接（Skill + 专有工具） |

## 一句话

用仓库根目录 **`miloco-agent/`** Sidecar（AgentScope + 飞书）兼容现有 `agent.webhook_url`，退役 OpenClaw；合并 [upstream](https://github.com/XiaoMi/xiaomi-miloco) 时官方树保持零改动。

## 独立仓库（Git Submodule）

`miloco-agent/` 已拆为独立仓库，主 fork 通过 **Git Submodule** 引用：

| 仓库 | 说明 |
|------|------|
| [traceless929/miloco-agent](https://github.com/traceless929/miloco-agent) | Sidecar 源码、测试、发布 |
| [traceless929/xiaomi-miloco](https://github.com/traceless929/xiaomi-miloco) | Fork 主仓（upstream 同步、`plugins/skills/`、官方 `backend/`） |

```bash
git clone --recurse-submodules https://github.com/traceless929/xiaomi-miloco.git

git submodule update --init --recursive

bash miloco-agent/scripts/miloco-stack.sh setup
bash miloco-agent/scripts/miloco-stack.sh start
```

Sidecar 日常开发可在 `miloco-agent/` 内独立 commit/push，再回到主仓 bump submodule 指针。

## 实现状态

| 阶段 | 状态 |
|------|------|
| P0 Webhook 骨架 | ✅ 已完成 |
| P1 AgentScope + 设备 Tools | ✅ 已完成 |
| P2 飞书 | ✅ 长连接 + MD/流式 + 多轮历史（`feishu:{open_id}`） |
| P3 通知 | ✅ policy + notify_send + TTS |
| P4 Cron/记忆/trace | ✅ 调度 + Tools + catalog + get_trace meta |
| P5 任务 Cron/运维 | ✅ user cron + agent_pending + 安装/supervisor 文档 |
| P6 管理配置平台 | ✅ `/admin` + API（LLM/飞书/Cron/桥接/P6+） |

（实现启动后更新上表。）
