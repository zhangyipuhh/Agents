# 项目记忆索引

> **读取规则**：先读本索引 → 按关键词定位分片 → 只读目标分片（memory/ 目录）。
> 禁止无目的全量读取任何分片；分片内查找优先 Grep 后按行号区间 Read。
> 历史全文归档：memory/_archive/project_memory_full.md（仅兜底，正常勿读）。

| 分片 | 内容 | 关键词 | 更新时间 |
|---|---|---|---|
| [架构与目录](memory/architecture.md) | 项目概述、技术栈、数据目录约定、项目架构、配置归属隔离、项目文件夹方案、环境变量 | 架构、技术栈、目录、路径、环境变量、OwnershipScope | 2026-07-26 |
| [数据库设计](memory/database.md) | 全部表结构、字段、索引、迁移约定、inspection_scripts 巡检脚本库表、devops_servers 巡检脚本外键改造、巡检脚本库编辑优先写入策略、`get_connection_config` 返回 14 键（基础 7 + 脚本原文 3 + 脚本库元数据 4）+ `server_ops._run_one` ValueError 归并 skipped 契约 | 表、字段、索引、迁移、init_all_tables、SQL、inspection_scripts、编辑优先、update_script_detail、get_connection_config、14 键、ValueError、skipped | 2026-08-04 |
| [API 与核心工具](memory/api-routes.md) | API 接口配置、API 路由汇总（路由→文件→权限）、核心工具清单、/api/admin/inspection-scripts 路由（含 PUT 更新 + 5 字段扫描响应） | /api/、路由、端点、require_admin、Core Tools、inspection-scripts、PUT | 2026-08-04 |
| [认证与会话控制](memory/auth.md) | 双 Token 认证、聊天并发控制、HITL、提示词三层架构、动态上下文注入（DYNAMIC_NODE_REGISTRY）、State/Context 构建器、referenced_servers 一等 context 字段 | 认证、Token、并发、HITL、提示词、上下文注入、registry、referenced_servers | 2026-07-26 |
| [Agent 与 Skill 体系](memory/agents-skills.md) | Agent 统一构造入口、Skill 系统、AGENTS.md 加载器、配置加载服务、工具注册中心、缓存、工具绑定双轨制、记忆存储、scripts/ | Agent、Skill、bootstrap、工具注册、缓存、记忆存储 | 2026-07-26 |
| [MCP 体系](memory/mcp.md) | MCP 配置 CRUD、MCP/Tool/Skill Admin Router、统一 Agent Router、MCPToolsRegistry | MCP、服务器、工具注册、Admin Router | 2026-07-26 |
| [前端架构](memory/frontend.md) | web/Agent 前端架构、MCP 管理组件、UserSettingsDialog 系列、斜杠命令注册表、触发器注册表（# 行内服务器 Chip）、TriggerPanel、MessageBubble mention 统一渲染、contenteditable 编辑器 DOM 工具、InputBox 会话切换清理本地态、TaskSchedulerManager context_overrides 参数化编辑器（2026-07-29）、巡检脚本按需两段式加载 + 脚本库扫描面板（2026-08-03）、巡检脚本库独立 Tab + 节点列表（含行尾删除按钮 + 二次 confirm + emit select null 反向同步）+ 编辑保存面板（2026-08-04） | 前端、Vue、组件、UserSettingsDialog、斜杠命令、triggerRegistry、TriggerPanel、inputEditor、会话切换、context_overrides、reference_server、inspection-scripts、巡检脚本、inspection-script-library、InspectionScriptLibraryPanel、InspectionScriptEditorPanel、删除按钮、行尾 delete | 2026-08-04 |
| [统一审计日志（2026-07-29）](memory/architecture.md#统一审计日志2026-07-29) | 统一日志 `LogService` 唯一入口；SSH/devops 事件；可信身份 + 可信 IP；管理员查询信封 | LogService、审计日志、SSH、devops、可信身份、可信 IP、log_ip、查询信封 | 2026-07-30 |
| [菜单权限与用户配置](memory/menu-acl.md) | 用户菜单权限管理（MENU_CATALOG/ACL，含 `task-scheduler.inspection-script-library` 巡检脚本库菜单）、用户服务器配置管理 | 菜单、权限、ACL、allowed_agents、服务器配置、inspection-script-library | 2026-08-04 |
| [DevOps 与沙箱](memory/devops-sandbox.md) | SSH 远程服务器管理、巡检脚本库（inspection_scripts / InspectionScriptService，含 update_script_detail + delete_script + 编辑优先扫描 + ON DELETE SET NULL）、lifespan 强依赖顺序、`get_connection_config` 返回 14 键（脚本库元数据 4 键透传到 `ServerOpsItem`）、沙箱 Agent 架构、SubAgent 事件协议 | DevOps、SSH、沙箱、SubAgent、事件协议、inspection_scripts、InspectionScriptService、update_script_detail、delete_script、编辑优先、ON DELETE SET NULL、get_connection_config、14 键、ServerOpsItem、脚本库元数据 | 2026-08-05 |
| [其他子系统](memory/misc.md) | 邮件系统、飞书工具、CI 测试 | 邮件、飞书、CI、GitHub Actions | 2026-07-31 |

## API 路由速查表

> 注册入口统一在 `app/main.py::register_routers`；端点级明细见 [api-routes 分片](memory/api-routes.md)。
> 「登录态」= 依赖全局 auth_middleware，无额外角色校验；「router 级」= `APIRouter(dependencies=[...])` 统一守护。

| 前缀 | 路由文件 | 权限 |
|---|---|---|
| /api/auth | app/shared/routers/auth_router.py | login/register/captcha 公开，其余登录态 |
| /api/users | app/shared/routers/user_router.py | 管理端点 require_admin；profile/username 登录用户限本人 |
| /api/session | app/shared/routers/session_router.py | 登录态；/admin/* 逐端点 require_admin |
| /api/files | app/shared/routers/file_router.py | 登录态 |
| /api/project | app/shared/routers/project_router.py | 登录态 |
| /api/core | app/core/router/file_upload_router.py | 登录态 |
| /api/core/download | app/core/router/file_download_router.py | 登录态 |
| /api/contract | app/features/contract_host_agent/router/contract_router.py | 登录态 + chat_concurrency_dependency 并发控制 |
| /api/map | app/routers/knowledge_router.py | 登录态 |
| /api/ai-coding-check | app/features/AI_Coding_Check_agent/router/ai_coding_check_router.py | 登录态 |
| /api/agent | app/routers/agent_router.py | 登录态；内部按 request.state.role 过滤可见 agent（allowed_agents） |
| /api/admin/agents | app/routers/agent_admin_router.py | require_admin（router 级） |
| /api/admin/mcp | app/routers/mcp_admin_router.py | 登录态（详见 mcp 分片） |
| /api/admin/tools | app/routers/tool_admin_router.py | require_admin（router 级） |
| /api/admin/skills | app/routers/skill_admin_router.py | require_admin（router 级） |
| /api/admin/scripts | app/routers/script_admin_router.py | require_admin（router 级） |
| /api/admin/task-schedules | app/routers/task_scheduler_router.py | 逐端点 require_admin_or_menu_acl('task-scheduler.scheduled') |
| /api/admin/email | app/routers/email_admin_router.py | 逐端点 require_admin_or_menu_acl('task-scheduler.email-settings.*') |
| /api/admin/api-configs | app/routers/api_config_router.py | 逐端点 require_admin_or_menu_acl('task-scheduler.api-config') |
| /api/admin/devops-servers | app/routers/devops_server_admin_router.py | 列表端点 require_admin_or_menu_acl('task-scheduler.server-management')，其余 require_admin；详情端点 2026-08-03 改造为返回 inspection_script_id / inspection_script_name / inspection_script_display_name 元数据（脚本原文改走 /api/admin/inspection-scripts/{id}） |
| /api/admin/inspection-scripts | app/routers/inspection_script_admin_router.py | 列表 require_admin_or_menu_acl('task-scheduler.server-management')；/scan / PUT / DELETE /{script_id} 仅 admin（PUT/DELETE 后续可基于 ACL 扩展） |
| /api/admin/user-servers | app/routers/user_server_router.py | 逐端点 require_admin_or_menu_acl('task-scheduler.server-management') |
| /api/admin/permissions | app/routers/menu_permission_router.py | require_admin（router 级） |
| /api/admin/permissions/agents | app/routers/agent_permission_router.py | require_admin（router 级） |

## 前端组件速查表

> 根目录均为 `web/Agent/src/`；「展示层」= 数据由父组件注入，不直接调 API。
> API 函数统一封装在 `src/utils/api.js`（`fetchWithAuth` 自动注入 Bearer + X-Session-ID + 401 刷新重试）。

| 分组 | 组件 | 数据来源 API |
|---|---|---|
| 入口 | App.vue（index.html） | /api/session/*、/api/agent/chat（SSE）、/api/auth/* |
| 入口 | KnowledgeApp.vue（knowledge.html） | /api/map/knowledge-chat（SSE）、/api/map/knowledge/files |
| 入口 | PortalApp.vue（portal.html） | public/app-config.json（运行时配置）、/api/auth/* |
| 入口 | views/LoginView.vue / RegisterView.vue（login.html） | /api/auth/captcha、login、register |
| 聊天 | ChatArea.vue / MessageBubble.vue / TopBar.vue | 展示层（App.vue 注入） |
| 聊天 | TriggerPanel.vue | 通用触发器面板（搜索 + 平铺 + 键盘导航；由 InputBox 注入 items/searchKeys） |
| 聊天 | InputBox.vue | /api/agent/list、/api/core/upload*、/api/core/upload-config、DELETE /api/core/attachments、/api/admin/user-servers/tree（# 触发器数据源） |
| 聊天 | KnowledgeChat.vue / ProfileInputBox.vue | /api/map/knowledge-chat（SSE）、/api/core/upload* |
| 聊天 | HumanApprovalBox.vue | HITL resume（经 chatStream 透传） |
| 聊天 | QueueStatusBanner.vue | SSE queue 事件 / HTTP 429 |
| 聊天 | SubAgentCard / SubAgentDrawer / ToolCallCard / SkillTags / SubAgentSuggestionStrip | 展示层（SSE 事件流解析自 sseParser.js） |
| 聊天 | DislikeDialog.vue | POST /api/agent/message-feedback |
| 会话/项目 | Sidebar.vue | /api/session/list、delete、title、export；/api/project/* |
| 会话/项目 | ProjectDialog.vue / ProjectDropdown.vue | /api/project/create、/list |
| 文件 | SessionFileDrawer / FolderTree / FilePreviewModal / FilePreview | /api/session/{id}/files/tree、preview、download |
| 文件 | FileManagerModal.vue / KnowledgePage.vue（旧版） | /api/map/knowledge/files、file-preview |
| 设置 | UserSettingsDialog.vue（8 Tab 容器） | /api/users/*、/api/session/admin/* |
| 设置 | AgentManager.vue（含 SectionEditor 子组件） | /api/admin/agents/*、/api/admin/tools、/api/admin/mcp/* |
| 设置 | McpServerManager.vue | /api/admin/mcp/servers/* |
| 设置 | ToolManager.vue | /api/admin/tools/* |
| 设置 | SkillManager.vue | /api/admin/skills/* |
| 设置 | TaskSchedulerManager.vue | /api/admin/task-schedules/*、/api/admin/devops-servers/*、/api/admin/user-servers/tree、/api/admin/scripts/*、/api/admin/email/policies、/api/admin/api-configs/tree |
| 设置 | EmailSettingsManager.vue | /api/admin/email/* |
| 设置 | ApiConfigManager.vue | /api/admin/api-configs/* |
| 设置 | MenuPermissionManager.vue | /api/admin/permissions/menu-catalog、/users/{id}/grants |
| 设置 | AgentAccessManager.vue | /api/admin/permissions/agents/catalog、/users/{id}/grants |
| 设置 | UserServerManager.vue / ImportServerDialog.vue | /api/admin/user-servers/*、/import；/api/admin/devops-servers（导入源列表） |
| 其他 | HelloWorld.vue | 脚手架示例，无 API |

## 写入规则

- 修改某主题 → 只 Edit 对应分片，并更新本索引对应行的「更新时间」。
- 新增章节 → 写入对应分片；若无合适分片，在 memory/ 新建分片并在本索引登记一行。
- 只记录最终/当前状态，变更历史查 git log。

## 变更日志

- **2026-07-30**：审计日志新增可信 IP 字段（`AgentContext.log_ip` + `request.client.host` 强制覆盖 + `SSHTools._emit_log` 写入 `LogEvent.ip_address`），SSH 工具审计日志补全客户端 IP（修复前 6 行 `ssh_execute_command` 全部 NULL）。
- **2026-07-29**：统一日志 `LogService` + 迁移 auth/user/session/SSH + admin 查询 API + 可信身份双层 + 命令/凭据脱敏 + 队列预留 + 197 测试 GREEN。
