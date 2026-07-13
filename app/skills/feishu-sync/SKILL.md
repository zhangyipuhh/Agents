---
name: feishu-sync
description: "封装飞书 Open API 推送消息、文档或卡片(被 requirement-ticket / change-ticket / ops-inspection 调用的被依赖基础能力)。2026-07-13 新增,当前为占位 SKILL.md。"
---

## Keywords (关键词)

- 飞书 (feishu)
- 飞书通知 (feishu-notify)
- 飞书同步 (feishu-sync)
- 飞书消息 (feishu-message)
- 飞书文档 (feishu-doc)
- 飞书卡片 (feishu-card)

# Feishu Sync(占位 · 2026-07-13 新增)

> **占位声明**:本 skill 当前**仅作为飞书同步能力的占位**,尚未实现任何 `@tool` 工具,也没有真实对接飞书 Open API。
> 当前项目代码库**未引入**飞书 SDK / lark SDK 依赖(见 phase 1 探索结果),后续 PR 需:
> 1. 选择飞书 SDK(`lark-oapi` 优先)并在 `app/requirements.txt` 中加依赖
> 2. 通过 MCP 适配器方式(参考项目已有 `mcp_registry` 模式)或直接 SDK 方式接入
> 3. 在 `app/shared/tools/skills/project/OpsTools.py` 中实现 `feishu_notify` `@tool`
> 4. 单测 `app/tests/shared/tools/skills/project/test_ops_tools.py`

## 依赖关系(关键 · 必须先实现本 skill)

- **被依赖方**:`requirement-ticket`(通知干系人) / `change-ticket`(通知审批人) / `ops-inspection`(推送异常告警) 都依赖本 skill
- **依赖方**:`mcp_registry` 注入的飞书 MCP server(将来)
- **配置依赖**:`app/core/config/settings.py` 中需新增 `feishu_app_id` / `feishu_app_secret` / `feishu_default_chat_id` 等敏感配置,通过环境变量注入

## 占位工作流(待实现)

- **Step 1**:接收调用方传入的目标(群 / 用户)、内容(文本 / 卡片 / 文档链接)、优先级
- **Step 2**:从 `app.state` 读取飞书 access_token(走标准的 tenant_access_token 流程)
- **Step 3**:调用飞书 Open API 发送消息;记录发送时间戳、消息 ID、调用方
- **Step 4**:返回发送结果(成功 / 失败 / 重试建议)给调用方

## 触发关键词

通常**不直接由用户触发**,而是由其他运维 skill 在内部调用(`requirement_ticket_create` / `change_ticket_create` / `inspection_run`)。
