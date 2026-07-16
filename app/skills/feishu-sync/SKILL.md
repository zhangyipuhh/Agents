---
name: feishu-sync
description: "封装飞书 Open API 主动推送消息、文档或卡片；并通过 WebSocket 长连接被动接收私聊与群聊 @机器人 消息，转交 project 智能体处理后回复。"
---

## Keywords (关键词)

- 飞书 (feishu)
- 飞书通知 (feishu-notify)
- 飞书同步 (feishu-sync)
- 飞书消息 (feishu-message)
- 飞书文档 (feishu-doc)
- 飞书卡片 (feishu-card)
- 飞书机器人 (feishu-bot)
- 飞书 WebSocket (feishu-ws)

## 能力清单

### 主动推送（agent 调用）
- `send_feishu_message` 工具：向飞书群/用户发送文本消息

### 被动接收（系统级服务，非工具）
- `FeishuWebSocketService`：随 FastAPI lifespan 启停
- 订阅 `im.message.receive_v1` 事件
- 私聊（p2p）：全部回复
- 群聊（group）：仅响应 @机器人 消息
- 转交 `settings.feishu.feishu_ws_agent_name` 指定的智能体处理
- 回复通过 `client.im.v1.message.create` 直接发送

## 依赖关系

- 被依赖方：`requirement-ticket` / `change-ticket` / `ops-inspection` 调用 `send_feishu_message`
- 配置依赖：`feishu_app_id` / `feishu_app_secret` / `feishu_ws_enabled` / `feishu_ws_agent_name`

## 触发关键词

- 通常不直接由用户触发；被动接收模式下由飞书消息事件自动驱动
- 主动推送由 agent 通过 `send_feishu_message` 工具触发
