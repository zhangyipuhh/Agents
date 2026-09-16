# 智能运维中心

智能运维中心是面向运维人员的工作台，提供 SSH 服务器管理、巡检脚本、采集记录、智能检测等能力。

![智能运维中心](/help/screenshots/features-ops-console/01-ops-console.png)

## 前置条件（必须先确认，否则功能不可用）

> ⚠️ **本章是全平台前置依赖最复杂的功能模块**。任一前置缺失会导致对应子功能不可用。

### 1. Docker daemon 必须运行
- Linux：`systemctl status docker` 或 `docker info` 验证
- Windows：Docker Desktop 必须启动
- macOS：Docker Desktop / OrbStack
- **未运行时调用 sandbox 工具会抛 `DockerException`**

### 2. `.env` 必须配置 `SANDBOX_*` 11 个字段（**重启后生效**）
配置文件位于项目根 `.env`，字段详见「[基本设置 → 沙箱与任务](/help/features/basic-settings#沙箱与任务)」。最关键的几个：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `SANDBOX_DOCKER_MODE` | `local` | local / socket / dind / k8s |
| `SANDBOX_IMAGE` | `python:3.12-alpine` | 容器内 Python 运行时 |
| `SANDBOX_MAX_MEMORY_MB` | `512` | 容器内存限制（MB） |
| `SANDBOX_NETWORK_ENABLED` | `false` | **默认禁用外网**（隔离） |
| `SANDBOX_DEFAULT_TIMEOUT` | `60` | 命令默认超时（秒） |
| `SANDBOX_FALLBACK_TO_LOCAL` | `true` | Docker 不可用时降级到本地 |

### 3. 至少配置 1 台 `devops_servers`
- admin 在「运维任务 → 服务器管理」新增
- 填写：服务器名 / IP / SSH 端口（默认 22）/ 用户名 / 密码或私钥
- 测试连通性后再启用

### 4. 用户被授予 `task-scheduler.server-management` 菜单 ACL
- 普通用户需在「权限管理 → 菜单管理」被授权
- ACL key：`task-scheduler.server-management`
- 仅有菜单权限还不够，**还需服务器级授权**（`user_server_nodes.created_by_user_id` 过滤）

### 5. 启用 CORS 允许来源（如跨域访问）
- `.env` 配置 `CORS_ALLOWED_ORIGINS`，默认空 List
- 第三方 server-to-server 不受 CORS 约束

## 主要模块

### 服务器管理

入口：左侧栏「运维控制台」。服务器以卡片形式展示，左上角指示灯标识健康状态（绿 = 正常，红 = 存在 warn/crit 指标，灰 = 未知），卡片上直接显示 CPU / 内存 / 存储 / IO 关键指标与最新检测时间。

#### 卡片操作
- 点击卡片标题：打开服务器详情窗口（采集记录 / 智能检测 / SSH 终端）
- 右上角图标：唤起巡检 / 编辑配置 / 删除服务器
- 顶部「服务器管理 / 日志管理」两个 Tab 切换视图


纳管 SSH 服务器，支持：

- **手动采集**：点击「智能检测」触发一次完整巡检
- **定时采集**：通过运维任务调度配置 cron 表达式
- **采集记录**：查看历史巡检结果、状态、耗时

![服务器管理主界面](/help/screenshots/features-ops-console/01-ops-console.png)

#### 服务器卡片信息
- 业务名 / 服务器名 / IP / 操作系统类型（Linux / Windows）
- LED 三态：正常（绿）/ 告警（黄）/ 故障（红）/ 未采集（灰）
- 最后检测时间（`YYYY-MM-DD HH:MM`，来自 `server_latest_snapshot.collected_at`）
- 4 联指标条：CPU 使用率 / 内存占用 / 存储使用 / 服务器负载（仅 Linux）

#### 卡片头操作按钮
- **日志按钮**：调取 `GET /api/admin/server-inspection/records?server_id=X&limit=100` 展示历史采集记录
- **智能检测按钮**：触发 `OpsDetectChatWindow` 流式聊天窗口

#### 详情窗口（点击服务器卡片打开）
- 4 联指标条（与卡片同款）
- 操作系统 / CPU 型号 / 运行时长（3 项 kv 表格）
- **物理盘分组**：按 `host_disk` + `disk_index` 分组，每组显示磁盘头 + 多分区卡
- 分区卡：使用率（来自 `disk_used_pct`）
- 磁盘头指标：排队 / IO 利用率（来自 `io_await_ms` / `io_util_pct`）

![服务器详情窗口](/help/screenshots/features-ops-console/01-ops-console.png)

### 采集记录窗口

![运维控制台滚动视图](/help/screenshots/features-ops-console/01-ops-console.png)

点击卡片头「日志」按钮打开，左侧列表（280px）+ 右侧详情（自适应）。

#### 左栏每行内容
- 时间（`formatCollectedAt` 友好展示）
- 状态徽章（`inslog-badge`）：pass / warn / crit / skipped / unassessed 五态色块
- 耗时（`formatDuration`）
- SSH exit_code
- 成功 / 失败
- error_message 红字摘要

#### 右栏详情
- 复用 `OpsDetailWindow` 同款样式
- 通过 `mapRecordToServer` 纯函数归一化为 `ServerItem` 形状
- 避免嵌套窗口外壳造成双重标题栏

![采集记录窗口](/help/screenshots/features-ops-console/01-ops-console.png)

### 巡检脚本库

可视化编辑巡检脚本，支持：

- 脚本库列表（按操作系统 / 用途分类）
- 脚本编辑（命令、参数、阈值）
- 脚本扫描：自动生成字段规则（CPU / 内存 / 磁盘 / 负载）
- 脚本删除（事务化保护）

![巡检脚本库](/help/screenshots/features-ops-console/01-ops-console.png)

#### 巡检字段规则表（来自 `memory/devops-sandbox.md`）

| 字段 | 适用系统 | 默认 warn | 默认 crit | 语法 |
|---|---|---|---|---|
| `cpu_used_pct` | Linux / Windows | 80 | 95 | 整数百分比 |
| `mem_used_pct` | Linux / Windows | 80 | 95 | 整数百分比 |
| `disk_used_pct` | Linux / Windows | 80 | 95 | 整数百分比 |
| `io_util_pct` | Linux | 80 | 95 | 整数百分比（`/proc/diskstats`） |
| `io_await_ms` | Linux | 10 | 50 | 浮点毫秒 |
| `load_1m` | Linux | 4 | - | 浮点数（独立于 80% 阈值） |
| `inode_used_pct` | Linux | 80 | 95 | 整数百分比（OS 指标） |
| `swap_used_pct` | Linux | 50 | 80 | 整数百分比（OS 指标） |

#### 介质差异化阈值（SSD / HDD）
- `ssd_warn` / `ssd_crit`：SSD 磁盘专用阈值
- `hdd_warn` / `hdd_crit`：HDD 磁盘专用阈值
- 介质识别：Linux `/sys/block/*/queue/rotational`（1=HDD, 0=SSD）；Windows `Win32_PhysicalMedia.MediaType`

### SSH 工具

智能体可在对话中调用 SSH 工具远程执行命令：

- `execute_command`：单条命令执行（带 `timeout` 入参被忽略，由 `devops_servers.ssh_timeout` 钳制）
- `execute_batch_commands`：批量命令执行
- `execute_script`：执行巡检脚本
- `execute_third_party_script`：执行第三方 SSH 脚本
- `get_system_logs`：获取系统日志（硬编码 30 秒超时）

#### SSH 执行期 timeout 高内聚方案
- `devops_servers.ssh_timeout INTEGER NOT NULL DEFAULT 30` + CHECK `[1, 120]`
- 单一解析点 `DevOpsServerService.resolve_ssh_timeout(value) -> int`
- `get_connection_config` 返回 dict 含 `ssh_timeout: int` 已钳制
- **LLM / 脚本不可绕过**（@tool timeout 入参 / run_server_ops.ssh_timeout 形参保留仅用于向后兼容 LLM schema / caller）

### 第三方 SSH 执行器

支持通过第三方接口（如安全网关、堡垒机）执行 SSH 命令，避免直接暴露服务器凭据。

#### 启用流程
1. `.env` 配置 `THIRD_PARTY_EXECUTOR_ENDPOINTS`（**注意：不是 `_JSON` 后缀**，详见 `memory/devops-sandbox.md`）
2. 配置 endpoints JSON 数组，含 `name` / `endpoint_url` / `public_key_pem` / `enabled` / `is_primary` 等
3. 巡检脚本中切换 `use_third_party_executor=true` + `third_party_endpoint_name=<name>`
4. 第三方失败按 crit 处理，**不**降级到本地 paramiko

#### 端点兜底增强（2026-08-05）
- `.env` 空值 / `[]` / 非法 JSON / 无 primary 全部走 `_read_env_file_endpoints_fallback` 兜底
- 失败时 `logger.error` 打印 `error_code / endpoint / exc / loaded_endpoints`
- `diagnostic_summary()` 返回 `[name, enabled, url]` 摘要（不含 `public_key_pem`）

### 智能检测

点击服务器卡片头的「智能检测」按钮，智能体会：

1. 自动调取最近一次采集记录
2. 结合知识库中的运维文档
3. 输出巡检结论 + 处置建议

#### 流式聊天窗口（`OpsDetectChatWindow`）
- 独立浮动窗口
- `onMounted` 自动调 `chatStream` 一次
- 合成 `ops-detect:{server_id}:{ts}` session_id（不落 sessions 表，不污染主侧边栏）
- `DETECT_QUESTION` 固定两段式问题文本
- `agent_name='project'`
- `extras={referenced_servers: [{name: businessName, server_type}]}` 注入
- SSE 流式渲染 `safeMarkdown`（DOMPurify XSS 加固）

![智能检测窗口](/help/screenshots/features-ops-console/01-ops-console.png)

### ACL 控制

智能运维中心受 `task-scheduler.server-management` 菜单 ACL 控制：

- 拥有该菜单权限：可访问所有分配的服务器
- 无该菜单权限：完全不可见

#### 三端点 ACL
- `GET /api/admin/server-inspection/latest`（最新快照）
- `GET /api/admin/server-inspection/records`（历史记录）
- `POST /api/admin/server-inspection/collect`（手动采集）

三端点均需 `require_admin_or_menu_acl('task-scheduler.server-management')` + OwnershipScope 数据层过滤。

## 常见问题

### Docker 不可用，sandbox 工具报错？
**错误文案**：`沙箱执行失败：Docker daemon 未运行或未安装。`

**修复**：
1. 启动 Docker daemon（Linux: `sudo systemctl start docker`）
2. 或设置 `SANDBOX_FALLBACK_TO_LOCAL=true`（仅开发环境，失去隔离）

### SSH 连接超时？
**错误文案**：`SSH 连接超时` 或 `Connection timed out`

**排查**：
1. 检查 `devops_servers.ssh_port`（默认 22，是否被防火墙修改）
2. 检查 `ssh_timeout` 配置（默认 30 秒，范围 [1, 120]）
3. 检查网络连通性：`ping <server_ip>` + `telnet <server_ip> 22`

### 采集记录状态全 pass，但详情窗口异常盘符红字？
**现象**：磁盘列表显示 `磁盘 C: 异常：使用率 95%`

**原因**：`field_results` JSONB 中的 `warn` / `crit` 项触发颜色高亮
**说明**：正常现象，阈值告警

### 智能检测窗口白屏？
**排查**：
1. 检查 `agent_name='project'` 是否在 `users.allowed_agents` 内
2. 检查 project 智能体是否启用了 `map` 工具（智能检测使用 `query_inspection_records`）
3. 查看 SSE 事件流是否有 `agent_error`

## 相关章节

- [基本设置 → 沙箱与任务](/help/features/basic-settings#沙箱与任务) — 沙箱配置详解
- [定时任务调度](/help/features/task-scheduler) — cron 触发巡检
- [MCP 服务器管理](/help/features/mcp-servers) — 第三方 SSH 网关
- [权限管理](/help/features/permission-management) — 服务器级 ACL
