# 项目记忆文档

## 项目概述

Agent User Management 是一个基于 FastAPI 的 AI Agent 管理平台，提供用户认证、会话管理、文件管理、多 Agent 功能等。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **数据库**: PostgreSQL（通过 asyncpg），支持 Memory 模式降级
- **认证**: JWT（双 Token 体系：Access Token + Refresh Token）
- **AI**: LangGraph + LangChain，支持多种 LLM 模型
- **工具**: MCP（Model Context Protocol）工具集成

## 项目架构

```
app/
├── core/                    # 核心模块
│   ├── server.py           # FastAPI 应用配置（生命周期、中间件、CORS）
│   ├── config/settings.py  # 配置管理
│   ├── database.py         # 数据库连接池
│   ├── agent/              # Agent 基类
│   ├── llmcalls/           # LLM 调用封装
│   ├── tools/              # 工具基类和 MCP 适配器
│   └── router.py           # 核心路由（文件上传/下载）
├── features/               # 功能模块（各 Agent）
│   ├── contract_host_agent/    # 合同主办 Agent
│   ├── contract_document_agent/ # 合同文档 Agent
│   ├── contract_approval_agent/ # 合同审批 Agent
│   ├── map_agent/              # 地图 Agent
│   ├── DevOps_agent/           # DevOps Agent
│   ├── AI_Coding_Check_agent/  # AI 代码检查 Agent
│   ├── audit_document_agent/   # 审计文档 Agent
│   └── Tagent/                 # T Agent
├── shared/                 # 共享模块
│   ├── routers/           # 路由
│   │   ├── auth_router.py    # 认证路由（登录、注册、验证码、refresh、validate）
│   │   ├── session_router.py # 会话管理路由
│   │   ├── user_router.py    # 用户管理路由
│   │   └── file_router.py    # 文件管理路由
│   └── utils/             # 工具类
│       ├── auth/          # 认证相关
│       │   ├── Safety.py          # JWT 认证（双 Token：Access + Refresh）
│       │   ├── user_db.py         # 用户数据库操作
│       │   ├── session_db.py      # Session 数据库操作
│       │   ├── refresh_token_db.py # Refresh Token 数据库操作（哈希存储）
│       │   ├── captcha.py         # 验证码生成
│       │   └── audit_log.py       # 审计日志
│       ├── Session/       # Session 缓存
│       ├── files/         # 文件操作
│       └── memory/        # 记忆存储（Checkpoint）
├── web/Agent/             # 前端 SPA（Vue 3 + Vite，多入口）
│   ├── index.html         # 主入口（Agent 聊天 + 知识库 Tab）
│   ├── knowledge.html     # 知识库独立页入口
│   ├── portal.html        # 门户导航入口（沈阳市自然资源和规划"一点通"）
│   ├── main.js / knowledge-main.js / portal-main.js  # 三个入口 JS
│   ├── src/
│   │   ├── App.vue        # 主应用根组件（未登录：Login/Register；已登录：Sidebar + ChatArea + InputBox）
│   │   ├── KnowledgeApp.vue # 知识库独立页根组件
│   │   ├── PortalApp.vue  # 门户根组件（顶部蓝色导航 + iframe 内嵌 knowledge.html）
│   │   ├── components/    # 业务组件（Sidebar/ChatArea/InputBox/HumanApprovalBox/FileList/FilePreview/...）
│   │   ├── views/         # LoginView、RegisterView
│   │   ├── utils/         # api.js（SSE/auth/session/file）、sseParser.js（thinking/text/timeline/tools）
│   │   ├── styles/        # variables.css（设计 token）、main.css
│   │   └── __tests__/     # Vitest（HumanApprovalBox / api / sseParser）
│   ├── vite.config.js     # 多入口（main/knowledge/portal）+ /api 代理 VITE_API_TARGET
│   ├── vitest.config.js   # 测试配置
│   ├── nginx.conf         # Docker 部署用 Nginx 模板（SSE 反代 + SPA fallback）
│   └── Dockerfile         # 多阶段构建：node:20-alpine 构建 → nginx:alpine 运行
└── main.py               # 应用入口
```

## 认证体系（双 Token）

### Token 类型

| Token | 有效期 | Payload type | 客户端存储 | 服务端存储 | 用途 |
|-------|--------|-------------|-----------|-----------|------|
| Access Token | 30 分钟 | `type: "access"` | 前端内存（JS 变量） | 无（纯 JWT 无状态） | 所有 API 请求的 `Authorization: Bearer` 认证 |
| Refresh Token | 24 小时 | `type: "refresh"` | HttpOnly Cookie（SameSite=Strict, Path=/api/auth） | 数据库（refresh_tokens 表，存 SHA256 哈希） | 仅用于 `/api/auth/refresh` 换取新 Access Token |

### 认证流程

```
页面加载
  │
  ├─ 1. 检查内存中是否有 Access Token
  │     ├─ 有 → 调用 /api/auth/validate 验证有效性
  │     │        ├─ 有效 → 进入主界面
  │     │        └─ 无效 → 进入步骤2
  │     └─ 无 → 进入步骤2
  │
  ├─ 2. 调用 /api/auth/refresh（Cookie 自动携带 Refresh Token）
  │     ├─ 成功 → 获取新 Access Token，进入主界面
  │     └─ 失败 → 跳转登录页
  │
  └─ 3. 登录页 → /api/auth/login
        ├─ 成功 → Access Token(内存) + Refresh Token(Cookie)
        └─ 失败 → 提示错误
```

### API 请求 Token 过期处理

- API 返回 401 → 自动调用 `/api/auth/refresh` 静默刷新
- 刷新成功 → 用新 Token 重试原请求
- 刷新失败 → 跳转登录页
- 最多重试1次

### Session 策略

- **需要 Session 的接口**（聊天相关）：
  - `/api/files/*` — 文件操作
  - `/api/agent/*` — Agent 交互
  - `/api/session/{id}/messages` — 获取消息
  - `/api/session/{id}/detail` — 会话详情
  - `/api/session/{id}/attachments` — 附件列表
  - `/api/session/{id}/title` (PUT) — 修改标题

- **不需要 Session 的接口**：
  - `/api/auth/*` — 认证相关
  - `/api/users/*` — 用户管理
  - `/api/session/create` — 创建会话
  - `/api/session/list` — 会话列表
  - `/api/session/delete/*` — 删除会话
  - `/api/session/admin/*` — Admin 会话管理

### 中间件执行顺序

FastAPI 中间件为 LIFO 栈：后注册的中间件先执行（最外层包裹最小层）。

```
请求 → auth_middleware(外层) → session_auth_middleware(内层) → 路由
```

1. `auth_middleware`（后注册，外） — 验证 Access Token（`/api/*` 非白名单路径）；非 API 路径（Vite HMR、静态资源）跳过验证
2. `session_auth_middleware`（先注册，内） — 验证 Session（需要 session 的路径）
3. 路由处理器

### 权限控制

- **角色区分**：用户表 `role` 字段支持 `admin` / `user`，登录时返回
- **Admin 权限校验**：`require_admin` FastAPI 依赖，检查 `request.state.role == 'admin'`，非 admin 返回 403
- **Admin 专属接口**：用户管理、在线监控、强制下线、会话查询等接口均受 `require_admin` 保护

### 安全措施

- Access Token payload 包含 `type: "access"`，Refresh Token 包含 `type: "refresh"`
- Refresh Token 不可用于普通 API（auth_middleware 拒绝 type=refresh）
- Access Token 不可用于 refresh 接口（refresh 接口拒绝 type=access）
- Refresh Token 通过 HttpOnly Cookie 传递，前端 JS 无法读取
- Cookie 属性：`HttpOnly; SameSite=Strict; Secure; Path=/api/auth; Max-Age=86400`
- Refresh Token 在服务端数据库存储哈希值，支持主动删除
- Admin 强制下线操作清除目标用户的所有 Refresh Token 与 Portal Refresh Token，保留 Session 记录以便审计查询
- 登出时：删除数据库记录 + 清除 Cookie + 删除该用户所有 portal_refresh_tokens
- 密码修改时：删除该用户所有 Refresh Token 记录并删除所有 Portal Refresh Token（强制所有设备重新登录）

### Portal Refresh Token（子 refresh_token 委派机制）

**背景**：门户导航页（portal.html）的 iframe 中可嵌入第三方应用；第三方应用需调用本应用 API，但本应用主 refresh_token 在 HttpOnly Cookie 中不可被 JS 读取。

**方案**：颁发"子 refresh_token"给父页，父页通过 postMessage 推送给第三方；第三方可像普通 SPA 一样用它反复换 access_token。

- **颁发**：`POST /api/auth/issue-portal-refresh-token`（需 Bearer access_token，auth_middleware 校验），额外检查该用户是否仍持有有效的 refresh_token（被踢后会被删除，无有效 refresh_token 时返回 401）；调用 `jwt_auth.generate_refresh_token` 生成标准 JWT 格式 token（与主 refresh_token 统一），SHA256 后存入 `portal_refresh_tokens` 表；**生成新 token 前先物理删除该用户所有旧记录**，确保同一用户只有一条 portal token
- **使用**：第三方 iframe 调 `POST /api/auth/refresh`，body `{"refresh_token":"<子>"}` 或 header `X-Refresh-Token`，换 access_token
- **TTL**：`PORTAL_REFRESH_TOKEN_TTL_SECONDS`（默认 86400 = 24h）
- **过期处理**：第三方 API 401 → 重试 refresh 失败 → `window.top.location.href = '/login'`；用户重新登录后父页重新颁发
- **删除**：登出、密码修改、admin 强制下线时均调用 `delete_user_tokens(user_id)` 一并物理删除该用户所有 portal_refresh_tokens
- **与主 refresh_token 的边界**：主 refresh_token 仍只通过 HttpOnly Cookie 走（原有逻辑完全不变）；子 token 是"借"给第三方的副本，**不进入主 refresh_tokens 表**
- **前端并发锁**：`PortalApp.vue` 的 `sendAuthToIframe` 使用 `isIssuingPortalToken` 标志锁，防止 iframe `load` 事件重复触发或 `PORTAL_AUTH_REQUEST` 并发导致重复申请
- **数据库约束**：`store_token` 内部先 DELETE 再 INSERT，从逻辑层面强制一个用户只有一条记录
- **postMessage 协议**：
  - 父 → 第三方：`{type:'PORTAL_AUTH', refreshToken, username, userId, userRole, apiBaseUrl, issuedAt, expiresIn}`
  - 第三方 → 父：`{type:'PORTAL_AUTH_REQUEST'}`（在首次加载未及时收到时、或 refresh 失败时主动请求）
  - 父校验 `event.source === iframe.contentWindow` 防冒用
  - 父用 `targetOrigin`（从 navItem 配置或 url 推断）避免 `postMessage(msg, '*')` 泄 token
- **详细文档**：[docs/portal-iframe-token-guide.md](file:///e:/laboratory/AI/Agents/agent-user-mangerment/docs/portal-iframe-token-guide.md) — Portal 导航页 iframe Token 获取完整端到端流程指南（含接口说明、postMessage 协议、第三方接入示例、兼容逻辑）

## 数据库设计

### users 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PRIMARY KEY | 用户ID |
| username | VARCHAR(100) UNIQUE | 用户名 |
| password_hash | VARCHAR(255) | bcrypt 密码哈希 |
| role | VARCHAR(20) DEFAULT 'user' | 角色（admin/user） |
| real_name | VARCHAR(20) DEFAULT '' | 真实姓名 |
| phone | VARCHAR(20) DEFAULT '' | 手机号 |
| email | VARCHAR(100) DEFAULT '' | 邮箱 |
| department | VARCHAR(100) DEFAULT '' | 部门 |
| position | VARCHAR(100) DEFAULT '' | 职位 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### sessions 表
| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | VARCHAR(100) PK | 会话ID（UUID） |
| user_id | INTEGER FK → users | 用户ID |
| username | VARCHAR(100) | 用户名 |
| title | VARCHAR(200) | 会话标题 |
| last_active_at | TIMESTAMP | 最后活跃时间 |
| status | VARCHAR(20) | 状态 |
| agent_type | VARCHAR(50) | Agent 类型 |
| created_at | TIMESTAMP | 创建时间 |

### conversation_records 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 记录ID |
| session_id | VARCHAR(100) FK | 会话ID |
| role | VARCHAR(20) | 角色（user/ai） |
| content | TEXT | 内容 |
| tool_calls | JSONB | 工具调用 |
| tool_call_id | VARCHAR(100) | 工具调用ID |
| created_at | TIMESTAMP | 创建时间 |

### attachments 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 附件ID |
| session_id | VARCHAR(100) FK | 会话ID |
| file_name | VARCHAR(500) | 文件名 |
| stored_path | VARCHAR(1000) | 存储路径 |
| file_type | VARCHAR(20) | 文件类型 |
| file_size | BIGINT | 文件大小 |
| mime_type | VARCHAR(100) | MIME类型 |
| file_id | VARCHAR(100) | 文件ID |
| created_at | TIMESTAMP | 创建时间 |

### refresh_tokens 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 记录ID |
| token_hash | VARCHAR(255) UNIQUE | Refresh Token 的 SHA256 哈希值 |
| user_id | INTEGER FK → users | 用户ID |
| expires_at | TIMESTAMP | 过期时间 |
| created_at | TIMESTAMP DEFAULT NOW() | 创建时间 |

### portal_refresh_tokens 表
门户导航场景下颁发给第三方 iframe 的"子 refresh_token"存储表。子 token 与正常 refresh_token 等效，但独立存储便于独立撤销与审计。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 记录ID |
| token_hash | VARCHAR(255) UNIQUE | Portal Refresh Token 的 SHA256 哈希值 |
| user_id | INTEGER FK → users | 用户ID |
| username | VARCHAR(100) | 用户名（冗余用于审计） |
| expires_at | TIMESTAMP | 过期时间（默认 24 小时） |
| revoked | BOOLEAN DEFAULT FALSE | ~~软删除标志（已废弃，逻辑上改为物理删除，不再使用）~~ |
| created_at | TIMESTAMP DEFAULT NOW() | 创建时间 |

## API 路由汇总

| 前缀 | 模块 | 说明 |
|------|------|------|
| /api/auth | auth_router | 认证（验证码、注册、登录、刷新、验证、登出、门户子 refresh_token） |
|   ├ GET /captcha | | 获取图形验证码（返回 key + base64 图片） |
|   ├ POST /register | | 用户注册（含验证码校验、密码复杂度校验） |
|   ├ POST /login | | 用户登录（验证码校验，返回 access_token + Set-Cookie refresh_token） |
|   ├ POST /login-api | | API 程序化登录（免验证码，返回 access_token + Set-Cookie refresh_token） |
|   ├ POST /refresh | | 刷新 Access Token（读取顺序：X-Refresh-Token 头 > body {refresh_token} > HttpOnly Cookie；同时查 refresh_tokens 与 portal_refresh_tokens） |
|   ├ GET /validate | | 验证 Access Token 有效性（返回 username、role、user_id） |
|   ├ POST /logout | | 用户登出（清除 Refresh Token + Cookie + Session + 撤销该用户所有 portal_refresh_tokens） |
|   ├ POST /issue-portal-refresh-token | | 颁发门户子 refresh_token（需 Bearer access_token；用于门户导航页推送第三方 iframe） |
| /api/users | user_router | 用户管理（列表、创建、更新、删除、踢人、改密码、改用户名、资料） |
|   ├ GET / | | 用户列表（admin 专用） |
|   ├ POST / | | Admin 创建用户 |
|   ├ GET /online | | 在线用户列表（admin 专用） |
|   ├ PUT /{user_id} | | Admin 更新用户资料 |
|   ├ DELETE /{user_id} | | 删除用户（admin 专用，同时清除该用户所有 Session） |
|   ├ POST /{user_id}/kick | | 强制用户下线（admin 专用，清除 Refresh Token 并标记 Session 为 kicked） |
|   ├ GET /{user_id}/sessions | | 指定用户会话列表（admin 专用） |
|   ├ PUT /{user_id}/password | | 修改密码（修改后强制清除所有 Refresh Token） |
|   ├ PUT /{user_id}/username | | 修改用户名（仅限修改自己的用户名） |
|   ├ GET /{user_id}/profile | | 获取用户个人资料（仅限查看自己的资料） |
|   ├ PUT /{user_id}/profile | | 更新用户个人资料（仅限修改自己的资料） |
| /api/session | session_router | 会话管理（创建、删除、列表、详情、标题、附件、消息） |
|   ├ POST /create | | 创建新会话 |
|   ├ DELETE /delete/{session_id} | | 删除会话（同时清理对话记录、附件、文件目录、checkpoint、缓存） |
|   ├ GET /list | | 获取当前用户的会话列表 |
|   ├ GET /{session_id}/detail | | 获取会话详情（含附件列表） |
|   ├ PUT /{session_id}/title | | 更新会话标题 |
|   ├ GET /{session_id}/attachments | | 获取会话附件列表 |
|   ├ GET /{session_id}/messages | | 获取会话历史消息（从 LangGraph Checkpoint 恢复，默认 50 条） |
|   ├ DELETE /admin/{session_id} | | Admin 强制删除任意会话 |
|   ├ GET /admin/search | | Admin 按用户名搜索会话 |
| /api/files | file_router | 文件管理（上传、下载、删除、列表、PDF 转图片） |
|   ├ POST /upload | | 批量上传文件 |
|   ├ POST /upload-base64 | | 批量上传 base64 编码文件 |
|   ├ GET /download/{file_uuid} | | 下载文件 |
|   ├ GET /info/{file_uuid} | | 获取文件信息 |
|   ├ DELETE /delete | | 批量删除文件 |
|   ├ GET /list | | 列出所有文件 |
|   ├ POST /convert | | 批量转换 PDF 为图片 |
| /api/core | file_upload_router | 核心文件上传（支持远程解析服务/本地 DocumentLoader 解析） |
|   ├ POST /uploadfile | | 批量上传文件（含文本提取/远程解析） |
|   ├ POST /upload-chunk | | 分片上传 |
|   ├ POST /merge-chunks | | 合并分片 |
| /api/core/download | file_download_router | 核心文件下载（支持 Range 断点续传、批量打包 ZIP） |
|   ├ GET /file | | 下载文件（支持 Range 请求、自定义下载文件名） |
|   ├ GET /by-name | | 按文件名模糊/精确匹配下载 |
|   ├ POST /batch | | 批量下载（打包为 ZIP） |
|   ├ GET /list | | 列出可下载文件（支持子目录、递归） |
| /api/contract | contract_router | 合同主办 Agent |
|   ├ POST /uploadfile | | 上传并处理合同文件（存储 file_id 到 LangGraph Store） |
|   ├ POST /chat | | 合同审批聊天（HtAgent 非流式） |
|   ├ POST /doc_chat | | 文档处理聊天（DocAgent 非流式） |
|   ├ POST /approval_chat | | 审批处理聊天（ApprovalAgent 非流式） |
|   ├ POST /store/value | | 根据 id 获取 LangGraph Store 中的值 |
|   ├ POST /store/value/set | | 向 LangGraph Store 中写入值 |
|   ├ POST /download_contract | | 下载合同文件（返回 base64） |
| /api/map | map_router | 地图 Agent |
|   ├ GET /knowledge/files | | 获取知识库文件元数据（自动扫描 Knowledge 目录） |
|   ├ GET /knowledge/file-download | | 下载知识库文件 |
|   ├ GET /knowledge/file-preview | | 知识库文件预览（支持 .doc 自动转 .docx） |
|   ├ POST /chat | | 地图智能体流式聊天（SSE，支持 HITL 中断与恢复） |
|   ├ POST /knowledge-chat | | 地图智能体知识库聊天（SSE，使用知识库系统提示词） |
| /api/ai-coding-check | ai_coding_check_router | AI 代码检查 Agent |
|   ├ POST /review | | 评审开发者数据（非流式 JSON API） |
| /mcp | mcp_router | MCP 服务器工具调用 |
|   ├ GET /servers | | 列出所有已连接的 MCP 服务器及其工具 |
|   ├ POST /call | | 调用指定 MCP 服务器的工具 |
|   ├ GET /tools/{server_name} | | 列出指定 MCP 服务器的工具详情 |

## 环境变量

- `AUTH_STORAGE_MODE` — 存储模式（postgres/memory）
- `DATABASE_URL` — PostgreSQL 连接字符串
- `PORTAL_REFRESH_TOKEN_TTL_SECONDS` — 门户子 refresh_token 有效期（秒），默认 86400 = 24 小时
- `VITE_API_TARGET` — 前端 Vite 代理目标地址（开发用），默认 `http://localhost:8001`
- ~~`VITE_PORTAL_NAV_CONFIG`~~ — 已废弃，门户导航配置迁移到 `public/app-config.json` 运行时配置
- 其他 LLM API Key 等

## 提示词三层架构

整个项目的系统提示词采用**三层分层设计**，各层职责分离，通过 Agent 基类自动拼接，确保通用规则统一维护、专用逻辑各 Agent 独立管理。

### 架构概述

| 层级 | 文件位置 | 形式 | 职责 |
|------|---------|------|------|
| 第一层 | `app/core/prompts.py` | `BASE_SYSTEM_PROMPT` 字符串 | 所有智能体共享的通用规则 |
| 第二层 | `app/features/{agent}/config/prompts.py` | `DEFAULT_SYSTEM_PROMPT` 字符串 | 单个 Agent 的角色、工作流程、工具组合策略 |
| 第三层 | `app/features/{agent}/tools/*.py` | 工具函数 docstring | 每个工具的具体用途、调用时机、参数说明 |

### 第一层 - 通用基类提示词

- **文件位置**：[app/core/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/core/prompts.py)
- **变量名**：`BASE_SYSTEM_PROMPT`
- **职责**：所有智能体共享的通用规则，包括：
  - **Core Principles**：准确理解用户意图、严格遵循工具参数说明、保持简洁、直接回答
  - **Knowledge Priority**：用户提及附件文件时，优先使用搜索工具查找附件内容，再使用自身知识
  - **Tool Usage**：严格按参数规范使用工具、禁止同时调用多个工具、一次调用等待结果后再决定下一步、无匹配工具时必须调用 `ask_user_question`（1-4 个问题、每个 2-4 个选项、`multiSelect` 可选、推荐项以 "(Recommended)" 结尾）
  - **Output Rules**：回复不超过 4 行、禁止铺垫和总结、无法帮助时提供 1-2 句替代方案
  - **Interaction**：仅在用户要求时主动、不擅自执行未请求的操作、意图不明时询问澄清
- **特点**：影响所有 Agent，通过 Agent 基类自动拼接在每个 Agent 的系统提示词最前面

### 第二层 - 智能体专用提示词

- **文件位置**：`app/features/{agent_name}/config/prompts.py`
- **变量名**：`DEFAULT_SYSTEM_PROMPT`
- **职责**：定义该 Agent 的专属内容：
  - **角色定义**：该 Agent 的业务身份和核心职责
  - **工作流程**：多阶段业务处理流程（如要件接收→验证→审批→确认）
  - **工具选择策略**：何时使用哪个工具、多个工具的优先级和组合方式
  - **输出格式要求**：表格格式、Markdown 结构、特定字段呈现方式
- **设计原则**：基于第一层，**不需要重复**通用规则。例如：
  - 第一层已规定"禁止同时调用多个工具"，第二层无需重复
  - 第一层已规定"保持简洁、禁止铺垫"，第二层只需关注业务输出格式
- **示例 Agent**：

| Agent | 提示词文件 |
|-------|-----------|
| 地图 Agent | [app/features/map_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/map_agent/config/prompts.py) |
| 合同主办 Agent | [app/features/contract_host_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/contract_host_agent/config/prompts.py) |
| 合同文档 Agent | [app/features/contract_document_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/contract_document_agent/config/prompts.py) |
| 合同审批 Agent | [app/features/contract_approval_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/contract_approval_agent/config/prompts.py) |
| DevOps Agent | [app/features/DevOps_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/DevOps_agent/config/prompts.py) |
| AI 代码检查 Agent | [app/features/AI_Coding_Check_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/AI_Coding_Check_agent/config/prompts.py) |

### 第三层 - 工具描述提示词

- **文件位置**：`app/features/{agent_name}/tools/*.py`
- **形式**：各工具函数的 docstring（被 `@tool` 装饰器提取）
- **职责**：描述每个工具的详细信息：
  - **调用时机**：什么用户意图/指令下应该调用该工具
  - **参数说明**：每个参数的含义、取值范围、格式要求
  - **参数组合**：哪些参数需要同时使用、互斥关系、默认值行为
  - **返回值格式**：工具执行成功后返回的数据结构和字段说明
- **特点**：LLM 通过 LangChain 的 `@tool` 装饰器自动将 docstring 转换为工具 schema，供模型在决策时阅读。工具描述越详细，模型调用越精准。
- **示例**：[app/features/map_agent/tools/MapTools.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/map_agent/tools/MapTools.py) 中 `set_map_center`、`add_map_marker` 等函数的 docstring

### 拼接机制

三层提示词在 Agent 基类中按顺序拼接，形成最终送入 LLM 的系统提示词。

**拼接位置**：[app/core/agent/agent.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/core/agent/agent.py) 的 `_llm_call` 方法（第 287 行）：

```python
system_prompt = (
    BASE_SYSTEM_PROMPT
    + "\n\n"
    + (self.system_prompt or "")
    + "\n\n"
    + (context.get("system_prompt") or "")
)
```

**拼接顺序**：

```
┌─────────────────────────────────────┐
│  第一层: BASE_SYSTEM_PROMPT         │  ← 通用规则（所有 Agent 共享）
├─────────────────────────────────────┤
│  第二层: Agent.system_prompt        │  ← Agent 专用规则（角色、流程、策略）
├─────────────────────────────────────┤
│  动态层: context.system_prompt      │  ← 运行时动态追加（可选）
└─────────────────────────────────────┘
```

- 第一层始终在最前，确保通用规则优先级最高
- 第二层紧跟其后，补充 Agent 专属业务逻辑
- 动态层由运行时上下文注入，用于会话级临时调整

### 分层设计原则

| 层级 | 应该写什么 | 不应该写什么 |
|------|-----------|-------------|
| 第一层 | 所有 Agent 通用的行为规则、工具使用规范、输出格式约束 | Agent 特有的业务逻辑、具体工具名称 |
| 第二层 | 该 Agent 的角色定义、工作流程、工具选择策略、业务判断标准 | 通用工具调用规范（如"不要同时调用多个工具"）、通用输出约束（如"保持简洁"） |
| 第三层 | 单个工具的调用时机、参数含义、参数组合、返回值说明 | 业务工作流程、工具之间的协调策略 |

**维护建议**：
- 修改第一层时需谨慎，变更会影响**所有 Agent**
- 第二层各 Agent 独立维护，互不影响
- 第三层随工具功能迭代同步更新 docstring，确保模型获取最新工具描述

## HITL 流程（2026-06-01 重构）

**工具**：`app/core/tools/HumanInTheLoopTools.py` 中的 `ask_user_question`（替代旧的 `request_human_approval`）

**数据契约**：
- 入参：Pydantic 约束的 `AskUserQuestionInput`（1-4 个 Question，每个 2-4 个 Option，header ≤ 12、label ≤ 30、description ≤ 200）
- 中断 payload：`{"action": "ask_user_question", "questions": [...]}`（LangGraph `interrupt()` 直接传 dict）
- 恢复值：`Command(resume={"answers": [[...], [...]]})`（每题一个 label 数组）
- State 字段：`pending_question: dict`、`question_answers: list`（用 `Overwrite` 追加）

**节点**：`app/core/agent/agent.py:hitl_check_node` 收到 `pending_question` 后调 `interrupt()`，恢复时构造 `HumanMessage` 回灌（保持 HumanMessage 模式避免 `tool_call_id` 风险）

**前端**：
- `web/Agent/src/components/HumanApprovalBox.vue`（445 → 534 行）：多 Tab 切换 + 虚拟 Other 项 + 多选模式 + 全局 `canSubmit` 门控
- 提交事件：`emit('submit', { answers: string[][] })`（替代旧 `{ decision, feedback }`）
- `web/Agent/src/App.vue:extractApprovalData`：直接读 `req.value?.questions`（替代旧的 3 层 `action_request/args` 解包）

**测试**：
- 后端：`tests/test_ask_user_question.py` 17 个测试（Schema 10 + Tool 2 + HitlCheckNode 5）
- 前端：`web/Agent/src/components/__tests__/HumanApprovalBox.spec.js` 14 个测试
- 核心工具：`app/tests/core/tools/` 新增 3 个测试模块：
  - `test_human_in_the_loop_tools.py`：Schema 7 + Tool 2，覆盖 QuestionOption/Question/AskUserQuestionInput 约束与 Other 注入逻辑
  - `test_base_tools.py`：导入 + get_current_time Mock 调用 + _split_content 分块 3 个用例
  - `test_mcp_tool_adapter.py`：导入 + 7 个主要函数/类存在性验证
- 全量：后端 17/17 + 前端 73/73 全部通过

## 前端架构（web/Agent）

`web/Agent/` 是基于 Vite + Vue 3 的多入口 SPA，对外提供三套独立页面（主 Agent、知识库、门户），共享同一套组件、工具函数与设计 token。

### 技术栈

- **核心框架**：Vue 3.4 + Vite 5（JavaScript，无 TypeScript）
- **UI 渲染**：marked（Markdown）+ highlight.js（代码高亮）+ @vue-office/{docx,excel,pdf,pptx}（Office 文档预览）
- **测试**：Vitest 4 + @vue/test-utils + happy-dom
- **包管理**：npm；脚本 `dev` / `build` / `preview` / `test` / `test:watch` / `test:coverage`
- **关键依赖**：vue-demi（@vue-office 的 Vue 2/3 兼容垫片）

### 多入口与挂载

`vite.config.js` 的 `build.rollupOptions.input` 显式声明三个 HTML 入口，分别对应不同的业务场景：

| 入口文件 | 挂载组件 | 部署路径 | 用途 |
|----------|----------|----------|------|
| `index.html` | `App.vue`（`src/main.js`） | `/` | 主聊天界面 + 知识库 Tab（Sidebar 切换 currentPage） |
| `knowledge.html` | `KnowledgeApp.vue`（`src/knowledge-main.js`） | `/knowledge` | 知识库独立页（文件侧栏 + 聊天） |
| `portal.html` | `PortalApp.vue`（`src/portal-main.js`） | `/portal` | 门户导航（顶部蓝色导航栏 + iframe 嵌入 `/knowledge`） |

三个入口共享 `src/components`、`src/utils`、`src/styles`，构建后产出三个独立的 JS Chunk。

### 组件清单（src/components）

- **根组件**：`App.vue`（主）、`KnowledgeApp.vue`（知识库）、`PortalApp.vue`（门户）、`KnowledgePage.vue`（旧版，被 `KnowledgeApp.vue` 替代，仍保留以兼容旧引用）
- **聊天**：`ChatArea.vue`、`InputBox.vue`、`MessageBubble.vue`、`SkillTags.vue`、`HumanApprovalBox.vue`、`TopBar.vue`
- **文件**：`FileList.vue`、`FilePreview.vue`、`FolderTree.vue`、`FileManagerModal.vue`
- **知识库**：`KnowledgeChat.vue`、`ProfileInputBox.vue`
- **公共**：`Sidebar.vue`、`HelloWorld.vue`、`UserSettingsDialog.vue`
- **视图**（`src/views/`）：`LoginView.vue`、`RegisterView.vue`

### 工具函数（src/utils）

- **`api.js`**：登录/注册/验证码/登出/refresh/validate；会话创建/列表/删除/详情/标题/附件/消息；文件上传（普通 + 分片 + base64）/下载/列表/删除；SSE `chatStream` / `knowledgeChatStream`；`X-Session-ID` 头注入；附件元数据组装
- **`sseParser.js`**：`isThinkingBlock` / `tryParsePythonLiteral` / `extractTextFromBlock` / `processContentBlocks` / `parseMessageContent` / `processSSEEvent` / `createAiMessage`；支持 Python 风格单引号字面量、JSON.parse、regex 回退三级解析
- **`index.js`**：聚合导出

### 认证流（前端）

- **三段式认证**（`App.vue:checkAuth` / `PortalApp.vue:checkAuth` / `KnowledgeApp.vue:onMounted`）：
  1. 优先调用 `validateToken` 验证当前 access token
  2. 失败则调用 `refreshToken` 换新 token，再 `validateToken`
  3. 仍失败则 `clearAuth` + 跳登录页
- **localStorage 键**：
  - `auth_token`：access token（每次请求 `Authorization: Bearer`）
  - `username` / `user_role` / `user_id`：用户基本信息
  - `session_id`：主 Agent 当前会话
  - `knowledge_session_id`：知识库独立会话（与主会话隔离，独立创建）
- **refresh_token 不存 localStorage**，由后端通过 HttpOnly Cookie 下发（`SameSite=Strict; Path=/api/auth`）
- **401 自动重试**：API 返回 401 → 自动 `refreshToken` → 用新 token 重试原请求，最多 1 次，失败跳登录

### SSE 流式与 HITL

- **后端 SSE 端点**：`/api/agent/*`（主聊天）、`/api/map/knowledge-chat`（知识库聊天）
- **事件格式**：`data: {json}\n\n`，由 `sseParser.js` 解析为以下块：
  - `text`：AI 回复正文
  - `thinking`：思考过程（折叠展示）
  - `timeline`：工具调用时间线
  - `tools`：工具调用记录
  - `interrupt`：HITL 中断（payload = `{action: "ask_user_question", questions: [...]}`）
- **HITL 恢复**：`HumanApprovalBox` 提交 `{answers: string[][]}` → `chatStream(..., resumeData)` → 后端 `Command(resume=...)` 继续执行
- **渲染**：`MessageBubble` 统一展示，marked 转 HTML、highlight.js 代码高亮

### Vite 开发代理（vite.config.js）

- 代理 `/api` → `VITE_API_TARGET`（默认 `http://localhost:8001`）
- 对 `/api/*/chat` 路径做 SSE 友好头处理：
  - 请求头：`Connection: keep-alive`、`Cache-Control: no-cache`、`Accept: text/event-stream`
  - 响应头：删除 `content-length`、设置 `cache-control: no-cache`、`connection: keep-alive`、`x-accel-buffering: no`
- **目的**：保证 LLM 流式输出不被 nginx/反代 buffer 截断

### 部署（Nginx + Docker）

- **`Dockerfile`**：多阶段构建 — `node:20-alpine` 构建 → `nginx:alpine` 运行
- **启动注入**：通过 `envsubst ${VITE_API_TARGET}` 把环境变量写入 `nginx.conf` 模板
- **`nginx.conf` 关键点**：
  - **SPA fallback**：`try_files $uri $uri/ /index.html`
  - **静态资源**：1 年缓存 + `Cache-Control: public, immutable`
  - **/api 反代**：`proxy_buffering off`、`proxy_cache off`、`chunked_transfer_encoding on`、支持 WebSocket Upgrade
  - **超时**：connect 60s、send/read 300s（支持长时 LLM 生成）
  - **健康检查**：`/health` 返回 `200 healthy\n`

### Portal 运行时配置

- **配置来源**：`public/app-config.json`（运行时 JSON，Vite 构建时自动复制到输出根目录）
- **配置模块**：`web/Agent/src/config/portal.js`（统一配置中心）
  - `loadAppConfig()`：应用启动时 `fetch('/app-config.json')`，将配置合并到响应式 `appConfig`
  - `getNavItems()`：获取导航项列表（从 `appConfig.navItems` 读取，校验失败回退默认）
  - `appConfig`：Vue `reactive` 对象，含 `brandTitle`、`brandDesc`、`navItems`
- **配置字段**：
  - `brandTitle`：品牌主标题（显示在导航栏、登录页、注册页、浏览器标签页）
  - `brandDesc`：品牌副标题/描述（显示在登录页品牌区）
  - `navItems`：导航项数组，字段同 NavItem
- **NavItem 字段**：
  - `key`：唯一键
  - `label`：显示文字
  - `type`：`'placeholder'`（占位提示） | `'iframe'`（嵌入 iframe）
  - `url`：type=iframe 时必填，相对路径或绝对 URL
  - `targetOrigin`：postMessage 的 targetOrigin；缺省时按 url 推断
- **默认配置**（`app-config.json` 缺失或解析失败时回退）：
  ```js
  {
    brandTitle: '沈阳市自然资源和规划"一点通"',
    brandDesc: '智慧政务服务平台',
    navItems: [
      { key: 'site-select', label: '智能选址', type: 'iframe', url: 'http://59.197.227.228/webgis/kjzr' },
      { key: 'pre-check', label: '智能预检', type: 'iframe', url: 'http://59.197.227.228/webgis/kjzr' },
      { key: 'rule-lib', label: '规则库', type: 'iframe', url: '/knowledge.html' }
    ]
  }
  ```
- **使用示例**（修改 `web/Agent/public/app-config.json`，无需重新打包）：
  ```json
  {
    "brandTitle": "自定义标题",
    "brandDesc": "自定义描述",
    "navItems": [
      { "key": "site-select", "label": "智能选址", "type": "iframe", "url": "http://59.197.227.228/webgis/kjzr" },
      { "key": "pre-check", "label": "智能预检", "type": "iframe", "url": "http://59.197.227.228/webgis/kjzr" },
      { "key": "rule-lib", "label": "规则库", "type": "iframe", "url": "/knowledge.html" }
    ]
  }
  ```

### 设计系统（src/styles/variables.css）

- **颜色 token**：`--color-bg-{primary,secondary,tertiary,hover,active}`、`--color-border`、`--color-border-light`、`--color-text-{primary,secondary,muted,inverse}`、`--color-accent` / `-hover` / `-light`、`--color-{success,warning,error,info}`
- **Tag 配色**：`--color-tag-{beta,new,free}` + 对应文字色
- **圆角**：`--radius-{sm:8, md:10, lg:12, xl:16, full:9999}`
- **阴影**：`--shadow-{sm, md, lg}`
- **间距**：`--space-{xs:4, sm:8, md:12, base:16, lg:24, xl:32, 2xl:48}`
- **字体**：`--font-family`（系统字体栈 + PingFang SC + Microsoft YaHei）、`--font-size-{xs..2xl}`、`--font-weight-{normal,medium,semibold,bold}`
- **过渡**：`--transition-fast` / `--transition` / `--transition-slow` / `--transition-colors` / `--transition-transform` / `--transition-opacity` / `--transition-shadow`
- **可访问性**：`--focus-ring` / `--focus-ring-inset`
- **布局**：`--sidebar-width: 260px`、`--topbar-height: 56px`、`--min-layout-width: 1024px`
- **z-index 分层**：dropdown 100 / sticky 200 / modal 300 / tooltip 400

### 测试（Vitest）

- **配置文件**：`vitest.config.js`（happy-dom 环境）
- **运行脚本**：`npm test`（单次）、`npm run test:watch`（监听）、`npm run test:coverage`（覆盖率）
- **测试分布**（`src/**/__tests__` 与 `src/components/__tests__`）：
  - `HumanApprovalBox.spec.js`：HITL 组件（多 Tab、虚拟 Other 项、多选、`canSubmit` 门控，14 用例）
  - `api.test.js`：`utils/api.js` 工具方法
  - `sseParser.test.js`：SSE 解析（含 Python 字面量兼容）
- **项目历史**：后端 17/17 + 前端 73/73 全部通过（参见 "HITL 流程" 章节）

