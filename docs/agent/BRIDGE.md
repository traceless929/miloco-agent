# OpenClaw 生态桥接（miloco-agent Sidecar）

Miloco 官方 Agent 能力以 **OpenClaw 插件 + `plugins/skills`** 为契约交付。  
Sidecar **不修改**官方树，通过本桥接层复用同一套 Skill 与工具名，上游更新 Skill 后 Sidecar **无需同步改 Python Tool**。

## 三层架构

```
plugins/skills/*.md          ← 官方 Skill 唯一源（与 OpenClaw 相同）
        ↓ AgentScope LocalSkillLoader + Skill 工具
miloco-cli (Bash)            ← Skill 正文中的命令原样执行
        ↓
OpenClaw 专有工具（桥接）     ← 名称与语义与插件一致
```

| 层 | 负责方 | Sidecar 实现 |
|----|--------|--------------|
| **Skill 文档** | `plugins/skills/` | `bridge/skills.py` → `Toolkit(skills_or_loaders=...)` |
| **CLI 执行** | `miloco-cli` | `Bash`（`$MILOCO_HOME` 注入 + `cli_resolve` 自动解析） |
| **插件工具** | `plugins/openclaw` TS | `bridge/tools.py` 同名桥接 |
| **Prompt 注入** | `plugins/openclaw/src/hooks/prompt.ts` | `bridge/prompt.py` + `prompt/injection.py` |

## OpenClaw 工具桥接表

| OpenClaw 工具 | Sidecar 桥接 | 说明 |
|---------------|--------------|------|
| `miloco_im_push` | `bridge/notify.py` | 飞书 IM；`needsBind` / `bindHint` 与插件一致 |
| `miloco_notify_bind` | `bridge/notify.py` | 写入 `$MILOCO_HOME/agent/notify_channel.json` |
| `miloco_habit_suggest` | `tools/habit_suggest.py` | 同名工具包装 |
| `cron` | `bridge/tools.py` | 用户任务 cron（`user_cron_registry`） |
| `memory_search` | `bridge/memory.py` | 检索 `memory/*-miloco-perception.md` |
| （内置）`Skill` | AgentScope | 读 `SKILL.md` 全文 |
| （内置）`Bash` | AgentScope + `MILOCO_HOME` | 跑 `miloco-cli` |

**不再**为每个 Skill 维护平行 Python Tool（`device_list` 等保留在 `as_tools.build_legacy_toolkit` 仅供单测）。

## 配置

| 变量 | 作用 |
|------|------|
| `MILOCO_HOME` | 数据目录（config、memory、notify_channel） |
| `MILOCO_SKILLS_DIR` | 可选，覆盖默认 `plugins/skills` 路径 |

## 上游合并工作流

1. `git merge upstream/main` — `plugins/skills` 随官方更新
2. 重启 Sidecar — `LocalSkillLoader` 按文件 mtime 重载
3. 仅当 OpenClaw **新增插件工具名**时，才需在 `bridge/tools.py` 加桥接

## miloco-cli 自动适配与一键安装

Sidecar **不要求** `miloco-cli` 事先在系统 PATH 中：

1. **自动解析**（`bridge/cli_resolve.py`）：依次查找 PATH → Sidecar `.venv/bin` → `~/.local/bin`。
2. **Bash 注入**：Skill 里写的 `miloco-cli ...` 会通过 shell 函数解析到上述路径，**未安装时 Agent 仍可加载 Skill**，只是 CLI 相关命令会失败。
3. **一键安装**：管理台 **OpenClaw 桥接 → 环境修复 → 一键安装 miloco-cli**，或 API `POST /admin/api/bridge/install-cli`（`pip install -e <repo>/cli` 装进 Sidecar venv）。
4. **安装脚本**：`scripts/miloco-agent-install.sh` 默认也会 `pip install -e cli`。

## 通知频道配置

IM 推送（`miloco_im_push`、Cron 摘要等）需要知道**接收人的飞书 open_id**，任选其一：

| 方式 | 操作 |
|------|------|
| **A. 默认 open_id** | `config.json` → `agent.feishu.default_receive_open_id`（管理台 **飞书** 页可填） |
| **B. 管理台绑定** | **OpenClaw 桥接** 页填写 open_id →「绑定为通知频道」，写入 `$MILOCO_HOME/agent/notify_channel.json` |
| **C. 使用默认绑定** | 已配置 `default_receive_open_id` 后，点「用 default_receive_open_id 绑定」或 `POST /admin/api/bridge/bind-notify` 空 body |
| **D. 飞书对话** | 私聊机器人发送口令 `*#绑定#*`（须完全一致；同时写入会话绑定与 notify_channel） |
| **E. Agent 工具** | 在飞书会话中调用 `miloco_notify_bind` |

未配置时管理台显示 **通知频道 · 未绑定**，`miloco_im_push` 会返回 `needsBind: true` 及绑定提示。

## 管理台

`/admin` 概览与 **OpenClaw 桥接** 页展示：

- `plugins/skills` 路径与已注册 Skill 列表
- `miloco-cli` 是否在 PATH / venv（含 `can_install`、一键安装）
- 通知频道是否绑定（含 `default_receive_open_id`）
- 桥接工具名（`miloco_im_push`、`cron` 等）
- `profile.md` / 感知记忆文件数量

详见 [ADMIN_PLATFORM.md](./ADMIN_PLATFORM.md)。

## 代码入口

- `miloco_agent/bridge/toolkit.py` — `build_agentscope_toolkit()`
- `miloco_agent/bridge/prompt.py` — OpenClaw 对齐的静态 prompt
- `miloco_agent/runtime/agentscope_runtime.py` — 每 turn 传入 `MilocoBridgeContext`
