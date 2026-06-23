# miloco-agent

Fork 专属 Sidecar：兼容 Miloco `agent.webhook_url` 契约，用于替换 OpenClaw Gateway + Plugin。

## 要求

- Python **≥ 3.11**（独立 venv，不并入 `backend/` workspace）
- 已运行的 Miloco Server（`miloco-cli service start`）
- 可选：`miloco-cli` 在 PATH（设备 catalog 注入）

## 快速开始

```bash
# 安装（仓库根目录）
bash scripts/miloco-agent-install.sh

# 启动（默认 :18789）
bash scripts/miloco-agent-run.sh
```

确保 `$MILOCO_HOME/config.json` 中：

```json
{
  "agent": {
    "webhook_url": "http://127.0.0.1:18789/miloco/webhook",
    "auth_bearer": "<与安装脚本生成的一致>",
    "llm": { "base_url": "...", "model": "...", "api_key": "..." },
    "feishu": {
      "enabled": true,
      "mode": "long_connection",
      "app_id": "...",
      "app_secret": "...",
      "history_turns": 10
    },
    "cron": { "enabled": true, "timezone": "Asia/Shanghai" }
  }
}
```

## 7×24 运行

```bash
export MILOCO_REPO=/path/to/xiaomi-miloco
export MILOCO_HOME=$HOME/.openclaw/miloco
# 参考 scripts/miloco-agent-supervisor.conf.example 配置 supervisor
```

## 功能概览

| 模块 | 说明 |
|------|------|
| Webhook | `agent` / `get_trace` 兼容 Server AgentDispatcher |
| **管理台** | `http://127.0.0.1:18789/admin` — LLM/飞书/Cron 配置 |
| 设备 Tools | list / spec / control / TTS |
| 通知 | notify_send + 分级策略 |
| 飞书 | 长连接 + MD/流式 + 多轮历史（`feishu:{open_id}`） |
| 家庭记忆 Cron | digest / patrol / dreaming / habit-suggest |
| 用户任务 Cron | `cron_add` / `cron_remove` + task link |
| Trace | turn meta 供 observability poller 消费 |

## 开发

```bash
cd miloco-agent
uv sync --extra dev
uv run pytest -q
uv run miloco-agent
```

## 排错

| 现象 | 处理 |
|------|------|
| webhook 401 | 检查 `agent.auth_bearer` 与请求头一致 |
| 飞书无回复 | 确认 `feishu.enabled`、应用权限、长连接进程日志 |
| catalog 为空 | 确认 Server 已启动且 `miloco-cli device catalog` 可执行 |
| Cron 不跑 | `agent.cron.enabled=true` 后重启 Sidecar |

文档见 [docs/agent/](../docs/agent/README.md)。

## OpenClaw 退役对照

| OpenClaw | miloco-agent |
|----------|--------------|
| `/miloco/webhook` | `webhook/` |
| Agent turn | `runtime/turn_runner.py` |
| device catalog 注入 | `prompt/catalog.py` |
| home-profile cron | `cron/jobs.py` + `cron/user_registry.py` |
| miloco_habit_suggest | `tools/habit_suggest.py` |
| trace / get_trace | `trace/store.py` |
| 飞书 IM | `channels/feishu/` |
