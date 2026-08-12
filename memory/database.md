# 数据库设计

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## 数据库设计

### message_feedback 表（2026-07-02 新增）

AI 回复的赞/踩反馈入库表。同一用户对同一条 AI 回复只能保留一种反馈（赞/踩互斥），踩时可填写问题描述、问题类型、期望的样子，用于运营/算法团队分析质量问题。

| 字段                  | 类型                         | 必填 | 说明                                                          |
| --------------------- | ---------------------------- | ---- | ------------------------------------------------------------- |
| id                    | SERIAL PRIMARY KEY           | 是   | 自增主键                                                      |
| user_id               | INTEGER FK → users (CASCADE) | 是   | 操作用户 ID，删除用户时其全部反馈记录一并删除                  |
| session_id            | VARCHAR(100)                 | 是   | 所属会话 ID                                                    |
| message_id            | VARCHAR(64)                  | 是   | 前端消息 ID（与 ChatArea message.id 对齐）                      |
| feedback_type         | VARCHAR(16)                  | 是   | `like`（赞）/ `dislike`（踩），CHECK 约束                       |
| problem_type          | VARCHAR(32)                  | 否   | 仅踩时填写：`factual_error` / `logic_error` / `off_topic` / `other` |
| problem_description   | TEXT                         | 否   | 踩时用户填写的"问题描述"（多行文本）                            |
| expected_answer       | TEXT                         | 否   | 踩时用户填写的"期望的样子"                                      |
| message_content       | TEXT                         | 否   | 用户原始问题内容快照                                           |
| ai_reply              | TEXT                         | 否   | AI 回复内容快照                                                |
| agent_name            | VARCHAR(64)                  | 否   | 当前绑定的 Agent 名称                                          |
| user_agent            | VARCHAR(255)                 | 否   | 浏览器 UA 字符串                                                |
| created_at            | TIMESTAMP                    | 是   | 入库时间，默认 `NOW()`                                          |

索引：`idx_message_feedback_user_id` / `idx_message_feedback_session_id` / `idx_message_feedback_type` / `idx_message_feedback_created_at`（DSC） / `idx_message_feedback_user_session_message`（UNIQUE，保证同一用户同一会话同一条消息只有一种反馈）

**接口**：`POST /api/agent/message-feedback`（`app/routers/agent_router.py`，与 `/api/agent/chat` 同前缀，本接口为该文件本次**唯一**新增的端点）。同一用户同一条消息已有反馈时，后端使用 `INSERT ... ON CONFLICT ... DO UPDATE` 更新为最新反馈，保证赞/踩互斥。401（未登录）/ 400（feedback_type 非法）/ 503（内存模式）/ 201（成功）。

**前端组件**：`web/Agent/src/components/DislikeDialog.vue`（踩时弹窗）+ `web/Agent/src/utils/api.js::submitMessageFeedback`（工具方法）+ `App.vue::handleLike` / `handleDislike` 改造。

**降级**：内存模式（`AUTH_STORAGE_MODE=memory`）下后端返回 503，前端 catch 后 toast "反馈功能仅在数据库模式下可用"，不阻塞用户继续聊天。

### agent_task_schedules / agent_task_runs 表（2026-07-10 新增）

智能体定时任务采用**应用内调度**，不为每条业务任务写入 Windows Task Scheduler 或 Linux cron/systemd timer；数据库是任务定义与执行历史的真相源。服务重启时由 `app/core/server.py::lifespan()` 初始化 `TaskSchedulerService`，从 `agent_task_schedules` 加载 `enabled=true` 的任务注册到 APScheduler；服务停机期间错过的触发不补跑，重启后按下一次计划时间执行。每次触发都会创建新的 `session_id`，并复用 `AgentConfigService.build_agent_instance()` 构造智能体，确保 AGENTS.md、Skill 绑定与工具绑定和聊天路径一致。

`agent_task_schedules` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | SERIAL PRIMARY KEY | 定时任务 ID |
| name | VARCHAR(200) | 任务名称 |
| description | TEXT | 任务描述 |
| agent_name | VARCHAR(100) FK → agents(name) | 目标智能体（target_type='agent' 时必填，'script' 时为 NULL） |
| prompt | TEXT | 定时触发时发送给智能体的提示词（target_type='agent' 时必填） |
| cron_expression | VARCHAR(100) | 5 段 crontab 表达式，如 `0 9 * * *` |
| timezone | VARCHAR(64) | IANA 时区，默认 `Asia/Shanghai` |
| enabled | BOOLEAN | 是否启用 |
| created_by_user_id | INTEGER FK → users(id) | 创建人，用于后台执行时创建 session |
| context_overrides | JSONB | 注入 AgentContext 的扩展字段，默认 `{}` |
| max_concurrent_runs | INT | 单任务并发配置，默认 1 |
| target_type | VARCHAR(16) DEFAULT 'agent' | 目标类型：`agent`（智能体）或 `script`（脚本） |
| script_name | VARCHAR(100) | 目标脚本名（target_type='script' 时必填，'agent' 时为 NULL） |
| script_args | JSONB | 脚本参数，默认 `{}`（target_type='script' 时使用） |
| notify_enabled | BOOLEAN NOT NULL DEFAULT FALSE | 脚本任务完成后是否按 notify_policy_id 发送通知邮件 |
| notify_policy_id | INTEGER FK → email_policies(id) ON DELETE SET NULL | 邮件策略 ID；删除策略时自动置 NULL |
| last_run_at / next_run_at | TIMESTAMP | 最近运行与下次运行时间 |
| created_at / updated_at | TIMESTAMP | 创建与更新时间 |

`agent_task_runs` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | SERIAL PRIMARY KEY | 执行记录 ID |
| schedule_id | INTEGER FK → agent_task_schedules(id) | 所属定时任务 |
| session_id | VARCHAR(100) | 本次触发创建的新会话 ID |
| agent_name | VARCHAR(100) | 执行时智能体名称快照（agent 任务） |
| prompt_snapshot | TEXT | 执行时提示词快照 |
| status | VARCHAR(32) | `pending` / `running` / `success` / `failed` / `skipped` |
| trigger_type | VARCHAR(32) | `scheduled` / `manual` |
| target_type | VARCHAR(16) DEFAULT 'agent' | 目标类型快照 |
| script_name | VARCHAR(100) | 目标脚本名快照（script 任务） |
| scheduled_at / started_at / finished_at | TIMESTAMP | 计划、开始、结束时间 |
| duration_ms | INTEGER | 执行耗时毫秒 |
| output_text | TEXT | 最后一条 AI 消息文本 |
| error_message | TEXT | 失败或跳过原因 |
| created_at | TIMESTAMP | 记录创建时间 |

**接口**：`app/routers/task_scheduler_router.py`，前缀 `/api/admin/task-schedules`，全部受 `require_admin_or_menu_acl('task-scheduler.scheduled')` 保护；提供列表、详情、新建、更新、删除、启停、立即运行与执行历史查询。`CreateTaskScheduleRequest` / `UpdateTaskScheduleRequest` 通过 Pydantic `model_validator(mode="after")` 跨字段校验 `target_type` 与 `agent_name`/`prompt`/`script_name` 一致性。每个端点构造 `OwnershipScope.from_request(request)` 透传 service；普通用户（含被授权 ACL 的非 admin）仅见/管自己创建的 schedule（2026-07-24 起，详见「通用配置归属隔离」落地三），越权/缺失统一 404。

**服务**：`app/shared/utils/agent/task_scheduler_service.py::TaskSchedulerService`，由 lifespan 真实初始化到 `app.state.task_scheduler_service`；测试中只能注入真实 service 实例，不允许通过 `app.state.db = MagicMock()` 虚构生产不存在的依赖。`execute_schedule` 根据 `target_type` 分支：`agent` 复用 `build_agent_instance + agent.invoke`；`script` 通过 `script_discovery_service.get_script()` 取 `RegisteredScript`，构造 `ScriptContext` 调用 `registered.func(context)`，把返回值用 `normalize_script_result` 拆为 `(body, attachments)` 后写入 `output_text`。当 `notify_enabled=True` 且 `notify_policy_id` 非空时，调用 `_dispatch_script_email` 按策略模板渲染并通过 `EmailService.send_email` 发邮件（fail-soft：邮件失败仅记 warning，不污染 run 状态）。`TaskSchedulerService.__init__` 新增 `email_config_service` 入参（可选），由 `app/core/server.py::lifespan` 在初始化时透传 `app.state.email_config_service`。

### 脚本定时任务系统（target_type='script'）

定时任务支持 `target_type='script'` 类型，允许把 `app/scripts/` 下用 `@register_script` 装饰的 Python 异步函数绑定为定时任务，与智能体任务共用 `agent_task_schedules` 表、调度器、执行历史与日志文件。

**脚本扫描源**：`app/scripts/` 目录（`paths.SCRIPTS_DIR`），递归扫描 `.py` 文件，跳过 `__init__.py` / `base.py` / `registry.py` 与下划线开头文件；通过 `importlib.util.spec_from_file_location` 动态加载触发 `@register_script` 装饰器执行。

**注册契约**：`app/scripts/registry.py::register_script(name, display_name, description="", params_schema=None)` 装饰 `async def run(context: ScriptContext) -> ScriptResult` 函数；`ScriptContext`（`app/scripts/base.py`，Pydantic BaseModel）含 `schedule_id`/`run_id`/`session_id`/`schedule_name`/`script_args`/`log_logger`/`started_at`/`trigger_type` 字段。

**返回值约定（`ScriptResult`）**：`str`（向后兼容旧契约，输出文本无附件）或 `(body, attachments)` 元组（`body=str`，`attachments=str / list[str] / None`）。`app/scripts/base.py::normalize_script_result` 把返回值归一化为 `(body, attachments_list)`；非白名单类型抛 `ScriptExecutionError`。调度器把 `body` 写入 `agent_task_runs.output_text`，把 `attachments_list` 作为通知邮件附件路径（仅当任务配置 `notify_enabled=True`）。

**发现服务**：`app/shared/utils/agent/script_discovery_service.py::ScriptDiscoveryService(scripts_dir: Path)`，由 lifespan 在 `settings.script_scan_enabled=True` 时初始化到 `app.state.script_discovery_service`；提供 `scan()`（返回 `{scanned, registered, failed}`）、`list_scripts()`（白名单字段：`name`/`display_name`/`description`/`params_schema`/`module_path`）、`get_script(name)`（返回含 `func` 引用的 `RegisteredScript`）。

**管理接口**：`app/routers/script_admin_router.py`，前缀 `/api/admin/scripts`，全部受 `require_admin` 保护；提供 `GET /api/admin/scripts`（白名单字段列表）与 `POST /api/admin/scripts/scan`（触发扫描，返回 `ScanSummary`）。

**脚本参数表单元数据契约**：`params_schema.properties.server_list` 仅在同时满足 `type=array`、`items.type=string`、`x-control=server-multiselect`、`x-source=devops-servers`、`x-value-field=business_name` 时由前端识别；`uniqueItems=true`，默认值为 `[]`。`server_list` 的持久化类型固定为 `list[str]`，元素为 `devops_servers.business_name`。`script_args` 继续使用开放字典与 JSONB 存储，schema 未声明或前端暂不支持的旧参数在编辑、保存时原样保留。

**`api_list` 系统级标准参数**（2026-07-22 新增）：`params_schema.properties.api_list` 仅在 `type=array`、`items.type=string`、`x-control=api-multiselect`、`x-source=api-configs`、`x-value-field=id` 时由前端识别；与 `server_list` 并列接入同一「添加参数」下拉与 `scriptParamValues` 容器；元素为 API 节点 id 字符串（如 `"12"`）。脚本侧统一通过 `app.scripts.api_check.run_api_checks(context)` 获取 `ApiCheckReport`（`items` / `total` / `passed` / `failed` / `skipped` + `summary_line()` / `to_markdown()` / `to_dict()`），适用于报告、附件、邮件正文。前端控件候选复用 `GET /api/admin/api-configs/tree`，按 `node_type==='api'` + 白名单 id/parent_id/node_type/name/sort_order 过滤，沿父文件夹链拼 path 用于展示；失效 id 显示「已失效」chip 与 server_list 一致。

**`server_list` 系统级标准参数**（2026-07-22 与 `api_list` 对齐补全）：`params_schema.properties.server_list` 仅在 `type=array`、`items.type=string`、`x-control=server-multiselect`、`x-source=devops-servers`、`x-value-field=business_name` 时由前端识别；元素为服务器业务名字符串（`devops_servers.business_name`）。脚本侧统一通过 `app.scripts.server_ops.run_server_ops(context)` 获取 `ServerOpsReport`（`items` / `total` / `passed` / `failed` / `skipped` + `summary_line()` / `to_markdown()` / `to_dict()`），命令来源是 `devops_servers.inspection_script_id` 外键引用 `inspection_scripts` 表的脚本原文（每台服务器关联一个巡检脚本条目），不在脚本入参中重复指定；前端控件候选复用 `GET /api/admin/devops-servers`，脱敏白名单 `id` / `business_name` / `server_type` / `updated_at`，失效业务名显示「已失效」chip。

### `inspection_scripts` 巡检脚本库表（2026-08-03 新增）

巡检脚本原文、解析器类型与字段规则从 `devops_servers` 三列内联存储抽离到独立 `inspection_scripts` 表；`devops_servers` 仅保留 `inspection_script_id` 外键引用。脚本按「平台 + 版本」命名（如 `linux-bash` / `windows-ps-5.1` / `windows-ps-7+`），`inspection_fields` 完全跟随脚本库条目，服务器层不可覆盖。详细字段级契约见 [devops-sandbox.md § 巡检脚本库 `inspection_scripts`](devops-sandbox.md#巡检脚本库-inspection_scripts)。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | SERIAL PRIMARY KEY | 主键 |
| name | VARCHAR(100) UNIQUE NOT NULL | 脚本库条目唯一标识（如 `linux-bash` / `windows-ps-5.1`） |
| display_name | VARCHAR(200) NOT NULL | 展示名称 |
| platform | VARCHAR(32) NOT NULL DEFAULT 'linux' | `linux` / `windows` |
| version | VARCHAR(32) NOT NULL DEFAULT '' | 版本字符串（`windows-ps-5.1` / `windows-ps-7+` 等） |
| inspection_parser | VARCHAR(16) NOT NULL DEFAULT 'json' | 解析器类型：`json` / `kv` / `csv` / `raw`（CHECK `inspection_scripts_parser_chk`） |
| inspection_script | TEXT NULL | bash / powershell 巡检脚本原文（多行） |
| inspection_fields | JSONB DEFAULT '[]'::jsonb | 字段规则列表（dict 形如 `{key, name_zh, unit, direction, warn, crit}`） |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引**：`idx_inspection_scripts_platform(platform)` / `idx_inspection_scripts_name(name)`

**数据源**：`InspectionScriptService.scan_and_upsert` 读取 `<项目根>/data/devops/inspection_scripts.yaml` → `INSERT ... ON CONFLICT (name) DO UPDATE ... RETURNING *, (xmax = 0) AS inserted`；2026-08-04 改造为「编辑优先」：DB 中已有 `name` 时**跳过**更新，保留人工编辑；同 name 重复（YAML 内）直接拒绝（不覆盖）；`scanned / inserted / updated / failed / skipped` 5 字段整数返回。

### 服务器采集落库表（2026-08-05 新增）

`server_inspection_records`（append-only 历史表）+ `server_latest_snapshot`（每服务器一行快照，双表同事务双写）：

| 表 | 列 / 类型 / 必填 / 说明 |
|---|---|---|
| `server_inspection_records` | `id BIGSERIAL PK` / `server_id INTEGER NOT NULL REFERENCES devops_servers(id) ON DELETE CASCADE` / `business_name VARCHAR(200) NOT NULL`（冗余快照） / `collected_at TIMESTAMPTZ NOT NULL DEFAULT now()` / `schedule_id INTEGER NULL REFERENCES agent_task_schedules(id) ON DELETE SET NULL` / `run_id INTEGER NULL REFERENCES agent_task_runs(id) ON DELETE SET NULL` / `inspection_script_id INTEGER NULL REFERENCES inspection_scripts(id) ON DELETE SET NULL` / `created_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL`（手动采集审计） / `success BOOLEAN NULL` / `skipped BOOLEAN NOT NULL DEFAULT FALSE` / `exit_code INTEGER NULL` / `duration_ms INTEGER NULL` / `inspection_status VARCHAR(16) NOT NULL DEFAULT 'unassessed'`（CHECK：`pass / warn / crit / unassessed / skipped`） / `error_message TEXT NULL` / `inspection_error TEXT NULL` / `parsed_values JSONB NULL` / `field_results JSONB NOT NULL DEFAULT '[]'::jsonb` / `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` |
| `server_latest_snapshot` | `server_id INTEGER PK FK→devops_servers ON DELETE CASCADE` / `record_id BIGINT NOT NULL FK→server_inspection_records ON DELETE CASCADE` / `business_name / collected_at / success / inspection_status / duration_ms / error_message / parsed_values / field_results`（冗余列） / `updated_at TIMESTAMPTZ` |

索引：`idx_sir_server_time(server_id, collected_at DESC)` / `idx_sir_collected_at(collected_at DESC)` / `idx_sir_run_id(run_id)`。

**数据归属**：`server_id` 指向 `devops_servers.id`（按物理服务器）；多用户共享同一份采集数据（指标是服务器事实，不随用户变）；手动采集触发的写入 `created_by_user_id` 供审计，定时采集为 `NULL`。

**双写契约（生产唯一落库入口）**：`app/shared/utils/server_inspection_record_service.py::ServerInspectionRecordService.save_inspection_result` 在单事务（`async with self._db.acquire() as conn: async with conn.transaction():`）内 `INSERT records ... RETURNING id` → `INSERT snapshot ... ON CONFLICT (server_id) DO UPDATE`（与 `InspectionScriptService.delete_script` 同款事务模式，杜绝历史与快照不一致）。

**写入链路**：
* 定时：`ops_inspection_sweep` 在 `run_server_ops(context)` 返回后 fail-soft 调 `save_inspection_result(report, schedule_id=..., run_id=...)`（异常仅记日志，不影响 docx/邮件）；
* 手动：`POST /api/admin/server-inspection/collect`（路由层组合，合成 ScriptContext → `run_server_ops` → `save_inspection_result(report, created_by_user_id=scope.user_id)`）。

**查询 API**：
* `list_latest(scope)` — admin 透传全量 `devops_servers` LEFT JOIN snapshot；普通用户按 `user_server_nodes`（`node_type='server'`）过滤、按 `server_id` 去重、按 `sort_order,node_id` 排序；service 层派生 `status`（pass→ok / warn,crit,success=False→err / skipped,unassessed,无快照→unknown）与 `metrics.cpu/mem/disk`（linux `100-cpu_idle_pct`、windows `cpu_used_pct`；根盘优先取 `disks[].disk_used_pct`：`/`（linux）/ `C:\\`（windows，大小写不敏感），无则取第一块，仍无 → `null`）；响应**不含 ip**（遵循脱敏约定）。
* `list_records(server_id, scope, start=None, end=None, limit=100)` — admin 仅校验 server 存在；普通用户需在可见节点集内；越权 → `None`（路由层 404，不回显 id）。

### `devops_servers` 巡检脚本外键改造（2026-08-03）

- 旧三列 `inspection_script TEXT` / `inspection_parser VARCHAR(16)` / `inspection_fields JSONB`（含对应 CHECK 约束 `devops_servers_inspection_parser_chk`）已通过 `DROP COLUMN IF EXISTS` / `DROP CONSTRAINT IF EXISTS` 强制移除（不再保留旧三列向前兼容）
- 新增 `inspection_script_id INTEGER NULL REFERENCES inspection_scripts(id) ON DELETE SET NULL`；索引 `idx_devops_servers_inspection_script_id`
- 升级路径：按计划文档 `.trae/documents/devops-inspection-script-library-plan.md` 一次性迁移旧三列内容到 `inspection_scripts` → 回填 `devops_servers.inspection_script_id` → 再执行 `DROP COLUMN IF EXISTS`
- 外键约束 `devops_servers_inspection_script_id_fk` 通过 `DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT` 实现幂等
- 详细字段级契约见 [devops-sandbox.md § 数据库表 `devops_servers`](devops-sandbox.md#数据库表-devops_servers2026-07-15-新增2026-08-03-改造)

**hello_script 脚本开发样板**：`app/scripts/examples/hello_script.py` 注册名为 `hello_script` / 展示名 `脚本开发样板`，是后续脚本开发的复制模板。参数 `mode`（默认 `text`）控制运行模式，`content`（默认 `定时任务执行成功`）控制输出正文，`server_list`（默认 `[]`）提供目标服务器业务名数组，`api_list`（默认 `[]`）提供 API 节点 id 数组。签名严格为 `async def run(context: ScriptContext) -> str | tuple[str, list[str]]`。

- **参数读取**：`context.script_args` 中读取 `mode` / `content` / `server_list` / `api_list`；`server_list` / `api_list` 缺失时按空数组处理，非列表、包含非字符串或空字符串时抛 `ScriptExecutionError`；`api_list` 还会额外校验每个元素必须是整数形式的字符串 id。
- **服务器参数语义**：`server_list` 元素为 `business_name`；样板只演示读取、校验、日志与摘要输出，不读取连接配置、不执行 SSH。
- **接口参数语义（`api_list`）**：元素为「API接口配置」树中 api 节点 id 的字符串形式；样板通过 `await run_api_checks(context)` 逐 id 执行 `ApiConfigService.send_request`（httpx 代理发送 + Mock/expectations 断言校验 + 落库 `api_check_runs`）；单条失败不中断整体，缺失节点产生 `check_passed=None` 的 skipped 项，其他异常产生 `check_passed=False` 的 failed 项；返回统一 `ApiCheckReport` 结构，正文追加 `api_check=<P>/<N> passed | id=... OK/FAIL/MISSING` 摘要；`mode=multi` 时 `.md` 附件还会包含 `report.to_markdown()` 接口清单表格。
- **服务器参数语义（`server_list`）**：元素为 `business_name`；样板通过 `await run_server_ops(context)` 对每台服务器读取解密后的连接配置（`DevOpsServerService.get_connection_config`），执行预存的 `inspection_script` 巡检脚本（命令来源是该字段，**不在脚本入参中指定**）；逐台结果封装为 `ServerOpsItem`（含 SSH 执行字段 + 巡检字段 `inspection_parser` / `parsed_values` / `field_results` / `inspection_status` / `inspection_error`），`ServerOpsReport` 提供 `summary_line()` / `to_markdown()` / `to_dict()` 三种输出，并附 `inspection_passed/warned/critical/unassessed` 4 项巡检计数；单台失败（鉴权 / 连接超时 / paramiko 异常 / 未配置 `inspection_script` / 解析评估失败等）**不中断**整体；缺少 `inspection_script` 产生 skipped 项；正文追加 `server_ops=<P>/<N> passed | inspection=pass:N,warn:N,crit:N,unassessed:N | biz-A OK(0,42ms)/PASS` 摘要；`mode=multi` 时 `.md` 附件含 8 列运维结果表格；阻塞 SSH 调用经 `asyncio.to_thread` 包装避免阻塞事件循环（验证：心跳协程在执行期间可继续推进）。
- **纯文本返回（`mode=text`）**：直接 `return summary`，无附件。
- **单附件返回（`mode=single`）**：生成一个 `.txt` 附件，返回 `(summary, [attachment_path])`。
- **多附件返回（`mode=multi`）**：生成 `.txt` 与 `.md` 两个附件，返回 `(summary, [path1, path2])`；当 `api_list` 非空时 `.md` 包含 `## 接口健康检查` 章节。
- **异常演示（`mode=error`）**：抛出 `ScriptExecutionError`，由调度器标记 run 为 `failed`。
- **正文摘要**：基础格式为 `f"{content} | schedule={schedule_name} (run_id={run_id}, trigger={trigger_type}, started_at=...)"`；`server_list` 非空时在末尾追加 ` | server_list=<business_name,...>`；`api_list` 非空时再追加 ` | api_check=<...>`，两者均为空数组时保持基础摘要不变。
- **附件路径约定**：`TASK_ATTACHMENT_DIR/{slugify_task_name(schedule_name)}/{started_at.strftime("%Y%m%d_%H%M%S")}_{run_id}.{ext}`
- **异步 IO**：附件写入通过 `await asyncio.to_thread(path.write_text, ...)` 执行，不阻塞调度器事件循环。
- **异常语义**：参数非法或 `mode=error` 时抛 `ScriptExecutionError`；`api_list` 非空且 `context.api_config_service is None` 时同步抛错；IO 异常向上透出，由 `TaskSchedulerService.execute_schedule()` 标记 run 为 `failed`。

**依赖**：`app.core.config.paths`（`TASK_ATTACHMENT_DIR` / `slugify_task_name`） + `app.scripts.base.ScriptContext` / `ScriptExecutionError` + `app.scripts.registry.register_script` + `app.scripts.api_check.run_api_checks` + `app.scripts.server_ops.run_server_ops`。**不依赖** `ToolRuntime` / 地图 store / `ProjectSiteSelectionCollection` / `WordReportGenerator`。

**`ops_inspection_sweep` 运维巡检扫描正式脚本**（2026-07-22 新增；`app/scripts/ops/ops_inspection_sweep.py`）：与 `hello_script`（开发样板，演示 4 种 mode 与附件生成）**职责正交**——`hello_script` 是「全契约演示 + 多模式附件生成」，`ops_inspection_sweep` 是「生产巡检细节日志输出 + 纯文本摘要」。两者签名与参数契约完全一致（`server_list` + `api_list`），可在同一台调度器上并存。

- **注册信息**：`@register_script(name="ops_inspection_sweep", display_name="运维巡检扫描", ...)`；模块路径 `app.scripts.ops.ops_inspection_sweep`，由 `ScriptDiscoveryService.rglob("*.py")` 自动发现并加载到注册表，无需手动 `import`。
- **包结构**：`app/scripts/ops/__init__.py` 为包标识；脚本与测试分别为 `app/scripts/ops/ops_inspection_sweep.py` 与 `app/tests/scripts/ops/test_ops_inspection_sweep.py`。
- **签名**：`async def run(context: ScriptContext) -> "ScriptResult"`，其中 `ScriptResult = Union[str, Tuple[str, Optional[Union[str, List[str]]]]]`。Phase D 起 `run` 返回 docx 附件时退化为 ``(body, [docx_path])`` 元组，docx 生成失败时退化为 ``body`` 字符串（fail-soft），与 `hello_script` 的 ``str | tuple[str, list[str]]`` 行为对齐。
- **复用契约（关键设计）**：脚本层**不重写** SSH 循环与 HTTP 检查循环，直接复用 `app.scripts.server_ops.run_server_ops(context)` + `app.scripts.api_check.run_api_checks(context)` 的全量报告结构，确保 SSH 失败 / 解析失败 / 评估失败 / 节点缺失等异常分级与全项目保持一致；脚本层只做「日志渲染 + 摘要汇总」两层职责，符合「高内聚低耦合 + 统一入口」原则。
- **参数 schema**：`params_schema.properties` 同时声明 `server_list`（`x-control=server-multiselect` / `x-source=devops-servers` / `x-value-field=business_name`）与 `api_list`（`x-control=api-multiselect` / `x-source=api-configs` / `x-value-field=id`），与 `hello_script` 完全一致；二者均默认 `[]`、元素为非空字符串、`uniqueItems=true`。
- **逐字段日志输出（与 `hello_script` 的差异核心）**：
  - **服务器巡检**：对 `ServerOpsReport.items` 每台服务器——
    - skipped 项只打印「`server biz=<name> SKIPPED reason=<reason>`」一行，**不**打印 `parsed_values` / `field_results`。
    - SSH 失败项只打印「`FAIL exit=<code> duration=<ms>ms parser=<parser> error=<err> inspection=<状态>`」+ 「`inspection_error=<err>`」（如有），**不**打印字段明细，避免误导。
    - SSH 成功项打印「`OK exit=0 duration=<ms>ms parser=<parser> inspection=<pass|warn|crit|unassessed> fields=<N>`」 + 「`parsed_values=<JSON>`（`ensure_ascii=False`，不可序列化时降级为 `repr`）」 + 每条 `field_results` 元素的「`field[<i>] key=<k> name=<zh> unit=<u> value=<v|none> direction=<d> warn=<n> crit=<n> -> <PASS|WARN|CRIT|未评估> [msg=<...>]`」。
    - `field_results=[]`（即 `inspection_status="unassessed"`）时打印「无可评估字段」一行。
  - **接口健康检查**：对 `ApiCheckReport.items` 每个接口——
    - 节点缺失（`check_passed=None`）只打印「`api id=<n> name=<name> MISSING reason=<reason>`」。
    - 其余打印「`api id=<n> name=<name> path=<p> http=<code|null> duration=<ms|null> passed=<bool>`」 + （如有错误）「`error=<msg>`」 + 每条 `assertion_results` 的「`assertion[<i>] type=<t> passed=<bool> [detail=<...>]`」。
- **返回值（Phase D 起为邮件正文 + docx 附件）**：
  - 基础段保留：`f"ops_inspection_sweep | schedule=<name> (run_id=<n>, trigger=<type>, started_at=<%Y-%m-%d %H:%M:%S>)"`。
  - `server_list` 非空时追加 ` | server_ops=<summary_line()>`；`api_list` 非空时再追加 ` | api_check=<summary_line()>`；两者均空数组或缺失键时**仅返回基础段**。
  - **Phase D 改造（2026-07-23）**：`run` 改为 `ScriptResult` 契约，返回值结构如下：
    - **body 部分**：`build_ops_email_body(...)` 构造的中文邮件正文（任务元数据 + 综述段落 + 关键告警列表 + 附件提示行），末尾追加原 `base_summary + server_ops + api_check` 旧摘要以保持数据库 `output_text` 可读性。
    - **附件部分**（`docx_path` 非 `None` 时）：返回 ``(body, [docx_path])`` 二元组；docx 文件实际落盘到 `TASK_ATTACHMENT_DIR/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.docx`。
    - **fail-soft**：`docx` 模块生成抛任何异常时，try/except 吞掉并把 `docx_path` 重置为 `None`，run 退化为只返回 `body` 字符串，避免调度器把整 run 标记为失败。
  - docx 报告内容由 `ReportConfig`（`ops_report.build_ops_report_config`）驱动，包含封面（主标题「沈阳不动产运维报告」+ 时间 + 任务名）、目录、综述、网络检查、服务器基本情况按业务循环（含元信息表 + 字段明细表或失败说明段）、接口健康检查按接口循环。
- **异常透传**：`server_list` 非空且 `devops_server_service is None` / `api_list` 非空且 `api_config_service is None` 时，由 `run_server_ops` / `run_api_checks` 直接抛 `ScriptExecutionError`，脚本不捕获；参数非法由 `resolve_server_list` / `resolve_api_list` 抛错。
- **日志写入位置**：所有细节日志通过 `context.log_logger.info(...)` 写入 `data/logs/Task/{slugify_task_name(schedule_name)}/{started_at:%Y%m%d_%H%M%S}_{run_id}.log`，与 `hello_script` 共享同一 run-level logger 注入点（`TaskSchedulerService._install_run_logger`）。
- **依赖**（Phase D 后扩展）：`app.scripts.base.ScriptContext` / `register_script` / `run_server_ops` / `run_api_checks` + `app.scripts.server_ops.ServerOpsReport` / `app.scripts.api_check.ApiCheckReport` + `app.scripts.ops.ops_report.compute_ops_summary` / `compute_ops_alerts` / `resolve_server_ip_map` / `build_ops_report_config` / `build_ops_email_body` + `app.core.config.paths.resolve_task_attachment_path` + `app.shared.utils.report.word.generator.WordReportGenerator`。docx 同步生成经 `await asyncio.to_thread(_generate_docx_report, ...)` 包装避免阻塞事件循环；IP 反查走 `context.devops_server_service`（`getattr(context, "devops_server_service", None)`），缺失/KeyError/异常统一返回 `None` 由报告渲染为 `-`，不中断整体流程。

**修复触发（2026-07-22 上线后立即发现并修复）**：第一次生产触发 `POST /api/admin/task-schedules/4/trigger`（执行 `ops_inspection_sweep`）即抛 `ScriptExecutionError: devops_server_service 不可用,无法执行 server_list 巡检`。根因是 `app/core/server.py::lifespan` 初始化顺序错误——DevOpsServerService / ApiConfigService 块位于 TaskSchedulerService 之后,导致 `TaskSchedulerService.__init__` 通过 `getattr(app.state, "devops_server_service"/"api_config_service", None)` 拿到 None 并永久缓存到 `self._devops_server_service` / `self._api_config_service`。修复:将两个 service 初始化块前移到 TaskSchedulerService 构造之前（详见「lifespan 初始化顺序」章节步骤 7-8）。回归保护:`app/tests/core/test_task_scheduler_lifespan.py` 新增 `test_lifespan_initializes_devops_server_before_task_scheduler` + `test_lifespan_initializes_api_config_before_task_scheduler`（源码顺序静态断言）+ `app/tests/core/test_server_lifespan.py` 既有的 `test_lifespan_injects_devops_server_service_into_task_scheduler` / `test_lifespan_injects_api_config_service_into_task_scheduler`（注入身份断言 `is`）。**EmailConfigService 顺序一直正确**（在 TaskSchedulerService 之前）,所以 `_dispatch_script_email` 从未暴露该 bug,本次 `ops_inspection_sweep` 启用 `server_list` 后才暴露。
- **测试**：`app/tests/scripts/ops/test_ops_inspection_sweep.py`（26 用例，Phase D +2，Phase E +1）—— P0：模块可导入、注册到 registry、`async def run(context: ScriptContext) -> ScriptResult` 签名（Phase D 由 `str` 升级为 `ScriptResult`）、params_schema 同时声明 `server_list` + `api_list` 且 UI 扩展契约正确；P1：空入参仅返回基础段 + 日志输出「无巡检项」/「无检查项」/「执行完成」；P1 server 路径：逐字段日志含 `parsed_values` + 每条规则 `key/name_zh/value/warn/crit -> 状态`、skipped 项不打印字段明细、SSH 失败项只打印错误摘要、`field_results=[]` 输出「无可评估字段」；P1 api 路径：逐接口日志含 `http/duration/passed` + 每条断言 `type/passed/detail`、节点缺失只打印 `MISSING + 原因`；P1 异常路径：`server_list` + service 不可用 / `api_list` + service 不可用均向上抛 `ScriptExecutionError`；P1 组合：`server_list` 与 `api_list` 同时非空时摘要同时追加两段（`server_ops` 在 `api_check` 前）；P2 工具函数：`_format_field_log`（pass / 缺失值 + message）/ `_format_assertion_log`（含 detail / 无 detail）/ `_safe_json_dumps`（dict / 不可序列化对象降级 `repr`）；P1 docx 生成（含 Task D1 + D2）：`_resolve_attachment_path` 返回 `.docx` 后缀且文件名遵循 `YYYYMMDD_HHMMSS_{run_id}.docx` 模板、`_generate_docx_report` 同步生成 > 1000 字节文件并按 `构造 → generate → save(path)` 顺序调用 `WordReportGenerator`、`run` 成功路径返回 ``(body, [docx_path])`` 元组且文件确实落盘、`run` docx 失败 fail-soft 退化为 `body` 字符串；**P1 docx 真实端到端（Phase E 新增）**：`test_run_real_docx_generation_end_to_end` 通过 sys.modules 快照-恢复机制（参照 `test_table_section.py::test_render_table_section_produces_docx`，清掉 conftest 安装的 docx Mock + 重新 import 真实 python-docx），调用 `ops_inspection_sweep.run()` 走完 `build_ops_report_config → WordReportGenerator → Document.save()` 全链路，断言 docx > 10KB 且 `Document.paragraphs + tables` 文本含「沈阳不动产运维报告」标题（避免 fake ZIP 头通过却不证明真实渲染工作）。回归保护：autouse fixture `_isolate_script_registry` 在每个用例前后清空 `_SCRIPT_REGISTRY`，避免 `hello_script` / `ops_inspection_sweep` 测试相互污染；`_attach_capture` / `_detach_capture` 自定义日志 capture handler 临时把 logger 级别降为 `DEBUG` 并卸载，避免默认 WARNING 级别吞掉 INFO 记录；Phase D 新增的 `_install_docx_fake_and_tmp_path` helper 同时 patch `WordReportGenerator`（绕过 `app/tests/conftest.py` 全局 mock 的 `docx` 模块）与 `_resolve_attachment_path`（重定向到 `tmp_path`，避免污染真实 `data/attachments/Task/` 目录），让 fake 生成器在 `save()` 中写出 `> 1000` 字节占位 zip 头以验证文件确实落盘且大小满足契约。

**`app/scripts/api_check.py` 标准化检查器**（2026-07-22 新增）：系统级标准 `api_list` 的统一入口。所有声明 `api_list` 的脚本都通过 `run_api_checks(context) -> ApiCheckReport` 获取一致的检查结果结构，避免各自手写循环。

- **数据类**：`ApiCheckItem`（frozen；`node_id` / `name` / `path` / `check_passed` / `http_status` / `duration_ms` / `error_message` / `run_id` / `assertion_results`），`ApiCheckReport`（`items` + 计数属性 `total` / `passed` / `failed` / `skipped` + 方法 `summary_line()` / `to_markdown()` / `to_dict()`）。
- **`resolve_api_list(script_args) -> list[int]`**：缺失/None/空数组 → `[]`；非列表 / 含非字符串 / 含空字符串 / 含非整数串 → 抛 `ScriptExecutionError`，消息含 `api_list`，便于调度器日志定位。
- **`run_api_checks(context, api_list=None) -> ApiCheckReport`**：`api_list` 参数缺省时从 `context.script_args.api_list` 调用 `resolve_api_list`；空 ids → 返回 `items=[]`；非空但 `context.api_config_service is None` → 抛错；其余沿 `service.get_tree()` 构建 `id → {name, path, node_type}` 映射（含多级文件夹父路径），逐 id 调用 `service.send_request`，捕获 `ApiConfigNotFoundError` → skipped，其他异常 → failed，**不中断**整体循环。
- **扫描隔离**：`app/shared/utils/agent/script_discovery_service.py::_SKIP_FILENAMES` 追加 `api_check.py`，避免被 ScriptDiscoveryService 误识别为脚本（标准库上下文里无 `@register_script`，双重加载会产生双模块身份）。
- **`ScriptContext.api_config_service`**：`app/scripts/base.py::ScriptContext` 新增 `api_config_service: Any = None` 字段；`arbitrary_types_allowed=True` 已开启，无需额外 Pydantic 配置。
- **调度器透传**：`TaskSchedulerService.__init__` 新增 `api_config_service: Optional[Any] = None` 入参；`execute_schedule` 的 script 分支构造 `ScriptContext` 时透传 `self._api_config_service`。
- **lifespan 注入**：`app/core/server.py::lifespan` 构造 `TaskSchedulerService` 时 `api_config_service=getattr(app.state, "api_config_service", None)`；`ApiConfigService` 在前面「API接口配置」章节已固定为 lifespan 初始化块，顺序约束满足。

**`app/scripts/server_ops.py` 标准化巡检执行器**（2026-07-22 新增；Task 3 落地）：与 `api_check.py` 完全对称，但面向**真实 SSH 巡检执行**而非 HTTP 健康检查。脚本声明 `server_list` 后，通过 `run_server_ops(context) -> ServerOpsReport` 获取统一执行结果结构。

- **数据类**：
  - `ServerOpsItem`（frozen）字段：`business_name` / `success` / `exit_code` / `stdout` / `stderr` / `duration_ms` / `error_message` / `skipped` / `inspection_parser` / `parsed_values` / `field_results`（元素为 `InspectionFieldResult.vars()` 形式 dict：`key` / `name_zh` / `unit` / `value` / `status` / `message` / `warn` / `crit`）/ `inspection_status` / `inspection_error`。
  - `ServerOpsReport`（`items` + 计数属性 `total` / `passed` / `failed` / `skipped` **+ 4 项巡检计数** `inspection_passed` / `inspection_warned` / `inspection_critical` / `inspection_unassessed`，**`skipped` 不计入 4 项巡检计数任何一项** + 方法 `summary_line()` / `to_markdown()` / `to_dict()`）。
- **`resolve_server_list(script_args) -> list[str]`**：缺失/None/空数组 → `[]`；非 list / 含非字符串 / 含空字符串 → 抛 `ScriptExecutionError`，消息含 `server_list`。
- **`inspection_fields` 序列化唯一真相源契约（2026-07-22 强化）**：`DevOpsServerService.get_connection_config(business_name)` 返回的 `inspection_fields` 字段是 **`list[InspectionFieldRule]`**（frozen dataclass，元素含 `key` / `name_zh` / `unit` / `direction` / `warn` / `crit` 属性）；service 在 `preload_all` / `_normalize_entry` / `get_connection_config` 阶段统一调用 `normalize_inspection_fields` 完成 dict→dataclass 转换。**`app/scripts/*` 任何模块（含 `server_ops._run_one`）一律不**调用 `normalize_inspection_fields`**，service 是序列化/结构化的唯一真相源。`_cache` 中保留 `list[dict]`（与 DB / YAML 形态一致），dict→InspectionFieldRule 转换在 `get_connection_config` **只此一处**。脚本侧对 `config["inspection_fields"]` 做 `isinstance(raw, list)` 防御性断言，回退空列表应对老 cache 或测试 stub；该契约由 `test_run_server_ops_does_not_re_normalize_inspection_fields`（断言 `server_ops` 模块不导出 / 不调用 `normalize_inspection_fields`）+ `test_run_server_ops_stub_service_mimics_real_normalization`（断言 stub 返回 `InspectionFieldRule` 列表）双重锁住。
- **`run_server_ops(context, server_list=None, *, ssh_timeout=30) -> ServerOpsReport`**：`server_list` 缺省时从 `context.script_args.server_list` 调用 `resolve_server_list`；空 names → 返回 `items=[]`；非空但 `context.devops_server_service is None` → 抛错；其余沿 `service.get_connection_config(business_name)` 取解密配置（`inspection_fields` 由 service 保证为 `list[InspectionFieldRule]`，直接喂给 `evaluate_inspection_fields`），逐台执行预存的巡检脚本（`asyncio.to_thread(ssh.executor.execute_script, ...)` 包装避免阻塞事件循环）；保留输入顺序；**单台任何阶段失败均不中断整体**。
- **`get_connection_config` 返回 14 键（2026-08-04 改造）**：`ip` / `port` / `username` / `password` / `server_type` / `blacklist` / `whitelist`（基础 7）+ 脚本原文三键 `inspection_script` / `inspection_parser` / `inspection_fields` + 脚本库元数据四键 `inspection_script_name` / `inspection_script_display_name` / `inspection_script_platform` / `inspection_script_version`（来自 `inspection_scripts` 表，由 `InspectionScriptService.get_script_by_id` 间接加载）。4 个元数据键供 `ServerOpsItem` 透传到脚本层日志 / docx / 邮件正文选择性展示，**不**包含 `inspection_script_id`（避免与 `_cache` 内部 id 混淆）。
- **异常分级契约**（按 `_run_one` 分支）：
  1. `get_connection_config` 抛 `KeyError`（业务名未注册） → `skipped=True` + `success=None` + `error_message` / `inspection_error` 含 KeyError 原文。
  2. `get_connection_config` 抛 `ValueError`（`inspection_script_id` 为空 / 脚本库条目不存在 / `InspectionScriptService` 未注入 三种 skipped 场景主动抛出） → `skipped=True` + `success=None` + `error_message` / `inspection_error` **直接透传** ValueError 原文（不再走旧版「未配置巡检脚本（inspection_script 为空）」文案）。
  3. `get_connection_config` 抛其他异常（解密失败 / Fernet 错配） → `success=False` + `inspection_status="crit"` + `error_message="配置解析失败: Type: message"` + `inspection_error` 同上；**不**泄漏 `ip` / `password` / 整个 config。
  4. `execute_script` 抛异常（paramiko `AuthenticationException` / `SSHException` 等） → `success=False` + `duration_ms` 非 None + `inspection_status="crit"` + `error_message` / `inspection_error` 含 `Type: message`，**不**泄漏 config。
  5. `SSHExecResult.exit_code != 0`（含 `success=False`） → `success=False` + `inspection_status="crit"`，**不**调用 `parse_inspection_output` / `evaluate_inspection_fields`；`stdout` / `stderr` / `exit_code` / `duration_ms` 保留；`error_message` / `inspection_error` 取 `stderr`（strip）或固定文案「远端巡检脚本执行失败」。
  5b. `exit_code == 0` 但 stderr 非空（shell 启动噪音，如远端 `.bashrc` 语法错误；`SSHExecResult.success=False` 但退出码为 0） → **不**判失败，继续走解析评估；stderr 保留在 `item.stderr` 供报告「错误」列展示；解析/评估失败仍按分支 6 判 `crit`。
  6. 解析 / 评估阶段异常（`InspectionParseError` / `ValueError` 等） → `success=False` + `inspection_status="crit"`；`stdout` / `stderr` / `exit_code` / `duration_ms` 保留；`error_message` / `inspection_error` 统一为「巡检解析评估失败: Type: message」，**不**泄漏 config（stdout 内的解析错误片段可保留）。
  7. 评估成功但 `evaluation.status == "crit"`（raw+结构化规则 / 字段缺失 / 非数值 / 阈值严重命中） → `success=(exit_code == 0)` **不变**（即 SSH 退出码 0 仍为 `True`），仅 `inspection_status="crit"` + 字段级 message；评估 `evaluation.error_message` 透传到 `inspection_error`。
- **`inspection_status` 取值**：`pass` / `warn` / `crit` / `unassessed` / `skipped`。`success` 与 `inspection_status` 解耦：`success` 反映「SSH 退出码为 0」的执行语义（stderr 非空不判失败，典型来源：远端 shell 启动文件如 `/root/.bashrc` 的语法错误，非交互式 SSH 会话每次都会触发）；`inspection_status` 反映脚本输出按规则评估的语义学判定——SSH 退出码 0 → `success=True`，但若评估命中 crit 仍可 `inspection_status="crit"`。
- **summary_line 契约**：
  - 旧契约保持：`server_ops=<P>/<executed> passed` + 可选 `, <skipped> skipped` + `; ` 分隔的 `biz-X OK(0,42ms)` / `biz-X FAIL(1,45ms)` / `biz-X SKIPPED`。
  - 新增：` | inspection=pass:N,warn:N,crit:N,unassessed:N`（`skipped` 不计入）。
  - 每项详情追加 `/PASS|WARN|CRIT|UNASSESSED|SKIPPED` 大写状态后缀。
  - 示例：`server_ops=3/4 passed, 1 skipped | inspection=pass:1,warn:1,crit:1,unassessed:1 | biz-A OK(0,42ms)/PASS; biz-B OK(0,30ms)/WARN; biz-C FAIL(2,10ms)/CRIT; biz-E SKIPPED/SKIPPED`。
- **to_markdown 契约**：列顺序固定 8 列：业务名 / 结果 / 退出码 / 耗时(ms) / stdout 摘要 / 错误 / **巡检状态** / **指标判定**。
  - 状态中文映射：`pass → 通过` / `warn → 告警` / `crit → 严重` / `unassessed → 未评估` / `skipped → 未执行`。
  - 指标判定格式（每字段）：`中文名 原值+单位 状态/消息 warn=<n> crit=<n>`，多字段以 `; ` 分隔；空 unit 不附加。
  - stdout 截断到 4000 字符 + `...` 后缀（与 api_check_runs.response_body 一致）。
  - 所有动态字段（业务名 / stdout / 错误 / 字段中文名 / 字段 message）的换行替换为空格、`|` 替换为 `\|`，避免 markdown 列解析错误。
  - skipped 行指标判定列内容：`error_message or inspection_error or "未执行"`，整体过 ``_escape_cell`` 转义；不再硬编码「未配置巡检脚本」分支，KeyError / 巡检脚本未配置等 skipped 原因如实展示。
- **to_dict 契约**：顶层 = `items` + `total` + `passed` + `failed` + `skipped` + **`inspection_passed`** + **`inspection_warned`** + **`inspection_critical`** + **`inspection_unassessed`**；每个 item = 老 8 字段 + **`inspection_parser`** + **`parsed_values`** + **`field_results`** + **`inspection_status`** + **`inspection_error`**；可直接 `json.dumps(..., ensure_ascii=False)`。
- **命令来源**：`devops_servers.inspection_script_id` 外键引用 `inspection_scripts` 表（2026-08-03 抽离；旧 `devops_servers.inspection_script TEXT` 三列已移除），不再由脚本入参指定，与 `api_list` 复用 `service.send_request` + Mock 的模式形成完全对称。
- **扫描隔离**：`app/shared/utils/agent/script_discovery_service.py::_SKIP_FILENAMES` 追加 `server_ops.py`，避免被 `ScriptDiscoveryService` 误识别为脚本。
- **`ScriptContext.devops_server_service`**：`app/scripts/base.py::ScriptContext` 新增 `devops_server_service: Any = None` 字段；与 `api_config_service` 并列。
- **调度器透传**：`TaskSchedulerService.__init__` 新增 `devops_server_service: Optional[Any] = None` 入参；`execute_schedule` 构造 `ScriptContext` 时透传 `self._devops_server_service`。
- **lifespan 注入**：`app/core/server.py::lifespan` 构造 `TaskSchedulerService` 时 `devops_server_service=getattr(app.state, "devops_server_service", None)`；`DevOpsServerService` 在 lifespan 第 357 行附近初始化，早于 `TaskSchedulerService`，顺序约束天然满足。
- **测试**：`app/tests/scripts/test_server_ops.py` 共 50 用例（原 22 + Task 3 新增 20 + 审查加固 5 + `inspection_fields` 序列化唯一真相源契约 3 用例：`test_run_server_ops_does_not_re_normalize_inspection_fields` 锁住"脚本侧**不**调用 `normalize_inspection_fields`"、`test_run_server_ops_handles_unexpected_inspection_fields_type` 锁住"老 cache / 非 list 输入走防御性类型断言回退 [] 不抛错"、`test_run_server_ops_stub_service_mimics_real_normalization` 锁住"`_StubDevOpsService` 必须模拟 service 返回 `list[InspectionFieldRule]`，调用方无需再 normalize"）全绿；覆盖 4 项巡检计数（含 skipped 不计）、summary 追加 `inspection=...` 与每项状态后缀、to_markdown 8 列与中文渲染 + 管道换行转义、to_dict 4 项巡检计数 + item 新字段、JSON pass；解析 / 评估 / SSH 失败各级异常分级与 `success` 解耦；KV / CSV 数字字符串 pass；raw+规则 crit 但 success 仍 True；缺字段 / 非数值 crit；无规则 unassessed；非法 JSON 一台失败但下一台继续；SSH 失败直接 crit 且不调 parse_inspection_output；执行异常与 skipped 的 inspection_error；skipped 指标判定列如实展示 error_message / inspection_error 并转义（含 KeyError 路径、inspection_script 未配置路径、全部为空时回退「未执行」）；stdout 截断边界精确（4000 x 保留 / 4001 x 截断加 `...`）；inspection_fields 序列化契约（service dataclass 注入 / 脚本侧不重复归一化）。

**lifespan 初始化顺序**（2026-07-22 修复 DevOpsServerService / ApiConfigService 顺序 bug）：
1. `DatabasePool.initialize()` + `register_schemas()`（`init_*_schema` 自动建表，包含邮件 / 定时任务 / 脚本相关表）
2. `db_pool = DatabasePool._pool` 取连接池引用
3. **初始化 `EmailConfigService`**：`app.state.email_config_service = EmailConfigService(db=db_pool, credential_key=...)` + `preload_all()`；早于 TaskSchedulerService，否则 `_dispatch_script_email` 会因 `self._email_config_service is None` 命中短路分支跳过发邮件。`settings.email_enabled=False` / DB 不可用 / `DEVOPS_CREDENTIAL_KEY` 诊断失败时挂 `None`，保留降级
4. `AgentConfigService` / `McpConfigService` / `ToolRegistryService` / `SkillRegistryService` 初始化与依赖注入
5. `MCPToolsRegistry` 初始化（DB 优先，yaml 兜底）
6. `agent_config_service.preload_all()` + `mcp_config_service.preload_all()` 预加载
7. **初始化 `DevOpsServerService`**（2026-07-22 前移）：`app.state.devops_server_service = DevOpsServerService(...)` + `preload_all()` + `DevOpsServerService.set_instance(svc)`；**必须**在 TaskSchedulerService 之前完成,否则 `run_server_ops(context)` 在脚本执行时拿到 `None` 触发 `ScriptExecutionError: devops_server_service 不可用`(2026-07-22 ops_inspection_sweep 触发任务 #4 实测)。`settings.devops.credential_key` 诊断失败 / DB 不可用时挂 `None`,`devops_server_service_hint` 缓存到 `app.state` 供 router 返回 500 detail
8. **初始化 `ApiConfigService`**（2026-07-22 前移）：`app.state.api_config_service = ApiConfigService(db=db_pool)` + `preload_all()`；与 DevOpsServerService 同源顺序 bug,前移后确保脚本调用 `run_api_checks` 时拿到真实实例。DB 不可用时挂 `None`,路由层 `_get_service` 返回 500
9. `ScriptDiscoveryService`（受 `settings.script_scan_enabled` 控制）→ `app.state.script_discovery_service`
10. **`TaskSchedulerService(db_pool, agent_config_service, script_discovery_service=..., email_config_service=getattr(app.state, "email_config_service", None), api_config_service=getattr(app.state, "api_config_service", None), devops_server_service=getattr(app.state, "devops_server_service", None))`** → `preload_all()` → `start()`
11. 清理阶段：`app.state.script_discovery_service = None` + `app.state.devops_server_service = None` + `TaskSchedulerService.shutdown()` + `DatabasePool.close()`

**配置项**：`settings.script_scan_enabled: bool`（`app/core/config/settings.py` L598）控制是否启用脚本扫描。

**前端**：`web/Agent/src/components/TaskSchedulerManager.vue` 提供 TAB_SCRIPT tab 页，含扫描按钮、summary 统计、脚本表格；任务表单按 `target_type` 条件显示 agent/script 字段。脚本参数不直接编辑 JSON，而是由所选脚本 `params_schema` 驱动“添加参数”列表；当前只支持 `server_list` 服务器多选控件，候选通过 `GET /api/admin/devops-servers` 按需加载并共享 in-flight 请求。控件支持搜索、全选当前过滤结果、清空、逐项移除、失效业务名标识；已失效业务名与旧任务未知参数只有在用户显式移除时才从提交 payload 删除。服务器清单仅渲染 `business_name` / `server_type`，脚本扫描和服务器扫描成功后均强制刷新对应列表。

**调度表单字段契约**：
- 「执行频率」可选 6 种类型（daily / weekly / monthly / yearly / interval_minutes / interval_hours），对应不同的 cron 表达式
- 「执行时间」字段（小时 + 分钟）由 `v-if="scheduleConfig.type !== 'interval_minutes' && scheduleConfig.type !== 'interval_hours'"` 控制显隐；interval 模式下 cron 表达式为 `*/N * * * *` 或 `0 */N * * *`，hour/minute 已被强制丢弃，UI 不展示这两个字段以避免误导
- 切换「执行频率」时 form 字段即时联动；切回非 interval 模式后「执行时间」字段重新出现
- `data-testid="schedule-time"` / `schedule-hour` / `schedule-minute` 在 interval 模式下不存在，单元测试用 `wrapper.find('[data-testid="schedule-time"]').exists()` 断言显隐

**测试覆盖**：
- `app/tests/scripts/test_registry.py`（20 用例）：装饰器注册、重复名拒绝、签名校验、registry 清理
- `app/tests/scripts/test_examples.py`（15 用例）：模块导入、`importlib.reload` 隔离注册、签名 `str | tuple[str, list[str]]`、四种 `mode` 分支（text 返回 str / single 返回单附件 / multi 返回双附件 / error 抛 `ScriptExecutionError`）、默认参数行为、`server_list` schema、非空业务名摘要、缺失/空数组兼容、非法类型/元素校验
- `app/tests/shared/utils/agent/test_script_discovery_service.py`（9 用例）：扫描、容错、白名单过滤、get_script
- `app/tests/shared/utils/agent/test_task_scheduler_service.py`：FakeDb 扩展、validate_payload 跨字段校验、execute_schedule script 分支、_install_run_logger 含 target_type/script_name、脚本通知邮件 Word `attachment_paths` 原样透传
- `app/tests/routers/test_script_admin_router.py`（6 用例）：路由注册、列表、扫描、500、403
- `app/tests/routers/test_task_scheduler_router.py`（13 用例，含 3 个 script 用例）：创建 script 任务 201、缺 script_name 422、agent 携带 script_name 422
- `app/tests/core/test_server_lifespan.py`（11 用例，含 4 个 script 用例）：script_scan_enabled 启停、注入 TaskSchedulerService、shutdown 清理

### 脚本任务 run 写入占位约定（2026-07-16 修复）

`agent_task_schedules.target_type='script'` 的任务，`agent_name` 与 `prompt` 在 schedules 表里允许为 NULL（已通过 `ALTER COLUMN DROP NOT NULL` 放宽），但下游写入执行历史 `agent_task_runs` 时，`agent_name VARCHAR(100) NOT NULL` 与 `prompt_snapshot TEXT NOT NULL` 仍为 NOT NULL 列；`_create_run` 直接 `schedule.get("agent_name")` 传 None 会触发 `asyncpg.NotNullViolationError`。

**约定**：`TaskSchedulerService._create_run` 在 `target_type=='script'` 时写入占位字符串，避免 NOT NULL 约束被违反：

| 列                  | agent 任务              | script 任务占位                                |
| ------------------- | ----------------------- | ---------------------------------------------- |
| `agent_name`        | `schedule["agent_name"]`| `script:{script_name}`（缺则 `script:unknown`）|
| `prompt_snapshot`   | `schedule["prompt"] or ""` | `[script] {script_name}`（缺则 `[script] unknown`）|
| `target_type`       | `agent`                 | `script`                                       |
| `script_name`       | `NULL`                  | `schedule["script_name"]`                      |

下游读取 run 列表 / 详情时应优先判断 `target_type`：若为 `script`，渲染占位符而非尝试在 `agents` 表中查询 `agent_name`。

**关联改动**：`app/routers/task_scheduler_router.py::_handle_service_error` 增加 `asyncpg.PostgresError` 兜底分支，将所有 DB 错误转为 `HTTPException(500, detail="database error: <Type>: <msg>")`，避免异常被 `auth_middleware` 的 `try/except Exception` 吞掉只显示无 detail 的 401/500。

**测试覆盖**：
- `app/tests/shared/utils/agent/test_task_scheduler_service_script_run.py`（4 用例）：占位写入、unknown 回退、agent 任务 passthrough、prompt None → 空串
- `app/tests/routers/test_task_scheduler_router_script_trigger.py`（3 用例）：script 任务 trigger 返回 202、NotNullViolationError 路径返回 500 含 detail、`_handle_service_error` 直接传参分支

### users 表

| 字段          | 类型                       | 说明               |
| ------------- | -------------------------- | ------------------ |
| id            | SERIAL PRIMARY KEY         | 用户ID             |
| username      | VARCHAR(100) UNIQUE        | 用户名             |
| password_hash | VARCHAR(255)               | bcrypt 密码哈希    |
| role          | VARCHAR(20) DEFAULT 'user' | 角色（admin/user） |
| real_name     | VARCHAR(20) DEFAULT ''     | 真实姓名           |
| phone         | VARCHAR(20) DEFAULT ''     | 手机号             |
| email         | VARCHAR(100) DEFAULT ''    | 邮箱               |
| department    | VARCHAR(100) DEFAULT ''    | 部门               |
| position       | VARCHAR(100) DEFAULT ''    | 职位               |
| allowed_agents | JSONB DEFAULT '[]'         | 允许使用的智能体 name 列表 |
| created_at     | TIMESTAMP                  | 创建时间           |
| updated_at    | TIMESTAMP                  | 更新时间           |

### MFA 认证表

`users` 表增加登录失败控制字段：`failed_login_count INTEGER NOT NULL DEFAULT 0`、`locked_until TIMESTAMP NULL`（naive，迁移脚本 `app/migrations/init_all_tables.sql` L61-L63）。登录失败达到配置阈值时锁定账号，正式登录成功后清零。

`user_mfa_totp` 表保存用户 TOTP 状态：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| user_id | INTEGER PRIMARY KEY FK → users | 用户 ID |
| secret_cipher | TEXT | Fernet 加密后的 TOTP secret |
| pending_secret_cipher | TEXT | 绑定/轮换确认前的临时密钥 |
| enabled_at | TIMESTAMPTZ | 启用时间；非空表示已启用 |
| last_used_step | BIGINT | 最近成功使用的 TOTP 时间步，防重放 |
| recovery_code_hashes | JSONB | bcrypt 恢复码哈希数组，一次性消费 |
| updated_at | TIMESTAMPTZ | 更新时间 |

`mfa_challenges` 表保存短期一次性 challenge：`token_hash CHAR(64)`、`user_id`、`purpose`（`login_verify` / `login_enroll` / `enroll_confirm`）、`expires_at`、`failed_attempts`、`consumed_at`、`created_at`。challenge 明文只在客户端内存和一次响应中存在，数据库只存 SHA-256 哈希；challenge 消费、TOTP 时间步更新和恢复码消费使用事务与行锁保证并发安全。

MFA 绑定、禁用、恢复码重置会同时撤销 `refresh_tokens` 与 `portal_refresh_tokens`；`/api/auth/login-api` 不使用上述浏览器 MFA 流程。

### sessions 表

| 字段           | 类型                | 说明           |
| -------------- | ------------------- | -------------- |
| session_id     | VARCHAR(100) PK     | 会话ID（UUID） |
| user_id        | INTEGER FK → users | 用户ID         |
| username       | VARCHAR(100)        | 用户名         |
| title          | VARCHAR(200)        | 会话标题       |
| last_active_at | TIMESTAMP           | 最后活跃时间   |
| status             | VARCHAR(20)         | 状态                   |
| agent_type         | VARCHAR(50)         | 智能体标识名称（default 表示未绑定） |
| agent_display_name | VARCHAR(200)        | 智能体展示名称（中文，如"地图智能体"） |
| created_at         | TIMESTAMP           | 创建时间               |

#### 会话智能体绑定持久化（2026-06-26）

会话与智能体的绑定关系通过 `sessions` 表的 `agent_type` + `agent_display_name` 持久化，实现"一次绑定、会话级始终沿用"：

- **绑定触发**：`agent_router.py::chat` 端点在处理请求时，若传入的 `agent_name` 非 `default`，且当前 session 的 `agent_type` 为 `default` / `''` / `None`，则调用 `SessionDB.update_session_agent(session_id, agent_name, display_name)` 将绑定关系同步写入内存缓存与数据库。
- **绑定约束**：已绑定非 default 智能体的会话不再允许通过 `/command` 切换智能体；前端 `InputBox.vue` 在 `boundAgentName` 非 default 时禁用斜杠命令下拉菜单，并展示不可移除的智能体标签。
- **状态恢复**：前端切换历史会话时，`App.vue::handleSessionSwitch` 从 `fetchSessionDetail` 响应中读取 `agent_type` 和 `agent_display_name`，恢复当前会话绑定的智能体状态，确保历史会话中继续沿用之前的智能体。
- **向后兼容**：未绑定过智能体的历史会话 `agent_type` 默认为 `default`，行为与改造前一致。

### `user_login_sessions` 用户登录会话表（2026-08-12 等保三级 §1.5 新增）

> 与 `sessions` 表的区别：**`sessions.last_active_at` 承载「对话会话」维度（聊天路由）**；本表承载「用户登录会话」维度（idle 检测，自动退出）。
> 两条维度独立，互不干扰。

| 字段              | 类型                              | 说明                                                     |
| ----------------- | --------------------------------- | -------------------------------------------------------- |
| id                | SERIAL PK                         | 自增主键                                                 |
| session_uuid      | VARCHAR(64) UNIQUE NOT NULL       | 随机 url-safe token（写入 `login_session_uuid` Cookie）  |
| user_id           | INTEGER NOT NULL FK → users(id)   | 用户 ID（`ON DELETE CASCADE`）                            |
| username          | VARCHAR(100) NOT NULL             | 用户名快照（审计用，不依赖 JOIN users）                   |
| login_at          | TIMESTAMP NOT NULL DEFAULT NOW()  | 登录时间                                                 |
| last_active_at    | TIMESTAMP NOT NULL DEFAULT NOW()  | 最后活跃时间（idle 检测依据）                             |
| expires_at        | TIMESTAMP NOT NULL                | 绝对过期时间（与 Refresh Token 同步 24h）                |
| ip_address        | VARCHAR(64)                       | 登录来源 IP（审计）                                       |
| user_agent        | TEXT                              | 登录 UA（审计）                                           |
| revoked_at        | TIMESTAMP                         | 主动撤销时间                                             |
| revoke_reason     | VARCHAR(50)                       | 撤销原因：`logout` / `idle` / `admin_revoke` / `replaced` |

索引：`idx_user_login_sessions_user_id`、`idx_user_login_sessions_last_active_at`、`idx_user_login_sessions_expires_at`、`idx_user_login_sessions_uuid`。

迁移：`init_all_tables.sql` 第 177 行附近的 `CREATE TABLE IF NOT EXISTS user_login_sessions` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（幂等）。

写入约束（**2026-08-08 MFA bug 教训**）：`last_active_at` / `login_at` / `expires_at` 均为 PG TIMESTAMP **朴素列**，写入必须用 `datetime.utcnow()`（naive datetime）。**禁止** `datetime.now(timezone.utc)`（aware datetime）→ asyncpg 抛 `DataError: invalid input for query argument ... (can't subtract offset-naive and offset-aware datetimes)`。

### conversation_records 表

| 字段         | 类型            | 说明            |
| ------------ | --------------- | --------------- |
| id           | SERIAL PK       | 记录ID          |
| session_id   | VARCHAR(100) FK | 会话ID          |
| role         | VARCHAR(20)     | 角色（user/ai） |
| content      | TEXT            | 内容            |
| tool_calls   | JSONB           | 工具调用        |
| tool_call_id | VARCHAR(100)    | 工具调用ID      |
| created_at   | TIMESTAMP       | 创建时间        |

### attachments 表

| 字段        | 类型            | 说明     |
| ----------- | --------------- | -------- |
| id          | SERIAL PK       | 附件ID   |
| session_id  | VARCHAR(100) FK | 会话ID   |
| file_name   | VARCHAR(500)    | 文件名   |
| stored_path | VARCHAR(1000)   | 存储路径 |
| file_type   | VARCHAR(20)     | 文件类型 |
| file_size   | BIGINT          | 文件大小 |
| mime_type   | VARCHAR(100)    | MIME类型 |
| file_id     | VARCHAR(100)    | 文件ID   |
| created_at  | TIMESTAMP       | 创建时间 |

### refresh_tokens 表

| 字段       | 类型                    | 说明                           |
| ---------- | ----------------------- | ------------------------------ |
| id         | SERIAL PK               | 记录ID                         |
| token_hash | VARCHAR(255) UNIQUE     | Refresh Token 的 SHA256 哈希值 |
| user_id    | INTEGER FK → users     | 用户ID                         |
| expires_at | TIMESTAMP               | 过期时间                       |
| created_at | TIMESTAMP DEFAULT NOW() | 创建时间                       |

### portal_refresh_tokens 表

门户导航场景下颁发给第三方 iframe 的"子 refresh-token"存储表。子 token 与正常 refresh_token 等效，但独立存储便于独立撤销与审计。

| 字段       | 类型                    | 说明                                                    |
| ---------- | ----------------------- | ------------------------------------------------------- |
| id         | SERIAL PK               | 记录ID                                                  |
| token_hash | VARCHAR(255) UNIQUE     | Portal Refresh Token 的 SHA256 哈希值                   |
| user_id    | INTEGER FK → users     | 用户ID                                                  |
| username   | VARCHAR(100)            | 用户名（冗余用于审计）                                  |
| expires_at | TIMESTAMP               | 过期时间（默认 24 小时）                                |
| revoked    | BOOLEAN DEFAULT FALSE   | ~~软删除标志（已废弃，逻辑上改为物理删除，不再使用）~~ |
| created_at | TIMESTAMP DEFAULT NOW() | 创建时间                                                |

### agents 表

统一智能体架构的运行时配置表，存储智能体元信息、状态 schema、上下文 schema 及 MCP 标签等。

| 字段                    | 类型                         | 说明                                                                                          |
| ----------------------- | ---------------------------- | --------------------------------------------------------------------------------------------- |
| id                      | SERIAL PK                    | 智能体ID                                                                                      |
| name                    | VARCHAR(100) UNIQUE          | 智能体唯一标识名                                                                              |
| display_name            | VARCHAR(200)                 | 显示名称                                                                                      |
| description             | TEXT                         | 描述                                                                                          |
| agents_md_path          | VARCHAR(500)                 | AGENTS.md 配置文件路径                                                                        |
| state_schema            | JSONB DEFAULT '{}'           | **遗留**状态 schema（兼容旧版本，由 config_schema.state_fields 拆分同步写入）           |
| context_schema          | JSONB DEFAULT '{}'           | **遗留**上下文 schema（兼容旧版本，由 config_schema.context_fields 拆分同步写入）       |
| **config_schema** | **JSONB DEFAULT '{}'** | 三层嵌套结构，覆盖 AgentConfig dataclass 字段 + state/context 字段 |
| mcp_tags                | JSONB DEFAULT '[]'           | MCP 标签列表                                                                                  |
| enabled                 | BOOLEAN DEFAULT TRUE         | 是否启用                                                                                      |
| sort_order              | INT DEFAULT 0                | 排序权重                                                                                      |
| **tool_bindings** | **JSONB DEFAULT '[]'** | agent 直接绑定的工具列表快照（缓存该智能体当前启用的工具列表，避免每次加载都联表查 agent_tool_bindings）。格式：`[{"tool_name":"sandbox","tool_type":"builtin","enabled":true,"sort_order":0}, ...]`，由 AgentConfigService.update_tool_bindings 保存配置时同步写入；`tool_type` 取值 `builtin`（内置 @register_tool 工具）/ `mcp`（MCP server 工具）/ `skill`（skill 工具） |
| **skill_bindings** | **JSONB DEFAULT '[]'** | agent 直接绑定的 skill 列表快照（缓存该智能体当前启用的 skill 列表，避免每次加载都联表查 skill 绑定）。格式：`[{"name":"hgsc","enabled":true,"sort_order":0}, ...]`，2026-06-29 随 skills 表新增。注：2026-06-30 起 `agent_skill_bindings` 表已废弃移除，skill 绑定完全改由本 JSONB 字段承载 |
| created_at              | TIMESTAMP                    | 创建时间                                                                                      |
| updated_at              | TIMESTAMP                    | 更新时间                                                                                      |

#### config_schema 三层嵌套结构

合并原 `state_schema` + `context_schema` 两字段为统一 `config_schema`，并扩展覆盖 AgentConfig dataclass 的运行参数（如 temperature / max_tokens / model_name 等）。

```json
{
  "model_type":    {"type": "str",   "default": "deepseek"},
  "temperature":   {"type": "float", "default": 0.5},
  "max_tokens":    {"type": "int",   "default": 4096},
  "state_fields": {
    "map_zoom":   {"type": "int",  "default": 10},
    "map_layer":  {"type": "str",  "default": "standard"}
  },
  "context_fields": {
    "audit_root": {"type": "str", "default": "data/audit"}
  }
}
```

- **顶层字段**（如 `model_type`/`temperature`）：覆盖 AgentConfig dataclass 字段
  - 通过 `dynamic_schema.parse_config_schema` → `build_agent_config_overrides` 提取
  - 在 `chat` 端点构造 AgentConfig 时通过 `**overrides` 解包注入
  - **保留字段**（不可覆盖）：`state_class` / `context_class` / `checkpointer` / `store`
- **state_fields**：state 字典的扩展字段（除 AgentState 基类保留字段外）
- **context_fields**：context 字典的扩展字段（除 AgentContext 基类保留字段外）

**迁移策略**：旧 `state_schema` + `context_schema` 数据保留（数据不丢失），由迁移 SQL 段 14.3/14.4 合并到 `config_schema.state_fields` / `context_fields`。后续版本稳定后可 `DROP COLUMN state_schema, context_schema`。

### JSONB 写入契约（2026-08-05 新增）

`app/core/database.py::_init_connection` 已注册 asyncpg jsonb codec：

```python
await conn.set_type_codec(
    'jsonb',
    encoder=json.dumps,    # Python 对象 → JSON 文本
    decoder=json.loads,    # JSON 文本 → Python 对象
    schema='pg_catalog',
    format='text',         # 文本协议
)
```

在 `format='text'` 协议下,asyncpg 写入行为：
- 传 Python dict / list → codec encoder → JSON 文本 → PG 端按 JSONB 解析 → 存为 JSONB object/array
- 传 Python string(已是 JSON 文本) → codec 不再 encode → PG 端按 JSONB 解析字符串字面量 → 存为 **JSONB string 类型**(双层编码:外层 `""` 包裹 dict/array 文本)

**契约**：**应用层不应再 `json.dumps` JSONB 字段**。直接传 dict / list 即可,codec 会自动处理。

**反模式示例（2026-08-05 已修复）**：`app/shared/utils/agent/agent_config_service.py` 早期版本的
`update_agent_config_schema` / `create_agent` / `update_tool_bindings` / `update_skill_bindings`
共 5 处写了 `json.dumps(...)`,导致 agents 表 JSONB 字段出现 string 类型(前端 GET 拿到 dict / list / string 混合形态,`jsonb_typeof` 永远是 `'string'`)。

**正确写法**：

```python
# ✅ 正确:直接传 dict / list
await db.execute(
    "UPDATE agents SET config_schema = $2, ... WHERE name = $1",
    name, config_schema,           # dict, 由 codec 自动 encode
)
await db.execute(
    "UPDATE agents SET tool_bindings = $2, ... WHERE name = $1",
    name, bindings,                # list, 由 codec 自动 encode
)

# ❌ 错误:先 json.dumps,产生 string JSONB
await db.execute(
    "UPDATE agents SET config_schema = $2, ... WHERE name = $1",
    name, json.dumps(config_schema),  # 已经是 JSON 文本 → PG 存为 string 类型
)
```

**回归保护**：
- `app/tests/shared/utils/agent/test_agent_config_service.py` 4 个新用例
  (`test_update_agent_config_schema_writes_dict_not_string_jsonb` /
  `test_update_tool_bindings_writes_list_not_string_jsonb` /
  `test_update_skill_bindings_writes_list_not_string_jsonb` /
  `test_create_agent_writes_dict_not_string_jsonb`) 断言写入参数类型必须是 dict / list,
  防止未来代码无意中重新引入 `json.dumps`。
- `app/tests/migrations/test_init_all_tables_inspection_schema.py` 7 个新用例验证
  `init_all_tables.sql` v6 章节(14.4 防御补丁 + 14.5 一次性修复段)存在。

**数据修复**：运维智能体 (project) 的 `state_schema / context_schema / tool_bindings / skill_bindings`
曾因 5 处冗余 `json.dumps` 被存为 string 类型 JSONB。`init_all_tables.sql` 14.5 节(2026-08-05 新增)
提供幂等修复:
```sql
-- 14.5.1 示例:state_schema string → object
UPDATE agents SET state_schema = CASE
    WHEN jsonb_typeof(state_schema) = 'string'
        THEN COALESCE(NULLIF((state_schema #>> '{}')::jsonb, 'null'::jsonb), '{}'::jsonb)
    WHEN state_schema IS NULL THEN '{}'::jsonb
    ELSE state_schema
END, updated_at = CURRENT_TIMESTAMP
WHERE jsonb_typeof(state_schema) = 'string' OR state_schema IS NULL;
```
- `(col #>> '{}')` 把 JSON string 提取为 text,再 `::jsonb` 重新解析为 object/array
- `WHERE jsonb_typeof = 'string' OR IS NULL` 保证幂等:已修过的 object / array 不会被覆盖
- 14.5.3 / 14.5.4 (tool_bindings / skill_bindings) 解析失败 fallback 到 `'[]'::jsonb`
- 14.4 节 WHERE 也加 `jsonb_typeof = 'object'` 防御,避免 array 与 object `||` 合并产生 array 元素

**未修复范围**：其他 service 里仍存在的 ~25 处 `json.dumps`(mcp_service / tool_service /
task_scheduler_service / user_db / devops_server_service / inspection_script_service /
api_config_service / conversation_db 等)与本 bug 同源,影响面更大,后续 PR 处理。
判断标准:用户能直接在前端 UI 看到的错误字段——目前只有 agents 表这 5 个字段。

### agent_tool_bindings 表

智能体与工具的绑定关系表，多对多映射。

| 字段       | 类型                          | 说明                                   |
| ---------- | ----------------------------- | -------------------------------------- |
| id         | SERIAL PK                     | 绑定ID                                 |
| agent_name | VARCHAR(100)                  | 智能体名称                             |
| tool_name  | VARCHAR(100)                  | 工具名称                               |
| is_enabled | BOOLEAN DEFAULT TRUE          | 是否启用该绑定                         |
| sort_order | INT DEFAULT 0                 | 排序权重                               |
| **tool_type** | **VARCHAR(20) DEFAULT 'builtin'** | 工具来源类型（`builtin` 内置 @register_tool 工具 / `mcp` MCP server 工具 / `skill` skill 工具）。默认 `builtin` 兼容历史数据 |
| created_at | TIMESTAMP                     | 创建时间                               |
|            | UNIQUE(agent_name, tool_name) | 唯一约束：同一智能体同一工具仅一条绑定 |

### agent_skill_bindings 表（已废弃移除）

> **2026-06-30 起移除**：原本用于存储智能体-skill 绑定关系的 `agent_skill_bindings` 表已废弃并从 `app/migrations/init_all_tables.sql` 中移除。Skill 绑定关系现在直接存储于 `agents.skill_bindings` JSONB 字段（参见上文 agents 表），由 `AgentConfigService.update_skill_bindings` / `get_skill_bindings` 全量维护，避免每次加载配置都联表查询。

历史上该表的字段如下（已不再使用，仅供 git log 回溯）：

| 字段       | 类型                           | 说明                                      |
| ---------- | ------------------------------ | ----------------------------------------- |
| id         | SERIAL PK                      | 绑定ID                                    |
| agent_name | VARCHAR(100)                   | 智能体名称                                |
| skill_name | VARCHAR(100)                   | skill 名称                                |
| is_enabled | BOOLEAN DEFAULT TRUE           | 是否启用该绑定                            |
| sort_order | INT DEFAULT 0                  | 排序权重                                  |
| created_at | TIMESTAMP                      | 创建时间                                  |
|            | UNIQUE(agent_name, skill_name) | 唯一约束：同一智能体同一 skill 仅一条绑定 |

### tools 表

统一工具元数据注册表，将散落在 `app/core/tools/` 与 `app/features/*/tools/` 下的工具函数元数据统一登记到数据库，供管理界面展示与 Agent 配置缓存查询。2026-06-25 新增。

| 字段                 | 类型                         | 说明                                                          |
| -------------------- | ---------------------------- | ------------------------------------------------------------- |
| id                   | SERIAL PK                    | 记录ID                                                        |
| name                 | VARCHAR(100) UNIQUE          | 工具唯一标识（与 @register_tool 注册名一致）                  |
| display_name         | VARCHAR(200)                 | 展示名称（管理界面用）                                        |
| category             | VARCHAR(100) NOT NULL        | 工具分类（如 filesystem / sandbox / mcp / map 等）            |
| description          | TEXT                         | 工具描述（来自 docstring 摘要）                               |
| module_path          | VARCHAR(500) NOT NULL        | Python 模块路径（如 app.core.tools.SandboxTools）             |
| file_path            | VARCHAR(500) NOT NULL        | 源文件相对路径（如 app/core/tools/SandboxTools.py）           |
| args_schema          | JSONB DEFAULT '{}'           | 参数 schema（Pydantic model 字段描述）                        |
| return_description   | TEXT                         | 返回值描述                                                    |
| function_description | TEXT                         | 函数完整描述（docstring 全文）                                |
| enabled              | BOOLEAN DEFAULT TRUE         | 是否启用                                                      |
| sort_order           | INT DEFAULT 0                | 排序权重                                                      |
| created_at           | TIMESTAMP                    | 创建时间                                                      |
| updated_at           | TIMESTAMP                    | 更新时间                                                      |

**索引**：`idx_tools_category(category)`、`idx_tools_enabled(enabled)`

### skills 表

统一 skill 元数据注册表，将项目中的 SKILL.md 文件元数据登记到数据库，供管理界面展示与 `agents.skill_bindings` JSONB 字段绑定引用。2026-06-29 新增。

| 字段          | 类型                         | 说明                                                          |
| ------------- | ---------------------------- | ------------------------------------------------------------- |
| id            | SERIAL PK                    | 记录ID                                                        |
| name          | VARCHAR(100) UNIQUE NOT NULL | skill 唯一标识（来自 SKILL.md frontmatter）                   |
| display_name  | VARCHAR(200)                 | 展示名称（管理界面用）                                        |
| category      | VARCHAR(100)                 | skill 分类                                                    |
| description   | TEXT                         | skill 描述                                                    |
| location      | VARCHAR(1000) NOT NULL       | SKILL.md 文件绝对路径                                         |
| base_dir      | VARCHAR(1000) NOT NULL       | SKILL.md 所在目录绝对路径                                     |
| content       | TEXT                         | 去除 frontmatter 后的正文                                     |
| enabled       | BOOLEAN DEFAULT TRUE         | 是否启用                                                      |
| sort_order    | INT DEFAULT 0                | 排序权重                                                      |
| created_at    | TIMESTAMP                    | 创建时间                                                      |
| updated_at    | TIMESTAMP                    | 更新时间                                                      |

**索引**：`idx_skills_category(category)`、`idx_skills_enabled(enabled)`

**种子数据**：`app/migrations/init_all_tables.sql` 末尾通过 `INSERT INTO skills ... ON CONFLICT (name) DO NOTHING` 写入 3 条内置 skill（`bdc_query` / `hgsc` / `knowledge_ydt`），location / base_dir 为对应 SKILL.md 绝对路径，content 为去除 frontmatter 后的正文。

**后端服务**：`app/shared/utils/agent/skill_service.py::SkillRegistryService` 提供 DB CRUD、内存缓存与未注册 skill 扫描能力。

### tools 表种子数据（2026-06-25 新增）

`app/migrations/init_all_tables.sql` 末尾追加 17 条 `INSERT INTO tools ... ON CONFLICT (name) DO NOTHING` 段落，作为内置工具元数据首装数据。

**生成脚本**：`scripts/seed_tools_from_source.py`

- 扫描 `app/core/tools/*.py` + `app/shared/tools/skills/**/*.py` 下所有 `.py` 文件
- 用 `ast.parse` 提取 `@tool` 装饰函数（支持 `@tool` 和 `@tool(...)` 两种形式）
- 提取 description 优先取 `@tool(description=...)` 参数，其次 docstring
- 输出幂等 INSERT SQL（`ON CONFLICT (name) DO NOTHING`）
- 默认 category 推断：路径含 `skills/{agent}/` → category = agent；其他 → "未分类"
- 支持 `--category-map` / `SEED_CATEGORY_MAP` 环境变量自定义 file_name → category 映射

**用法**：

```powershell
# 干跑（仅打印工具数量）
python scripts/seed_tools_from_source.py --dry-run

# 输出到文件
python scripts/seed_tools_from_source.py --output app/migrations/seed_tools.sql

# 自定义分类（PowerShell 传 UTF-8）
$bytes = [System.IO.File]::ReadAllBytes("scripts/category_map.json")
$env:SEED_CATEGORY_MAP = [System.Text.Encoding]::UTF8.GetString($bytes)
$env:PYTHONIOENCODING = "utf-8"
python scripts/seed_tools_from_source.py --output app/migrations/seed_tools.sql
```

**幂等性**：所有 INSERT 使用 `ON CONFLICT (name) DO NOTHING`，可重复执行。新增工具后重新生成 SQL 追加到 `init_all_tables.sql` 即可。

**当前种子工具数量**：17 个（5 个 BaseTools + 1 explore + 1 ask_user_question + 1 sandbox + 9 map_agent MapTools）

### 工具加载流程

**`_load_tools` 双轨制**（`app/shared/utils/agent/agent_config_service.py:AgentConfigService._load_tools`）：

1. **高优先级**：`tool_bindings` 直接绑定
   - `tool_type="builtin"` → `tool_service.get_tool_by_name(name)` 返回的 `tool_instance`
   - `tool_type="mcp"` → 解析 `name="server.method"` 复合名，调 `mcp_registry.get_tools_with_server(server=, names=)`
2. **低优先级回退**：`tool_bindings` 未加载到工具时，按 `mcp_tags` 过滤整个 server
3. **无默认工具**：`tool_bindings` 和 `mcp_tags` 都为空时返回空列表

**MCP 工具命名约定**（2026-06-25 落地）：

- `tool_bindings[].tool_name` 格式：`server_name.method_name`（如 `amap.search`）
- 解析后调用 `mcp_registry.get_tools_with_server(server="amap", names=["search"])`
- 避免跨 server 命名冲突（如多个 server 都提供 `search` method）
- 新增辅助方法：`AgentConfigService._parse_mcp_tool_name(tool_name) -> (server, method)`

**`mcp_registry.get_tools_with_server` 新增参数**（2026-06-25 落地）：

- `mcp_client: Optional[Any] = None` 显式传入 MCP 客户端（默认 None，回退到 `self._client`）
- 三个方法同步增加：`get_tools_with_server` / `_get_tools_with_server_async` / `get_tools_with_server_async`

### 工具热加载链路（2026-06-25 补全）

| 写操作                                    | 触发函数                                       | 缓存影响                                            |
| ----------------------------------------- | ---------------------------------------------- | --------------------------------------------------- |
| `tool_admin_router` create/update/delete/set_tool_enabled | `_invalidate_agent_config_cache(request)` → `agent_service.invalidate_all_cache()` | 清空所有 agent 缓存（含 tools 列表）|
| `mcp_admin_router` create/update/delete/toggle_server | `_invalidate_agent_config_cache(request)`（已有）| 清空所有 agent 缓存（含 tools 列表）|
| `agent_admin_router` PUT tool-bindings   | `service.update_tool_bindings` → `_refresh_cache(name)` | 单 agent 缓存刷新（tools=None 延迟重新加载）|
| `agent_admin_router` PUT skill-bindings  | `service.update_skill_bindings` → `_refresh_cache(name)` | 单 agent 缓存刷新（tools=None 延迟重新加载）|

**实现位置**：

- `app/routers/tool_admin_router.py:_invalidate_agent_config_cache`（新增）
- `app/routers/mcp_admin_router.py:_invalidate_agent_config_cache`（已有）
- `app/routers/agent_admin_router.py:update_agent_tool_bindings`（已自动调 `_refresh_cache`）
- `app/routers/agent_admin_router.py:update_agent_skill_bindings`（已自动调 `_refresh_cache`）


### map_agent 种子脚本

**文件位置**: `app/migrations/seed_map_agent.py`（含 `app/migrations/__init__.py` 包初始化）

向 `agents` / `agent_tool_bindings` 表写入 map_agent 初始配置，幂等可重复执行。Skill 绑定由 `agents.skill_bindings` JSONB 字段管理，不再写入独立的 `agent_skill_bindings` 表（已废弃移除）。

| 函数                   | 说明                                                                                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `seed_map_agent(db)` | 核心种子函数。先 `SELECT` 判断 agents 表是否已有 map_agent，已存在则 UPDATE，不存在则 INSERT；工具绑定使用 `ON CONFLICT DO UPDATE` 幂等写入 |
| `main()`             | 脚本入口，从 `DATABASE_URL` 环境变量（默认 `postgresql://postgres:postgres@localhost:5432/feature_agent`）读取连接并执行种子                       |

**map_agent 配置常量**:

- `MAP_AGENT_STATE_SCHEMA`：map_center={"latitude":0,"longitude":0} / map_zoom=10 / map_markers=[] / map_layer="standard" / map_polygons=[]
- `MAP_AGENT_CONTEXT_SCHEMA`：清空为 `{}`，基类保留字段由 `dynamic_schema._BASE_CONTEXT_DEFAULTS` 兜底
- `MAP_AGENT_TOOLS`: explore / query_knowledge / get_current_time / generate_report / save_business_info / ask_user_question / sandbox / load_skill / read_skill_file（9 个）
- `MAP_AGENT_SKILLS`: data-skill（1 个）

**执行方式**: `python -m app.migrations.seed_map_agent` 或 `psql -U postgres -d feature_agent -f app/migrations/init_all_tables.sql`

**测试**: `app/tests/shared/test_seed_map_agent.py`（3 用例：可导入 / INSERT 路径 / UPDATE 幂等路径）

### mcp_server_configs 种子脚本

**文件位置**: `app/migrations/seed_mcp_servers.py`

从 `app/shared/tools/mcp/config.yaml` 加载 MCP server 配置，写入 `mcp_server_configs` 表。**幂等**：表已有数据时跳过导入（与 lifespan `seed_from_yaml_if_empty` 行为一致）。

| 函数                     | 说明                                                                                                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `seed_mcp_servers(db)` | 核心种子函数。先 `SELECT name FROM mcp_server_configs` 判断表是否非空，非空则跳过；空则复用 `McpConfigService.seed_from_yaml_if_empty()` 导入 YAML 种子，返回本次实际写入条数 |
| `main()`               | 脚本入口，从 `DATABASE_URL` 环境变量（默认 `postgresql://postgres:postgres@localhost:5432/feature_agent`）读取连接并执行种子                                                  |

**执行方式**: `python -m app.migrations.seed_mcp_servers`

**测试**: `app/tests/shared/test_seed_mcp_servers.py`（4 用例：可导入 / 表非空跳过 / YAML 导入端到端 / YAML 为空不抛异常）

### mcp_server_configs 表

MCP 服务器配置表，从 YAML 迁移至数据库管理。

| 字段               | 类型                               | 说明                                                                                   |
| ------------------ | ---------------------------------- | -------------------------------------------------------------------------------------- |
| id                 | SERIAL PK                          | 配置ID                                                                                 |
| name               | VARCHAR(100) UNIQUE                | 服务器唯一名称                                                                         |
| display_name       | VARCHAR(200)                       | 显示名称                                                                               |
| type               | VARCHAR(20)                        | 服务器类型（sse/stdio 等）                                                             |
| url                | VARCHAR(500)                       | SSE 模式的 URL                                                                         |
| command            | JSONB                              | stdio 模式的启动命令                                                                   |
| timeout            | INT DEFAULT 5                      | 连接超时（秒）                                                                         |
| read_timeout       | INT DEFAULT 300                    | 读取超时（秒）                                                                         |
| tags               | JSONB DEFAULT '[]'                 | 标签列表                                                                               |
| enabled            | BOOLEAN DEFAULT TRUE               | 是否启用                                                                               |
| progress_reporting | JSONB DEFAULT '{"enabled": false}' | 进度上报配置                                                                           |
| tool_config        | JSONB                              | 工具注入配置（enable_injection、default_param_keys、hidden_param_keys、unwrap_result） |
| sampling           | JSONB DEFAULT '{"enabled": false}' | 采样配置                                                                               |
| methods_synced_at  | TIMESTAMP                          | 方法列表最后同步时间                                                                   |
| created_at         | TIMESTAMP                          | 创建时间                                                                               |
| updated_at         | TIMESTAMP                          | 更新时间                                                                               |

#### 字段扩展

补齐 4 列使 DB 成为 source of truth：

| 字段                | 类型  | 默认值          | 说明                    |
| ------------------- | ----- | --------------- | ----------------------- |
| `args`            | JSONB | `'[]'::jsonb` | stdio 参数列表          |
| `env`             | JSONB | `'{}'::jsonb` | 进程环境变量            |
| `headers`         | JSONB | `'{}'::jsonb` | HTTP/SSE 自定义头       |
| `connect_timeout` | INT   | `10`          | TCP/HTTP 连接超时（秒） |

幂等迁移：`ADD COLUMN IF NOT EXISTS`（PostgreSQL 9.6+），兼容已建库。迁移脚本位于 `app/migrations/init_all_tables.sql` 末尾（COMMIT 之前）。

### 前端 MCP 管理页面

`web/Agent/src/components/McpServerManager.vue` 提供 MCP server 的增删改查 UI。

**表单字段**：名称、显示名、类型、URL、Command、Tags、Timeout、Read Timeout、Connect Timeout、Args（JSON）、Env（JSON）、Headers（JSON）、Tool Config（JSON）、进度上报开关（编辑时）。

- Args/Env 仅在类型为 `stdio` 时显示。
- Headers 仅在类型为 `sse`/`http` 时显示。
- Tool Config 支持配置 `enable_injection`/`default_param_keys`/`hidden_param_keys`/`unwrap_result`。
- 进度上报（`progress_reporting.enabled`）仅在编辑服务器时显示开关，保存时通过 `updateMcpServer` 更新；新增服务器沿用后端默认值 `{"enabled": false}`。详情面板同步展示当前进度上报启用状态。

### mcp_server_methods 表

MCP 服务器方法列表表，用于运行时方法管理。

| 字段        | 类型                             | 说明                                   |
| ----------- | -------------------------------- | -------------------------------------- |
| id          | SERIAL PK                        | 方法ID                                 |
| server_name | VARCHAR(100)                     | 所属服务器名称                         |
| method_name | VARCHAR(200)                     | 方法名称                               |
| enabled     | BOOLEAN DEFAULT TRUE             | 是否启用                               |
| description | TEXT                             | 方法描述                               |
| created_at  | TIMESTAMP                        | 创建时间                               |
|             | UNIQUE(server_name, method_name) | 唯一约束：同一服务器同一方法仅一条记录 |

### projects 表（2026-06-30 新增）

项目文件夹方案的核心表。用户在聊天框下拉框选择"新建空白项目"或"使用现有文件夹"后会话文件落到独立项目目录。

| 字段          | 类型                              | 说明                                                          |
| ------------- | --------------------------------- | ------------------------------------------------------------- |
| id            | SERIAL PK                         | 项目主键 ID                                                   |
| user_id       | INTEGER NOT NULL REFERENCES users | 创建者用户 ID（ON DELETE CASCADE）                            |
| name          | VARCHAR(200) NOT NULL             | 项目名称（用户输入）                                          |
| uuid          | VARCHAR(64) UNIQUE NOT NULL       | 项目独立唯一标识；为空时后端按 UUID v4 自动生成，不再强制等于 session_id |
| relative_path | VARCHAR(500)                      | 2026-07-01 新增：项目对应现有文件夹的相对路径（仅"使用现有文件夹"场景非空） |
| created_at    | TIMESTAMP DEFAULT NOW()           | 创建时间                                                      |
| updated_at    | TIMESTAMP DEFAULT NOW()           | 更新时间                                                      |

**索引**：`idx_projects_user_id(user_id)`

**uuid 语义**：
- uuid 是项目独立唯一标识，由后端生成（UUID v4），不再复用创建时所在 session 的 session_id。
- 一个 uuid 全局唯一（UNIQUE 约束）。
- 多 session 可共享同一项目（通过 `sessions.project_id` 关联）。
- 物理路径按 `relative_path` 字段解析；默认路径格式为 `<项目根>/data/project/yyyy/mm/dd/{uuid}/`。

### sessions.project_id 字段（2026-06-30 新增）

会话关联的项目 ID（一对多：多会话可共用同一项目）。

```sql
ALTER TABLE sessions ADD COLUMN project_id INTEGER
    REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX idx_sessions_project_id ON sessions(project_id);
```

- NULL = 不使用文件夹（默认 / 旧会话 / 用户主动解绑）
- 关联项目 = `data/upload/yyyy/mm/dd/{session_id}/` 之外的独立项目目录
- ON DELETE SET NULL：项目被删除时相关 session 自动解绑，文件保留

### attachments.project_id 字段（2026-06-30 新增）

附件冗余存储所属项目 ID，便于按项目聚合查询。

```sql
ALTER TABLE attachments ADD COLUMN project_id INTEGER
    REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX idx_attachments_project_id ON attachments(project_id);
```

**不强制 NOT NULL**：旧附件无 project_id（兼容存量数据）。

