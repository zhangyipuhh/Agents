# 定时任务调度

定时任务调度模块负责**按 cron 表达式触发 SSH 巡检**与**手动执行巡检脚本**。所有调度记录在 `agent_task_schedules` 表中。

![定时任务调度](/help/screenshots/features-task-scheduler/01-task-scheduler.png)

## 前置条件

- 至少 1 台 `devops_servers`（admin 在「运维任务 → 服务器管理」配置）
- 至少 1 个 `inspection_scripts`（admin 在「运维任务 → 巡检脚本库」编辑）
- Docker daemon 运行（沙箱执行链路需要）
- `.env` 配置 `SANDBOX_*`（详见「[基本设置 → 沙箱与任务](/help/features/basic-settings#沙箱与任务)」）
- 用户被授予 `task-scheduler.scheduled` 菜单 ACL

## 核心字段

`agent_task_schedules` 表：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | TEXT | ✓ | 任务名（中文） |
| `cron_expression` | TEXT | ✓ | 标准 5 段 cron 表达式 |
| `server_ids` | JSONB | ✓ | 触发服务器列表（`devops_servers.id` 数组） |
| `script_id` | INTEGER | ✓ | 执行的 `inspection_scripts.id` |
| `enabled` | BOOL | | 默认 true |
| `agent_name` | TEXT | | 默认 `project`（智能体名） |
| `context_overrides` | JSONB | | 上下文覆盖（如 `referenced_servers`） |

## cron 表达式语法

### 5 段格式

```
* * * * *
│ │ │ │ │
│ │ │ │ └─ 星期几（0-6，0=周日）
│ │ │ └─── 月份（1-12）
│ │ └───── 日（1-31）
│ └─────── 小时（0-23）
└───────── 分钟（0-59）
```

### 常见示例

| 表达式 | 含义 |
|---|---|
| `0 2 * * *` | 每天凌晨 2:00 |
| `*/15 * * * *` | 每 15 分钟 |
| `0 9-18 * * 1-5` | 工作日 9:00-18:00 整点 |
| `0 0 1 * *` | 每月 1 日 0:00 |
| `30 2 * * 0` | 每周日 2:30 |

### 特殊字符

| 字符 | 含义 | 示例 |
|---|---|---|
| `*` | 任意值 | `*` = 每分钟 |
| `,` | 列举多个值 | `1,3,5` = 1/3/5 |
| `-` | 范围 | `1-5` = 1/2/3/4/5 |
| `/` | 步长 | `*/10` = 每 10 |
| `?` | 不指定（仅日/星期） | 仅在 Quartz cron 中使用 |

### 语法说明

- **不支持秒级精度**：标准 5 段 cron（不支持 6 段 Quartz）
- **不支持年份**：标准 5 段 cron（不支持 6 段扩展）
- **夏令时**：使用本地时区，按服务器系统时区

## 触发链路

### 手动触发

1. admin 在「运维任务 → 定时任务」点击「立即执行」
2. `POST /api/admin/task-schedules/{id}/run` 路由
3. 合成 `ScriptContext`：`schedule_id=<id>` / `run_id=0` / `trigger_type='manual'`
4. 复用 `run_server_ops` 路径
5. 落库 `server_inspection_records` 表

### 自动触发（cron）

1. 后台 cron scheduler 每分钟检查
2. 命中 cron 表达式 → 异步任务 `run_server_ops(...)`
3. SSH 执行（`SSHTools.execute_script` 或第三方执行器）
4. `save_inspection_result` 落库

### 触发链路图

```
cron 命中
  ↓
run_server_ops(schedule_id, run_id, trigger_type='cron')
  ↓
SSHTools.execute_script(server_id, script_id)
  ↓
SSH 执行 → 输出 parsed_values + field_results
  ↓
save_inspection_result(server_id, schedule_id, run_id)
  ↓
server_inspection_records 落库
  ↓
触发智能检测（若 enabled）
```

## 启停任务

### API
- `PUT /api/admin/task-schedules/{id}/enabled` body `{"enabled": true/false}`

### 效果
- `agent_task_schedules.enabled` 字段更新
- 后台 scheduler 立即生效（next tick 不再触发）
- 手动触发不受影响（可任意时刻手动执行）

## context_overrides 参数化

### 用途
- 注入 `referenced_servers` 列表（智能体 context）
- 注入 `project_id` / `session_id` 等

### 语法

```json
{
  "referenced_servers": [
    {"name": "business_1", "server_type": "linux"},
    {"name": "business_2", "server_type": "windows"}
  ],
  "project_id": "proj_001",
  "session_id": null
}
```

### 设置后效果
- 注入到 `build_agent_instance(context_overrides=...)`
- system prompt 中渲染 `<servers>` 动态节点 XML 后缀
- 智能体可按 `business_name` 精确反查

## 并发与队列

- `agent_chat_max_concurrency` 默认 5
- 触发执行超出并发上限时，进入 `chat_concurrency_dependency` 队列
- 前端展示「排队中」横幅

## 常见问题

### cron 表达式解析失败？
**错误文案**：`invalid cron expression`

**修复**：使用标准 5 段格式，不支持 Quartz 的 `?` 字符或年份字段。

### 任务执行失败？
**排查**：
1. 检查服务器在线（ping）
2. 检查 SSH 凭据
3. 查看 `server_inspection_records.error_message` 字段
4. 检查 `ssh_timeout`（默认 30 秒）

### 没有触发？
**排查**：
1. 检查 `enabled=true`
2. 检查 cron 表达式是否正确（`crontab.guru` 验证）
3. 检查服务器时区（`date` 命令）
4. 查看 scheduler 日志

## 相关章节

- [智能运维中心](/help/features/ops-console) — 服务器 / 巡检脚本库
- [基本设置 → 沙箱与任务](/help/features/basic-settings#沙箱与任务) — SANDBOX_* 配置
- [权限管理](/help/features/permission-management) — 菜单 ACL