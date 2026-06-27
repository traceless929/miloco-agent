# Miloco Agent 管理配置平台

> **Fork 专属** · Sidecar `:18789` 内置，**不修改** Miloco 官方 `web/`。

## 访问

```text
http://127.0.0.1:18789/admin
```

鉴权：请求头 `Authorization: Bearer <agent.auth_bearer>`（与 webhook 相同）。管理台页面会把 token 存到 `localStorage`。

侧栏 **OpenClaw 桥接** 页可检查：`plugins/skills` 是否就绪、`miloco-cli` 是否在 PATH、通知频道是否绑定。详见 [BRIDGE.md](./BRIDGE.md)。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin` | 静态管理台 HTML |
| GET | `/admin/api/status` | Sidecar / Server / LLM / 飞书 / Cron / **桥接** 状态 |
| GET | `/admin/api/bridge` | OpenClaw 桥接详情（Skill 目录、miloco-cli、工具列表） |
| POST | `/admin/api/bridge/install-cli` | 一键安装 miloco-cli 到 Sidecar venv |
| POST | `/admin/api/bridge/bind-notify` | 绑定飞书 open_id 为 IM 通知频道 |
| GET | `/admin/api/config` | 脱敏后的 `agent.*` 配置 |
| PATCH | `/admin/api/config` | 合并写入 `feishu` / `llm` / `cron`（**保存后自动热加载**） |
| POST | `/admin/api/reload` | 手动热加载配置并重启 Cron 调度器 |
| GET | `/admin/api/crons` | 受管 + 用户 Cron 列表 |
| POST | `/admin/api/crons/trigger` | 手动触发 Cron（`kind` + `name`/`job_id`） |
| POST | `/admin/api/crons/user` | 新增用户 Cron |
| PATCH | `/admin/api/crons/user/{job_id}` | 更新用户 Cron（含启用/禁用） |
| DELETE | `/admin/api/crons/user/{job_id}` | 删除用户 Cron |
| GET | `/admin/api/server/tasks` | 只读代理 Miloco Server `/api/tasks` |
| GET | `/admin/api/traces` | 最近 Agent turn 摘要（进程内 trace） |
| GET | `/admin/api/traces/files` | 落盘 jsonl.gz 文件列表（`$MILOCO_HOME/trace/agent/`） |
| DELETE | `/admin/api/traces/files/{run_id}` | 删除单个落盘 trace |
| POST | `/admin/api/traces/files/cleanup` | 批量清理（`run_ids` / `older_than_days` / `day` / `delete_all`） |
| GET | `/admin/api/traces/{run_id}` | 读取单回合 trace 事件（内存 meta + 落盘 jsonl） |
| POST | `/admin/api/ops/restart` | 重启 Sidecar（supervisor 或 `miloco-agent-restart.sh`） |
| GET | `/admin/api/sessions` | 飞书多轮会话文件摘要 |

### 配置写入规则

- 仅修改 `config.json` 的 `agent` 段，不触碰 `server` / `model` 等官方字段。
- 密钥字段若提交掩码值（`********` 开头）则**保留原值**。
- LLM / Cron 保存后会**自动热加载**；**飞书 app_id/secret 变更需重启 Sidecar 进程**才完全生效。

## 与官方 Web 的关系

| 能力 | 官方 Web `:1810` | Agent 管理台 `:18789` |
|------|------------------|------------------------|
| 设备 / 规则 / 任务 | ✅ | 只读任务列表代理 |
| 感知 / 家庭档案 | ✅ | — |
| Agent LLM / 飞书 / Cron | — | ✅ |
| OpenClaw 桥接（Skill / CLI） | — | ✅ |
| Agent turn 日志 / 重启 | — | ✅ |
| OpenClaw 退役后的 Agent 运维 | — | ✅ |

后续可选：在官方 Web 用 iframe / 链接跳转本管理台，仍不改 backend 契约。

## 安全建议

- `agent.auth_bearer` 务必设置强随机值（`miloco-agent-install.sh` 会自动生成）。
- 管理台默认与 Sidecar 同端口，**不要**将 `:18789` 暴露到公网。
- 家用场景绑定 `127.0.0.1` 或 LAN + 反代鉴权即可。

## P6+ 已实现

| 项 | 说明 |
|----|------|
| Server 任务代理 | `GET /admin/api/server/tasks` |
| 用户 Cron 管理 | 管理台表单 + REST 增删改 |
| 运行日志 | `GET /admin/api/traces` +「运行日志」页；Cron 回合自动落盘 jsonl.gz，可点「查看」展开工具/LLM 事件 |
| Sidecar 重启 | `POST /admin/api/ops/restart`；可用 `MILOCO_AGENT_SUPERVISOR` 走 supervisorctl |

### Trace 落盘（对齐 OpenClaw）

- 路径：`$MILOCO_HOME/trace/agent/YYYYMMDD/<runId>__<query>.jsonl.gz`
- **Cron** 会话（`session_key` 以 `cron:` 开头）每回合自动落盘，无需开 debug
- 非 Cron：与 OpenClaw 相同，需 `config.json` 中 `"debug": true` 或存在 `$MILOCO_HOME/.debug_observability`
- 单日上限 300 个文件；`jsonlPath` 写入 turn meta，管理台「运行日志」可查看
