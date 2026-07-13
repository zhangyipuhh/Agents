---
name: requirement-ticket
description: "向需求管理系统插入需求单,生成工单编号,随后调用 feishu-sync 通知相关干系人。2026-07-13 新增,当前为占位 SKILL.md,尚未实现 @tool。"
---

## Keywords (关键词)

- 需求单 (requirement-ticket)
- 需求管理 (requirement-mgmt)
- 需求录入 (requirement-create)
- 干系人通知 (stakeholder-notify)

# Requirement Ticket(占位 · 2026-07-13 新增)

> **占位声明**:本 skill 当前**仅作为需求单插入能力的占位**,尚未实现任何 `@tool` 工具,也没有真实对接需求管理系统(ZenTao / Jira / 自研)。
> 当前项目代码库**未发现**需求单相关 service,后续 PR 需:
> 1. 选定需求管理系统并封装其 API(ZenTao / Jira / 自研 HTTP API)
> 2. 在 `app/shared/tools/skills/project/OpsTools.py` 中实现 `requirement_ticket_create` `@tool`
> 3. `requirements/` 目录下补充需求字段 schema、必填校验、状态机
> 4. 单测 `app/tests/shared/tools/skills/project/test_ops_tools.py`

## 依赖关系

- **被依赖方**(将来):`ops-log-aggregate` 可能在汇总时引用本 skill 创建的需求单
- **依赖方(必须先实现)**:`feishu-sync`(创建完成后必须调用飞书通知)
- **数据库依赖(将来)**:本 skill 预计向 `requirement_tickets` 表写入(具体 schema 待定),用于反查与回填

## 占位工作流(待实现)

- **Step 1**:通过 `intent_clarification` 收齐必填字段(标题、描述、优先级、干系人列表、目标版本)
- **Step 2**:调用需求管理系统 API 创建工单,获取工单编号
- **Step 3**:写库(本系统)保存需求单快照 + 工单编号映射
- **Step 4**:调用 `feishu_notify` 把工单编号、链接、摘要推送到相关飞书群

## 触发关键词

「新建一个需求单」「录入需求」「创建工单」「发起需求评审」等。
