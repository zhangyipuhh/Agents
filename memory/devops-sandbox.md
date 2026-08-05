# DevOps 与沙箱

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## DevOps 系统（SSH 远程服务器管理，2026-07-15 落地）

> **背景**：原 `app/features/DevOps_agent/` 已下线（Agent 形态撤销）；SSH 工具（CommandInterceptor / SSHTools）下沉到 `app/shared/tools/skills/devops/`，配置管理下沉到 `app/shared/utils/devops_server_service.py`，admin 入口由专门的 router 提供，**不再创建 Agent / agent_tool_bindings / seed_devops_agent**。

### 核心模块

| 路径 | 职责 |
|---|---|
| `app/shared/utils/devops_server_service.py` | `DevOpsServerService(db, config_path, credential_key, inspection_script_service)` 单例；`preload_all` / `scan_and_upsert` / `list_public_servers` / `get_server_detail` / `get_connection_config` / `server_exists` / `delete_server`；详情仅返回 `_DETAIL_FIELDS` 含 `inspection_script_id` / `inspection_script_name` / `inspection_script_display_name` 三键（脚本原文由 `InspectionScriptService` 单独提供） |
| `app/shared/utils/inspection_script_service.py` | 2026-08-03 新增：`InspectionScriptService(db, config_path)` 单例；YAML 配置入口 `<项目根>/data/devops/inspection_scripts.yaml`；`preload_all` / `scan_and_upsert` / `list_scripts`（白名单 7 字段）/ `get_script_detail(id)` / `get_script_by_id(id)` / `get_script_by_name(name)` / `resolve_script_for_server(server_type, script_name)`；写路径持 `self._write_lock` |
| `app/shared/tools/skills/devops/CommandInterceptor.py` | 命令策略过滤器，黑名单优先 + 白名单 allowlist + 精确/前缀/正则三模式 |
| `app/shared/tools/skills/devops/SSHTools.py` | 3 个 `@tool(description=...)`：execute_command / execute_batch_commands / get_system_logs |
| `app/routers/devops_server_admin_router.py` | `GET /api/admin/devops-servers`（列表端点 `Depends(require_admin_or_menu_acl("task-scheduler.server-management"))`）+ `GET /api/admin/devops-servers/{server_id}`（详情；仅 admin；返 `{id, business_name, server_type, updated_at, whitelist, inspection_script_id, inspection_script_name, inspection_script_display_name}`；脚本原文改走 `/api/admin/inspection-scripts/{id}`）+ `POST /api/admin/devops-servers/scan`（仅 admin）+ `DELETE /api/admin/devops-servers/{server_id}`（仅 admin；返 `204 No Content`），router 自身不再有 `dependencies=[Depends(require_admin)]`，每个端点显式声明权限 |
| `app/routers/inspection_script_admin_router.py` | 2026-08-03 新增：`GET /api/admin/inspection-scripts`（列表 7 字段白名单：admin OR `task-scheduler.server-management` ACL）+ `POST /api/admin/inspection-scripts/scan`（admin only；返 `{scanned, inserted, updated, failed}` 4 整数）+ `GET /api/admin/inspection-scripts/{script_id}`（admin only；返完整详情含 `inspection_script` / `inspection_fields`；不存在 → 404 + 「脚本不存在」） |

### 配置 / 路径常量（2026-07-15；2026-08-03 扩展）

- `app/core/config/paths.py::DEVOPS_SERVER_CONFIG_PATH` = `<项目根>/data/devops/servers.yaml`
- `app/core/config/paths.py::DEVOPS_SERVER_CONFIG_DIR` = `<项目根>/data/devops`
- `app/core/config/paths.py::DEVOPS_INSPECTION_SCRIPTS_CONFIG_PATH`（2026-08-03 新增）= `<项目根>/data/devops/inspection_scripts.yaml`
- `app/core/config/paths.py::resolve_devops_inspection_scripts_config_path(path)`（2026-08-03 新增）：绝对路径原样返回 / 相对项目根解析 / 空字符串抛 `ValueError`；语义与 `resolve_devops_server_config_path` 对齐
- `app/core/config/settings.py::DevOpsSettings`：字段 `servers_config_path`（env `DEVOPS_SERVERS_CONFIG_PATH`）、`credential_key`（env `DEVOPS_CREDENTIAL_KEY`，空字符串走「延期到初始化时严格校验」语义，不让 import 崩溃）、`inspection.scripts_config_path`（env `DEVOPS_INSPECTION_SCRIPTS_CONFIG_PATH`，2026-08-03 新增）。`model_config` 声明 `env_prefix="DEVOPS_"`（2026-07-15 修复），使字段 `credential_key` 匹配 env `DEVOPS_CREDENTIAL_KEY`、`servers_config_path` 匹配 env `DEVOPS_SERVERS_CONFIG_PATH`

### 数据库表 `devops_servers`（2026-07-15 新增；2026-08-03 改造）

- 列：`id` / `business_name UNIQUE` / `ip` / `port` / `username` / `password_encrypted BYTEA` / `server_type` / `blacklist JSONB` / `whitelist JSONB` / **`inspection_script_id INTEGER NULL REFERENCES inspection_scripts(id) ON DELETE SET NULL`**（2026-08-03 新增；旧三列 `inspection_script` / `inspection_parser` / `inspection_fields` 已通过 `DROP COLUMN IF EXISTS` 移除）/ `created_at` / `updated_at`
- CHECK：`server_type IN ('linux', 'windows')`、`port BETWEEN 1 AND 65535`
- 索引：`idx_devops_servers_server_type` / `idx_devops_servers_updated_at DESC` / **`idx_devops_servers_inspection_script_id`**（2026-08-03 新增）
- 工具元数据：在 `app/migrations/init_all_tables.sql` 的 `tools` 表中登记了 `execute_command` / `execute_batch_commands` / `get_system_logs` 三个工具（`module_path=app.shared.tools.skills.devops.SSHTools` / `file_path=app/shared/tools/skills/devops/SSHTools.py`；`args_schema` 显式不含 `runtime`；`business_name` 为必填字段，`args_schema` 标记 `required` 且工具入口验空）。

### 生命周期 / admin API

- `app/core/server.py::lifespan`：数据库池建立后，先初始化 `InspectionScriptService`（2026-08-03 新增），随后调用 `app.core.config.devops_diagnostics.diagnose_credential_key()` 校验密钥；通过且 `inspection_script_service` 已就绪时构造 `DevOpsServerService` 并 `set_instance(svc)` + 挂 `app.state.devops_server_service`；yield 后 `reset()` 单例并清理 `app.state.devops_server_service`。失败时把诊断 hint 写入 `app.state.devops_server_service_hint`，router 会读取并放入 500 detail。
- `app/core/config/devops_diagnostics.py`（2026-07-15 新增）：从 `settings.devops.credential_key` 读取，分 4 类返回诊断结果：`missing`（完全没配）/ `misspelled`（env 里有相近键）/ `settings_unread`（env 里有精确键名但 settings 读不到）/ `invalid_fernet`（值非空但 Fernet 校验失败）。hint 不打印完整密钥，只显示长度+前 4 字符指纹。
- `app/routers/devops_server_admin_router.py`：移除 router 级 `dependencies=[Depends(require_admin)]`，改为每个端点显式声明权限；`GET /api/admin/devops-servers` 列表端点使用 `Depends(require_admin_or_menu_acl("task-scheduler.server-management"))`（admin 直 bypass，普通用户需 `task-scheduler.server-management` 菜单 ACL）；`POST /scan` / `GET /{server_id}` / `DELETE /{server_id}` 均保留 `Depends(require_admin)`（admin-only）。服务未初始化返回 500 + `detail=<lifespan 写入的 hint>`（无 hint 时退回 `"DevOpsServerService not initialized"`）；`GET` 列表严格只返回 `{id, business_name, server_type, updated_at}`；`POST /scan` 严格只返回 `{scanned, inserted, updated, failed}`；扫描异常时不回显原始 `detail` / 路径 / IP / 密码 / 名单。`GET /api/admin/devops-servers/{server_id}`（2026-08-03 改造）按需返回详情：仅含 `_DETAIL_FIELDS = {id, business_name, server_type, updated_at, whitelist, inspection_script_id, inspection_script_name, inspection_script_display_name}`，命中失败 → 404 + `"服务器不存在"`（不回显 server_id），router 防御性二次过滤保证即便 service 失误返回了 ip/port/username/password 也会被白名单过滤；脚本原文**不**进入此响应，改由 `GET /api/admin/inspection-scripts/{script_id}` 按需提供。`DELETE /api/admin/devops-servers/{server_id}` 返 `204 No Content`：先 `server_exists` 探测（不存在 → 404 + `"服务器不存在"`），再 `delete_server`（service 持 `_write_lock` 同步删 `_cache` + `db.execute("DELETE FROM devops_servers WHERE id = $1", server_id)`）；DB 异常 → 500 + `"删除服务器失败"`，不回显 SQL / 原 detail。
- **不再为 DevOps 工具创建 Agent**——工具通过 ToolRegistryService 扫描 `app/shared/tools/skills/devops/SSHTools.py` 自动发现，admin 界面按元数据展示。
- **运行时必备配置**：`settings.devops.credential_key` 必须由 `Fernet.generate_key()` 生成（44 字节 base64），非法格式会在 `diagnose_credential_key()` 走 `invalid_fernet` 分支，效果同上。`data/devops/servers.yaml` 由 `.gitignore` 排除（`servers.yaml.example` 是公开模板），缺失时 `scan_and_upsert` 安全返回 0 但列表为空，不报错。

### 巡检脚本库 `inspection_scripts`（2026-08-03 抽离）

> 巡检脚本原文、解析器类型与字段规则从 `devops_servers` 三列内联存储抽离到独立 `inspection_scripts` 表；`devops_servers` 仅保留 `inspection_script_id` 外键引用。脚本按「平台 + 版本」命名（如 `linux-bash` / `windows-ps-5.1` / `windows-ps-7+`），`inspection_fields` 完全跟随脚本库条目，服务器层不可覆盖。

#### 数据库表 `inspection_scripts`

- 列：`id SERIAL PK` / `name VARCHAR(100) UNIQUE NOT NULL` / `display_name VARCHAR(200) NOT NULL` / `platform VARCHAR(32) NOT NULL DEFAULT 'linux'` / `version VARCHAR(32) NOT NULL DEFAULT ''` / `inspection_parser VARCHAR(16) NOT NULL DEFAULT 'json'` / `inspection_script TEXT NULL` / `inspection_fields JSONB DEFAULT '[]'::jsonb` / `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` / `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- CHECK：`inspection_parser IN ('json', 'kv', 'csv', 'raw')`（约束名 `inspection_scripts_parser_chk`）
- 索引：`idx_inspection_scripts_platform(platform)` / `idx_inspection_scripts_name(name)`

#### 服务 `InspectionScriptService`（`app/shared/utils/inspection_script_service.py`）

- 单例 + `set_instance` / `get_instance` / `reset`；构造 `InspectionScriptService(db, config_path)`，YAML 默认 `<项目根>/data/devops/inspection_scripts.yaml`，路径解析走 `resolve_devops_inspection_scripts_config_path`
- `preload_all()`：`SELECT id, name, display_name, platform, version, inspection_parser, inspection_script, inspection_fields, created_at, updated_at FROM inspection_scripts ORDER BY id` 全量加载；`inspection_fields` 兼容 str（`json.loads`）/ list / 其它 → 统一还原为 `list[dict]`，非 str/list 兜底为 `[]`；持 `self._write_lock` 原子替换 `_cache: Dict[name, rec]` + `_id_cache: Dict[id, rec]`
- `scan_and_upsert()`：读取 YAML；顶层 `dict` 取 `inspection_scripts` 键，list 直接用，非 list → `failed+=1`；逐 entry 调 `_normalize_entry` 做必填校验（`name` / `display_name` 非空字符串、`platform ∈ {linux, windows}`、`version` 默认空串、`inspection_parser ∈ {json,kv,csv,raw}`、`inspection_script` 空 / 纯空白 → `None` 且 rstrip 末尾换行、`inspection_fields` 复用 `normalize_inspection_fields` 归一化为 `list[dict]`）；同 name 重复直接拒绝（`failed+=1`，**不覆盖**）；单条 upsert 用 `INSERT ... ON CONFLICT (name) DO UPDATE ... RETURNING *, (xmax = 0) AS inserted` 一次往返，缓存通过 RETURNING 行同步 `_cache` / `_id_cache`
- 公开读 API：
  - `list_scripts()`：返回白名单 7 字段 `id / name / display_name / platform / version / inspection_parser / updated_at`，**不**暴露 `inspection_script` / `inspection_fields`
  - `get_script_detail(script_id)`：按 id 取完整详情（含 `inspection_script` + `inspection_fields`），未命中返回 `None`
  - `get_script_by_id(script_id)` / `get_script_by_name(name)`：内部完整记录查询，供 `DevOpsServerService.get_connection_config` 注入解析
  - `resolve_script_for_server(server_type, script_name=None)`：显式 `script_name` 命中 → 返回 id，未命中返回 `None`（不静默回退）；否则按 `_DEFAULT_SCRIPT_NAMES`（`linux → linux-bash` / `windows → windows-ps-5.1`）解析，未注册返回 `None`
- 写路径（`preload_all` / `scan_and_upsert`）持 `self._write_lock`；读路径无锁
- 字段规则强类型化：`inspection_fields` 在 `_normalize_entry` 中通过 `normalize_inspection_fields` 归一化为 `list[InspectionFieldRule]`，落库前再回退为 `list[dict]`（`json.dumps(..., ensure_ascii=False)` 入参）

#### Admin 路由 `InspectionScriptAdminRouter`（`app/routers/inspection_script_admin_router.py`）

- 前缀 `/api/admin/inspection-scripts`，tags=`['Inspection Script Admin']`
- `GET ""`：`Depends(require_admin_or_menu_acl("task-scheduler.server-management"))`；调 `svc.list_scripts()` 后再 `_LIST_FIELDS = (id, name, display_name, platform, version, inspection_parser, updated_at)` 防御性二次白名单过滤，**不**返回脚本原文
- `POST /scan`：`Depends(require_admin)`；`await svc.scan_and_upsert()`；异常时 `logger.exception` 后返 500 + `"inspection script scan failed"`（不回显路径 / 原始 detail）；成功返 `{scanned, inserted, updated, failed, skipped}`（5 整数键白名单，2026-08-04 扩展）
- `GET /{script_id}`：`Depends(require_admin)`；`svc.get_script_detail(script_id)`（同步）；未命中 → 404 + `"脚本不存在"`（不回显 script_id）；成功返完整详情（含 `inspection_script` 与 `inspection_fields`）
- `PUT /{script_id}`（2026-08-04 新增）：`Depends(require_admin)`；请求体 `UpdateInspectionScriptRequest`；**`await svc.update_script_detail(script_id, payload)`**（2026-08-05 修正——router 必须 await async service 方法，否则拿到 coroutine 触发 `ResponseValidationError`）；不存在 / 入参非法 → 404 + `"脚本不存在"`
- `DELETE /{script_id}`（2026-08-04 新增；**2026-08-05 事务化**）：`Depends(require_admin)`；`await svc.delete_script(script_id)`（同样必须 await）；成功 → 204 No Content；service 返回 False → 404 + `"脚本不存在"`。**事务化删除**：`InspectionScriptService.delete_script` 在单事务内依次执行 `SELECT name FROM inspection_scripts WHERE id=$1 FOR UPDATE` → `UPDATE devops_servers SET inspection_script_id=NULL WHERE inspection_script_id=$1` → `DELETE FROM inspection_scripts WHERE id=$1`；事务成功提交后用本次事务内读到的 name 清空 `_id_cache[id]` 与 `_cache[name]`，并清扫同 name 漂移到其它 id 的所有 `_id_cache` 残留；DB 异常向上抛出（路由层映射为通用 500），缓存保持原样。`devops_servers.inspection_script_id` 的 `ON DELETE SET NULL` FK 作为兜底保留。
- 服务未初始化：所有端点统一返 500 + `"InspectionScriptService not initialized"`

#### `DevOpsServerService` 与脚本库的协作契约

- 构造入参新增 `inspection_script_service`；`get_connection_config(business_name)` 通过 `inspection_script_id` 调 `inspection_script_service.get_script_by_id(script_id)` 取脚本原文；`inspection_fields` **仅此一处**调用 `normalize_inspection_fields` 转 `list[InspectionFieldRule]`（service 是序列化/结构化的唯一真相源，脚本侧不再重复归一化）
- **返回值结构（2026-08-04 扩展）**：`get_connection_config` 返 14 键 = 基础 7 键（`ip` / `port` / `username` / `password` / `server_type` / `blacklist` / `whitelist`）+ 脚本原文 3 键（`inspection_script` / `inspection_parser` / `inspection_fields`）+ 脚本库元数据 4 键（`inspection_script_name` / `inspection_script_display_name` / `inspection_script_platform` / `inspection_script_version`）。4 个元数据键供 `ServerOpsItem` 透传到脚本层日志 / docx / 邮件正文选择性展示（运维场景下显示"该服务器使用了 linux-bash"或"Windows PowerShell 5.1"），**不**包含 `inspection_script_id`（避免与 `_cache` 内部 id 混淆）
- 脚本未关联（`inspection_script_id IS NULL`）/ InspectionScriptService 未注入 / 脚本库条目不存在 → `get_connection_config` 抛 `ValueError`（错误消息分别含「服务器未关联巡检脚本（inspection_script_id 为空）」/「巡检脚本库条目不存在或已被删除」/「InspectionScriptService 未注入」），由 `server_ops._run_one` 归并为 `skipped=True` 并透传 ValueError 原文到 `error_message` / `inspection_error`，不返回半残 dict
- `_normalize_entry` 在 YAML 扫描阶段调 `inspection_script_service.resolve_script_for_server(server_type, inspection_script_name)`：未命中（无显式 name 且 server_type 默认脚本未注册 / 显式 name 未注册）→ 该条目记 `failed`，不阻断其他条目
- `get_server_detail(server_id)` 走 `inspection_script_service.get_script_by_id(script_id)` 解析 `inspection_script_name` / `inspection_script_display_name`；返回字段仅含元数据（**不**返回脚本原文，原文改走 `/api/admin/inspection-scripts/{id}`）

### 巡检脚本库 `inspection_scripts`（2026-08-03 新增；当前契约）

> 本段是「巡检脚本库 `inspection_scripts`」章节的扩展段，记录 YAML 当前契约 / 脚本输出形态 / 运维踩坑回归保护等落地细节。前一段「服务 `InspectionScriptService`」是模块契约，本段是数据契约。

#### 字段规则行规则（元素 schema）

- `key`：非空字符串，与脚本输出 JSON 字段名一一对应；同一脚本库条目内唯一；非空。
- `name_zh`：非空字符串，前端展示用。
- `unit`：字符串；缺省 / 缺失 = `""`；空单位时填 `""`，**不要写 null**。
- `direction`：`"high"` | `"low"` | `"ignore"` 三选一。
- `warn` / `crit`：`high` 时 `warn <= crit`，`low` 时 `warn >= crit`（边界包含）；`ignore` 时必须为 `None`。

#### YAML 当前契约（`data/devops/inspection_scripts.yaml`）

- **`linux-bash`**（默认 linux 平台）：4 条规则——`disk_used_pct / 磁盘使用率 / % / high / 80 / 90`、`mem_used_pct / 内存使用率 / % / high / 80 / 90`、`cpu_idle_pct / CPU 空闲率 / % / low / 20 / 10`、`load_1m / 1 分钟平均负载 / "" / high / 4.0 / 8.0`
- **`windows-ps-5.1`**（默认 windows 平台）：4 条规则——`disk_used_pct / 磁盘使用率 / % / high / 80 / 90`、`mem_used_pct / 内存使用率 / % / high / 80 / 90`、`cpu_used_pct / CPU 使用率 / % / high / 80 / 95`、`uptime_hours / 系统运行时间 / 小时 / ignore / null / null`

#### 巡检脚本输出形态

- **`linux-bash`**：脚本输出形如 `{"disks":[{"mount":"/","disk_used_pct":42},...],"mem_used_pct":...,"cpu_idle_pct":...,"load_1m":...}`；`disk_used_pct` 数值是**纯数字**（无 `%` 后缀，`%` 由 `unit` 字段承担）；脚本通过 `df -P` + awk 一次性构造 JSON 片段，**awk 内维护 `sep` 变量在每条 JSON 片段前加 `,`**（第一项 `sep=""`, 后续项 `sep=","`），`gsub(/%/, "", $5)` 去 `%`；过滤 `tmpfs/devtmpfs/overlay/squashfs/sysfs/proc/cgroup/...` 等虚拟文件系统；`cpu_idle_pct` 末尾追加 `tr -dc '0-9.'` 把 `%id` / `%ni` 后缀剥掉，输出纯数字 `92.5`
- **`windows-ps-5.1`**：脚本用 PowerShell 遍历 `Get-PSDrive -PSProvider FileSystem`（过滤 `Used` / `Free` 都不为 null 且 `Used+Free > 0` 的盘），手工拼接 `disks` 数组 + `mem_used_pct` + `cpu_used_pct` + `uptime_hours` 为单行 JSON。**JSON 全部用单引号字符串拼接**（避免双引号字符串 `\"` 转义陷阱），`mount` 中 `\` 通过 `.Replace('\', '\\')` 双重化为 JSON 兼容的 `\\`；最终 `Write-Output` 单行 JSON。注意：本节点仍是 `Get-WmiObject` 系列（非 `Get-CimInstance`），保持对老版 PowerShell / WMI-only 环境的兼容

#### 运维踩坑（2026-07-22 锁定；2026-08-03 迁移到脚本库后契约保留）

- Linux 输出 `{"disks":[{...}{...}]}` 缺逗号（导致 JSON 解析失败 `Expecting ',' delimiter`）+ `cpu_idle_pct=92.5%id`（`%id` 是 `top` 输出的列后缀）。两种 bug 都由 `parse_inspection_output` 抛 `InspectionParseError`（`InspectionParseError: inspection json output is not valid JSON: Expecting ',' delimiter`）便于运维侧定位。修复通过 `awk BEGIN { sep="" } ... sep=","` + `tr -dc '0-9.'` 完成
- Windows 脚本曾因 `.Replace('\\','\\')` 在双引号字符串中被 PowerShell 误解析成反引号转义触发 `UnexpectedToken`；修复为单引号字符串 + `.Replace('\', '\\')` 双重化
- 回归测试（保留在 `app/tests/shared/utils/inspection/test_parser.py`）：`test_parse_disks_array_regression_bug_user_reported` + `test_evaluate_disks_array_matches_user_real_linux_output` 锁定 Linux 修复契约；`test_parse_windows_powershell_disks_array_with_escaped_backslashes` 锁定 Windows mount 转义契约

#### 旧数据兜底

- 升级前数据库已存在但旧三列（`inspection_script` / `inspection_parser` / `inspection_fields`）非空的 `devops_servers` 行：按计划文档 `.trae/documents/devops-inspection-script-library-plan.md` 一次性迁移到 `inspection_scripts` 表 + 回填 `devops_servers.inspection_script_id` 后，再执行 `DROP COLUMN IF EXISTS`；`preload_all` 阶段不主动兜底字段值，仅在缺失 `inspection_script_id` 时让 `get_connection_config` 抛 `ValueError`
- `InspectionScriptService.scan_and_upsert` 不存在的 YAML 文件安全返回 `{scanned: 0, inserted: 0, updated: 0, failed: 0}`

#### `pydantic-settings v2` 嵌套 BaseSettings 不递归读 `.env`（2026-07-15 已修复）

- `Settings.devops: DevOpsSettings = Field(default_factory=DevOpsSettings)` 这种嵌套写法，顶层 `.env` 的扁平 key `DEVOPS_CREDENTIAL_KEY` 默认不会穿透到 `settings.devops.credential_key`（其他子 settings 如 `LLMSettings.model_name` 因为字段名直接对应环境变量名而能正常加载；`FeishuSettings.feishu_app_id` / `SandboxSettings.sandbox_docker_mode` 因字段名自带前缀而能正常加载；唯独 `DevOpsSettings.credential_key` 字段名不带 `devops_` 前缀但 env 名带 `DEVOPS_` 前缀，导致不匹配）
- **修复方案**：在 `DevOpsSettings.model_config` 声明 `env_prefix="DEVOPS_"`，使字段 `credential_key` 匹配 env `DEVOPS_CREDENTIAL_KEY`；`inspection.scripts_config_path`（2026-08-03 新增）同样靠 `env_prefix="DEVOPS_"` 匹配 env `DEVOPS_INSPECTION_SCRIPTS_CONFIG_PATH`
- 诊断函数 `diagnose_credential_key()` 的 `settings_unread` 分支保留为防御性诊断，hint 文本已更新为「理论上不应触发，可能是 settings 单例被显式传入空值覆盖或 .env 文件路径/编码异常」
- 回归测试：`app/tests/core/test_devops_diagnostics.py::test_devops_settings_reads_env_via_prefix`

### lifespan 强依赖顺序（2026-08-03 新增章节）

> `DevOpsServerService` 是 `InspectionScriptService` 的**强依赖**：未注入 InspectionScriptService 时构造 DevOpsServerService 会得到半残元数据（`get_connection_config` 缺脚本字段 / admin 详情误返回 None 元数据）。lifespan 通过「前置初始化 + 缺失则跳过构造」的方式避免半残实例被注入到 `app.state`。

- **强依赖链**：`EmailConfigService`（早于 TaskScheduler）→ `AgentConfigService` / `McpConfigService` / `ToolRegistryService` / `SkillRegistryService` → `MCPToolsRegistry` → **`InspectionScriptService`（2026-08-03 新增）** → **`DevOpsServerService`（依赖 InspectionScriptService）** → `ApiConfigService` → `UserServerService` → `ScriptDiscoveryService` → `TaskSchedulerService`
- **2026-08-03 新增段 `InspectionScriptService` 初始化**：DB 池就绪后调用 `_preload_and_publish_service(app, InspectionScriptService, ..., constructor_kwargs={"db": db_pool, "config_path": str(resolve_devops_inspection_scripts_config_path(settings.devops.inspection.scripts_config_path))})`；构造 / preload 任一异常 → `app.state.inspection_script_service = None`，**不**调用 `set_instance`，避免半残实例被注入导致 DevOpsServerService 拿到缺失字段的元数据
- **2026-08-03 改造段 `DevOpsServerService` 初始化**：密钥诊断通过 + `getattr(app.state, "inspection_script_service", None) is not None` → 调用 `_preload_and_publish_service(app, DevOpsServerService, ..., constructor_kwargs={"db": db_pool, "config_path": ..., "credential_key": ..., "inspection_script_service": getattr(app.state, "inspection_script_service", None)})`；密钥诊断失败 → 挂 `devops_server_service_hint = diag.hint`，admin router 500 + hint；**InspectionScriptService 缺失** → 挂 `devops_server_service_hint = "InspectionScriptService 未初始化（缺失或构造失败），DevOpsServerService 作为其强依赖同样不构造..."`，admin router 500 + hint，**不构造 DevOpsServerService**（防止半残 None 元数据被注入 app.state）；构造 / preload 异常同样经 `_preload_and_publish_service` 走 None 兜底 + hint 保留
- **`_preload_and_publish_service` 统一发布辅助**（`app/core/server.py::lifespan` 顶部私有 helper）：构造 → preload 协程 → `set_instance`（成功才调用）→ 挂 `app.state.<state_attribute>`；任一阶段异常统一写 `app.state.<state_attribute> = None` + 不调用 `set_instance`，杜绝半残实例污染下游
- **清理阶段顺序**（与启动顺序**相反**）：`TaskSchedulerService.shutdown()` → `MCPToolsRegistry.shutdown()` → `DevOpsServerService.reset()` + `app.state.devops_server_service = None` → **`InspectionScriptService.reset()` + `app.state.inspection_script_service = None`（2026-08-03 新增）** → `ScriptDiscoveryService` 引用置 None → `FeishuWebSocketService.stop()` → `SkillsService.reset()` → `LogService.stop()` → `DatabasePool.close()`
- **历史修复回顾**：
  - 2026-07-22 修复 `DevOpsServerService` / `ApiConfigService` 在 lifespan 晚于 `TaskSchedulerService` 初始化的顺序 bug（`ops_inspection_sweep` 触发任务 #4 暴露 `devops_server_service 不可用`）；保留与 2026-08-03 改造叠加
  - 2026-08-03 进一步约束 `InspectionScriptService` 早于 `DevOpsServerService`；缺失时 DevOpsServerService 不构造而非保留半残实例

### 巡检字段规则解析与阈值评估模块 `app/shared/utils/inspection/parser.py`

- **职责**：纯函数式模块；只负责把运维在 YAML / 表单中声明的字段规则 (dict) 规范化为强类型 `InspectionFieldRule`、按 `inspection_parser` 类型解析 SSH 输出为 `parsed_values`、对 `parsed_values` 做阈值评估产出每字段 `InspectionFieldResult` 与聚合 `InspectionEvaluation`。**不**连接 SSH、**不**读写数据库、**不**写日志、**不**做副作用；上层 (DevOps 工具 / 服务) 自由组装。
- **公开 API**（`app/shared/utils/inspection/__init__.py` 同步导出）：
  - 异常：`InspectionParseError(ValueError)` —— 解析失败时抛出，消息尽量包含原始文本片段。
  - `@dataclass(frozen=True) InspectionFieldRule(key: str, name_zh: str, unit: str, direction: str, warn: Optional[float], crit: Optional[float])`
  - `@dataclass(frozen=True) InspectionFieldResult(key, name_zh, unit, value: Any, status: str, message: str, warn, crit)`
  - `@dataclass(frozen=True) InspectionEvaluation(parsed_values: Any, fields: Tuple[InspectionFieldResult, ...], status: str, error_message: str = "")`
  - `normalize_inspection_fields(raw) -> list[InspectionFieldRule]`：规则规范化。
  - `parse_inspection_output(parser, stdout) -> Any`：按解析器类型解析 stdout。
  - `evaluate_inspection_fields(parsed_values, rules, parser) -> InspectionEvaluation`：阈值评估。
- **`normalize_inspection_fields` 校验规则**：
  - `raw is None` → `[]`；非 `list` → `ValueError`。
  - 元素必须为 `dict`；`key` / `name_zh` 必须为非空字符串；`unit` 必须为 `str`，缺省默认 `""`。
  - `direction` 仅接受 `"high"` / `"low"` / `"ignore"`；`key` 在同一列表内必须唯一。
  - `high` / `low` 的 `warn` / `crit` 必须为有限数字 (`bool` / 字符串 / `NaN` / `Infinity` 全部拒绝；`bool` 在 Python 中是 `int` 子类，此处用 `isinstance(value, bool)` 提前拦截)。
  - `high` 要求 `warn <= crit`，`low` 要求 `warn >= crit`（边界包含：`warn == crit` 合法）。
  - `ignore` 的 `warn` / `crit` 必须缺省或显式 `None`，否则 `ValueError`。
  - 所有非法情形抛 `ValueError`，消息包含 `<key=xxx>` 或 `<index=N>` 上下文，便于定位。
- **`parse_inspection_output` 行为**：
  - `parser` 大小写不敏感；接受 `json` / `kv` / `csv` / `raw`，未知类型抛 `InspectionParseError`。
  - `json`：取最后一行非空文本，用 `json.loads` 解析为对象或数组并保留原值；字符串 / 数字 / `null` / 布尔等顶层标量视为非法。
  - `kv`：每个非空行按第一个 `=` 切分为 `key=value`（`value` 保留原样字符串，`value` 中后续 `=` 不再切分）；无有效键值对抛 `InspectionParseError`。
  - `csv`：第一行表头 + 第一条数据行，使用标准库 `csv`；空表头 / 无数据行 / 表头无可用键视为非法。
  - `raw`：原样返回 `stdout`（允许空字符串 / `None` 透传）。
  - `json` / `kv` / `csv` 的空 / 全空白 / 非法输入一律抛 `InspectionParseError`（继承 `ValueError`）。
- **`evaluate_inspection_fields` 行为**：
  - 无规则 → `status="unassessed"`，`error_message=""`。
  - 全部 `ignore` → 总 `unassessed`，各字段 `status="unassessed"`，但 `value` 保留原始值以供前端展示。
  - 含 `high` / `low` 规则但 `parser == "raw"` → 总 `status="crit"`，`error_message="raw 解析器不支持结构化阈值评估, 请改用 json / kv / csv 解析器"`；字段列表仍输出 (`status="unassessed"` + `value=None`) 以便前端展示字段元数据。
  - 声明字段缺失 / 非数值 (`bool` 也不算) → 字段 `status="crit"`，`value` 保留 (`None` 或原值)，`message` 写明原因；规则配置的 `warn` / `crit` 仍严格拒绝字符串，但 KV / CSV 解析值中的完整有限数字字符串（含前后空白、科学计数法）可转换后参与阈值评估，空串、`NaN` / `Infinity` 字符串及非数字继续为 `crit`，JSON 字符串不转换。
  - 顶层 JSON 数组或直接传入的其它非 `Mapping` 值在有声明字段时按字段缺失评估为 `crit`，`InspectionEvaluation.parsed_values` 始终保留原始非 `Mapping` 值，不替换为 `{}`。
  - `high` 方向：`value >= crit` ⇒ `crit`，`value >= warn` ⇒ `warn`，否则 `pass`（边界包含）。
  - `low` 方向：`value <= crit` ⇒ `crit`，`value <= warn` ⇒ `warn`，否则 `pass`（边界包含）。
  - 总状态优先级：`crit` > `warn` > `pass` > `unassessed`（`unassessed` 不下拉其它字段的严重度）。
  - `parsed_values` 中的未声明字段被忽略；声明字段缺失 → 该字段 `crit`，总状态被下拉到 `crit`。
  - **disks 数组展开（2026-07-22 新增）**：当 `parsed_values` 是 `Mapping`、声明的 `high` / `low` 字段在顶层缺失，但存在键名 `_DISKS_ARRAY_KEY = "disks"` 且为 `list` 时，对每个元素重复运行该规则；`field_results` 顺序与数组顺序一致，每条 `message` 携带 `磁盘 <mount>` 上下文（无 mount 则为空）；非 `Mapping` 元素或单元素缺字段的元素**跳过**（不污染整体结果），仅当数组本身为空或所有元素都缺字段时降级为单条 `crit` 占位（message 含 `disks 数组为空`）；`disks` 数组**只**作用于顶层 key 缺失、且 `disks` 数组存在的场景（如 `disk_used_pct`），不影响其它字段（如 `mem_used_pct` / `cpu_idle_pct`）的原有路径。辅助函数：`_classify_single_value(rule, raw_value, *, allow_string) -> str` 与 `_expand_disks_array(rule, disks, *, allow_string) -> Tuple[Tuple[InspectionFieldResult, ...], str]`。
- **测试同步（2026-07-22 新增）**：
  - `app/tests/shared/utils/inspection/test_parser.py` 新增 4 个 disks 数组展开用例：`test_evaluate_inspection_fields_disks_array_expands_rule`（2 元素，第一 pass 第二 crit，message 带 mount，parsed_values 保留原值）、`test_evaluate_inspection_fields_disks_array_empty_marks_crit`（空数组 → 单条 crit 占位，message 含「disks 数组为空」）、`test_evaluate_inspection_fields_disks_array_partial_missing_or_bad_values`（非 Mapping 元素跳过 / 非数值元素单条 crit / 无 mount 的元素 message 为空）、`test_evaluate_inspection_fields_no_disks_key_still_crit`（顶层既无声明字段也无 disks 数组 → 原「字段在解析结果中缺失」路径不变）。用例总数：61 → 65。
  - 运维反馈 bug 后**追加**3 个回归用例：`test_parse_disks_array_regression_bug_user_reported`（用户报告坏输出 → `InspectionParseError`，消息含 `not valid JSON`）、`test_evaluate_disks_array_matches_user_real_linux_output`（真实 Linux 输出：4 盘 + mem=80 触发 warn，mount 顺序正确，cpu_idle/load_1m pass）、`test_parse_windows_powershell_disks_array_with_escaped_backslashes`（Windows PowerShell 输出含 `\\` 转义 mount，解析后仍是 `C:\` / `D:\`，disks 数组展开 2 条 + uptime_hours ignore → unassessed）。用例总数：65 → 68，全绿。
  - `app/tests/scripts/test_server_ops.py` 新增 1 个端到端用例：`test_run_server_ops_expands_disks_array_into_field_results`，覆盖脚本 stdout 含 `disks` 数组 + `inspection_fields` 单条 `disk_used_pct` 规则 → `ServerOpsItem.field_results` 出现 2 条同名 key、`inspection_status="crit"`、`parsed_values` 保留原 dict、`to_markdown()` 含 `磁盘 /` 与 `磁盘 /data`。用例总数：50 → 51，全绿。
- **使用边界**：本模块**仅**做解析与评估，不负责 `inspection_script` 实际执行、SSH 连接、结果持久化、消息推送；后续 PR 接 `run_inspection_script` / `inspection_run` `@tool` 时应消费本模块三个公开 API。

### 强白名单契约（2026-07-15 落地）

- `CommandInterceptor(whitelist=None)` 与 `whitelist=[]` 行为完全等价：均视为「空白名单」并启用 allowlist，**所有非黑名单命令必须命中白名单才放行**。
- SSHTools 在内部构造拦截器时直接传入 DB 行 `whitelist` 字段（dict / JSONB 反序列化结果）；DB 中 `whitelist` 为 `NULL` 或 `[]` 都表示「拒绝所有非黑名单命令」，调用方必须显式配置命中项（Linux：`echo ` / `ls ` / `tail ` 等；Windows：`Get-Service` / `powershell ` 等）。

### IP/网络/环境变量黑名单补强（2026-07-27 新增）

- **触发**：运维反馈 `whitelist` 不放行 `hostname -I` / `ifconfig` / `ip addr` 等查询 IP 的命令，但通过 `cat /etc/hosts` / `env` / `printenv` / `echo $SSH_CONNECTION` 等宽口径白名单条目，AI 仍可绕路拿到本机 PUBLIC / PRIVATE / VIP / SCAN 全量 IP。运维选定「黑名单补强」方案，不修改白名单结构。
- **变更范围**：仅 `data/devops/servers.yaml` Linux 节点 `blacklist` 列表新增 7 条；白名单、CommandInterceptor 代码、example 模板均不动。
- **新增条目**（路径类正则前缀 + 命令类正则边界 + 变量类正则词边界）：
  - `^cat /etc/hosts`（正则，^ 锚定开头）：拦截 `/etc/hosts` 及其子路径 `.allow` `.deny`（Oracle RAC / 集群主机表写全 PUBLIC/VIP/PRIVATE/SCAN IP）
  - `^cat /proc/net/`（正则，^ 锚定开头 + 路径前缀）：拦截 `/proc/net/tcp` `/proc/net/route` `/proc/net/fib_trie` 等网络状态
  - `^cat /sys/class/net/`（正则，^ 锚定开头 + 路径前缀）：拦截网卡 MAC / 链路状态
  - `^env(\s|$)`（正则，^ + 空白/行尾边界）：仅拦截无参 `env`，`env KEY=VAL` 写变量形式（运维极少使用）一并被拒
  - `^printenv`（正则，^ 锚定开头）：拦截 `printenv` / `printenv SSH_CONNECTION` 等任意参数
  - `\bset\b`（正则，词边界）：拦截 bash 内置 `set` 刷出全部变量；不误伤 `unset` / `reset` / `dataset`
  - `\bSSH_(CONNECTION|CLIENT|TUNNEL)\b`（正则，词边界）：拦截 `echo $SSH_CONNECTION` / `echo ${SSH_CLIENT}` / `printenv SSH_TUNNEL` / `awk '{print ENVIRON["SSH_CONNECTION"]}'` 等变量引用；不误伤 `MY_SSH_CONNECTION_TOKEN` 等无关字符串
- **白名单保留条目**：`cat /etc/os-release` / `cat /etc/redhat-release` / `cat /proc/cpuinfo` / `cat /proc/meminfo` / `cat /var/log/` / `grep ` / `awk ` / `echo ` 等全部不受影响（黑名单优先于白名单仅在被拒路径上生效）。
- **正则分类器踩坑（2026-07-27 修复）**：`SSH_(CONNECTION|CLIENT|TUNNEL)` 不含 `_REGEX_TOKENS` 中任一转义序列（`\(` / `\(` / `\|` 都需要反斜杠前缀才能触发 `_looks_like_regex`），原写法会被分类到 `_blacklist_exact` 而非正则，整串 `echo $SSH_CONNECTION` 不等于字面 `ssh_(...)` → 不拦截。修复方案：在条目首加 `\b` 词边界触发 `_looks_like_regex` 走正则路径；同样地 `^` 前缀也是合法触发器。运维后续如需新增正则黑名单，需保证条目以 `^` 开头或包含 `_REGEX_TOKENS`（`\d` / `\s` / `\w` / `\b` / `\(` / `\)` / `\[` / `\]` / `\{` / `\}` / `\$` / `\^` / `\.` / `\+` / `\*` / `\?` / `\|` / `\\` / `.*` / `.+` / `.?`）之一，否则会走精确匹配失效。
- **回归保护**：`app/tests/shared/tools/skills/devops/test_command_interceptor.py` 新增 9 个用例（7 条目各 1 + 1 合法路径不被误伤 + 1 黑名单分类器踩坑防回归），用例总数：31 → 40。整个 devops 测试目录 64/64 PASS。
- **设计权衡**：`hostname -I` / `ifconfig` / `ip addr` 等直查命令仍不在白名单内（用户原本已观察到拦截行为，符合设计预期）；运维如确需直查 IP，应通过 inspection_script 内聚的运维工具（如巡检脚本固定采集 + 服务端解析）获取，不在白名单命令面放宽。
- **白名单潜在 bug 备忘（不在本次范围）**：`data/devops/servers.yaml` 第 69 行 `"cat /var/log/"` 无尾空格 → 走精确条目，按 `startswith(pattern + " ")` 判定；`cat /var/log/messages` 不以 `"cat /var/log/ "` 开头 → 不会命中精确条目。本次黑名单补强不影响该行为；后续如要让子路径生效，应改为带尾空格的前缀条目 `"cat /var/log/ "` 或正则 `^cat /var/log/`。

### Windows IIS/FTP 查看命令白名单与 appcmd 写操作黑名单（2026-07-27 新增）

- **触发**：服务器 56（Windows，`6.69.18.56:9984`）的 `whitelist` 不放行 IIS/FTP 查看命令，但运维场景下需支持 `Get-WmiObject Win32_Service` / `Get-Service W3SVC` / `appcmd list sites` 等只读命令查询 IIS 应用池、FTP 站点、当前连接数。运维选定"扩展 whitelist + 配套加 appcmd 写操作 blacklist"方案，不动 `inspection_script`。
- **变更范围**：仅 `data/devops/servers.yaml` + `data/devops/servers.yaml.example` Windows 节点 `blacklist` / `whitelist` 列表；CommandInterceptor / SSHTools / 服务层 / 路由 / 前端均不动。
- **白名单新增条目**（仅精确 / 前缀，无正则）：
  - `Get-WmiObject`（精确）：PowerShell 5.1 默认可用，覆盖 `Win32_Service` / `Win32_PerfRawData_W3SVC_WebService` / `Win32_PerfRawData_FtpService` / `Win32_PerfRawData_MSFTPSVC_FTPService` 等 WMI 类查询。
  - `Get-Process`（精确）：兜底查询 w3wp / ftpsvc 工作进程。
  - `Select-Object` / `Where-Object` / `Format-Table` / `Format-List` / `Out-String`（精确）：管道逐段必需，参考 `test_pipeline_tail_segment_with_exact_whitelist` 已锁定的契约。
  - `"%systemroot%\\system32\\inetsrv\\appcmd.exe list "`（前缀带尾空格）：IIS 7+ 通用只读命令行，覆盖 `list sites` / `list apps` / `list apppools` / `list vdirs` / `list config` / `list backups` / `list wps`。
  - `powershell -Command ` / `powershell -EncodedCommand `（前缀带尾空格）：放行 LLM 习惯的 PowerShell 外壳包裹形式（`powershell -Command "Get-Service W3SVC"` / `powershell -EncodedCommand <Base64>`）。SSHTools 实际包装形式即后者（`app/shared/utils/ssh/platform_shell.py:91-96`）。引号内的子命令因 `_split_pipeline` 引号保护不拆段，整段走前缀条目匹配；引号外的管道仍按 `|` 拆段独立校验。
- **黑名单新增条目**（仅前缀，配套防误写）：
  - 服务写操作：`Start-Service ` / `Set-Service ` / `Restart-Service `（与历史 `Stop-Service ` 对称）。
  - appcmd 写 / 启停 / 删除 / 备份还原：`appcmd add ` / `appcmd set ` / `appcmd delete ` / `appcmd start ` / `appcmd stop ` / `appcmd recycle ` / `appcmd restore ` / `appcmd uninstall `（白名单只放行 list 子命令）。
- **白名单保留条目**：`Get-Service` / `Get-WinEvent ` 不变；`inspection_script` 仍不受白名单约束（`data/devops/servers.yaml.example:57-58`），黑/白名单变更不影响固定巡检脚本。
- **appcmd 路径细节**：`%systemroot%\\system32\\inetsrv\\appcmd.exe` 在 YAML 中字面 `\\`（YAML 不解释转义），CommandInterceptor 按字面前缀匹配，不会触发正则分支（`_REGEX_TOKENS` 不含 `\\`）。
- **PowerShell 外壳引号保护说明**：`powershell -Command "Get-Service W3SVC"` 整段被引号包裹， `_split_pipeline` 不拆段，整段匹配 `powershell -Command ` 前缀 → 放行。这是 `CommandInterceptor._split_pipeline` 的既有契约（`CommandInterceptor.py:219-307`），运维可在双引号内自由组合 cmdlets。安全语义上引号内的命令被 PowerShell 解析为字符串字面量，恶意 cmdlet 仍会被 PowerShell 自身安全策略拦截；运维如需拆段校验，可改用管道形式（`powershell -Command 'Get-Service W3SVC' | Select-Object ...`）。
- **回归保护**：`app/tests/shared/tools/skills/devops/test_command_interceptor.py` 新增用例覆盖：白名单精确条目（`Get-WmiObject` / `Get-Process` 放行 / `Get-WmiObjectList` 不放行）、appcmd 前缀条目（`appcmd list sites` 放行 / `appcmd list` 不带尾空格被拒 / `appcmd set site` 被前缀黑名单拒）、服务写操作黑名单（`Start-Service W3SVC` / `Set-Service W3SVC` / `Restart-Service W3SVC` 拒）、appcmd 全套黑名单（`appcmd add / set / delete / start / stop / recycle / restore / uninstall` 前缀拒）、PowerShell 外壳前缀（`powershell -Command "Get-Service W3SVC"` / `powershell -EncodedCommand <Base64>` 放行 / 管道拆分 `powershell -Command 'Get-Service W3SVC' | Select-Object ...` 拆段后双段放行）。用例总数：40 → 56。整个 devops 测试目录 64/64 PASS。
- **设计权衡**：未引入 `Get-Web*` / `Get-Ftp*` 等 `WebAdministration` 模块 cmdlet（依赖模块已安装，跨环境不稳定）；未引入 `Get-CimInstance`（虽 PowerShell 7 推荐，但 PS 5.1 已有 `Get-WmiObject` 覆盖，留待未来 PR 追加）。
- **不引入 WebAdministration 的理由**：本项目服务器 11/56 历史巡检脚本均使用 `Get-WmiObject`（`memory/devops-sandbox.md:204` legacy-compatible PowerShell 约束），运维团队已对 `Get-WmiObject` 形成使用习惯；引入新 cmdlet 需在白名单增加更多条目且依赖模块版本，扩大攻击面。
- **PowerShell 外壳前缀的设计权衡**：未引入 `cmd /c` / `cmd.exe` 前缀（运维可能用 `cmd /c "net start" | findstr iis` 等），原因：① cmd 入口是字符串拼接重灾区（`&` 链式命令、`%VAR%` 展开），需要更复杂的子段白名单；② PowerShell 5.1 已能覆盖运维 95% 场景（Get-Service / Get-WmiObject / Get-Process / appcmd list），cmd 仅在调用旧批处理脚本时必需；③ 暂未观察到 `cmd /c` 形式的真实运维调用需求。如后续真实场景需要，再追加 `cmd /c ` 前缀。

### 命令白名单放宽与管道逐段校验（2026-07-15）

- 白名单条目匹配语义统一为 `startswith`（大小写不敏感）：精确条目（无尾空格）和前缀条目（尾空格）都按 startswith 判断；正则条目按 `re.search` 判断。
  - `whitelist=["df"]` 自动放行 `df`、`df -h`、`df -i`、`df -T /tmp`。
  - 黑名单精确条目仍按 `==` 严格匹配，不被白名单 startswith 弱化（防御层语义不变）。
- 管道 / 组合命令逐段拆分校验：`CommandInterceptor._split_pipeline` 按 `|`/`||`/`&&`/`;`/`&` 在引号外拆分；引号（单 / 双）内的分隔符视为普通字符，不拆分。
- 每段子命令独立走「黑名单 → 白名单」校验：任一子段失败即整批拒绝，错误信息标注失败子段索引（如 `子命令[1]='rm -rf /tmp' 不在白名单中`）。
- **子段标准化（2026-07-15）**：管道后续子段进入白名单匹配前会先走 `CommandInterceptor.normalize_segment`（`strip + lstrip("|;") + strip`），去除前导分隔符与空白，让精确白名单条目（如 `Select-Object`、`Out-String`）能正常命中 `| Select-Object ...` / `| Out-String`。
- 内置安全黑名单（默认生效，运维不可关闭）：`$\(`（命令替换）、`` ` ``（反引号）、`<\(` / `>\(`（进程替换）、单 `&` 后台执行（正则 `(?<![&|])&(?!&)` 避开 `&&` 与 `&|`）。
- 管道命令运维配置：白名单需逐段子命令都列入；常用只读管道工具集合建议 `["ls ", "cat ", "grep ", "tail ", "awk ", "sort ", "head ", "wc ", "df", "echo "]`。
- 重定向（`>` / `<`）不在内置黑名单内：若运维需禁止可自行追加黑名单正则（如 `> *\S` 防写文件）。

### 正则判定收紧与内置安全黑名单分离（2026-07-15）

- 用户配置的黑/白名单条目判定规则收紧：**仅当显式以 `^` 开头或包含显式正则转义序列**（`\\d` / `\\s` / `\\w` / `\\b` / `.*` / `.+` / `\\(` / `\\)` / `\\[` / `\\]` / `\\{` / `\\}` / `\\$` / `\\^` / `\\.` / `\\+` / `\\*` / `\\?` / `\\|` / `\\\\`）才被识别为正则；含普通字符 `.` / `*` / `+` / `|` / `%` 等的精确条目按字面量匹配，不再误判为正则。
- 内置安全黑名单 `_SAFETY_BLACKLIST` 在 `__init__` 时**强制按正则编译**并独立存放于 `self._blacklist_safety_regex`，不依赖用户的正则判定特征，避免收紧规则后安全条目（反引号、`$\(` 等）被绕过。
- `is_allowed` 决策顺序：① 空命令 ② 内置安全黑名单（强制正则）③ 整串用户黑名单（精确/前缀/正则）④ `_split_pipeline` 子段逐段校验（每段：用户黑名单 → 白名单）。

### 路径集中（2026-07-15）

- `app/core/config/paths.py::resolve_devops_server_config_path(path)`：绝对路径原样返回；相对路径相对项目根解析；空字符串抛 `ValueError`。
- `DevOpsSettings.servers_config_path` 默认值来自 `paths.DEVOPS_SERVER_CONFIG_PATH`（通过 `default_factory`）；`server.py::lifespan` 改用 `resolve_devops_server_config_path` 解析，不再使用 `os.path.dirname(__file__)`。
- `server.py::lifespan` 中 DevOpsServerService 初始化异常仅记 `type(exc).__name__`，不再 `exc_info=True`，避免异常消息泄漏敏感细节。

### 扫描与缓存（2026-07-15）

- `DevOpsServerService.scan_and_upsert` 输入兼容两种顶层形态：`[ ... ]` 与 `{ "servers": [ ... ] }`；非 list 的 `servers` 字段记 `failed` 计数，不抛异常。
- 写入采用单条 `INSERT ... ON CONFLICT (business_name) DO UPDATE ... RETURNING *, (xmax = 0) AS inserted`：缓存通过 RETURNING 行直接同步 `id` / `created_at` / `updated_at` / `password_encrypted`，不依赖再读 DB，扫描成功后 `get_connection_config(business_name)` 可立即解密。
- 同一 `business_name` 重复出现 → 直接计入 `failed`（不允许后者覆盖前者），重复条目不进入缓存。
- **写入路径持 `asyncio.Lock`（2026-07-15；2026-08-04 扩展到脚本绑定）**：`DevOpsServerService._write_lock` 保护 `preload_all` / `scan_and_upsert` / `delete_server` / `set_inspection_script` 中的 `_cache` 与 DB 写入段；读路径（`get_connection_config` / `list_public_servers` / `server_exists` 的 cache 命中分支）无锁。`set_inspection_script(server_id, inspection_script_id)` 支持绑定与传 `None` 解绑，成功后同步缓存的 `inspection_script_id` / `inspection_script_name` / `inspection_script_display_name` 三字段；脚本不存在与脚本服务不可用使用不同异常，路由分别映射为 404 与脱敏 500。

### 前端契约（2026-07-15；2026-07-22 新增删除按钮）

- `web/Agent/src/utils/api.js` 导出 `fetchDevOpsServers` / `scanDevOpsServers` / `deleteDevOpsServer`（大写 O），POST / DELETE 均不带 `Content-Type` / body。
- `TaskSchedulerManager.vue` 服务器表新增「操作」列与每行「删除」按钮（`data-testid="server-delete-btn-{id}"`），点击触发 `window.confirm` 二次确认；通过 `deleteDevOpsServer(serverId)` 调用 `DELETE /api/admin/devops-servers/{server_id}`，成功后仅从本地 `devopsServers.value` 移除该行（不刷新全表），失败走通用脱敏文案「删除服务器失败，请稍后重试」。同一行删除中再次点击会被 `isDeletingRowId` 短路防重复提交。
- `TaskSchedulerManager.vue` 服务器表显示「业务名 / 系统类型 / 最近同步 / 操作」四列；操作列为每行「删除」按钮（见上文）。扫描统计严格只渲染 `scanned / inserted / updated / failed` 4 个整数（白名单复制），未知字段不进入 DOM。
- 切换服务器 Tab 首次加载后置 `hasLoaded=true`，再次进入不重复 GET；服务器列表加载共享 in-flight Promise，参数面板与扫描 Tab 并发请求复用同一次 GET；扫描成功后强制刷新列表。
- 脚本任务的 `server_list` 候选来自同一脱敏清单，提交值只包含 `business_name` 字符串数组；连接配置仍仅允许服务端通过 `DevOpsServerService.get_connection_config(business_name)` 获取，`ip` / `port` / `username` / `password` / `blacklist` / `whitelist` 不得写入 `script_args` 或前端 DOM。
- 列表加载失败显示「服务器列表加载失败」，扫描失败显示「扫描失败，请稍后重试」，两者状态独立。

### 前端按需脚本详情 / 扫描说明（2026-08-03 新增）

- **详情按需两段式加载（2026-08-03 改造）**：`TaskSchedulerManager.vue::openScriptDialog(row)` 改为两段式——
  1. 先 `fetchDevOpsServerDetail(row.id)` 调 `GET /api/admin/devops-servers/{id}` 取 `inspection_script_id` 等元数据
  2. 若 `inspection_script_id == null` → 弹窗以 `{ ...devopsDetail, inspection_script: null }` 直接展示空态
  3. 若非空，再 `fetchInspectionScriptDetail(scriptId)` 调 `GET /api/admin/inspection-scripts/{id}` 取完整脚本原文 + 字段规则；最终 `scriptDialog.value = { open: true, row, detail: { ...devopsDetail, ...scriptDetail }, loading: false, error: '' }`
  4. 脚本详情失败 → 弹窗保留 devops meta 并显示「脚本原文加载失败，请稍后重试」（脱敏文案，不回显后端 detail）
- **服务器详情元数据契约**：弹窗头部新增「平台 / 版本」展示（来自 `inspection_script_display_name` + `inspection_script_name`）；弹窗内容以 `<pre class="script-content">` 等宽字体保留换行/缩进（`white-space: pre`）展示 `inspection_script`，未配置显示「未配置巡检脚本」空态，标题旁附解析器标签 `inspection_parser`
- **白名单弹窗契约不变**：与巡检脚本弹窗互斥（同一时刻仅一个 open），通过 `whitelistDialog.open` / `scriptDialog.open` 互斥切换；列表端点契约不变仍只返 4 字段
- **巡检脚本库扫描面板（2026-08-03 新增）**：`TaskSchedulerManager.vue` 服务器 Tab 内独立 `<section class="inspection-script-scan" data-testid="inspection-script-scan-section">`，仅 admin 可见；含扫描按钮（`data-testid="scan-inspection-scripts-btn"`）+ 提示文案「从 `data/devops/inspection_scripts.yaml` 同步所有平台巡检脚本；仅展示扫描统计，不暴露脚本原文」+ 独立的扫描统计 / 错误区域（`inspectionScanSummary` / `inspectionScanErrorMessage` / `inspectionScanSuccessMessage`），不影响服务器扫描的提示
- **触发函数 `triggerInspectionScriptsScan`**：admin only；带防重复提交（`isScanningInspectionScripts.value` 短路）；调 `scanInspectionScripts()` → `POST /api/admin/inspection-scripts/scan`；失败时使用脱敏文案「巡检脚本扫描失败，请稍后重试」，不回显后端 detail；成功解析 `{scanned, inserted, updated, failed}` 4 字段整数并写入 `inspectionScanSummary`，未知字段不进入 DOM
- **API 封装（`web/Agent/src/utils/api.js`，2026-08-03 新增；2026-08-04 扩展）**：
  - `fetchInspectionScripts()` → `GET /api/admin/inspection-scripts`（admin OR `task-scheduler.inspection-script-library` ACL；返白名单 7 字段）
  - `scanInspectionScripts()` → `POST /api/admin/inspection-scripts/scan`（admin only；返 `{scanned, inserted, updated, failed, skipped}` 5 字段）
  - `fetchInspectionScriptDetail(scriptId)` → `GET /api/admin/inspection-scripts/{scriptId}`（admin only；404 → Error「脚本不存在」，500 → Error 含后端 detail 不回显 script_id）
  - `updateInspectionScript(scriptId, payload)` → `PUT /api/admin/inspection-scripts/{scriptId}`（admin only，2026-08-04 新增；编辑保存接口）

### 巡检脚本库独立 Tab（2026-08-04 新增）

- **菜单权限**：新二级菜单 `task-scheduler.inspection-script-library`（`level=2`，`parent_id='task-scheduler'`，`sort_order=6`，`required_role='admin'`，`icon_key='code'`），从 `task-scheduler.server-management` 拆出独立授权；端点 ACL key 同步替换（列表端点从 `server-management` 迁出为新菜单权限；scan / detail / update 仍 admin only）
- **前端容器**：`TaskSchedulerManager.vue` 新增第 6 个子 Tab（`TAB_LIBRARY = 'library'`），`data-testid="panel-library"`。左右分栏：左侧 `InspectionScriptLibraryPanel`（搜索框 + 节点列表，按 `name / display_name / platform / version` 过滤），右侧 `InspectionScriptEditorPanel`（编辑表单：display_name / platform / version / inspection_parser / 脚本正文多行 textarea / 字段规则表格 + 新增 / 删除）
- **扫描入口迁移**：2026-08-03 旧设计放在「服务器扫描入库」Tab 顶部（`inspection-script-scan-section`），2026-08-04 已迁出至「巡检脚本库」Tab 顶部（`library-scan-btn`）。5 字段扫描统计（`scanned/inserted/updated/skipped/failed`）写入 `libraryScanSummary`
- **编辑优先扫描**：`InspectionScriptService.scan_and_upsert` 改造为「DB 中已有 `name` 跳过更新」——写循环前增加 `if name in self._cache: stats["skipped"] += 1; continue`，不再触发 `_upsert_one_returning`，人工编辑内容不被覆盖
- **保存工作流**：选中节点 → 编辑器 watch 监听 `props.scriptId` 调 `fetchInspectionScriptDetail` 拉详情 → 用户改字段 → 点保存调 `updateInspectionScript(scriptId, payload)` → 成功后 `form` 同步为后端最新记录 + 顶部出现成功提示（`onLibraryScriptSaved` 回调写入 `libraryScanSuccessMessage`）
- **服务新增 `update_script_detail`**：`UPDATE inspection_scripts SET ... WHERE id = $1 RETURNING ...` 单条往返；白名单校验 `platform ∈ {linux, windows}` / `inspection_parser ∈ _VALID_PARSERS` / `display_name` 非空；写后立即同步 `_cache[name]` / `_id_cache[script_id]`（持 `_write_lock`）；DB 写入异常 / 入参非法 / script_id 不存在均返回 `None`（不抛）
- **服务新增 `delete_script(id) -> bool`**：`DELETE FROM inspection_scripts WHERE id = $1` 单条往返；入参非法（`None` / 非 int / `<=0`）→ `False`；DB 返回非 `DELETE n` 格式或 `n=0`（无匹配行）→ `False`；DB 异常 → `logger.exception` 后 `False`；命中 `DELETE 1` → 持 `_write_lock` 同步移除 `_id_cache[script_id]` 与 `_cache[name]`（仅当 `_cache[name]['id'] == script_id` 才动 `_cache`），返回 `True`。`devops_servers.inspection_script_id` 外键为 `ON DELETE SET NULL`，无需手动清理服务器端缓存

### 安全约束

1. **密码 Fernet 对称加密**：service 构造时校验 `credential_key`（44 字节 base64）；`password_encrypted` 写 `BYTEA`，`get_connection_config` 仅供 `SSHTools` 内部解密使用。
2. **公示字段白名单**：`list_public_servers` 严格只含 `id` / `business_name` / `server_type` / `updated_at`；admin router 做二次白名单过滤防御。
3. **扫描失败隔离**：`scan_and_upsert` 返回 4 个数字（`scanned/inserted/updated/failed`），不暴露 YAML 路径 / IP / 密码 / 名单。admin router 把异常统一映射为 500 + 通用错误 `devops server scan failed`。
4. **平台派生仅来自 server**：SSHTools 不接受 LLM 端 `server_type` 覆盖；`server_type` 由 `get_connection_config` 给出后 `_wrap_for_platform` 决定 `bash` 或 `powershell`。
5. **整批拒绝**：批量执行前先做策略过滤；任一命令黑名单命中即整批拒绝，不调用 `paramiko.exec_command`。
6. **SSH 异常通用化**：`AuthenticationException` / `SSHException` / 其他异常一律返回中文通用错误（不携带原始异常字符串），杜绝 IP / 密码 / 用户名泄漏。
7. **Windows 日志命令**：`get_system_logs` 在 Windows 平台走 `Get-WinEvent` 命令（带 LogName 映射），Linux 仍走 `tail -n`，命令本身同样过 `CommandInterceptor`。
8. **批量拦截响应**：被拦截时不返回 `allowed_commands`（避免额外命令回显），仅返回 `blocked_commands` 的 `index` / `command` / `reason`。
9. **解析异常通用化（2026-07-15）**：SSHTools 三个工具 `_resolve_server_config` 的异常捕获改为 `except Exception`，覆盖 `ValueError`（Fernet 密钥错配 `解密失败（Fernet key 与加密时不一致？）: <business_name>`）等所有内部异常，统一返回通用错误 `"无法解析服务器配置"`，不外泄密钥错配细节与业务名。

10. **Windows PowerShell 包装改为 `-EncodedCommand`（2026-07-22 修复）**：`app/shared/utils/ssh/platform_shell.wrap_script_for_platform` 的 Windows 分支从原先的 `powershell.exe -Command "<naive escaped>"` 改为 Microsoft 官方推荐的 `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand <Base64>`(UTF-16 LE)。**触发原因**：`测试服务器56` (Windows) `inspection_script` 多行 PowerShell(用 `Get-PSDrive` / `Where-Object` / `ConvertToDateTime` 等 cmdlet)在原 naive 包装下无法在 Windows OpenSSH server 上正常启动 PowerShell 进程,30 秒后 paramiko `TimeoutError`,`exit_code=None`;`run_id=214` 16:28:36 调度任务 #4 实测命中。原实现 `replace('"', '\\"')` 仅转义双引号,无法处理多行 / 反斜杠 / `$variable` / 反引号 / 单引号,且未携带 `-ExecutionPolicy Bypass` 绕过 Windows 默认 `Restricted` 策略、未携带 `-NoProfile -NonInteractive` 避免 `$PROFILE` 阻塞 / 交互提示。修复后整段脚本作为 UTF-16 LE → Base64 整体传入,完全避开 shell quoting / 转义 / 编码问题;`SSHTools._wrap_for_platform` 也从自实现改为复用 `wrap_script_for_platform`,消除双份 naive 包装漂移。**回归保护**:`app/tests/shared/utils/ssh/test_platform_shell.py` 6 用例,涵盖 Windows 必须用 `-EncodedCommand` / round-trip UTF-16 LE 解码 / 多行 + 特殊字符(`$` / `\` / `{}` / 反引号)无损 / `_encode_powershell_for_encoded_command` round-trip / 空脚本拒绝;`app/tests/shared/tools/skills/devops/test_ssh_tools.py::test_get_system_logs_windows_uses_get_winevent` 改为断言 Base64 解码后含 `Get-WinEvent`;`test_windows_inspection_scripts_support_legacy_powershell` 是预先存在的 yaml 与断言不一致(2026-07-22 已观察到,不属本次修复范围)。

11. **Windows 非 PTY exec 挂死 + PowerShell 输出 80 列硬换行 + Linux stderr 噪音三重修复（2026-07-22）**：`run_id=215` 实测两台服务器均 FAIL 但 MobaXterm 可连。根因与修复：① Windows OpenSSH 默认 shell 在非 PTY exec 通道下等待 stdin EOF 才退出，paramiko `stdout.read()` 阻塞至超时（`TimeoutError`）——`ssh/executor.py::execute_script` 与 `SSHTools` 三处 `exec_command` 调用点统一在读取前 `stdin.close()`（底层 `channel.shutdown_write()`），巡检脚本均不读 stdin，对 Linux / Windows 均无副作用；② Windows PowerShell 5.1 非控制台宿主下 `Write-Output` 经 `Out-Default` 按宿主 80 列硬换行（`\r\n` 截断单行 JSON，如 `cpu_used_pc\r\nt`）——`platform_shell._wrap_powershell_output` 在 `-EncodedCommand` 编码前把用户脚本包进 `& { ... } | Out-String -Width 4096` + `[Console]::Out.Write($__daimon_out)`，绕过宿主宽度格式化；③ Linux 服务器 `/root/.bashrc` 第 22 行残留 `//` 注释（bash 非法语法），非交互 SSH 会话每次都在 stderr 混入 `No such file or directory` 噪音——`server_ops._run_one` 失败判定从 `result.success=False`（含 stderr 非空）放宽为**退出码非 0**，exit 0 + stderr 噪音继续解析评估，stderr 保留在 `item.stderr` 供报告展示。**回归保护**：`test_executor.py` 新增 `test_execute_script_closes_stdin_write_side`；`test_ssh_tools.py` 新增 `test_execute_command_closes_stdin_write_side`；`test_server_ops.py` 新增 `test_ssh_stderr_noise_with_zero_exit_still_evaluated`（exit 0 + stderr 噪音 → success=True 正常评估）与 `test_ssh_stderr_noise_with_zero_exit_parse_failure_marks_crit`（噪音 + 不可解析 → crit）；`test_platform_shell.py` 新增 `test_wrap_powershell_output_wraps_user_script` 并将两处 round-trip 断言改为「脚本原文保留在输出收集包装内」。修复后两台真实服务器端到端复验 `server_ops=2/2 passed`（服务器11 PASS、测试服务器56 磁盘 94.5% 真实 CRIT）。
10. **业务名容错（2026-07-15）**：`_resolve_server_config` 兜底从 `runtime.context["business_name"]` 取值时要求 `isinstance(name, str) and name.strip()`，非字符串类型（MagicMock / None）一律视为缺失，避免下游 KeyError 噪声。
11. **连接期 timeout（2026-07-15）**：`SSHTools._open_client` 显式传 `timeout / auth_timeout / banner_timeout` 给 paramiko.connect，默认 10s（可由 DB 行 `ssh_connect_timeout` 字段覆盖，钳制到 `[1, 60]`）；`exec_command` 的 `timeout` 参数由 `_clamp_timeout` 钳制到 `[1, 120]`。防止对端不可达时工具 hang 死、防止 LLM 误传 `timeout=999999` 导致阻塞。

### 测试覆盖

- `app/tests/shared/test_devops_server_service.py` —— 44 个用例（含 2026-07-22 增补 `delete_server` / `server_exists` 4 个用例 + 巡检脚本字段 9 个用例）：Fernet 校验、Singleton、preload、扫描别名/字段/统计 / `servers:` 顶层 dict / 重复拒绝 / 缓存 RETURNING 同步 / 路径 resolver / 默认路径来自 paths / `_ensure_list` 防御性 JSONB 反序列化（9 个用例覆盖 list 透传 / JSON 字符串还原 / dict 包装 / 非法 JSON 兜底 / None 与基本类型兜底 / `preload_all` 与 `get_connection_config` 端到端字符串还原）/ **巡检脚本字段 9 个用例**（`_normalize_entry` str / literal block / 空 → None / 非法 parser → failed、`scan_and_upsert` 写缓存 + SQL 含新列 + 字面块换行保留、`preload_all` 加载 + 默认值回落、`get_connection_config` 暴露字段）。
- `app/tests/shared/utils/test_devops_server_service.py` —— 10 个用例（2026-07-15 新增）：单例生命周期、`credential_key` 校验（空/非法）、`_write_lock` 类型校验（Bug-6）、`preload_all` 与 `scan_and_upsert` 写路径持锁观测、并发 `scan_and_upsert` 序列化、`_ensure_list` 防御性还原（list / dict / str-JSON / None / 非 JSON / 数字）、`list_public_servers` 严格白名单字段不外泄、`get_connection_config` 未注册业务名抛 KeyError。
- `app/tests/shared/tools/skills/devops/test_command_interceptor.py` —— 31 个用例（2026-07-15 扩展）：原 23 + Bug-1/Bug-2 回归 8 个（`normalize_segment` 去除前导 `|`/`;`、精确白名单 `system.service` / `100%` 按字面量匹配、`^` 前缀仍走正则、`\d` 转义序列仍走正则、管道后续子段精确白名单命中、子段未列入拒绝）。
- `app/tests/shared/tools/skills/devops/test_ssh_tools.py` —— 27 个用例（2026-07-15 扩展）：原 17 + Bug-3/4/5/7 回归 10 个（Fernet ValueError 通用化、业务名 MagicMock 兜底、`_open_client` 传 timeout / auth_timeout / banner_timeout、`_clamp_timeout` 钳制边界、`execute_batch_commands` 拒绝 None / 空列表）。
- `app/tests/core/test_devops_server_lifespan.py` —— 4 个用例：DB 池就绪、空池降级、空 key 跳过、单例 reset。
- `app/tests/routers/test_devops_server_admin_router.py` —— 26 个用例（原 20 + 2026-07-24 增补 ACL 双重门 6 个用例）：路由注册（含 DELETE）、白名单二次过滤、扫描 4 数字、异常不外泄、service 缺失返 500、DELETE 路由注册 / 204 / 404 / service 缺失 500 / DB 失败 500 不外泄 / **`inspection_script` / `inspection_parser` 永不进入 GET 响应**（service 失误返回含脚本字段时 router 二次白名单过滤） / **GET 列表三重 ACL 矩阵**（admin 直 bypass / 普通用户 + `task-scheduler.server-management` ACL 通过 / 无 ACL 403 + service 未被调用） / **其他 admin-only 端点回归保护**（拥有 ACL 的普通用户调 `/scan` / `/{id}` / `DELETE /{id}` 仍返 403）。新增测试通过 `_stub_menu_visible` 仅替换 `MenuPermissionService.get_visible_menu_ids` 方法（复用 conftest autouse fixture 注入的真实 `MenuPermissionService(db=None)`），符合「禁止在测试中虚构生产不存在的依赖」硬约束。
- `app/tests/core/test_devops_diagnostics.py` —— 8 个用例（2026-07-15 新增）：`missing` / `misspelled` / `settings_unread` / `invalid_fernet` 4 类分支、首尾空白忽略、`frozen=True` 不变性、通过路径不打印完整密钥。
- `web/Agent/src/components/__tests__/TaskSchedulerManager.spec.js` —— 65 个用例（2026-07-22 增补 4 个删除按钮用例）：任务列表与调度表单、目标类型显隐、服务器/脚本扫描与强制刷新、白名单脱敏、防重复请求与失败重试、`server_list` schema 参数添加/搜索/多选/回显/失效项/旧参数兼容、并发加载、脚本切换隔离、首次加载与强制刷新失败后的脱敏重试、「保存任务」按钮位于 detail-header 顶部 actions 行（新建模式仅保存、编辑模式追加启停/运行/删除）、服务器行删除按钮（每行渲染 / confirm 取消 / confirm 确认后本地移除 / 网络错误脱敏文案）。

## 沙箱 Agent 架构（Sandbox Agent）

基于 LangChain `deepagents` 库实现，提供安全的代码执行与文件操作环境，通过 Docker 容器隔离保证安全性。

### 核心组件

| 组件                        | 文件位置                                                  | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DockerSandboxBackend`    | `app/shared/tools/middleware/docker_sandbox_backend.py` | Docker 容器生命周期管理、命令执行、文件上传下载；区分 host_workspace（宿主机视角，用于 bind mount）与 container_workspace（容器内视角，/workspace）；支持 4 种 docker_mode 路径投影                                                                                                                                                                                                                                                                       |
| `DockerSandboxMiddleware` | `app/shared/tools/middleware/docker_sandbox_backend.py` | 继承 `FilesystemMiddleware`，自动管理 `DockerSandboxBackend`，提供沙箱工具集；Docker 不可用时可按 `SANDBOX_FALLBACK_TO_LOCAL` 配置降级到 `LocalShellBackend` 本地执行                                                                                                                                                                                                                                                  |
| `sandbox` 工具            | `app/core/tools/SandboxTools.py`                        | `@tool` 装饰的 `sandbox` 函数，通过 `create_deep_agent` 启动沙箱子智能体 |
| `SandboxSettings`         | `app/core/config/settings.py`                           | Pydantic BaseSettings，管理 11 个 `SANDBOX_*` 环境变量，控制 docker_mode / 镜像 / 资源限制 / 路径前缀 / fallback_to_local                                                                                                                                                                                                                                                                                                                               |

### Docker 容器隔离

- **镜像**：默认 `python:3.12-alpine`，可配置
- **资源限制**：`max_memory_mb`（默认 512MB）、`max_cpu_percent`（默认 100%）
- **网络控制**：`network_enabled=False` 默认关闭网络，防止数据外泄
- **工作目录**：每个 Session 独立 host workspace 为项目根下 `data/upload/{session_id}`，由 `app/core/tools/SandboxTools.py` 统一创建后传入 `DockerSandboxMiddleware` / `DockerSandboxBackend`；容器内通过 Docker volume 映射到固定的 `/workspace`，避免 Windows 路径盘符冒号与 Docker mount 格式冲突。后端不再自行创建工作目录。

### 容器化部署模式

`DockerSandboxBackend` 拆分 `workspace`（应用视角）与 `host_workspace`（宿主机视角），通过 `SandboxSettings.docker_mode` 配置 4 种部署模式：

| 模式             | 适用场景                                    | docker_mode | host_workspace 投影                   | Docker 客户端                                 |
| ---------------- | ------------------------------------------- | ----------- | ------------------------------------- | --------------------------------------------- |
| **local**  | 本地直接跑（无容器）                        | `local`   | == workspace                          | `docker.from_env()`                         |
| **socket** | 应用容器挂载宿主机 `/var/run/docker.sock` | `socket`  | `host_workspace_prefix + workspace` | `docker.DockerClient(base_url=docker_host)` |
| **dind**   | Docker-in-Docker（需 `--privileged`）     | `dind`    | == workspace                          | `docker.from_env()`（连内嵌 daemon）        |
| **k8s**    | K8s API 创建 Pod（占位，未实现）            | `k8s`     | _NotImplementedError_               | —                                            |

**关键字段**：

- `SANDBOX_DOCKER_MODE`：枚举 `local / socket / dind / k8s`
- `SANDBOX_DOCKER_HOST`：Docker daemon URL，socket 模式必填（如 `unix:///var/run/docker.sock`）
- `SANDBOX_HOST_WORKSPACE_PREFIX`：宿主机视角前缀，socket 模式必填（如 `/host/app/data`）
- `SANDBOX_CONTAINER_WORKSPACE`：容器内工作目录（bind mount target），默认 `/workspace`

**典型部署**（socket 模式）：

```yaml
# docker-compose.sandbox.example.yml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - ./data:/app/data
environment:
  - SANDBOX_DOCKER_MODE=socket
  - SANDBOX_DOCKER_HOST=unix:///var/run/docker.sock
  - SANDBOX_HOST_WORKSPACE_PREFIX=/app/data   # 容器内 /app/data 对应宿主机 /app/data
```

**K8s 模式占位**：`docker_mode=k8s` 时抛 `NotImplementedError`，提示需先实现 `K8sBackend` 类并在 `DockerSandboxBackend._resolve_host_workspace` 分发。

**Docker 不可用降级**：

- 配置项 `SANDBOX_FALLBACK_TO_LOCAL`（默认 `false`）控制 Docker daemon 不可用时是否降级到本地执行
- `false`（默认）：`DockerSandboxMiddleware` 继续抛出 RuntimeError，`sandbox()` 工具返回清晰的 `tool_error` 事件，提示用户 Docker 未运行
- `true`：`DockerSandboxMiddleware` 在 Docker 连接失败时自动切换到底层 `LocalShellBackend`，子智能体在当前进程的本地 `workspace` 继续执行文件/命令操作
- **安全提示**：`true` 模式会失去 Docker 容器隔离，子智能体代码直接在宿主机/应用进程环境运行，仅限开发、测试或完全可信的内网环境使用

### 长生命周期容器优化

采用**预热容器 + `docker exec`** 方案：

1. **预热启动**：`DockerSandboxBackend.__init__` 时启动容器，执行 `tail -f /dev/null` 保持运行
2. **命令执行**：`execute()` 通过 `docker exec` 在运行中容器内执行命令，无需重复创建容器
3. **会话复用**：同一 `session_id` 复用同一容器，多次命令执行零启动开销
4. **清理释放**：`cleanup()` 显式销毁容器，释放资源

### Subagent 工具模式

沙箱功能通过 `app/core/tools/SandboxTools.py` 中的 `sandbox` 工具函数提供，父 Agent 调用该工具时：

1. 使用 `create_deep_agent` 创建沙箱子智能体
2. 通过 `DockerSandboxMiddleware` 提供隔离的 Docker 容器环境
3. 子智能体自主决策并执行代码/文件操作
4. 执行完成后自动清理 Docker 容器资源

- **调用方式**：`sandbox` 作为 `@tool` 注册到 core agent 工具链，LLM 自动决策调用时机
- **安全边界**：子智能体运行在独立 Docker 容器中，与父 Agent 完全隔离
- **工具集**：`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`（由 `DockerSandboxMiddleware` 继承自 `FilesystemMiddleware` 提供）

**子智能体最终文本取值**：循环结束后取子智能体最终 AI 文本时，数据源使用 `all_messages`（循环内累计的消息列表），并对兜底分支增加 `logger.warning` 记录便于排查。

### 依赖

- `deepagents==0.5.5` — LangChain deepagents 库
- `docker==7.1.0` — Docker SDK for Python

### 沙盒执行前端展示

参考 Kimi "Kimi's Computer" 设计，实现沙盒执行过程的实时前端展示：

**交互流程**：

1. 沙盒开始执行后，AI 聊天气泡的 **timeline.tool 块内**显示 `SubAgentCard` 子智能体折叠卡片（图标、工具名、父 prompt 预览、状态徽章、消息数、耗时）
2. 用户点击子智能体卡片，右侧滑出 `SubAgentDrawer` 详情面板，展示父提问 + 子智能体消息流 + 沙箱摘要 + 沙箱事件时间线
3. 执行完成后，子智能体卡片更新为完成状态

**后端事件**

- `app/core/tools/SandboxTools.py` 增加 `_extract_sandbox_summary_and_events()` 函数，从子智能体消息流中实时提取摘要和事件
- `tool_progress` 事件增加 `sandbox_summary`（当前步骤、总步骤、进度百分比、状态消息）和 `sandbox_events`（详细事件列表）
- `tool_stop` 事件增加 `final_summary`（完成摘要和结果预览）
- 预定义 5 个执行步骤：生成代码 → 写入文件 → 执行代码 → 获取输出 → 分析结果

**前端组件**：

| 组件                 | 文件                                              | 职责                                                                                                                             | 状态                                                          |
| -------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `SubAgentCard`     | `web/Agent/src/components/SubAgentCard.vue`     | 通用子智能体折叠卡片（含沙箱）；按 toolCallId 嵌入 `timeline.tool` 块内                                                        | 保留（功能扩展）                                              |
| `SubAgentDrawer`   | `web/Agent/src/components/SubAgentDrawer.vue`   | 通用子智能体详情 Push Drawer；**支持左侧拖拽调整宽度，宽度记忆在 localStorage** | 保留（功能合并原 SandboxDrawer）                              |


**SubAgentDrawer 模式**：见 "SubAgent 事件协议" 章节。

**前端沙箱数据流**

- `web/Agent/src/utils/sseParser.js`：
  - `createAiMessage()` 移除 `sandboxExecution` 字段；沙箱数据统一由 `subAgents` 列表维护
  - `processSSEEvent()` 的 `custom` case 删除 `if (customToolData.tool === 'sandbox')` 块
  - `updateSubAgentFromCustomEvent()` 增强：tool_start/tool_progress 时合并 `sandbox_summary` 到 `subAgent.summary`；tool_stop 时合并 `final_summary`
- `web/Agent/src/components/MessageBubble.vue`：
  - 移除 `sandboxExecution` prop
  - `timeline.tool` 块移除 `sandboxExecution` 条件分支
  - 新增 `getSubAgentsForGroup(group)`：按 `toolCallId` 在 `group.items` 中查找匹配 subAgent 列表，渲染 `SubAgentCard` 于 `timeline.tool` 内
  - 移除 timeline 之外的 `subagent-cards` 容器（卡片不再堆在会话末尾）
- `web/Agent/src/components/ChatArea.vue`：移除 `sandbox-execution` prop 透传和 `open-sandbox-drawer` 事件
- `web/Agent/src/App.vue`：
  - 移除 `SandboxDrawer` import + 模板
  - 移除 `sandboxDrawerVisible` / `currentSandboxEvents` / `currentSandboxSummary` / `currentSandboxStatus` 状态
  - 移除 `openSandboxDrawer` / `closeSandboxDrawer` 函数
  - 移除 `sandboxExecution` 自动关闭 watch
  - 保留 `SubAgentDrawer` 与 `openSubAgentDrawer` / `closeSubAgentDrawer`

**动画交互优化**：

- `web/Agent/src/components/MessageBubble.vue`：
  - 新增 `hasRunningSubAgent` computed：当 `props.subAgents` 中存在 `status === 'running'` 时返回 true
  - 当 `hasRunningSubAgent` 为 true 时，抑制主智能体思考块的 `thinking-pulse`（🧠 图标缩放脉冲）和 `streaming-cursor`（▌ 光标闪动），保留「思考中...」文字与黄色高亮边框
  - 目的：避免用户通过主智能体思考动画来判断子智能体运行状态
- `web/Agent/src/components/SubAgentCard.vue`：
  - `running` 状态的 `.subagent-icon` 增加 `subagentIconBounce` 上下跳动动画（1.2s infinite），直观提示子智能体正在执行
  - `.subagent-status.running` 增加 `statusPulse` 透明度呼吸动画（2s infinite），进一步强化「执行中」状态感知
  - 目的：将视觉焦点从主智能体思考区转移到子智能体工具条上

### AIMessage 解析兼容性

`_extract_sandbox_summary_and_events` 的 AI 消息分支扩展为兼容以下 content 类型，避免 Anthropic Claude / 部分 OpenAI 兼容模型返回的 list[ContentBlock] 时 `code_generation` 事件整体被跳过：

- **`str`** — 原样提取 markdown ``` 代码块
- **`list[ContentBlock]`** — 拼接所有 `type == "text"` 块后再提取（兼容 Anthropic / 部分 OpenAI 兼容模型）
- **`None` / `dict`** — 防御性归一化

SandboxDrawer 时间线包含 `code_generation` 事件（显示 LLM 生成的代码），与 ToolMessage 事件并存展示"LLM 决策 → 工具执行"完整链路。

## SubAgent 事件协议

> **目标**：子智能体（sandbox / explore / query_knowledge 等）的执行过程在父 AI 聊天气泡中折叠为 `SubAgentCard` 卡片；点击卡片从右侧 push 出 `SubAgentDrawer` 详情面板，展示父提问 + 子智能体内部消息流 + 沙箱摘要 + 沙箱事件时间线（tool='sandbox' 时）。子智能体卡片嵌入 `timeline.tool` 块内按时序渲染，展示元信息（icon/label）由后端统一维护并下发。

### 沙箱 workspace 统一创建约束

为避免多处重复创建/猜测沙箱工作目录，`SandboxTools.py` 是唯一负责创建 `data/upload/{session_id}` 的入口：

- `app/core/tools/SandboxTools.py`：根据 `session_id` 构建 `data/upload/{session_id}`，调用 `mkdir(parents=True, exist_ok=True)` 创建，然后将其作为 `workspace` 参数传给 `DockerSandboxMiddleware`。
- `DockerSandboxBackend` / `DockerSandboxMiddleware`：构造函数要求必须显式传入 `workspace`；传入空/None 时立即抛出 `ValueError`。
- 降级到 `LocalShellBackend` 时，直接使用调用方已创建的 `workspace` 作为 `root_dir`，中间件/fallback 分支不再 `os.makedirs`。
- 这样保证 Docker 模式与本地降级模式使用完全一致的目录结构 `data/upload/{session_id}`。

### 架构总览

```
父 AI 聊天气泡
  └─ timeline (thinking / tool / text)
       └─ tool 块内
            └─ SubAgentCard（折叠卡片，按 toolCallId 匹配）  ──点击──>  SubAgentDrawer（右侧 push drawer）
                                                                       ├─ 头部（工具图标 + 状态徽章）
                                                                       ├─ 沙箱摘要（仅 sandbox：进度条 + 步骤 + 耗时）
                                                                       ├─ 父 agent 提问（可折叠）
                                                                       ├─ 子智能体消息流（HumanMessage / AIMessage / ToolMessage）
                                                                       ├─ 沙箱事件时间线（仅 sandbox，sandbox_events 透传）
                                                                       └─ 底部摘要（耗时 / 消息数 / 工具调用次数）
```

### 后端事件新增字段（向后兼容）

`app/core/tools/events.py` 的 `ToolEvent.data` 字典内追加 3 个新字段（既有字段全部保留）：

| 字段               | 类型           | 出现时机                 | 说明                                                                                                                        |
| ------------------ | -------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `thread_id`      | `str`        | 全部                     | 子 agent 标识（==`tool_call_id`），便于前端按 id 维护 subagent 列表                                                       |
| `parent_prompt`  | `str`        | `tool_start`           | 父 agent 传给子 agent 的 prompt（用于抽屉顶部"父提问"区）                                                                   |
| `child_messages` | `list[dict]` | `tool_progress`        | 子 agent 当前累积的全部 messages，结构化（langchain 对象 → dict）                                                          |
| `final_messages` | `list[dict]` | `tool_stop`            | tool_stop 时的最终消息快照（结构同 `child_messages`），覆盖到 `messages` 字段                                           |
| `meta`           | `dict`       | `tool_start` / history | 子智能体展示元信息 `{icon, label}`，由后端 `app/core/tools/subagent_registry.py` 统一维护并下发；前端首次收到后缓存复用 |

`child_messages` / `final_messages` 每项格式：

```json
{
    "type": "HumanMessage" | "AIMessage" | "ToolMessage" | "Unknown",
    "role": "user" | "ai" | "tool" | "system" | "unknown",
    "content": "str 或 list[ContentBlock]",
    "tool_calls": [{"name", "args", "id"}],   // 仅 AIMessage
    "tool_call_id": "str",                     // 仅 ToolMessage
    "name": "str"                              // 仅 ToolMessage: 工具名
}
```

### 第三方调用兼容保证

`/api/map/chat` SSE 接口有第三方 iframe/portal 调用，本改造**仅新增字段**，不修改/删除既有字段：

- SSE 事件类型 `update` / `custom` / `message` / `end` / `error` / `interrupt` / `tool_stop` **不变**
- `custom` 事件 `data` 字典内仅**追加** `thread_id` / `parent_prompt` / `child_messages` / `final_messages` / `meta` 字段
- SSE 顶层 `{type, data}` **追加** `thread_id` 字段
- `update` 事件顶层追加 `langgraph_node` 字段（节点名），`thread_id` 统一为空字符串（updates 模式下无法精确获取子线程 ID，仅用于格式统一）
- 老客户端标准 JSON 解析**忽略未知字段**，行为不变

### 历史消息 subAgents 字段

子智能体历史通过 LangGraph Checkpoint 持久化，完整还原。核心机制：

- 子智能体的 thread_id == 父 LLM 调该工具时的 `tool_call_id`
- `create_deep_agent(checkpointer=await get_async_checkpointer())` 使用全局共享 checkpointer
- 全局 checkpointer 同时被主智能体使用（共享同一张 `checkpoints` 表），LangGraph 自动按 thread_id 隔离
- PostgreSQL 模式：子智能体 messages 落库，跨进程跨重启可恢复
- 内存模式：单进程内可恢复，重启清空
**返回结构（前端兼容，老字段保留）**：

```json
{
  "session_id": "...",
  "messages": [
    {"id": "...", "type": "user", "role": "user", "content": "..."},
    {"id": "...", "type": "ai", "role": "assistant", "content": "...",
     "tool_calls": [{"name": "sandbox", "id": "call_xxx", "args": {}}]},
    // 子智能体消息流
    {"type": "subagent", "role": "subagent",
     "thread_id": "call_xxx", "tool": "sandbox",
     "parent_message_id": "ai-msg-1",
     "messages": [...], "total": 5,
     // 展示元信息由后端统一提供
     "meta": {"icon": "📦", "label": "沙箱执行"}},
    {"id": "...", "type": "user", "role": "user", "content": "..."}
  ],
  "total": 4
}
```

**前端处理（向前兼容）**：

- `web/Agent/src/utils/sseParser.js` 新增 2 个导出：`isSubAgentHistoryItem(msg)` / `convertSubAgentHistoryToAiSubAgent(msg)`
- `web/Agent/src/App.vue` 还原 history 循环中新增 `else if (isSubAgentHistoryItem(msg))` 分支：把后端 subagent 元素转换为 `subAgent` 对象，**追加到上一个 AI 消息的 `subAgents` 列表中**（而非独立 push 到 messages），由 MessageBubble 的 SubAgentCard 渲染
- 老前端（不识别 `type:"subagent"`）落到 `else` 分支当成普通消息渲染，字段不破坏
- 2026-06-26 新增：后端 AIMessage 返回 `tool_calls`，`App.vue` 历史恢复循环中为普通工具（非子智能体）构造最小化 `tool_stop` 事件注入 `tools/timeline`，使 `MessageBubble` 的 `ToolCallCard` 在历史会话中正常渲染（状态为"已完成"，步骤数为 1）

