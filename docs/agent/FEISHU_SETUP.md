# 飞书 IM 接入指南（Miloco Agent Sidecar）

> Fork 专属 · 配合 `miloco-agent` P2 飞书通道

## 接入方式

| 模式 | 配置 `mode` | 说明 |
|------|-------------|------|
| **长连接（推荐，默认）** | `long_connection` | Sidecar **主动出站**连飞书 WebSocket，**无需公网 IP / ngrok** |
| Webhook 回调 | `webhook` | 飞书 **POST** 到你的公网 `https://.../feishu/webhook`，需验签/解密 |

长连接基于官方 `lark-oapi` SDK，仅支持**企业自建应用**；每应用最多 50 条连接。

## 1. 开放平台配置（长连接）

1. 登录 [飞书开放平台](https://open.feishu.cn/app) 创建企业自建应用
2. 开启 **机器人** 能力
3. **权限**（按需申请）：
   - `im:message` — 获取与发送单聊、群组消息
   - `im:message:send_as_bot` — 以应用身份发消息
   - `cardkit:card:write` — 流式卡片（`stream_reply: true` 时需要）
4. **事件订阅** → 选择 **「使用长连接接收事件」**（不要填请求 URL）
5. 订阅事件：`im.message.receive_v1`（接收消息）
6. 记录 **App ID**、**App Secret**

长连接模式下 **不需要** `verification_token` / `encrypt_key`。

## 2. Sidecar 配置

写入 `$MILOCO_HOME/config.json` 的 `agent.feishu`：

```json
{
  "agent": {
    "feishu": {
      "enabled": true,
      "mode": "long_connection",
      "app_id": "cli_xxxxxxxx",
      "app_secret": "xxxxxxxx",
      "default_receive_open_id": "ou_xxxxxxxx"
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `mode` | `long_connection`（默认）或 `webhook` |
| `app_id` / `app_secret` | 长连接鉴权 + 发消息 `tenant_access_token` |
| `verification_token` / `encrypt_key` | 仅 **webhook** 模式需要 |
| `default_receive_open_id` | MVP 单用户：主动通知默认收件人；绑定表为空时允许该用户对话 |

### 回复格式

| 配置 | 说明 |
|------|------|
| `reply_format: "markdown"`（默认） | 交互卡片 `markdown` 组件，表格/列表会渲染 |
| `reply_format: "text"` | 纯文本，不渲染 MD |
| `stream_reply: true`（默认） | CardKit 流式打字机；需权限 `cardkit:card:write` |
| `stream_interval_s: 0.5` | 流式更新节流间隔（秒） |

流式失败时会自动降级为一次性 Markdown 卡片。

```json
"feishu": {
  "reply_format": "markdown",
  "stream_reply": true
}
```


## 3. 启动与验证

```bash
MILOCO_HOME=./docker/data bash miloco-agent/scripts/miloco-agent-run.sh
```

启动后日志应出现 `feishu long-connection thread started`。

1. 在开放平台保存长连接事件订阅（应用需已发布或可用范围包含你）
2. 在飞书私聊机器人发送：**列出在线设备**
3. Agent 处理完成后应收到文本回复（LLM + 工具调用可能需十余秒）

> 飞书要求事件在约 3s 内 ack；Sidecar 在 WS 回调里**异步**投递到主事件循环处理，避免阻塞 SDK。

## 4. Webhook 模式（可选）

若必须用公网回调，设置 `"mode": "webhook"` 并配置：

```
https://<公网域名>/feishu/webhook
```

同时填写 `verification_token`、`encrypt_key`（若开启加密）。

## 5. 用户绑定（可选）

- 无绑定文件时：任意用户可对话（开发期）
- 发送口令 **`*#绑定#*`**（须完全一致，避免日常对话误触「绑定」）：将当前 `open_id` 写入会话绑定与 `notify_channel.json`
- 可选别名：`*#绑定miloco#*`、`*#绑定通知#*`
- 有绑定记录后：仅已绑定用户可对话

## 6. 与 Miloco Server 的关系

| 链路 | 入口 |
|------|------|
| 用户飞书对话 | 长连接 `im.message.receive_v1` → `TurnRunner` → 飞书回复 |
| 规则 / 建议 / 绑定 | Server `POST /miloco/webhook`（不变） |

感知、规则、设备 API 仍由 **Miloco Server** 提供；Sidecar 不修改 `backend/`。

## 7. 排错

| 现象 | 处理 |
|------|------|
| 长连接未建立 | 检查出站能否访问飞书；日志是否有 `feishu long-connection`；App ID/Secret |
| 开放平台保存订阅失败 | 确认已选「长连接」且 Sidecar 进程在运行 |
| Webhook 保存地址失败 | 公网可达、`mode=webhook`、返回 challenge |
| 401 bad signature | 仅 webhook：核对 token / encrypt_key |
| 收消息无回复 | Sidecar 日志；`agent.llm` 有效；Server `:1810` 可达 |
| 403 Kimi | Kimi Code 需白名单 User-Agent（Sidecar 已自动处理） |
