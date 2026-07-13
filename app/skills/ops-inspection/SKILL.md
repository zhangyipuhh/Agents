---
name: ops-inspection
description: "主动或定时触发项目巡检(定时模式对接 TaskSchedulerService 5 段 crontab),汇总检查项并产出报告;若发现异常则调用 feishu-sync 推送告警。2026-07-13 新增,当前为占位 SKILL.md,尚未实现 @tool。"
---

## Keywords (关键词)

- 巡检 (inspection)
- 主动巡检 (active-inspection)
- 定时巡检 (scheduled-inspection)
- 健康检查 (health-check)
- 巡检报告 (inspection-report)
- 异常告警 (anomaly-alert)

# Ops Inspection(占位 · 2026-07-13 新增)

> **占位声明**:本 skill 当前**仅作为巡检触发能力的占位**,尚未实现任何 `@tool` 工具,也没有真实定义巡检项。
> 当前项目代码库**未发现**巡检相关实现,后续 PR 需:
> 1. 定义巡检项清单(健康检查、配置漂移、日志异常、容量预警等)
> 2. 在 `app/shared/tools/skills/project/OpsTools.py` 中实现 `inspection_run` `@tool`
> 3. 主动模式:在 `AGENTS.md` 触发规则中匹配「主动巡检」类关键词后调用本 skill
> 4. 定时模式:通过 `app/routers/task_scheduler_router.py` 的现有定时任务能力注册周期巡检(`TaskSchedulerService` 已支持 5 段 crontab)
> 5. 单测 `app/tests/shared/tools/skills/project/test_ops_tools.py`

## 依赖关系

- **被依赖方**:`project` 智能体在用户发起「巡检一下」类请求时调用本 skill
- **依赖方(必须先实现)**:`feishu-sync`(异常告警推送) / `ops-log-aggregate`(巡检结果写日志)
- **定时任务依赖**:`TaskSchedulerService`(`app/shared/utils/agent/task_scheduler_service.py`)
- **数据库依赖(将来)**:本 skill 预计向 `inspection_runs` / `inspection_items` 表写入(具体 schema 待定)

## 占位工作流(待实现)

### 主动模式

- **Step 1**:用户发起「巡检」请求,智能体调用 `inspection_run`
- **Step 2**:遍历巡检项清单(健康检查 / 配置漂移 / 日志异常 / 容量预警),并行执行
- **Step 3**:聚合巡检结果,生成 Markdown 报告
- **Step 4**:若发现异常项,调用 `feishu_notify` 推送告警;调用 `change_ticket_create` 自动创建修改单(可选)
- **Step 5**:写库保存本次巡检记录

### 定时模式

- **Step 1**:通过 admin 接口在 `task_schedules` 表注册 `agent_name='project'`、`prompt='inspection_run'` 的周期任务
- **Step 2**:由 `TaskSchedulerService` 按 crontab 表达式自动触发,后续步骤同主动模式 Step 2-5

## 触发关键词

「巡检」「主动巡检」「定时巡检」「健康检查一下」「今天有定时巡检吗」等。
