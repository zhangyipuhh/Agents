---
name: ops-log-aggregate
description: "汇总项目运维记录(巡检结果、告警条目、人工处理记录),按时间/类型/责任人维度聚合,生成运维日报/周报底稿。2026-07-13 新增,当前为占位 SKILL.md,尚未实现 @tool。"
---

## Keywords (关键词)

- 运维记录 (ops-log)
- 运维汇总 (ops-aggregate)
- 运维日报 (ops-daily)
- 运维周报 (ops-weekly)
- 巡检结果 (inspection-result)
- 告警聚合 (alert-aggregate)

# Ops Log Aggregate(占位 · 2026-07-13 新增)

> **占位声明**:本 skill 当前**仅作为 `project` 智能体定位扩展的占位**,尚未实现任何 `@tool` 工具,也没有真实读取运维日志的逻辑。
> 后续 PR 将补充:
> 1. `app/shared/tools/skills/project/OpsTools.py` 中 `ops_log_aggregate` / `ops_log_query` 两个 `@tool` 的实现
> 2. `references/` 下的运维日志数据源约定(日志文件路径、命名规范、字段 schema)
> 3. `seed_project_agent.py` 的 `PROJECT_AGENT_SKILLS` / `PROJECT_AGENT_TOOLS` 同步注册
> 4. 单测 `app/tests/shared/tools/skills/project/test_ops_tools.py`

## 依赖关系

- **被依赖方**:`requirement-ticket` / `change-ticket` / `ops-inspection` 在产出报告时可能引用本 skill 的查询结果作为依据
- **依赖方(将来)**:`TaskSchedulerService` 定时触发日报生成时,会路由到本 skill
- **数据库依赖(将来)**:本 skill 预计通过 `app/shared/utils/project/project_db.py` 风格的封装读取运维日志,具体表结构待定

## 占位工作流(待实现)

- **Step 1**:解析用户请求(日报 / 周报 / 自定义时间窗)
- **Step 2**:拉取时间窗内的运维日志(巡检结果、告警条目、人工处理记录)
- **Step 3**:按「时间 / 类型 / 责任人」三维聚合,生成 Markdown 底稿
- **Step 4**:可选调用 `feishu-sync` 把日报推送到指定飞书群

## 触发关键词

「运维记录汇总」「运维日报」「运维周报」「汇总本周巡检结果」「按责任人统计告警」等。
