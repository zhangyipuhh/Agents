# API 与核心工具

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## API 接口配置（2026-07-20 新增）

「用户设置与管理 → 定时任务」内的第 4 个 Tab「API接口配置」，类 Apifox 的轻量接口管理与健康校验模块。**与定时任务调度完全解耦**（不参与 cron），仅复用其设置入口。

### 数据库表（`init_all_tables.sql` 章节 21，幂等 DDL）

- `api_config_nodes`：树节点（`parent_id` 自引用 NULL=根，`node_type` CHECK `folder|api`，`name`，`sort_order`），索引 `(parent_id)`，删除 ON DELETE CASCADE
- `api_configs`：接口配置（`node_id` UNIQUE FK 级联），`method` CHECK `POST|PUT`、`url`、`params`/`headers`/`form_fields` JSONB（`[{name,value,description}]`）、`body_type` CHECK `none|json|xml|text|form-data|x-www-form-urlencoded`、`body_content` TEXT、`expectations` JSONB 断言规则
- `api_check_runs`：调用历史（`config_id` FK 级联），`http_status/duration_ms/check_passed/response_excerpt(截断4000)/error_message`，索引 `(config_id, created_at DESC)`

### 后端

- `app/shared/utils/api_config_service.py::ApiConfigService`：构造注入 db（`db=None` 优雅降级：preload no-op、读返回空、写抛 RuntimeError）；内存+DB 双写；所有写/读方法接收 `scope: OwnershipScope` 参数做用户归属隔离（2026-07-24 起，详见「通用配置归属隔离」落地二）；`preload_all()` / `get_tree(scope)` / `create_node(parent_id, node_type, name, scope)`（api 节点自动建默认配置行；非 admin 父节点必须可见且 folder）/ `update_node(node_id, scope, ...)`（防环 + 父节点归属校验）/ `delete_node(node_id, scope)`（**非空文件夹抛 ValueError 拒绝删除，统计全部子节点防误删**）/ `get_config(node_id, scope)` / `upsert_config(node_id, scope, ...)`（枚举与 expectations 结构校验）/ `send_request(node_id, scope)`（httpx.AsyncClient timeout=15 代理发送 + 断言校验 + 落库，网络异常也落库）/ `list_runs(node_id, scope, ...)`；新增 `get_node_internal(node_id)` 内存缓存轻量查询供调度器内部使用
- 断言类型（`_evaluate_expectations`）：`status_code`(eq) / `body_contains`(子串) / `json_field`(点号 path 下钻，`exists|eq`)
- 缺失/越权语义：`get_config / upsert_config / send_request / list_runs / update_node / delete_node` 对缺失节点或非 admin 越权统一抛 `ApiConfigNotFoundError`（路由映射 404）；`create_node` / `update_node` 对父节点不可见抛 `ValueError("父节点不存在")`（路由映射 400，保留前端 UX）；folder 类型不匹配仍 `ValueError`（400）
- `app/routers/api_config_router.py`：`/api/admin/api-configs` 端点授权契约（2026-07-26 调整）：
  - 只读 `GET /tree`：JWT-only（登录态即可，OwnershipScope 按归属过滤；普通用户仅见自己的接口节点）；
  - 写端点：`POST /nodes`、`PUT /nodes/{id}`、`DELETE /nodes/{id}`（非空文件夹 400）、`GET|PUT /nodes/{id}/config`、`POST /nodes/{id}/send`、`GET /nodes/{id}/runs?limit=20` 均 `require_admin_or_menu_acl('task-scheduler.api-config')`；
  - 每个端点构造 `OwnershipScope.from_request(request)` 透传 service
- 注册：`app/main.py::register_routers`；lifespan 初始化在 `app/core/server.py`（DB 池就绪后，`app.state.api_config_service`），DB 不可用时不挂载，路由 `_get_service` 返回 500

### 前端（`web/Agent/`）

- `TaskSchedulerManager.vue`：`TAB_API='api'` 追加为第 4 个 tab「API接口配置」，panel 内挂载 `<ApiConfigManager />`；API panel 使用 `.task-panel-api` 作为可伸缩布局容器，详情区通过 flex 高度链向下传递可用空间，API 配置详情面板内部负责纵向滚动
- `src/components/ApiConfigManager.vue`：左侧工具栏（搜索框 + 放大镜图标 + 单个 `+` 触发器；触发器内部使用 18×18、20×20 viewBox 的对称 SVG 加号，依靠 32×32 flex 容器双轴居中，不依赖系统字体字形度量；点击 `+` 弹出菜单显示「新建文件夹 / 新建接口」两项，行为与原独立 button 一致；菜单点击外部或按 Esc 关闭）+ 自定义递归树（inline 重命名 / 删除，api 节点带 method 徽标）；右侧配置区（method 下拉 POST/PUT + URL + 发送/保存），子 tab `Params/Body/Headers/Mock`；Headers 参数名提供常用请求头建议（Content-Type/Authorization/Accept/User-Agent 等）；Body 类型 none/form-data/x-www-form-urlencoded/JSON/XML/Text（**仅文本，不含文件上传**）；Mock 为预期结果断言规则编辑器（状态码等于/响应体包含/JSON字段）；发送结果区展示状态码、耗时、check_passed 徽标、断言明细、响应体预览；左右面板填满 API Tab 可用高度，树列表与详情内容分别在面板内部滚动
- `src/utils/api.js` 追加封装：`fetchApiConfigTree/createApiConfigNode/updateApiConfigNode/deleteApiConfigNode/fetchApiConfig/saveApiConfig/sendApiConfig/fetchApiConfigRuns`

### 测试

- `app/tests/shared/utils/test_api_config_service.py`（service 单测，httpx 经 monkeypatch 替换 AsyncClient，db 用 stub）
- `app/tests/routers/test_api_config_router.py`（路由契约；`app/tests/routers/conftest.py` 新增 autouse fixture 注入**真实** `ApiConfigService(db=None)`，生产对应点为 lifespan）
- `web/Agent/src/components/__tests__/ApiConfigManager.spec.js`（树交互/子tab/Body切换/Mock规则/发送结果；锁定新建触发器的 SVG、viewBox、`aria-hidden` 与按钮 `aria-label` 结构契约）；`TaskSchedulerManager.spec.js` tab 顺序断言更新为 4 tab

### 网络代理陷阱（2026-07-23 排查记录）

`ApiConfigService.send_request()` 使用 `httpx.AsyncClient(timeout=15)` 代理发送 HTTP 请求。**httpx 默认读系统代理**（`HTTP_PROXY` / `HTTPS_PROXY` 环境变量 + Windows 注册表 `Internet Settings\ProxyServer`），所以**本机或运行环境中只要误开了 HTTP 代理（例如 `127.0.0.1:10808` 这类本地代理 / 调试代理 / 科学上网代理），所有「发送接口」请求都会被强制转发到该代理**，而代理本身可能不通或挂死，最终命中 15s 超时，表现与「目标接口异常」完全一致。

而 **apifox 这类 Electron 桌面应用不受 Windows 系统代理影响**，它的 Chromium 内核走自己的 `net` 模块，默认 `direct` 直连，所以同样一台机器上 apifox 63ms 通、后端代理 15s 超时，**用户体感是「接口实际通的，但本系统发不出去」**。

受影响范围：所有走 `httpx` / `requests` / `urllib3` / `axios`(Node) / WinINet(WPS/PowerShell `Invoke-WebRequest`) 的代码路径都吃这个坑；不影响 WinHTTP、独立 C 客户端、Electron 默认直连。

排查要点（再次遇到「curl/Postman 通，本系统 15s 超时」时按此清单定位）：
1. `[System.Net.WebProxy]::GetDefaultProxy().Address` 看本机默认代理；或 `netsh winhttp show proxy` 看 WinHTTP 代理
2. `Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'.ProxyServer` 看 IE/系统代理
3. 环境变量 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` / `http_proxy`
4. 若任一项非空，让用户关闭或为该进程显式设 `trust_env=False`(httpx) / `--noproxy`(curl) / 关闭科学上网工具，再回归测试

代码侧故意**不**加 `trust_env=False`：保留「直连目标不通时自动走系统代理」的灵活性，运维/调试场景有真实需求；唯一兜底是 `ApiConfigService.send_request` 的 `timeout=15` 给前端可观测的「超时」信号，便于对照用户场景。

## API 路由汇总

> 全部路由的「前缀 → 文件 → 权限」映射见根目录索引 `project_memory.md` 的「API 路由速查表」（以 `app/main.py::register_routers` 为准）；本表记录端点级明细。

| 前缀                                | 模块                   | 说明                                                                                                                                                                                  |
| ----------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| /api/auth                           | auth_router            | 认证（验证码、注册、登录、刷新、验证、登出、门户子 refresh_token）                                                                                                                    |
| /api/auth/mfa                    | mfa_router             | 登录 challenge 端点公开；状态、绑定、禁用、恢复码管理要求 Bearer 登录态 |
| ├ POST /login/verify             |                       | 校验 TOTP/一次性恢复码后签发正式浏览器会话 |
| ├ POST /login/enroll/start       |                       | 管理员首次绑定流程生成待确认密钥与二维码 |
| ├ POST /login/enroll/confirm     |                       | 确认 TOTP，启用 MFA 并一次性返回恢复码 |
| ├ GET  /status                   |                       | 返回当前用户 MFA 启用状态与强制策略 |
| ├ POST /totp/enroll/start        |                       | 已登录用户启用或轮换 TOTP |
| ├ POST /totp/enroll/confirm      |                       | 确认已登录用户 TOTP 绑定 |
| ├ POST /totp/disable             |                       | 普通用户二次验证后禁用；管理员禁止禁用 |
| └ POST /recovery-codes/regenerate|                       | 二次验证后生成新的一次性恢复码 |
| /api/project                        | project_router         | 2026-06-30 新增：项目文件夹 CRUD + session 绑定/解绑；2026-07-06 新增删除/重命名端点                                                                                                  |
| ├ POST /create                      |                        | 创建项目（body: {name, uuid}，uuid=创建时 session_id）                                                                                                                                |
| ├ GET  /list                        |                        | 当前用户项目列表                                                                                                                                                                       |
| ├ GET  /{id}/info                   |                        | 单项目详情                                                                                                                                                                            |
| ├ DELETE /{id}/delete               |                        | 删除项目（同步解绑其下会话）                                                                                                                                                          |
| ├ PUT  /{id}/rename                 |                        | 重命名项目（body: {name}）                                                                                                                                                            |
| ├ PUT  /session/bind                |                        | 将会话绑定到项目（body: {session_id, project_id}）                                                                                                                                    |
| └ PUT  /session/unbind              |                        | 解除会话项目关联（body: {session_id}）                                                                                                                                                |
| ├ GET /captcha                     |                        | 获取图形验证码（返回 key + base64 图片）                                                                                                                                              |
| ├ POST /register                   |                        | 用户注册（含验证码校验、密码复杂度校验）                                                                                                                                              |
| ├ POST /login                      |                        | 用户登录（验证码校验，返回 access_token + Set-Cookie refresh_token + Set-Cookie access_token HttpOnly Cookie）                                                                       |
| ├ POST /login-api                  |                        | API 程序化登录（免验证码，返回 access_token + Set-Cookie refresh_token + Set-Cookie access_token HttpOnly Cookie）。路由层在请求方自动建号（memory 模式无该用户）时调 `password_policy.validate_password`；弱口令返回 400，detail 提示「自动登录失败：…」。 |
| ├ POST /refresh                    |                        | 刷新 Access Token（读取顺序：X-Refresh-Token 头 > body {refresh_token} > HttpOnly Cookie；同时查 refresh_tokens 与 portal_refresh_tokens；响应 JSON 保留 access_token 并同步轮换 access_token HttpOnly Cookie）                    |
| ├ GET /validate                    |                        | 验证 Access Token 有效性（Bearer 优先、access_token HttpOnly Cookie 兜底；返回 username、role、user_id）                                                                              |
| ├ POST /logout                     |                        | 用户登出（清除 Refresh Token + Cookie + Session + 撤销该用户所有 portal_refresh_tokens）                                                                                              |
| ├ POST /issue-portal-refresh-token |                        | 颁发门户子 refresh_token（需 Bearer access_token；用于门户导航页推送第三方 iframe）                                                                                                   |
| /api/users                          | user_router            | 用户管理（列表、创建、更新、删除、踢人、改密码、改用户名、资料）                                                                                                                      |
| ├ GET /                            |                        | 用户列表（admin 专用）                                                                                                                                                                |
| ├ POST /                           |                        | Admin 创建用户                                                                                                                                                                        |
| ├ GET /online                      |                        | 在线用户列表（admin 专用）                                                                                                                                                            |
| ├ PUT /{user_id}                   |                        | Admin 更新用户资料（**不含 password**——admin 无权改密码；设计详见 memory/auth.md 权限控制小节）                                                                                       |
| ├ DELETE /{user_id}                |                        | 删除用户（admin 专用，同时清除该用户所有 Session）                                                                                                                                    |
| ├ POST /{user_id}/kick             |                        | 强制用户下线（admin 专用，清除 Refresh Token 并标记 Session 为 kicked）                                                                                                               |
| ├ GET /{user_id}/sessions          |                        | 指定用户会话列表（admin 专用）                                                                                                                                                        |
| ├ PUT /{user_id}/password          |                        | 修改密码（**仅本人**——要求 old_password；admin 无绕过入口；修改后强制清除所有 Refresh Token）                                                                                                                                          |
| ├ PUT /{user_id}/username          |                        | 修改用户名（仅限修改自己的用户名）                                                                                                                                                    |
| ├ GET /{user_id}/profile           |                        | 获取用户个人资料（仅限查看自己的资料）                                                                                                                                                |
| ├ PUT /{user_id}/profile           |                        | 更新用户个人资料（仅限修改自己的资料）                                                                                                                                                |
| /api/session                        | session_router         | 会话管理（创建、删除、列表、详情、标题、导出、附件、消息、文件空间）+ Admin 批量删除/历史消息/导出 Markdown                                                                           |
| ├ POST /create                     |                        | 创建新会话                                                                                                                                                                            |
| ├ DELETE /delete/{session_id}      |                        | 删除会话（同时清理对话记录、附件、文件目录、checkpoint、缓存）                                                                                                                        |
| ├ GET /list                        |                        | 获取当前用户的会话列表                                                                                                                                                                |
| ├ GET /{session_id}/detail         |                        | 获取会话详情（含附件列表）                                                                                                                                                            |
| ├ PUT /{session_id}/title          |                        | 更新会话标题                                                                                                                                                                          |
| ├ GET /{session_id}/export/markdown |                        | 导出会话完整对话为 Markdown（含子智能体轨迹）                                                                                                                                         |
| ├ GET /{session_id}/attachments    |                        | 获取会话附件列表                                                                                                                                                                      |
| ├ GET /{session_id}/messages       |                        | 获取会话历史消息（从 LangGraph Checkpoint 恢复，默认 50 条；返回 messages 中按时序插入 `type:"subagent"` 元素，承载 sandbox/explore 子智能体的完整轨迹；AIMessage 携带 `tool_calls` 字段，前端据此恢复普通工具卡片） |
| ├ GET /{session_id}/files/tree     |                        | 2026-07-01 新增：获取会话/项目文件空间树形结构（含原文件目录与解析缓存目录）                                                                                                          |
| ├ GET /{session_id}/files/preview  |                        | 2026-07-01 新增：预览会话文件空间中单个文件（文本/Markdown 返回 content；Office/PDF/图片返回下载 URL）                                                                                |
| ├ GET /{session_id}/files/download |                        | 2026-07-01 新增：下载会话文件空间中的文件（带路径遍历校验）                                                                                                                           |
| ├ DELETE /admin/{session_id}       |                        | Admin 强制删除任意会话                                                                                                                                                                |
| ├ DELETE /admin/batch              |                        | Admin 批量删除会话（body: {session_ids}），返回 success / deleted_count / total / failed                                                                                              |
| ├ GET  /admin/{session_id}/messages |                        | Admin 获取任意会话历史消息（从 LangGraph Checkpoint 恢复，含子智能体轨迹；默认 50 条，limit=0 返回全部）                                                                              |
| ├ GET  /admin/{session_id}/export/markdown |                        | Admin 导出任意会话完整对话为 Markdown（含子智能体轨迹）                                                                                                                               |
| ├ GET /admin/search                |                        | Admin 按用户名搜索会话                                                                                                                                                                |
| /api/files                          | file_router            | 文件管理（上传、下载、删除、列表、PDF 转图片）                                                                                                                                        |
| ├ POST /upload                     |                        | 批量上传文件                                                                                                                                                                          |
| ├ POST /upload-base64              |                        | 批量上传 base64 编码文件                                                                                                                                                              |
| ├ GET /download/{file_uuid}        |                        | 下载文件                                                                                                                                                                              |
| ├ GET /info/{file_uuid}            |                        | 获取文件信息                                                                                                                                                                          |
| ├ DELETE /delete                   |                        | 批量删除文件                                                                                                                                                                          |
| ├ GET /list                        |                        | 列出所有文件                                                                                                                                                                          |
| ├ POST /convert                    |                        | 批量转换 PDF 为图片                                                                                                                                                                   |
| /api/core                           | file_upload_router     | 核心文件上传（支持远程解析服务/本地 DocumentLoader 解析；2026-07-13 统一 3MB 上限，与 `FILE_PARSER_ENABLED` 无关）                                                                     |
| ├ GET /upload-config               |                        | 2026-07-13 新增：返回 `{max_file_size_mb, parser_enabled}`，供前端在 onMounted 时拉取并启用客户端预校验                                                                  |
| ├ POST /uploadfile                 |                        | 批量上传文件（含文本提取/远程解析）；超 `max_file_size_mb` 返回 413                                                                                                                  |
| ├ POST /upload-chunk               |                        | 分片上传                                                                                                                                                                              |
| ├ POST /merge-chunks               |                        | 合并分片；合并后总大小超 `max_file_size_mb` 返回 413                                                                                                                                |
| ├ DELETE /attachments              |                        | 2026-07-01 新增：按 stored_path 批量删除附件（.md 缓存 + 原文件 + attachments 记录），校验 session_id/project_id 归属                                                                                                                                                              |
| /api/core/download                  | file_download_router   | 核心文件下载（支持 Range 断点续传、批量打包 ZIP）                                                                                                                                     |
| ├ GET /file                        |                        | 下载文件（支持 Range 请求、自定义下载文件名）                                                                                                                                         |
| ├ GET /by-name                     |                        | 按文件名模糊/精确匹配下载                                                                                                                                                             |
| ├ POST /batch                      |                        | 批量下载（打包为 ZIP）                                                                                                                                                                |
| ├ GET /list                        |                        | 列出可下载文件（支持子目录、递归）                                                                                                                                                    |
| /api/contract                       | contract_router        | 合同主办 Agent                                                                                                                                                                        |
| ├ POST /uploadfile                 |                        | 上传并处理合同文件（存储 file_id 到 LangGraph Store）                                                                                                                                 |
| ├ POST /chat                       |                        | 合同审批聊天（HtAgent 非流式，受 `chat_concurrency_dependency` 并发控制）                                                                                                           |
| ├ POST /doc_chat                   |                        | 文档处理聊天（DocAgent 非流式，受 `chat_concurrency_dependency` 并发控制）                                                                                                          |
| ├ POST /approval_chat              |                        | 审批处理聊天（ApprovalAgent 非流式，受 `chat_concurrency_dependency` 并发控制）                                                                                                     |
| ├ POST /store/value                |                        | 根据 id 获取 LangGraph Store 中的值                                                                                                                                                   |
| ├ POST /store/value/set            |                        | 向 LangGraph Store 中写入值                                                                                                                                                           |
| ├ POST /download_contract          |                        | 下载合同文件（返回 base64）                                                                                                                                                           |
| /api/map                            | knowledge_router       | 地图 Agent                                                                                                     |
| ├ GET /knowledge/files             |                        | 获取知识库文件元数据（自动扫描 Knowledge 目录）                                                                                                                                       |
| ├ GET /knowledge/file-download     |                        | 下载知识库文件                                                                                                                                                                        |
| ├ GET /knowledge/file-preview      |                        | 知识库文件预览（支持 .doc 自动转 .docx）                                                                                                                                              |
| ├ POST /knowledge-chat             |                        | ~~地图智能体知识库聊天~~（2026-06-29 起，知识库页面 `/knowledge.html` 已切换至 `/api/agent/chat` 并固定使用 `agent_name=knowledge_ydt`，本端点保留但前端不再调用）                                                                                        |
| /api/ai-coding-check                | ai_coding_check_router | AI 代码检查 Agent                                                                                                                                                                     |
| ├ POST /review                     |                        | 评审开发者数据（非流式 JSON API）                                                                                                                                                     |
| /api/admin/email                    | email_admin_router     | 邮件系统管理（详见「邮件系统」章节）：SMTP 配置 CRUD + 连接测试 + 策略 CRUD + 测试发送（multipart/form-data）+ 按策略发送                                                           |

## DevOps 服务器与巡检脚本库管理（2026-07-15 新增；2026-08-03 改造）

### `/api/admin/devops-servers`（`app/routers/devops_server_admin_router.py`）

- `GET ""`：admin OR `task-scheduler.server-management` ACL；返回白名单 7 字段 `{id, business_name, server_type, updated_at, inspection_script_id, inspection_script_name, inspection_script_display_name}`（严格二次过滤；不暴露 ip / 端口 / 凭据 / 名单 / 脚本原文）
- `POST /scan`：admin only；触发 `DevOpsServerService.scan_and_upsert()`；严格返回 `{scanned, inserted, updated, failed}` 4 整数；异常 → 500 + `"devops server scan failed"`
- `GET /{server_id}`（2026-08-03 改造）：admin only；返回白名单 `_DETAIL_FIELDS = {id, business_name, server_type, updated_at, whitelist, inspection_script_id, inspection_script_name, inspection_script_display_name}`（**脚本原文不返回**，由 `/api/admin/inspection-scripts/{script_id}` 按需提供）；不存在 → 404 + `"服务器不存在"`（不回显 server_id）
- `PUT /{server_id}/inspection-script`：admin only；请求体 `{inspection_script_id: int | null}`，选择脚本或解绑后由 `DevOpsServerService.set_inspection_script` 同步 DB 与内存缓存；成功返回 7 字段安全记录；服务器不存在 → 404 + `"服务器不存在"`；脚本不存在 → 404 + `"巡检脚本不存在"`；服务缺失或内部异常 → 500 + 脱敏文案
- `DELETE /{server_id}`：admin only；返 204 No Content；不存在 → 404 + `"服务器不存在"`；DB 异常 → 500 + `"删除服务器失败"`

### `/api/admin/inspection-scripts`（`app/routers/inspection_script_admin_router.py`，2026-08-03 新增；2026-08-04 改造）

> DevOps 巡检脚本库统一管理入口。脚本原文、解析器、字段规则从 `devops_servers` 三列抽离到 `inspection_scripts` 表后，devops 详情端点仅返元数据，**脚本原文改走本组端点按需加载**。

- `GET ""`：admin OR `task-scheduler.inspection-script-library` ACL（2026-08-04 从 `task-scheduler.server-management` 迁出为独立菜单权限）；返回白名单 7 字段 `{id, name, display_name, platform, version, inspection_parser, updated_at}`（**不**暴露 `inspection_script` / `inspection_fields`）
- `POST /scan`：admin only；触发 `InspectionScriptService.scan_and_upsert()` 读取 `data/devops/inspection_scripts.yaml`；2026-08-04 改造为「编辑优先」——DB 中已有 `name` 跳过更新，**不**覆盖人工编辑；返回 5 整数 `{scanned, inserted, updated, failed, skipped}`；异常 → 500 + `"inspection script scan failed"`（不回显路径 / 原始 detail）
- `GET /{script_id}`：admin only；返回完整详情含 `inspection_script` 与 `inspection_fields`（`{id, name, display_name, platform, version, inspection_parser, inspection_script, inspection_fields, created_at, updated_at}`）；不存在 → 404 + `"脚本不存在"`（不回显 script_id）；服务未初始化 → 500 + `"InspectionScriptService not initialized"`
- `PUT /{script_id}`（2026-08-04 新增）：admin only；请求体 `UpdateInspectionScriptRequest{display_name, platform, version, inspection_parser, inspection_script, inspection_fields}`（Pydantic 校验 `platform ∈ {linux,windows}` / `inspection_parser ∈ {json,kv,csv,raw}` / `display_name 1-200` 字符）；调用 `InspectionScriptService.update_script_detail` 写 DB 并同步 `_cache` / `_id_cache`；返回更新后的完整记录（`_DETAIL_FIELDS` 11 字段）；script_id 不存在 → 404 + `"脚本不存在"`；非法入参（service 内部白名单校验失败）→ 404 + `"脚本不存在"`
- `DELETE /{script_id}`（2026-08-04 新增；**2026-08-05 事务化**）：admin only；调用 `InspectionScriptService.delete_script(id)` 在 `async with self.db.acquire() as conn: async with conn.transaction():` 内完成 `SELECT name FOR UPDATE` + `UPDATE devops_servers SET inspection_script_id=NULL` + `DELETE FROM inspection_scripts`，事务成功提交后清理 `_id_cache` / `_cache` 并清扫同 name 漂移；成功 → 204 No Content（无响应体）；service 返回 False（DB 无匹配行）→ 404 + `"脚本不存在"`（不回显 script_id）；DB 异常向上抛出 → 500 + 脱敏文案；服务未初始化 → 500 + `"InspectionScriptService not initialized"`。**asyncpg 关键约束**：`db` 是 `asyncpg.Pool`（无 `.transaction()`），事务必须在 connection 上开；任何后续 service 想加事务，请走 `db.acquire() → conn.transaction()` 链路。**副作用**：`devops_servers.inspection_script_id` 显式置 NULL（业务层）+ FK `ON DELETE SET NULL` 兜底；前端 `InspectionScriptLibraryPanel.vue` 删除后本地 `filter` 移除节点，无需再触发额外刷新。
- 服务实例从 `request.app.state.inspection_script_service` 获取；lifespan 强依赖顺序详见 [devops-sandbox.md § lifespan 强依赖顺序](devops-sandbox.md#lifespan-强依赖顺序2026-08-03-新增章节)

### 前端 API 封装（`web/Agent/src/utils/api.js`，2026-08-03 新增；2026-08-04 扩展）

- `fetchInspectionScripts()` → `GET /api/admin/inspection-scripts`（admin OR `task-scheduler.inspection-script-library` ACL）
- `scanInspectionScripts()` → `POST /api/admin/inspection-scripts/scan`（admin only）
- `fetchInspectionScriptDetail(scriptId)` → `GET /api/admin/inspection-scripts/{scriptId}`（admin only）
- `updateInspectionScript(scriptId, payload)` → `PUT /api/admin/inspection-scripts/{scriptId}`（admin only）
- `deleteInspectionScript(scriptId)` → `DELETE /api/admin/inspection-scripts/{scriptId}`（admin only；204 No Content）

### `/api/admin/server-inspection`（`app/routers/server_inspection_router.py`，2026-08-05 新增）

运维控制台（App.vue::currentPage === 'ops-console' 内嵌子页面，2026-08-08 等保三级改造）数据源。三端点全部 `require_admin_or_menu_acl('task-scheduler.server-management')` + OwnershipScope 数据层过滤：

- `GET /latest` → `ServerInspectionRecordService.list_latest(scope)`；admin 透传全量 `devops_servers`，普通用户按 `user_server_nodes`（`node_type='server'`）过滤、按 `server_id` 去重、按 `sort_order,node_id` 排序；每行 `status` 派生（pass→ok / warn,crit,success=False→err / skipped,unassessed,无快照→unknown）与 `metrics.cpu/mem/disk`（linux `100-cpu_idle_pct`、windows `cpu_used_pct`；根盘优先取 `disks[].disk_used_pct`：`/`（linux）/ `C:\\`（windows，大小写不敏感），无则取第一块，仍无 → `null`）；响应**不含 ip**（遵循脱敏约定）。
- `GET /records?server_id=&start=&end=&limit=` → `ServerInspectionRecordService.list_records(server_id, scope, ...)`；admin 仅校验 server 存在；普通用户需在可见节点集内；越权 → `None` → 404（不回显 id）；limit 范围 1~1000（FastAPI Query 校验）；service ValueError → 400。
- `POST /collect` body `{server_ids: [int...]}`（1~50 项）→ `resolve_collect_targets` 校验（缺失 → 404、越权 → 403）→ 合成 ScriptContext（`schedule_id=0, run_id=0, schedule_name='manual-collect', trigger_type='manual', log_logger=模块 logger, devops_server_service=app.state.*`）→ `await run_server_ops(context, server_list=business_names)` → `save_inspection_result(report, created_by_user_id=scope.user_id)`；返回 `{collected, items: [{server_id, business_name, success, inspection_status, duration_ms, error_message, field_results}]}`，供前端就地刷新 UI。

## 核心工具 (Core Tools)

### Sandbox 工具

**文件位置**: `app/core/tools/SandboxTools.py`

**功能**: 提供 `sandbox` 工具函数，启动沙箱子智能体在隔离的 Docker 容器中执行代码和文件操作。

**使用方式**: 作为 `@tool` 注册到 core agent 工具链，LLM 自动决策调用时机。

**实现细节**:

- 使用 `create_deep_agent` (deepagents) 创建子智能体
- 使用 `DockerSandboxMiddleware` 提供隔离执行环境
- 工作目录: `data/upload/{session_id}`
- **workspace 统一创建入口**: `app/core/tools/SandboxTools.py` 负责根据 `session_id` 创建 `data/upload/{session_id}` 目录，然后显式传入 `DockerSandboxMiddleware` / `DockerSandboxBackend`。后端/中间件不再自行创建工作目录，未传入有效 workspace 时抛出 `ValueError`。
- 默认镜像: `python:3.12-alpine`
- 资源限制: 内存 512MB，CPU 100%，无网络
- 支持流式事件: `tool_start` / `tool_progress` / `tool_stop`
- Docker 不可用降级: 通过 `SANDBOX_FALLBACK_TO_LOCAL` 控制是否降级到 `LocalShellBackend` 本地执行（默认 `false`，保持安全边界）

**依赖**:

- `DockerSandboxMiddleware` / `DockerSandboxBackend`: `app/shared/tools/middleware/docker_sandbox_backend.py`

### BaseFilesystemTool

**文件位置**: `app/core/tools/base/BaseFilesystemTool.py`

**功能**: 封装文件系统子智能体的通用执行逻辑：创建子智能体、流式执行、事件推送、用户停止信号感知、结果提取与异常处理。

**2026-07-06 改造（与 sandbox 保持一致）**：`explore` 与 `query_knowledge` 都通过本类的 `arun` 启动子智能体，因此**改造 arun 一处即同时覆盖两个子智能体的 abort_event 感知**。

- import 调整：`get_current_request` → `get_abort_signal, get_current_request`
- 进入 `arun` 时取出 `session_id = runtime.context.get("session_id", "default")` + `abort_event = get_abort_signal(session_id)`
- 进入 stream 前的预检查：仅记录日志（不直接置 `stopped_by_user`，由主循环统一处理）
- 主循环检测改为**双保险**：abort_event 优先（主动 abort 通道）→ is_disconnected 兜底（非主动关闭场景）；任一触发即视为用户停止
- `stopped_by_user` 分支**无需改**——已正确构造 `ToolMessage(tool_call_id=...)` + `Command(update={"messages": [ToolMessage]})` 返回，避免 orphan tool_calls 触发 2013 错误

**与 sandbox 改造的一致性**：`BaseFilesystemTool.arun` 的 abort_event 检测路径与 `SandboxTools.sandbox` 完全一致，差别仅是 sandbox 额外需要清理 Docker 容器（`middleware.cleanup()`）——本类不需要此步（无 Docker 资源）

**使用方式**: 上层工具（如 `explore`、`query_knowledge`）实例化 `BaseFilesystemTool`，传入 `tool_name`、`system_prompt`，然后调用 `await tool.arun(prompt, runtime, root_path)`。

**设计目的**:

- 将 `FilesystemReadTools.explore` 中耦合的 `create_agent`、middleware 组装、astream 循环等逻辑下沉到可复用的基础类。
- 通过 `root_path` 参数灵活支持不同目标目录（session 上传目录、知识库目录等），避免一个工具承担多种职责。

**关键属性**:

- `tool_name`: SSE 事件与日志使用的工具名。
- `system_prompt`: 子智能体系统提示词。
- `max_file_size_mb`: 文件搜索中间件允许的最大单文件大小，默认 10 MB。

**方法**:

- `create_child_agent(root_path, model) -> Agent`: 创建挂载 `EncodingSafeFileSearchMiddleware`、`FilesystemMiddleware`、`TodoListMiddleware`、`ContextEditingMiddleware` 的子智能体。
- `arun(prompt, runtime, root_path) -> Command`: 校验目录、发送事件、执行子智能体、处理停止信号、从最后一条 AIMessage 提取结果并返回 `Command`。

**结果提取规则**:

- 子智能体执行完成后，统一从循环内累计的 `all_messages` 中提取最后一条 `AIMessage` 的文本内容作为最终结果。
- 不再使用 `response_format` / `structured_response`，`explore` 与 `query_knowledge` 均按此规则返回结果。
- 若 `all_messages` 为空或未包含有效 AIMessage，使用兜底字符串 `"子智能体执行完成，但未获取到文本回复。"` 并记录 `logger.warning`。
- `_extract_last_ai_text` 通过消息类型名字符串 `"AIMessage"` 识别，兼容测试环境 Mock。

**依赖**:

- `EncodingSafeFileSearchMiddleware`: `app/shared/tools/middleware/encoding_safe_file_search.py`
- `FilesystemMiddleware` / `FilesystemBackend`: `deepagents`
- `get_async_checkpointer`: `app/shared/utils/memory/checkpoint.py`
- `get_async_store`: `app/shared/utils/memory/store.py`（2026-06-26 新增：LangGraph Store 全局单例，与 `get_async_checkpointer` 对齐）
- `get_current_request`: `app/core/tools/_stop_signal.py`

### explore 工具

**文件位置**: `app/core/tools/FilesystemReadTools.py`

**功能**: 启动文件系统探索子智能体，读取当前 session 上传目录 `data/upload/{session_id}` 中的文件并分析。

**变更**:

- 移除原 `knowledge_root` 分支，`explore` 仅保留最基础的 session 文件读取能力。
- 通用执行逻辑迁移到 `BaseFilesystemTool`，`explore` 仅负责解析 `session_id`、构造 `root_path`、实例化 `BaseFilesystemTool` 并调用 `arun`。
- **当 session 上传目录为空（用户未上传任何文件）时，`explore` 不再启动子智能体，而是直接返回包含 `"未找到文件"` 的 ToolMessage Command，避免 `ValueError` 异常上抛影响主流程。**
- 知识库检索能力由 `app/shared/tools/skills/map_agent/MapTools.py` 中的 `query_knowledge` 工具承担。

### query_knowledge 工具

**文件位置**: `app/shared/tools/skills/map_agent/MapTools.py`

**功能**: 启动知识库检索子智能体，在配置的知识库目录中搜索并读取文档。

**使用方式**: 通过 LangChain `@tool(description=...)` 装饰器注册；与 agent 的绑定关系由 DB `tools.tool_bindings`（`agent_tool_bindings` 表）控制，可被任意 agent 通过 `tool_bindings` 自由绑定使用，与 `app/core/tools/BaseTools.py` 的绑定风格一致。

**实现细节**:

- 通过 `runtime.context["knowledge_root"]` 获取目标知识库路径，由调用方（如 `/api/map/knowledge-chat`，实现在 `app/routers/knowledge_router.py`）在 AgentContext 中注入。
- 调用 `BaseFilesystemTool(...).arun(prompt, runtime, root_path)` 复用通用子智能体执行逻辑。
- 未配置 `knowledge_root` 时直接返回错误 `Command`，避免子智能体在无效路径上运行。
- 已注册为子智能体工具（`subagent_registry.SUBAGENT_TOOL_NAMES` 包含 `query_knowledge`），前端 `sseParser.js` 的 `SUBAGENT_META` 同步了图标与标签。

**扩展方式**:

- 未来需要查询其他知识库时，可新增一个工具函数，仅修改 `root_path` 来源（如从 `runtime.context["other_knowledge_root"]` 读取），并复用同一个 `BaseFilesystemTool`。

### generate_report / save_business_info 工具

**文件位置**: `app/shared/tools/skills/map_agent/MapTools.py`

**配套配置模块**: `app/shared/tools/skills/map_agent/config/`（含 `__init__.py` / `settings.py` / `config.py`）

**功能**:

- `generate_report(data, runtime)`：根据项目信息 + 知识库上下文生成 Word 报告并返回下载地址。
  - 输入模型：`GenerateReportInput`（project_name / project_type，必填）。
  - 从 `runtime.store.get((store_id, session_id), "process_data")` 读取 `report_data`，使用 `ProjectSiteSelectionCollection.model_validate()` 反序列化。
  - 调 `get_report_config(data, collection)` 构建 `ReportConfig`，再由 `WordReportGenerator` 生成 docx。
  - 演示模式（`DEMONSTRATION_CONFIG["demonstration_report_enabled"]=True`）下，切换到示例 docx 文件路径。
- `save_business_info(input_data, runtime)`：保存项目业务信息并生成业务编号。
  - 输入模型：`SaveBusinessInfoInput`（5 个 Optional 字段，验证在 `_validate_business_info` 内手动执行）。
  - 业务编号格式：`YDT{YYYYMMDD}{4位序号}`，通过 `INSERT ... ON CONFLICT DO UPDATE` 数据库原子 Upsert 保证并发安全。
  - 内存模式（`DatabasePool.is_enabled()=False`）下使用 UUID 前 4 位兜底。

**Schema 初始化**: `init_map_business_info_schema` 使用 `@register_schema` 装饰器，建表 `map_business_info` / `map_business_no_counter` 与 2 个索引（session_id / created_at），与 `app/migrations/init_all_tables.sql:165-191` 同步。

**注册装饰器**（2026-06-26 更新）：所有工具统一改为 LangChain `@tool(description=...)` 单装饰器模式；description 直接挂在 `@tool` 上，归属与启用完全由 DB `tools` / `agent_tool_bindings` 控制，移除了原先 `@register_tool(name=..., agent="map_agent", description=...)` + `@tool` 双装饰器中的 `agent` 字段限制。`@register_tool` 装饰器本身保留（其他模块可能仍在用）。

**来源**: 2026-06-26 从 `e:\laboratory\AI\Agents\dev-main\app\features\map_agent\config\config.py` 和 `MapToolstmp.py`（项目根临时备份）复刻而来，仅修改 1 行 import 路径（`app.features.map_agent.config` → `app.shared.tools.skills.map_agent.config`）。原 `app/features/map_agent/` 目录已废弃。

**测试**: `app/tests/shared/tools/skills/map_agent/`（16 用例：5 个 generate_report + 2 个 init_map_business_info_schema + 9 个 save_business_info）。

## 脚本管理接口权限拆分（2026-07-26 新增）

「普通用户在定时任务表单中需能选择全部已注册脚本」的诉求触发本次拆分。原 `app/routers/script_admin_router.py` 整个 router 挂 `Depends(require_admin)`，导致普通用户即便获得 `task-scheduler.scheduled` 菜单授权也无法调 `/api/admin/scripts` GET，前端 `fetchScripts()` 被 403 吞掉后脚本下拉为空。

**新权限模型**：

| 端点 | 权限 | 说明 |
|---|---|---|
| `GET /api/admin/scripts` | JWT-only（任何登录用户可读） | 返回脚本白名单字段（`name / display_name / description / params_schema / module_path`），不暴露脚本源码 |
| `POST /api/admin/scripts/scan` | `Depends(require_admin)` | 防普通用户触发磁盘扫描；普通用户调过去会 403 |

**实施**：

- 移除 router 级 `dependencies=[Depends(require_admin)]`
- GET 端点保留 `router.get("", response_model=...)`，仅依赖 auth_middleware 注入的 JWT
- POST `/scan` 单独加 `dependencies=[Depends(require_admin)]`（端点级依赖）

**安全考量**：

- 脚本列表是白名单字段，不暴露内部函数引用或敏感元数据
- 配合「智能体数据源分流」（见下文）：前端 `TaskSchedulerManager.vue` 在普通用户场景下智能体走 `/api/agent/list`（按 `user_agent_acl` 过滤），脚本走 `/api/admin/scripts` GET（全量不过滤）
- 失效授权处理：admin 收回智能体授权后，编辑老任务时下拉不含该 option，`form.agent_name` v-model 自动归零，用户必须重选才能保存（`schedule-agent` select 已 required）

**测试**（`app/tests/routers/test_script_admin_router.py`）：

- `test_list_scripts_returns_200`：admin GET 200
- `test_user_can_list_scripts`：普通用户 GET 200
- `test_scan_scripts_returns_200` + `test_admin_scan_scripts_still_allowed`：admin POST scan 200
- `test_user_cannot_access_script_admin`：**改造后**普通用户 POST scan 403（原测 GET 403，现改为 POST scan 锁 admin-only 契约）
- `test_script_admin_service_missing_returns_500`：服务未初始化时 GET 500

## 智能体数据源分流（2026-07-26 新增）

`TaskSchedulerManager.vue` 原 `loadInitialData()` 固定调 `fetchAdminAgentList`（`GET /api/admin/agents`），普通用户被 `require_admin` 拒绝后 `safeFetch` 吞错，`agents.value = []`，导致「目标智能体」下拉为空。

**新数据源**：

| 角色 | API | 后端过滤 |
|---|---|---|
| admin | `fetchAdminAgentList` → `GET /api/admin/agents` | 无（返回全量含禁用项 + config_schema） |
| 普通用户 | `fetchAgentList` → `GET /api/agent/list` | admin bypass + 普通用户按 `user_agent_acl` 自动过滤；`agent_config_service.list_agents` 仅返回 `enabled=TRUE` 行 |

**后端契约**（`app/routers/agent_router.py:181-208` `list_agents`）：

- admin（`request.state.role == 'admin'`）→ 返全量启用智能体
- 普通用户 → `allowed_agents` 为空则返 `[]`（fail-secure）；否则按 `request.state.allowed_agents` 过滤 name
- `user_agent_acl` 数据源由 `auth_middleware` 写入 `request.state.allowed_agents`（2026-07-24 从 `users.allowed_agents` JSONB 字段迁出）

**前端契约**（`web/Agent/src/components/TaskSchedulerManager.vue:1079-1082`）：

```js
const agentFetcher = props.isAdmin ? fetchAdminAgentList : fetchAgentList
const [taskRes, agentRes] = await Promise.all([
  safeFetch(fetchTaskSchedules, [], 'task-schedules'),
  safeFetch(agentFetcher, [], 'agents'),
])
```

`enabledAgents` computed 仍按 `agent.enabled !== false` 过滤（普通用户路径下 `/api/agent/list` 已过滤启用项，过滤层冗余但兼容 admin 路径）。

**测试**（`web/Agent/src/components/__tests__/TaskSchedulerManager.spec.js`）：

- `setupFetchMock` 新增 `/api/agent/list` mock（返回 `mockAgents.filter(a => a.enabled !== false)`，可通过 `agentListResponse` 覆盖）
- 新增 describe 块「TaskSchedulerManager 普通用户数据源分流（2026-07-26 新增）」4 用例：普通用户走 `/api/agent/list` 而非 `/api/admin/agents` / 普通用户能拉 `/api/admin/scripts` / admin 仍走 `/api/admin/agents` / 下拉过滤生效

