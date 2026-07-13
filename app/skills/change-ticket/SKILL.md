---
name: change-ticket
description: "向变更管理系统插入修改单,记录变更内容、影响范围、审批流,随后调用 feishu-sync 通知审批人。2026-07-13 新增,当前为占位 SKILL.md,尚未实现 @tool。"
---

## Keywords (关键词)

- 修改单 (change-ticket)
- 变更管理 (change-mgmt)
- 变更申请 (change-request)
- 审批流 (approval-flow)
- 影响范围 (impact-scope)

# Change Ticket(占位 · 2026-07-13 新增)

> **占位声明**:本 skill 当前**仅作为修改单插入能力的占位**,尚未实现任何 `@tool` 工具,也没有真实对接变更管理系统。
> 当前项目代码库**未发现**修改单相关 service,后续 PR 需:
> 1. 选定变更管理系统并封装其 API(可能与需求管理系统共用一套,也可能独立)
> 2. 在 `app/shared/tools/skills/project/OpsTools.py` 中实现 `change_ticket_create` `@tool`
> 3. `references/` 目录下补充变更影响范围评估模板、回滚方案模板
> 4. 单测 `app/tests/shared/tools/skills/project/test_ops_tools.py`

## 依赖关系

- **被依赖方**(将来):`ops-inspection` 巡检发现的「需变更修复」项会转交给本 skill
- **依赖方(必须先实现)**:`feishu-sync`(创建完成后必须调用飞书通知审批人)
- **数据库依赖(将来)**:本 skill 预计向 `change_tickets` 表写入(具体 schema 待定),关联到对应 `requirement_ticket`(可选)

## 占位工作流(待实现)

- **Step 1**:通过 `intent_clarification` 收齐必填字段(变更标题、变更原因、影响范围、回滚方案、审批人列表、计划上线时间)
- **Step 2**:调用变更管理系统 API 创建工单,获取工单编号
- **Step 3**:写库(本系统)保存修改单快照 + 工单编号映射
- **Step 4**:调用 `feishu_notify` 把工单编号、影响范围摘要、回滚方案链接推送到审批人飞书账号

## 触发关键词

「新建修改单」「发起变更」「创建变更申请」「录入变更影响范围」等。
