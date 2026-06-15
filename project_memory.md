# 项目记忆文档

## 项目概述

Agent User Management 是一个基于 FastAPI 的 AI Agent 管理平台，提供用户认证、会话管理、文件管理、多 Agent 功能等。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **数据库**: PostgreSQL（通过 asyncpg），支持 Memory 模式降级
- **认证**: JWT（双 Token 体系：Access Token + Refresh Token）
- **AI**: LangGraph + LangChain，支持多种 LLM 模型（版本详见下方 "AI 依赖版本与文档约定"）
- **工具**: MCP（Model Context Protocol）工具集成

### AI 依赖版本与文档约定（2026-06-14 记录）

#### LangChain / LangGraph 全家桶版本（锁定自 `app/requirements.txt`）

| 包 | 版本 | 用途 |
|----|------|------|
| `langchain` | 1.2.16 | LangChain 1.x 主包（统一入口） |
| `langchain-core` | 1.3.2 | 核心抽象（Message、Runnable、@tool 等） |
| `langchain-classic` | 1.0.2 | LangChain 1.x 兼容层（旧链式 API、AgentExecutor 等） |
| `langchain-community` | 0.4.1 | 社区工具/向量库集成 |
| `langchain-text-splitters` | 1.1.1 | 文本切分器 |
| `langchain-openai` | 1.1.6 | OpenAI / 兼容 OpenAI 协议模型 |
| `langchain-anthropic` | 1.4.2 | Anthropic Claude |
| `langchain-google-genai` | 4.2.2 | Google Gemini |
| `langchain-deepseek` | 1.0.1 | DeepSeek |
| `langchain-ollama` | 1.0.1 | Ollama 本地模型 |
| `langchain-mcp-adapters` | 0.2.1 | MCP 工具适配为 LangChain 工具 |
| `langchain-protocol` | 0.0.14 | 协议层（实验） |
| `langgraph` | 1.1.10 | LangGraph 主包（图编排、Checkpoint、Store） |
| `langgraph-checkpoint` | 4.1.1 | Checkpoint 抽象基类与内存实现 |
| `langgraph-checkpoint-postgres` | 3.1.1 | PostgreSQL Checkpoint 后端 |
| `langgraph-prebuilt` | 1.0.13 | 预构建节点（ToolNode、create_react_agent 等） |
| `langgraph-sdk` | 0.3.1 | LangGraph 远程部署 SDK |
| `langmem` | 0.0.30 | 长期记忆扩展 |
| `langsmith` | 0.7.38 | LangSmith 追踪/评估 SDK |
| `deepagents` | 0.5.5 | LangChain 官方 subagent 库（沙箱 Agent 依赖） |

#### 文档查询约定

- **凡涉及 LangChain / LangChain-Core / LangGraph / LangSmith / LangMem / deepagents 的 API 使用**，必须通过 **context7 MCP** 查找对应官方文档后再调用，禁止凭记忆使用旧版本 API。
- 优先查询顺序：
  1. `usecontext7_mcp` → `get-library-docs` 拉取目标库的最新 docs（如 `/langchain-ai/langchain`、`/langchain-ai/langgraph`）
  2. 命中失败再降级 WebSearch + 官方文档站（`https://python.langchain.com/`、`https://langchain-ai.github.io/langgraph/`）
- 版本兼容注意：项目使用 **LangChain 1.x + LangGraph 1.x**（旧版 0.x 的 `create_react_agent`、`AgentExecutor`、`LLMChain` 等签名已变更，迁移文档参考 context7 `/langchain-ai/langchain` 的 v1 migration guide）
- 更新 `app/requirements.txt` 时，必须同步更新本表版本号，避免文档查错版本

## 数据目录约定（2026-06-12 重构）

运行时数据目录位于**项目根**（非 `app/` 内），便于与代码解耦并避免被打入 Docker 镜像。

```
data/                          # 项目根运行时数据目录（原 app/data）
├── Knowledge/                 # 知识库数据（地图 Agent）
│   ├── metadata.json
│   ├── sync_metadata.py
│   └── tmp/                   # 临时缓存（doc 转换、large_tool_results）
├── upload/                    # 用户上传文件（按 session_id 分目录）
├── download/                  # 用户下载文件（按 session_id 分目录）
├── upload_chunks/             # 分片上传临时目录（按 file_id 分目录）
└── demonstration/download/    # 演示模式专用下载目录
```

### 关键变更

- **路径常量**（统一改为相对项目根）：
  - `app/core/router/file_upload_router.py`：`UPLOAD_DIR = Path("data/upload")`、`CHUNKS_DIR = Path("data/upload_chunks")`
  - `app/core/router/file_download_router.py`：`DOWNLOAD_DIR = Path("data/download")`
  - `app/shared/utils/files/fileTransfer.py` / `file_upload_handler.py` / `pdfToImage.py`：默认参数 `upload_dir="data/upload"`
- **基于 `Path.cwd()` 的子智能体工作目录**：
  - `app/core/tools/SandboxTools.py`：`workspace = project_root / "data" / "upload" / session_id / "sandbox"`
  - `app/core/tools/FilesystemReadTools.py`：`root_path = project_root / "data" / "upload" / session_id`
- **Knowledge 目录**：`app/features/map_agent/router/map_router.py` 中 `_PROJECT_ROOT` 由 4 次 `os.path.dirname` 改为 5 次，确保升到项目根而非 `app/`
- **审计/地图工具**：`app/features/audit_document_agent/tools/tools.py`、`app/features/map_agent/tools/MapTools.py`、`app/features/Tagent/Tagent.py` 等同步更新
- **.gitignore**：`app/data/` → `data/`（已同步）
- **Dockerfile 无需修改**：`COPY app/ /app/app/` 不会包含项目根的 `data/`，数据仅运行时生成

## 项目架构

```
app/
├── core/                    # 核心模块
│   ├── server.py           # FastAPI 应用配置（生命周期、中间件、CORS）
│   ├── config/settings.py  # 配置管理
│   ├── database.py         # 数据库连接池
│   ├── concurrency/        # 并发控制模块
│   │   ├── agent_concurrency_queue.py  # 基于内存的 Agent 聊天并发队列
│   │   ├── chat_concurrency_dependency.py  # FastAPI 依赖封装
│   │   └── __init__.py     # 包初始化
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
    ├── audit_document_agent/   # 审计文档 Agent
    ├── sandbox_agent/          # 沙箱 Agent（已重构为 subagent 工具模式，见核心工具）
    └── Tagent/                 # T Agent
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
- **详细文档**：
  - [docs/portal-iframe-token-guide.md](file:///e:/laboratory/AI/Agents/agent-user-mangerment/docs/portal-iframe-token-guide.md) — Portal 导航页 iframe Token 获取完整端到端流程指南（含接口说明、postMessage 协议、第三方接入示例、兼容逻辑）
  - [docs/third-party-api-integration-guide.md](file:///e:/laboratory/AI/Agents/agent-user-mangerment/docs/third-party-api-integration-guide.md) — 第三方后端 API 接入完整指南（**非 iframe 场景**，v2.0 2026-06-11 重构：仅需 login-api → 业务 API → refresh → 重新登录 → logout 5 步，无需 portal 子 token / postMessage）
  - [docs/refresh-token-misunderstanding.md](file:///e:/laboratory/AI/Agents/agent-user-mangerment/docs/refresh-token-misunderstanding.md) — Refresh Token 调研澄清报告（2026-06-11 7 个 pytest 用例实测：refresh_token 调任意业务接口均返回 401，不会驱动业务）

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
|   ├ POST /chat | | 合同审批聊天（HtAgent 非流式，受 `chat_concurrency_dependency` 并发控制） |
|   ├ POST /doc_chat | | 文档处理聊天（DocAgent 非流式，受 `chat_concurrency_dependency` 并发控制） |
|   ├ POST /approval_chat | | 审批处理聊天（ApprovalAgent 非流式，受 `chat_concurrency_dependency` 并发控制） |
|   ├ POST /store/value | | 根据 id 获取 LangGraph Store 中的值 |
|   ├ POST /store/value/set | | 向 LangGraph Store 中写入值 |
|   ├ POST /download_contract | | 下载合同文件（返回 base64） |
| /api/map | map_router | 地图 Agent |
|   ├ GET /knowledge/files | | 获取知识库文件元数据（自动扫描 Knowledge 目录） |
|   ├ GET /knowledge/file-download | | 下载知识库文件 |
|   ├ GET /knowledge/file-preview | | 知识库文件预览（支持 .doc 自动转 .docx） |
|   ├ POST /chat | | 地图智能体流式聊天（SSE，支持 HITL 中断与恢复，受 `chat_concurrency_dependency` 并发控制） |
|   ├ POST /knowledge-chat | | 地图智能体知识库聊天（SSE，使用知识库系统提示词，受 `chat_concurrency_dependency` 并发控制） |
| /api/ai-coding-check | ai_coding_check_router | AI 代码检查 Agent |
|   ├ POST /review | | 评审开发者数据（非流式 JSON API） |
| /mcp | mcp_router | MCP 服务器工具调用 |
|   ├ GET /servers | | 列出所有已连接的 MCP 服务器及其工具 |
|   ├ POST /call | | 调用指定 MCP 服务器的工具 |
|   ├ GET /tools/{server_name} | | 列出指定 MCP 服务器的工具详情 |

## 核心工具 (Core Tools)

### Sandbox 工具

**文件位置**: `app/core/tools/SandboxTools.py`

**功能**: 提供 `sandbox` 工具函数，启动沙箱子智能体在隔离的 Docker 容器中执行代码和文件操作。

**使用方式**: 作为 `@tool` 注册到 core agent 工具链，LLM 自动决策调用时机。

**实现细节**:
- 使用 `create_deep_agent` (deepagents) 创建子智能体
- 使用 `DockerSandboxMiddleware` 提供隔离执行环境
- 工作目录: `data/upload/{session_id}/sandbox`（2026-06-12 路径重构，原 `app/data/upload/...` 已迁移到项目根 `data/`）
- 默认镜像: `python:3.12-alpine`
- 资源限制: 内存 512MB，CPU 100%，无网络
- 支持流式事件: `tool_start` / `tool_progress` / `tool_stop`

**依赖**:
- `DockerSandboxMiddleware` / `DockerSandboxBackend`: `app/shared/tools/middleware/docker_sandbox_backend.py`

## Agent 聊天并发控制

**文件位置**: `app/core/concurrency/chat_concurrency_dependency.py`

**功能**: 限制同时处理的 Agent 聊天请求数，超出最大并发数时进入 FIFO 内存队列等待。

**配置项**:
- `AGENT_CHAT_MAX_CONCURRENCY` — Agent 聊天接口最大并发数，超出时进入内存队列等待，默认 3。

**已接入路由**:
- `app/features/map_agent/router/map_router.py`:
  - `POST /api/map/chat`
  - `POST /api/map/knowledge-chat`
- `app/features/contract_host_agent/router/contract_router.py`:
  - `POST /api/contract/chat`
  - `POST /api/contract/doc_chat`
  - `POST /api/contract/approval_chat`

**使用方式**: 通过 FastAPI 路由装饰器的 `dependencies=[Depends(chat_concurrency_dependency)]` 参数接入，无需修改端点函数内部逻辑。

## 环境变量

- `AUTH_STORAGE_MODE` — 存储模式（postgres/memory）
- `DATABASE_URL` — PostgreSQL 连接字符串
- `PORTAL_REFRESH_TOKEN_TTL_SECONDS` — 门户子 refresh_token 有效期（秒），默认 86400 = 24 小时
- `VITE_API_TARGET` — 前端 Vite 代理目标地址（开发用），默认 `http://localhost:8001`
- ~~`VITE_PORTAL_NAV_CONFIG`~~ — 已废弃，门户导航配置迁移到 `public/app-config.json` 运行时配置
- `AGENT_CHAT_MAX_CONCURRENCY` — Agent 聊天接口最大并发数，超出时进入内存队列等待，默认 3
- **沙箱容器化配置（2026-06-12 新增，由 `SandboxSettings` 管理）**：
  - `SANDBOX_DOCKER_MODE` — 部署模式 `local` / `socket` / `dind` / `k8s`，默认 `local`
  - `SANDBOX_DOCKER_HOST` — Docker daemon URL，socket 模式必填
  - `SANDBOX_IMAGE` — 沙箱镜像，默认 `python:3.12-alpine`
  - `SANDBOX_MAX_MEMORY_MB` — 容器内存限制（MB），默认 512，下限 64
  - `SANDBOX_MAX_CPU_PERCENT` — 容器 CPU 限制（百分比），默认 100，范围 10-100
  - `SANDBOX_NETWORK_ENABLED` — 是否启用容器网络，默认 `false`
  - `SANDBOX_DEFAULT_TIMEOUT` — 命令默认超时（秒），默认 60
  - `SANDBOX_CONTAINER_WORKSPACE` — 容器内工作目录，默认 `/workspace`
  - `SANDBOX_HOST_WORKSPACE_PREFIX` — 宿主机视角工作目录前缀，socket 模式必填
  - `SANDBOX_K8S_NAMESPACE` — K8s 模式命名空间（占位）
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

## 沙箱 Agent 架构（Sandbox Agent）

基于 LangChain `deepagents` 库实现，提供安全的代码执行与文件操作环境，通过 Docker 容器隔离保证安全性。

### 核心组件

| 组件 | 文件位置 | 职责 |
|------|---------|------|
| `DockerSandboxBackend` | `app/shared/tools/middleware/docker_sandbox_backend.py` | Docker 容器生命周期管理、命令执行、文件上传下载；区分 host_workspace（宿主机视角，用于 bind mount）与 container_workspace（容器内视角，/workspace）；支持 4 种 docker_mode 路径投影 |
| `DockerSandboxMiddleware` | `app/shared/tools/middleware/docker_sandbox_backend.py` | 继承 `FilesystemMiddleware`，自动管理 `DockerSandboxBackend`，提供沙箱工具集 |
| `sandbox` 工具 | `app/core/tools/SandboxTools.py` | `@tool` 装饰的 `sandbox` 函数，通过 `create_deep_agent` 启动沙箱子智能体；2026-06-12 重构：容器化部署配置从 `Settings.get_sandbox_config()` 注入；2026-06-13 扩展：填充 subagent 结构化字段（详见下文 "SubAgent 事件协议"） |
| `SandboxSettings` | `app/core/config/settings.py` | Pydantic BaseSettings，管理 10 个 `SANDBOX_*` 环境变量，控制 docker_mode / 镜像 / 资源限制 / 路径前缀 |

### 架构变更历史

**2026-06-12 重构**: 从独立 FastAPI 路由 (`/api/sandbox/chat`) 迁移为 core agent 的 subagent 工具模式。
- 删除: `app/features/sandbox_agent/` 目录及所有文件
- 新增: `app/core/tools/SandboxTools.py` 工具函数
- 变更: 从独立 SSE 端点变为通过 core agent 工具链调用

### Docker 容器隔离

- **镜像**：默认 `python:3.12-alpine`，可配置
- **资源限制**：`max_memory_mb`（默认 512MB）、`max_cpu_percent`（默认 100%）
- **网络控制**：`network_enabled=False` 默认关闭网络，防止数据外泄
- **工作目录**：每个 Session 独立 host workspace（如 `/tmp/sandbox/{session_id}`），通过 Docker volume 映射到容器内固定的 `/workspace`，避免 Windows 路径盘符冒号与 Docker mount 格式冲突

### 容器化部署模式（2026-06-12 新增）

**问题背景**：把应用打包成容器运行时，`DockerSandboxBackend` 启动的子容器需要 bind mount 应用容器的工作目录到子容器。但 `self.workspace`（应用进程视角）对宿主机 Docker daemon 不可见，导致 bind mount 失败。

**解决方案**：拆分 `workspace`（应用视角）与 `host_workspace`（宿主机视角），通过 `SandboxSettings.docker_mode` 配置 4 种部署模式：

| 模式 | 适用场景 | docker_mode | host_workspace 投影 | Docker 客户端 |
|------|---------|-------------|---------------------|---------------|
| **local** | 本地直接跑（无容器） | `local` | == workspace | `docker.from_env()` |
| **socket** | 应用容器挂载宿主机 `/var/run/docker.sock` | `socket` | `host_workspace_prefix + workspace` | `docker.DockerClient(base_url=docker_host)` |
| **dind** | Docker-in-Docker（需 `--privileged`） | `dind` | == workspace | `docker.from_env()`（连内嵌 daemon） |
| **k8s** | K8s API 创建 Pod（占位，未实现） | `k8s` | _NotImplementedError_ | — |

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

### 长生命周期容器优化

为解决容器创建耗时问题（秒级 → 50-200ms），采用**预热容器 + `docker exec`** 方案：

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

**最终文本取值修复（2026-06-15）**：循环结束后取子智能体最终 AI 文本时，数据源从 `data["messages"]`（循环最后一个流块的数据，当最后一块是 `updates` 模式时该键不存在）改为 `all_messages`（循环内累计的消息列表），并对兜底分支增加 `logger.warning` 记录便于排查。修复前父 LLM 会一直收到「沙箱子智能体执行完成，但未获取到文本回复。」兜底字符串，修复后能拿到子智能体真实产出。

### 依赖

- `deepagents==0.5.5` — LangChain deepagents 库
- `docker==7.1.0` — Docker SDK for Python

### 沙盒执行前端展示（2026-06-12 新增，2026-06-14 改造）

参考 Kimi "Kimi's Computer" 设计，实现沙盒执行过程的实时前端展示：

**交互流程**（2026-06-14 改造后）：
1. 沙盒开始执行后，AI 聊天气泡的 **timeline.tool 块内**显示 `SubAgentCard` 子智能体折叠卡片（图标、工具名、父 prompt 预览、状态徽章、消息数、耗时）
2. 用户点击子智能体卡片，右侧滑出 `SubAgentDrawer` 详情面板，展示父提问 + 子智能体消息流 + 沙箱摘要 + 沙箱事件时间线
3. 执行完成后，子智能体卡片更新为完成状态

**后端变更**：
- `app/core/tools/SandboxTools.py` 增加 `_extract_sandbox_summary_and_events()` 函数，从子智能体消息流中实时提取摘要和事件
- `tool_progress` 事件增加 `sandbox_summary`（当前步骤、总步骤、进度百分比、状态消息）和 `sandbox_events`（详细事件列表）
- `tool_stop` 事件增加 `final_summary`（完成摘要和结果预览）
- 预定义 5 个执行步骤：生成代码 → 写入文件 → 执行代码 → 获取输出 → 分析结果

**前端组件**（2026-06-14 改造后）：
| 组件 | 文件 | 职责 | 状态 |
|------|------|------|------|
| `SubAgentCard` | `web/Agent/src/components/SubAgentCard.vue` | 通用子智能体折叠卡片（含沙箱）；按 toolCallId 嵌入 `timeline.tool` 块内 | 保留（功能扩展） |
| `SubAgentDrawer` | `web/Agent/src/components/SubAgentDrawer.vue` | 通用子智能体详情 Push Drawer（2026-06-15 精简后不再有沙箱专属 UI 区块）；**支持左侧拖拽调整宽度，宽度记忆在 localStorage** | 保留（功能合并原 SandboxDrawer） |
| `SandboxProgress` | `web/Agent/src/components/SandboxProgress.vue` | ~~聊天气泡中的进度摘要卡片~~ | **2026-06-14 已删除**（被 SubAgentCard 替代） |
| `SandboxDrawer` | `web/Agent/src/components/SandboxDrawer.vue` | ~~右侧 push drawer 沙盒详情面板~~ | **2026-06-14 已删除**（被 SubAgentDrawer 合并） |
| `SandboxEventItem` | `web/Agent/src/components/SandboxEventItem.vue` | ~~单个沙箱事件展示~~ | **2026-06-14 已删除**（被 SubAgentDrawer 内部实现替代） |

**合并原因**：原 `SandboxProgress` 与 `SubAgentCard` 功能重复（均展示沙箱状态/耗时/查看详情入口），且 `SandboxDrawer` 与 `SubAgentDrawer` 数据重叠（`subAgent.events` 已透传 `sandbox_events`，`subAgent.summary` 已合并 `final_summary`），无独立存在价值。

**SubAgentDrawer 模式**：见 "SubAgent 事件协议（2026-06-13 新增，2026-06-14 改造）" 章节。

**前端变更**（2026-06-14 改造）：
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

**2026-06-15 动画交互优化**：
- `web/Agent/src/components/MessageBubble.vue`：
  - 新增 `hasRunningSubAgent` computed：当 `props.subAgents` 中存在 `status === 'running'` 时返回 true
  - 当 `hasRunningSubAgent` 为 true 时，抑制主智能体思考块的 `thinking-pulse`（🧠 图标缩放脉冲）和 `streaming-cursor`（▌ 光标闪动），保留「思考中...」文字与黄色高亮边框
  - 目的：避免用户通过主智能体思考动画来判断子智能体运行状态
- `web/Agent/src/components/SubAgentCard.vue`：
  - `running` 状态的 `.subagent-icon` 增加 `subagentIconBounce` 上下跳动动画（1.2s infinite），直观提示子智能体正在执行
  - `.subagent-status.running` 增加 `statusPulse` 透明度呼吸动画（2s infinite），进一步强化「执行中」状态感知
  - 目的：将视觉焦点从主智能体思考区转移到子智能体工具条上
  - **2026-06-14 修复**：在 `newSession()`（新建任务入口）与 `handleSessionSwitch()`（切换历史会话入口）中显式调用 `closeSubAgentDrawer()`，确保切换/新建会话后上一会话的 `SubAgentDrawer` 详情自动收起，避免抽屉状态残留导致 UI 显示与当前会话不一致（`currentSubAgent.value` 在抽屉 `v-show=false` 后不再被消费，无需额外清空）
  - **2026-06-15 增强**：`SubAgentDrawer` 新增左侧拖拽条，支持用户拖动调整抽屉宽度；宽度记忆在 `localStorage('subagent-drawer-width')`，最小 320px、最大 800px（同时受视口宽度 - 200px 限制），拖拽至 180px 以下自动收起抽屉

### AIMessage 解析兼容性（2026-06-12 修复）

`_extract_sandbox_summary_and_events` 的 AI 消息分支扩展为兼容以下 content 类型，避免 Anthropic Claude / 部分 OpenAI 兼容模型返回的 list[ContentBlock] 时 `code_generation` 事件整体被跳过：

- **`str`** — 原样提取 markdown ``` 代码块
- **`list[ContentBlock]`** — 拼接所有 `type == "text"` 块后再提取（兼容 Anthropic / 部分 OpenAI 兼容模型）
- **`None` / `dict`** — 防御性归一化

实现要点（`app/core/tools/SandboxTools.py`）：
- 新增 `_get_message_text(msg)`：优先用 langchain 内置 `.text` 属性（langchain-core 1.x 自动归一化 str / list[ContentBlock]），缺失时回退 `_extract_text_from_message_content`
- 新增 `_extract_code_blocks_heuristic(text)`：当 AIMessage 文本中**没有 markdown ``` 包裹**时（如 Anthropic Claude 倾向输出原始代码），扫描 Python/Shell 关键字（def/import/print/class/return、echo/if[/fi 等）自动识别代码块
- 新增 `_extract_ai_tool_calls(msg)` + `_ai_tool_call_to_event(tc, step)`：从 AIMessage 中提取 LLM 决策的工具调用（前置事件），覆盖两种来源
  - OpenAI 风格：`msg.tool_calls` 字段
  - Anthropic 风格：`msg.content_blocks` 中 `type == "non_standard"` 嵌套的 `tool_use` 块
  - 工具名优先于 args 字段（`write_file` 即使 input 中无 `content` 也归为 file_write）
- `current_step` 推进：code_generation 完成后推进到 step=2；每多一个 tool_call 再 +1（上限 5）

效果：SandboxDrawer 时间线中**新增** `code_generation` 事件（显示 LLM 生成的代码），与原 ToolMessage 事件并存展示"LLM 决策 → 工具执行"完整链路。

## SubAgent 事件协议（2026-06-13 新增，2026-06-14 改造）

> **目标**：子智能体（sandbox / explore 等）的执行过程在父 AI 聊天气泡中折叠为 `SubAgentCard` 卡片；点击卡片从右侧 push 出 `SubAgentDrawer` 详情面板，展示父提问 + 子智能体内部消息流 + 沙箱摘要 + 沙箱事件时间线（tool='sandbox' 时）。
>
> **2026-06-14 改造**：`SandboxProgress` / `SandboxDrawer` / `SandboxEventItem` 已删除并合并；子智能体卡片从"会话末尾堆放"改为"嵌入 `timeline.tool` 块内按时序渲染"。
> **2026-06-14-2 修复**：`update` 事件（`hitl_check` / `summarize` / `llm_call` 等节点状态）不再落入父气泡"思考过程"区；`update` SSE payload 统一附加 `thread_id`（空字符串）与 `langgraph_node`（节点名）字段，与 `custom` / `message` 事件格式保持一致。

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

| 字段 | 类型 | 出现时机 | 说明 |
|------|------|---------|------|
| `thread_id` | `str` | 全部 | 子 agent 标识（== `tool_call_id`），便于前端按 id 维护 subagent 列表 |
| `parent_prompt` | `str` | `tool_start` | 父 agent 传给子 agent 的 prompt（用于抽屉顶部"父提问"区） |
| `child_messages` | `list[dict]` | `tool_progress` | 子 agent 当前累积的全部 messages，结构化（langchain 对象 → dict） |
| `final_messages` | `list[dict]` | `tool_stop` | tool_stop 时的最终消息快照（结构同 `child_messages`），覆盖到 `messages` 字段 |

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

### 后端改动文件

| 文件 | 改动 |
|------|------|
| `app/core/tools/subagent_message_extractor.py`（**新增**） | `extract_structured_messages(messages)` 把 LangChain BaseMessage 列表转为结构化 dict；兼容 HumanMessage / AIMessage / ToolMessage 及 Mock 后缀；支持 OpenAI `tool_calls` / Anthropic `content[].tool_use` / langchain-core 1.x `content_blocks` 三种 AIMessage tool_call 来源 |
| `app/core/tools/SandboxTools.py` | `tool_start` / `tool_progress` / `tool_stop` / `tool_error` 事件 data 追加 `thread_id` + `parent_prompt` + `child_messages` / `final_messages` |
| `app/core/tools/FilesystemReadTools.py` | 同上；并新增 `all_messages` 累积逻辑（从 `updates` 模式 `node_name.messages` 提取） |
| `app/features/map_agent/router/map_router.py` | `custom` 模式 SSE yield 时在顶层追加 `thread_id` 字段（从 `data.data.thread_id` / `data.tool_call_id` 推导），**老客户端忽略未知字段不破坏**；`updates` 模式同步追加 `thread_id`（空字符串）与 `langgraph_node`（节点名）字段，统一 SSE 格式 |
| `app/core/tools/events.py` | 注释追加新字段文档（实现不动） |
| `app/tests/core/tools/test_subagent_message_extractor.py`（**新增**） | 22 个 pytest 用例：role 分类 / content 归一化 / 三种 tool_call 来源 / 边界条件 |

### 前端改动文件

**2026-06-14-2 修复**：

| 文件 | 改动 |
|------|------|
| `web/Agent/src/utils/sseParser.js` | `processSSEEvent` 的 `update` case 显式跳过 `hitl_check` 节点；`isSubAgentMessage` 增加 `metadata.lc_agent_name` / `metadata.langgraph_node` 多维度判定，防御 tool_start 与 message 到达顺序抖动的 race condition；调用点同步透传 metadata |
| `web/Agent/src/utils/__tests__/subAgentParser.test.js` | 新增 6 个用例：`hitl_check` update 不进入 thinking / timeline；`isSubAgentMessage` 通过 `lc_agent_name` / `langgraph_node` 识别子智能体；`message` 事件在 `lc_agent_name=sandbox` 时不写入父气泡 |

**2026-06-14 改造**：删除 `SandboxProgress` / `SandboxDrawer` / `SandboxEventItem` 三个组件并合并功能到 SubAgent 体系。

| 文件 | 改动 |
|------|------|
| `web/Agent/src/utils/sseParser.js` | `createAiMessage()` 移除 `sandboxExecution: null` 字段；`processSSEEvent` 的 `custom` case 删除 `if (customToolData.tool === 'sandbox')` 块；`updateSubAgentFromCustomEvent` 增强：tool_start/tool_progress 合并 `sandbox_summary` 到 `subAgent.summary`，tool_stop 合并 `final_summary`；**新增导出** `SUBAGENT_TOOLS` 集合与 `isSubAgentTool(tool)` 工具函数，供 MessageBubble 判断子智能体类型 |
| `web/Agent/src/components/SubAgentDrawer.vue` | 2026-06-14 集成沙箱摘要 + 沙箱事件时间线（**2026-06-15 再次精简后整段已删除**）；`renderMessageContent` 扩展 LangChain 0.3+ `tool_use` / `tool_result` ContentBlock 支持 |
| `web/Agent/src/components/MessageBubble.vue` | 移除 `sandboxExecution` prop；`timeline.tool` 块移除 `sandboxExecution` 条件分支；新增 `extractToolCallId()` / `toolSubAgentMap` / `getSubAgentsForGroup()`：按 `toolCallId` 在 `group.items` 中查找匹配 subAgent 渲染 `SubAgentCard`；移除 timeline 之外的 `subagent-cards` 容器；**2026-06-14 再改造**：新增 `isSubAgentItem()` / `getNonSubAgentItems()` 函数；`timeline.tool` 块的 `tools-header` / `tools-body` 仅在「存在非子智能体项目」时渲染，count 与 body 只展示普通工具调用；subagent 仅通过 SubAgentCard 折叠卡展示，避免消息在「工具调用」与「div」双重渲染 |
| `web/Agent/src/components/ChatArea.vue` | 移除 `sandbox-execution` prop 透传；移除 `open-sandbox-drawer` 事件 |
| `web/Agent/src/App.vue` | 移除 `SandboxDrawer` import + 模板；移除 `sandboxDrawerVisible` / `currentSandboxEvents` / `currentSandboxSummary` / `currentSandboxStatus` 状态；移除 `openSandboxDrawer` / `closeSandboxDrawer` 函数；移除 `sandboxExecution` 自动关闭 watch |
| `web/Agent/src/components/SandboxProgress.vue` | **删除**（被 SubAgentCard 替代） |
| `web/Agent/src/components/SandboxDrawer.vue` | **删除**（被 SubAgentDrawer 合并） |
| `web/Agent/src/components/SandboxEventItem.vue` | **删除**（被 SubAgentDrawer 内部实现替代） |
| `web/Agent/src/components/__tests__/SubAgentCard.spec.js` | 新增 2 个用例：sandbox 类子智能体的 summary 字段不破坏卡片渲染；parentPrompt 缺失时仅展示核心字段 |
| `web/Agent/src/components/__tests__/SubAgentDrawer.spec.js` | 新增 6 个用例：tool=sandbox + summary 展示沙箱摘要、tool=sandbox + events 展示沙箱事件区、tool=非 sandbox 不展示沙箱区、沙箱事件可折叠、AIMessage.content 为 LangChain 0.3+ list[ContentBlock] 渲染、AIMessage.content 包含 thinking 块渲染 |
| `web/Agent/src/components/__tests__/MessageBubble.spec.js`（**新增**） | 5 个用例：timeline.tool 内按 toolCallId 渲染 SubAgentCard、timeline 外不再有 subagent-cards 容器、点击 SubAgentCard 触发 open-subagent-drawer、无匹配 subAgent 时不渲染、多 subAgent 数据驱动 |
| `web/Agent/src/utils/__tests__/subAgentParser.test.js` | 新增 2 个用例：tool_progress 携带 sandbox_summary 时合并到 subAgent.summary；tool_stop 携带 final_summary 时合并到 subAgent.summary（最终态） |

**2026-06-14 第三次去重（跨 timeline group 唯一渲染）**：同一次子智能体执行（同一 `toolCallId`）的 `custom` 事件（tool_start / tool_progress×N / tool_stop）被 `thinking` / `text` 事件隔开后，`mergedTimeline` 会拆为多个独立 `tool` group，每个 group 都会渲染一张重复的 `SubAgentCard`。

- `web/Agent/src/components/MessageBubble.vue`：
  - **新增** `subAgentsByGroup` computed：对 `mergedTimeline` 做一次完整扫描，在 group 维度上"每个 toolCallId 仅首次出现"返回 subAgent 列表（返回与 mergedTimeline 等长的二维数组）
  - **重构** `getSubAgentsForGroup(group)`：从普通函数 + 组件级 Set 改为基于 `subAgentsByGroup` 索引查找的兼容层（同名同语义，模板无需改动）
  - **设计权衡**：用 computed 而非普通函数 + 组件级 Set 的原因是 Vue 3 mount 阶段会多次调用 render function，普通函数内部用 Set 记录"已渲染"会在 mount 内的连续 render 间互相污染（同一组数据在第二次 render 时被错误地判定为"已渲染过"而跳过）；computed 由 Vue 缓存，仅在依赖（`mergedTimeline` / `props.subAgents`）变化时重算，多次 render 期间返回同一结果；计算内部用本地 Set（每次重算时新建），天然避免跨 render 污染
- `web/Agent/src/components/__tests__/MessageBubble.spec.js`：新增 3 个用例（同 id 跨多个 tool group 只渲染 1 张 / 不同 id 各自独立 / 全部去重后空 group 不渲染）
- `SubAgentDrawer` 不受影响（数据源 `subAgent.messages` 由 sseParser 持续累积，与 timeline 渲染解耦）

### 第三方调用兼容保证

`/api/map/chat` SSE 接口有第三方 iframe/portal 调用，本改造**仅新增字段**，不修改/删除既有字段：

- SSE 事件类型 `update` / `custom` / `message` / `end` / `error` / `interrupt` / `tool_stop` **不变**
- `custom` 事件 `data` 字典内仅**追加** `thread_id` / `parent_prompt` / `child_messages` / `final_messages` 字段
- SSE 顶层 `{type, data}` **追加** `thread_id` 字段
- `update` 事件顶层追加 `langgraph_node` 字段（节点名），`thread_id` 统一为空字符串（updates 模式下无法精确获取子线程 ID，仅用于格式统一）
- 老客户端标准 JSON 解析**忽略未知字段**，行为不变

### 历史消息 subAgents 字段

当前后端 `fetchSessionMessages` 不持久化 subagent 元数据。**还原历史时 `subAgents = []`**（Out of Scope，后续 PR 处理 Checkpoint 持久化）。

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
| `login.html` | `LoginView`（`src/login-main.js`） | `/login` | 登录页统一入口（`App.vue` / `PortalApp.vue` 不再内联渲染 `LoginView`；由 `/login` 唯一承载） |

三个入口共享 `src/components`、`src/utils`、`src/styles`，构建后产出三个独立的 JS Chunk。

### 组件清单（src/components）

- **根组件**：`App.vue`（主）、`KnowledgeApp.vue`（知识库）、`PortalApp.vue`（门户）、`KnowledgePage.vue`（旧版，被 `KnowledgeApp.vue` 替代，仍保留以兼容旧引用）
- **登录入口**：`login.html` + `src/login-main.js`（独立 Vite 入口；承载 `LoginView`；由 `redirectToLogin()` 跳到 `/login?redirect=...` 统一访问）
- **聊天**：`ChatArea.vue`、`InputBox.vue`、`MessageBubble.vue`、`SkillTags.vue`、`HumanApprovalBox.vue`、`TopBar.vue`
- **文件**：`FileList.vue`、`FilePreview.vue`、`FolderTree.vue`、`FileManagerModal.vue`
- **知识库**：`KnowledgeChat.vue`、`ProfileInputBox.vue`
- **公共**：`Sidebar.vue`、`HelloWorld.vue`、`UserSettingsDialog.vue`
- **Subagent 折叠与抽屉（2026-06-13 新增，2026-06-14 改造）**：
  - `SubAgentCard.vue`：通用子智能体折叠卡片（含沙箱），**2026-06-14 改造后挂在父 AI 气泡的 `timeline.tool` 块内**（按 toolCallId 匹配，遵循事件流时序，不再堆在会话末尾）；工具图标 + 父 prompt 预览 + 状态徽章 + 耗时 + 消息数 + "查看详情" 入口；点击 emit('click', subAgent)
  - `SubAgentDrawer.vue`：通用子智能体详情 Push Drawer；**2026-06-14 改造合并原 `SandboxDrawer` 职责**（`SandboxProgress` / `SandboxDrawer` / `SandboxEventItem` 三个组件已删除），沙箱专属摘要与事件时间线 **2026-06-15 再次精简后整段移除**；分层展示父 prompt / HumanMessage / AIMessage（含 tool_calls 决策区） / ToolMessage 三类消息 + 底部耗时/消息数/工具调用次数摘要；`renderMessageContent` 扩展支持 LangChain 0.3+ 多模态 ContentBlock（text / thinking / tool_use / tool_result）
- **普通工具卡片（2026-06-15 新增）**：
  - `ToolCallCard.vue`：普通（非 subagent）工具调用专属卡片，与 `SubAgentCard` 视觉风格对齐；**关键差异：不触发抽屉**（普通工具没有子智能体消息流），body 以"步骤"形式逐步展示每条 SSE 事件（tool_start / tool_progress / tool_stop / tool_error）；头部扳手图标在 `status='running'` 时使用 SubAgentCard 同款 `subagentIconBounce` 闪动动画；默认 `running` 展开、`success/error` 折叠
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
- **登录页统一入口**：`/login`（独立 HTML 入口，由 `vite.config.js` 多入口构建；`nginx.conf` 通过 `location /login { try_files ... /login.html; }` 路由）。
  - 由 `web/Agent/src/login-main.js` 启动，挂载 `LoginView`，监听 `login-success` 事件并按 `?redirect=` 回跳。
  - `App.vue`（`/Agent/`）与 `PortalApp.vue`（`/portal`）**不**再渲染 `LoginView` / `RegisterView`；未登录时统一通过 `redirectToLogin()` 跳到 `/login?redirect=<原页面>`。
  - `auth.js#isAlreadyOnLoginPage()` 把 `/login` 视为登录页（`buildLoginUrl` 默认目标）。
- **PortalApp 登录页归属**：`PortalApp.vue`（`/portal` 入口）**不**渲染 `LoginView`；未登录时只通过 `redirectToLogin()` 跳转到 `/login?redirect=/portal`，由 `/login` 入口统一渲染登录页。
  - 原因：避免在 `/portal` 短暂渲染 `LoginView` 触发 `/api/auth/captcha` 后被浏览器取消（造成"captcha 调两次，第一次失败"），以及避免"登录页闪烁两次"。
  - `PortalApp.checkAuth` 失败路径**不**置 `authReady.value = true`；只有成功路径（已登录）才置 `authReady=true`，让 Vue 渲染门户导航栏。
- **App.vue 不再渲染 LoginView**：`App.vue`（`/Agent/` 入口）同样**不**渲染 `LoginView` / `RegisterView`；未登录时通过 `redirectToLogin()` 跳到 `/login?redirect=/Agent/`。这样消除了"`auth-loading-screen` 占位 → `LoginView`"的一次视觉切换。
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
  - `subAgentParser.test.js`（2026-06-13 新增，2026-06-14 扩展）：subagent 解析（custom 事件维护 subAgents 列表 + sandbox_summary 合并 + 工具函数，**14** 用例）
  - `SubAgentCard.spec.js`（2026-06-13 新增，2026-06-14 扩展）：折叠卡片（**11** 用例）
  - `SubAgentDrawer.spec.js`（2026-06-13 新增，2026-06-14 扩展，2026-06-15 精简）：独立 Push Drawer（**19** 用例）
  - `MessageBubble.spec.js`（**2026-06-14 新增**）：timeline.tool 内按 toolCallId 渲染 SubAgentCard 等（5 用例）
- **项目历史**：后端 17/17 + 前端 73/73 全部通过（参见 "HITL 流程" 章节）
- **2026-06-13 更新**：后端新增 `test_subagent_message_extractor.py` 22 用例通过；前端 SubAgentCard/SubAgentDrawer/subAgentParser 共 29 用例通过；累计前端 111/111 全量通过
- **2026-06-14 更新**：合并沙箱执行与子智能体展示，删除 `SandboxProgress` / `SandboxDrawer` / `SandboxEventItem` 三个组件；新增 `MessageBubble.spec.js`（5 用例）+ 扩展 `SubAgentCard`（+2）、`SubAgentDrawer`（+6）、`subAgentParser`（+2）；累计 **126/126** 全量通过（Vite build 成功）
- **2026-06-14 二次精简**：`SubAgentDrawer.vue` 沙箱摘要区（`.drawer-summary`）移除 `.summary-progress` 进度条 div（含 `progress-track` / `progress-fill` / 步骤计数 `X/Y`），保留状态指示（`.summary-status`）与耗时展示（`.summary-time`）；同步清理 3 个 unused computed（`sandboxProgressPercent` / `sandboxCurrentStep` / `sandboxTotalSteps`）与对应 CSS（`.summary-progress` / `.progress-track` / `.progress-fill` / `.progress-text` / `@keyframes progressPulse`）；`SubAgentDrawer.spec.js` 摘要区测试用例由「`3/6` 进度文本」改为「进度条不存在 + 耗时文本存在」；累计 **129/129** 全量通过（Vite build 成功）
- **2026-06-14 再更新**：subagent 工具调用不在「工具调用」块内重复展示；`MessageBubble.vue` 导出 `isSubAgentTool` 工具，新增 `isSubAgentItem` / `getNonSubAgentItems` 过滤逻辑；`MessageBubble.spec.js` 扩展 +3 用例（全 subagent / 混合 / 全普通）；累计 **129/129** 全量通过（Vite build 成功）
- **2026-06-14 第三次去重**：`MessageBubble.vue` 新增 `subAgentsByGroup` computed + 重构 `getSubAgentsForGroup`（基于 `mergedTimeline` 索引查找），保证同一 `toolCallId` 在跨多个 `tool` group 时仅首次渲染 `SubAgentCard`，后续 group 中同 id 直接跳过；`MessageBubble.spec.js` 新增 3 个用例（同 id 跨 group 只 1 张 / 不同 id 独立 / 全部去重后空 group 不渲染）；累计 **132/132** 全量通过（Vite build 成功）
- **2026-06-15 第三次精简**：`SubAgentDrawer.vue` 整段移除"沙箱执行摘要"区块（`.drawer-summary` + `.summary-status` + `.status-indicator` + `.summary-time` + `@keyframes statusBlink`），含 5 行模板注释；同步删除 `isSandbox` / `sandboxSummary` / `sandboxElapsedMs` 三个仅被该 div 使用的 computed；`SubAgentDrawer.spec.js` 删除 2 个针对该 div 的用例（sandbox summary 存在/非 sandbox 不展示）；`sseParser.js` 透传 `sandbox_summary` / `sandbox_events` 数据保持不变（移除的是展示，数据仍由前端接收便于后续扩展）；累计 **154/154** 全量通过（Vite build 成功；含 SubAgentDrawer.spec.js 19 用例）
- **2026-06-15 第四次：普通工具卡片 (ToolCallCard) 改造**：
  - **新增** `web/Agent/src/components/ToolCallCard.vue`：普通工具调用专属卡片，与 `SubAgentCard` 视觉风格对齐（共用 `.subagent-card` / `.subagent-row` / `.subagent-icon-running` 动画与状态色），关键差异是 **不触发抽屉**（普通工具没有子智能体消息流），body 以"步骤"形式逐步展示每条 SSE 事件（tool_start / tool_progress / tool_stop / tool_error），头部扳手图标在 `running` 状态使用 SubAgentCard 同款 `subagentIconBounce` 闪动动画；默认 `running` 展开、`success/error` 折叠；时间戳 `* 1000` 转换（sseParser 透传的 timestamp 为秒单位）；提供 `dataToEntries` / `progressSummary` / `startSummary` / `stopSummary` / `errorSummary` 五个摘要工具函数把每条事件 data 转为可读字符串
  - **修改** `web/Agent/src/components/MessageBubble.vue`：
    - `import ToolCallCard from './ToolCallCard.vue'`
    - 新增 `getToolCardGroups(items)` helper：按 `toolCallId` 把非 subagent 事件分组，缺失 toolCallId 时按出现顺序合成 `__auto_N` 唯一 id
    - `timeline.tool` 分支改造：用 `<ToolCallCard v-for=...>` 替换原 `tools-header` (N) + `tools-body` JSON 列表；SubAgentCard 路径（`timeline-subagent-list`）保持不变
    - 降级模式（历史消息回放，无 timeline）同步改造：原 `tools-section` 改用 `getToolCardGroups(tools)` + `timeline-toolcard-list`
    - CSS 新增 `.timeline-toolcard-list { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; align-items: flex-end; }`（与 `.timeline-subagent-list` 风格一致）
    - 旧 `isToolsExpanded` / `toggleTools` / `formatToolItem` / `getNonSubAgentItems` 函数保留（不再被模板使用，但删除为破坏性改动，留作 dead-code 备用）
  - **新增** `web/Agent/src/components/__tests__/ToolCallCard.spec.js`：**23** 用例，覆盖 importable / 工具名+步骤数 / 状态徽章 (running / success / error / tool_stop非success退error) / 扳手动画 class / 默认展开折叠 / 点击切换 / 步骤渲染（时间戳+类型徽章+摘要+乱序追加）/ error 摘要 / 缺失 timestamp 占位 / 抽屉事件守卫 / 空 events / startTime+endTime 耗时 / 多事件合并到一张卡
  - **更新** `web/Agent/src/components/__tests__/MessageBubble.spec.js`：3 个老用例迁移（`tools-header` 断言改为 `tool-call-card` 数量断言；SubAgentCard 选择器用 `.subagent-card.clickable` 区分避免 ToolCallCard 复用 `.subagent-card` class 造成选择器冲突）；新增 3 个 ToolCallCard 集成测试
  - 累计 **183/183** 全量通过（Vite build 成功）
- **2026-06-15 第五次：ToolCallCard bug 修复 + 样式解耦**（用户反馈普通工具弹出智能体卡片）：
  - **Bug 修复（核心）**：`MessageBubble.vue` 的 `subAgentsByGroup` computed **未过滤非 subagent 工具事件**，导致 `sseParser.updateSubAgentFromCustomEvent` 对所有 tool 名都创建 subAgents 条目（含普通工具），普通工具（如「生成报告」）会被 `getSubAgentsForGroup` 按 toolCallId 匹配并渲染为 `SubAgentCard`，点击触发 `SubAgentDrawer`。修复：在 `subAgentsByGroup` 循环中增加 `if (!isSubAgentItem(item)) continue` 过滤（判断 `item.data.tool` 是否属于 SUBAGENT_TOOLS），仅 subagent 工具（sandbox / explore）才走 SubAgentCard 路径
  - **样式解耦**：ToolCallCard 重写为完全独立 class `.tool-call-card`（不再复用 `.subagent-card`，避免选择器冲突）：
    - 头部 SVG 扳手图标（独立设计，与 SubAgentCard 的 emoji 区分）
    - 显式「**普通工具**」蓝色徽章（`.tool-call-badge`）+ tooltip「普通工具（非子智能体）」，与 SubAgentCard（无此徽章）一眼可辨
    - 状态色：running=accent 蓝、success=**accent 蓝**（不是 SubAgentCard 的 success 绿色）、error=红
    - 步骤行单行紧凑：时间戳 + 类型徽章 + 摘要 + 详情切换按钮；**key-value 详情默认折叠**，点击单条步骤可展开（`.tool-step-detail` 内含完整 key-value 表格）
  - **新增** 测试用例（**+10 用例 → 193/193 全量通过**）：
    - `MessageBubble.spec.js` 新增 `MessageBubble 普通工具不被误渲染为 SubAgentCard（2026-06-15 修复）` 描述块 3 个回归测试：普通工具事件不应渲染 SubAgentCard / subagent 工具正常渲染 / 混合场景分别渲染
    - `ToolCallCard.spec.js` 新增 5 个测试：「普通工具」徽章存在性 + title 属性 / 头部 SVG 扳手图标（独立图标）/ 独立 class `.tool-call-card`（不复用 `.subagent-card`）/ success 状态用蓝色（与 SubAgentCard 绿色区分）/ 步骤默认不显示 key-value 详情 / 点击步骤行可展开折叠 key-value 详情 / 展开后展示 key-value 字段
  - 累计 **193/193** 全量通过（Vite build 成功）
- **2026-06-15 第六次：ToolCallCard 样式微调**（用户反馈完成态颜色 + 步骤分隔 + 文案）：
  - **完成态颜色统一**：将 `.tool-call-card.success` / `.tool-call-status.success` 的边框与文字色从蓝色（accent）改为**绿色 #10b981**（`.tool-call-card.success` 背景也加上 `rgba(16, 185, 129, 0.04)` 浅绿渐变），与 `SubAgentCard` 完成态保持视觉一致；running 仍为蓝色，error 仍为红色
  - **步骤行间横线分隔**：每个 `.tool-step` 增加 `border-bottom: 1px dashed rgba(0, 0, 0, 0.08)`；最后一步通过 `.tool-step:last-child { border-bottom: none; }` 取消分隔（避免视觉割裂）；padding 微调 3px→4px 让分隔线更透气
  - **文案调整**：`typeLabel` 中 `tool_progress` 从「进度」改为「**进行中**」（与状态徽章「执行中」语义区分：徽章是状态，行徽章是事件类型）
  - **新增** 1 个测试 → **194/194** 全量通过：步骤行间用横线分隔（验证 DOM 兄弟节点关系 + 最后一步不显示分隔）；原"成功用蓝色"测试改为"成功用绿色"；步骤渲染测试断言"进行中"文案
- **2026-06-15 第七次：知识库页面接入子智能体卡片**（用户反馈"调用 explore 但是没有出现子智能体卡片"）：
  - **复用策略**：本次**全部复用主聊天页已有组件**（`SubAgentCard` / `SubAgentDrawer` / `MessageBubble` 的 `sub-agents`/`download-info` props 与 `open-subagent-drawer` emit），仅做"接线"工作，零重写
  - **`KnowledgeChat.vue`（Tab 版聊天组件）**：
    - `defineEmits` 数组追加 `'open-subagent-drawer'`
    - `<MessageBubble>` 模板尾部追加 `:download-info="message.downloadInfo"` + `:sub-agents="message.subAgents"` + `@open-subagent-drawer="(sa) => emit('open-subagent-drawer', sa)"`
  - **`KnowledgePage.vue`（Tab 版中间层）**：
    - `defineEmits` 数组追加 `'open-subagent-drawer'`
    - `<KnowledgeChat>` 模板追加 `@open-subagent-drawer="(sa) => emit('open-subagent-drawer', sa)"` 向上冒泡
  - **`App.vue`（主应用根）**：`<KnowledgePage>` 模板追加 `@open-subagent-drawer="openSubAgentDrawer"`，直接复用第 360-364 行已有的 `openSubAgentDrawer` 函数 + 顶层 `<SubAgentDrawer>`（第 595-599 行）；**Tab 版知识库页不需自持抽屉状态**
  - **`KnowledgeApp.vue`（独立 SPA）**：因不在 App.vue 渲染树内，必须自持：
    - 顶部追加 `import SubAgentDrawer from './components/SubAgentDrawer.vue'`（复用主聊天页组件）
    - 新增 `subAgentDrawerVisible` / `currentSubAgent` 响应式状态（与 App.vue 同模式）
    - 新增 `openSubAgentDrawer(subAgent)` / `closeSubAgentDrawer()` 函数
    - `<MessageBubble>` 模板追加 `:download-info` + `:sub-agents` + `@open-subagent-drawer="openSubAgentDrawer"`
    - 模板底部（`</main>` 之后）渲染 `<SubAgentDrawer>`（与 App.vue 同款 props/emits）
  - **测试同步**（按 HARD RULE 新增 3 个测试文件，**+12 用例 → 206/206 全量通过**）：
    - `web/Agent/src/components/__tests__/KnowledgeChat.spec.js`（4 用例）：组件 importable / subAgents prop 透传 / downloadInfo prop 透传 / open-subagent-drawer 事件冒泡
    - `web/Agent/src/components/__tests__/KnowledgePage.spec.js`（2 用例）：组件 importable / KnowledgeChat emit 向上冒泡
    - `web/Agent/src/KnowledgeApp.spec.js`（5 用例）：组件 importable / SubAgentDrawer stub 在 DOM / openSubAgentDrawer 切换 DOM / closeSubAgentDrawer 重置 / 监听 drawer @close 事件
  - **关键技术点**：
    - KnowledgeChat 的 `messages` 是**内部 `reactive([])`** 而非 prop（与 ChatArea 不同），测试需通过 `wrapper.vm.messages.push(...)` 注入
    - KnowledgeApp 的 `onMounted` 会调用 `fetchKnowledgeFiles` / `createNewSession` / `validateToken` / `refreshToken`，测试需 `vi.mock('./utils/api.js')` 与 `vi.mock('./utils/auth.js')` 隔离副作用
    - MessageBubble 子组件在测试中以 stub 形式呈现（template 暴露所有 props 为 DOM），便于通过 DOM 查询断言透传

## CI 测试（pytest + GitHub Actions）

### 后端测试目录（`app/tests/`）

- **配置**：`app/pytest.ini`（`testpaths = tests`、`addopts = -v --tb=short`）
- **基础设施**：`app/tests/conftest.py` 与 `app/tests/shared/conftest.py`
  - 在收集阶段 autouse mock 外部依赖：`asyncpg`、`langchain.*`、`langgraph.*`、`docx.*`、`aiofiles`、`pypdf`、`pymupdf`、`deepagents.*`、`mcpClient.*`、`sse_starlette`、`markitdown`、`unstructured` 等
  - 对 `docx.enum`、`docx.shared`、`docx.oxml` 等子包使用 `types.ModuleType` + `__path__` 注入，保证 `from docx.enum.section import WD_SECTION_START` 等子模块导入可用
  - 对 `langgraph.types.Command`、`langgraph.prebuilt.ToolNode`、`langgraph.graph.MessagesState/StateGraph/START/END` 等提供 `Mock` 或自定义 `_Command` 类
  - 在 `app` fixture 中 patch `typing._type_check`，遇到带 `_mock_name` 属性的对象直接跳过原始类型检查，避免 `Optional[Mock]`、`Union[AgentState, LGCommand]` 等注解触发 SyntaxError
  - 提供 fixtures：`app`（session 级 FastAPI 实例）、`client`（function 级 TestClient）、`jwt_auth`、`admin_token`/`user_token`/`admin_headers`/`user_headers`

### 测试覆盖

- **`tests/core/`**：核心模块（config、database、server、prompts、agent_context、dependencies）
- **`tests/core/tools/`**：HITL 工具、BaseTools、MCP 适配器
- **`tests/shared/`**：auth_router、file_router、session_router、user_router、user_db、session_db、refresh_token_db、portal_refresh_token_db、captcha、safety、DocumentLoader
- **`tests/features/*/`**：9 个 Agent 冒烟测试（config 可导入、提示词非空、tools 可导入、router 已注册到 `/api/*` 路径）
- **`tests/features/sandbox_agent/`**：沙箱 Agent 专项测试
  - `test_docker_backend.py`：DockerSandboxBackend 容器生命周期、命令执行、文件操作、异常处理
- **`tests/integration/`**：端到端认证流程（注册→登录→validate→logout）

### Mock 策略

- **不引入真实 PostgreSQL / 真实 LLM / 真实文件系统**，全部内存 + Mock
- 数据库：`AUTH_STORAGE_MODE=memory` + `UserDB._memory_users`、`SessionDB` 内存字典
- LLM：所有 `langchain_*.Chat*`、`init_chat_model` 均为 `Mock`
- 文件系统：`pypdf`、`PyMuPDF`、`docx`、`PIL`、`numpy` 均为 `Mock` 或 `ModuleType`
- `app/main.py::register_routers(target_app=None)`：支持在测试中注入 test app 实例，避免依赖全局 `app`

### CI 工作流（`.github/workflows/pr-check.yml`）

- **触发**：`pull_request` 与 `push` 到 `main` / `preview` 分支
- **Jobs**：
  - `backend-test`：`ubuntu-latest` + `actions/setup-python@v5`（Python 3.11，`cache: pip`）→ `pip install -r app/requirements.txt` → `pytest --tb=short -q`
  - `frontend-test`：`ubuntu-latest` + `actions/setup-node@v4`（Node 20，`cache: npm`）→ `npm ci` → `npm run test`（vitest）
  - `docker-build-check`：`ubuntu-latest` + `docker/setup-buildx-action@v3` + `docker/build-push-action@v5` 构建 `app/Dockerfile` 与 `web/Agent/Dockerfile`，不 push
- **缓存**：pip 与 npm 均启用 GHA 缓存加速

### 验证结果

- **本地全量**：`cd app && python -m pytest tests/ -v --tb=short` → **130 passed**（2026-06-08）
- **2026-06-15 新增**：`app/tests/core/tools/test_sandbox_no_text_reply_fix.py`（2 个 P0 用例）
  - `test_sandbox_returns_last_ai_text_when_last_chunk_is_updates_mode`：核心修复回归测试，覆盖用户报告的「最后一块是 updates 模式导致兜底」场景
  - `test_sandbox_returns_fallback_when_no_ai_message_in_all_messages`：边界测试，覆盖「子智能体无 AI 文本产出」时兜底 + logger.warning 触发
- **本地 core/tools 子集**：`pytest app/tests/core/tools/ -v` → **105 passed**（2026-06-15，含新增 2 用例）
- **CI 期望**：与本地一致，所有用例通过

### 已知工程实践

- **TestClient.delete() 不支持 `data` / `json` 关键字**：Starlette `TestClient.delete` 显式仅暴露 `params`、`headers`、`cookies` 等；如需发送 JSON body，应改用 `client.request("DELETE", url, headers=..., json=...)`（参见 `app/tests/shared/test_file_router.py::test_delete_files`）
- **PortalRefreshTokenDB 仅暴露物理删除**：使用 `delete_token(token_hash)`，不存在 `revoke_token`（参见 `app/tests/shared/test_portal_refresh_token_db.py`）

