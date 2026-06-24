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

## 数据目录约定（2026-06-19 重构）

运行时数据目录位于**项目根**（非 `app/` 内），便于与代码解耦并避免被打入 Docker 镜像。

```
data/                          # 项目根运行时数据目录（原 app/data）
├── Knowledge/                 # 知识库数据（地图 Agent）
│   ├── metadata.json
│   ├── sync_metadata.py
│   └── tmp/                   # 临时缓存（doc 转换、large_tool_results）
├── upload/                    # 用户上传原文件（按日期 + session_id 分目录）
│   ├── session_index.json     # session_id -> 日期目录的映射索引
│   └── yyyy/mm/dd/{session_id}/
├── tmp/                       # 上传文件的 .md 转换结果（与 upload 平行）
│   └── upload/yyyy/mm/dd/{session_id}/
├── download/                  # 用户下载文件（按 session_id 分目录）
├── upload_chunks/             # 分片上传临时目录（按 file_id 分目录）
└── demonstration/download/    # 演示模式专用下载目录
```

### 关键变更

- **Session 路径管理器**：新增 `app/shared/utils/files/session_path_manager.py`
  - 所有 `data/upload` 与 `data/tmp/upload` 路径统一通过该模块解析。
  - 目录按 `yyyy/mm/dd/{session_id}` 组织，并通过 `data/upload/session_index.json` 维护 session 到日期的索引。
  - `register_session_upload_date(session_id)` 在创建 session 时调用；`remove_session_upload_date(session_id)` 在清理时调用。
  - 兼容旧路径：若找不到索引，会回退到 `data/upload/{session_id}` 查找。
- **路径常量**（统一改为相对项目根，并通过 `session_path_manager` 解析）：
  - `app/core/router/file_upload_router.py`：`UPLOAD_DIR` 已废弃，改为 `spm.get_session_upload_dir(session_id, create=True)` 与 `spm.get_session_tmp_upload_dir(session_id, create=True)`。
  - `app/core/router/file_download_router.py`：`DOWNLOAD_DIR = Path("data/download")`（未变更）
  - `app/shared/utils/files/fileTransfer.py` / `file_upload_handler.py` / `pdfToImage.py` / `FilesystemReadTools.py` / `SandboxTools.py`：统一使用 `session_path_manager` 获取日期化路径。
- **文件上传与原文件保留**：
  - 原文件保存到 `data/upload/yyyy/mm/dd/{session_id}/{filename}`。
  - `DocumentLoader` / `MinerU` 转换后的 `.md` 保存到 `data/tmp/upload/yyyy/mm/dd/{session_id}/{filename}.md`。
- **子智能体工作空间保持源目录**：
  - `app/core/tools/FilesystemReadTools.py`：`root_path = get_session_upload_dir(session_id, create=True)`，explore 子智能体在 `data/upload/...` 下搜索/列出原文件。
  - `app/core/tools/SandboxTools.py`：`workspace = get_session_upload_dir(session_id, create=True)`，沙箱挂载点同样指向原文件目录。
- **read 重定向补丁**：`app/shared/tools/middleware/filesystem_encoding_fix.py`
  - 对 `deepagents.backends.filesystem.FilesystemBackend.read` 打 monkey patch。
  - 读取时先把路径按 `self.cwd` 解析为绝对路径；若路径在 `data/` 下且不在 `data/tmp/` 下，映射到 `data/tmp/` 下对应位置（避免重复映射）。
  - 将扩展名统一替换为 `.md`；目标 `.md` 不存在时不回退，返回 not found（错误信息使用原始路径）。
  - **非文本文件 base64 适配（2026-06-22）**：当原始文件扩展名为 `.pdf`、`.png`、`.mp4` 等非文本类型时，`deepagents` 的 `FilesystemMiddleware` 会把 `read_result` 的 `content` 直接作为 base64 字段传入多模态 content block。由于实际读取的是 `.md` 纯文本，补丁会在返回前将文本进行 base64 编码，并将 `FileData.encoding` 设为 `"base64"`，从而避免 LLM API 报 "pdf base64 data is invalid" 等参数校验错误。
- **Knowledge 目录**：`app/routers/knowledge_router.py` 中 `_PROJECT_ROOT` 使用 3 次 `os.path.dirname`（新文件位于 `app/routers/` 下，3 次到项目根）
- **Knowledge 元数据路径迁移（2026-06-20）**：
  - `KNOWLEDGE_DIR = data/Knowledge/`（**不变**，query_knowledge 子智能体扫描的真实知识库根目录）
  - `METADATA_FILE = data/tmp/Knowledge/metadata.json`（**迁移**，与 `large_tool_results/` 同级存放，避免污染真实知识库目录）
  - `TMP_DIR = KNOWLEDGE_DIR`（**回退**，消除冗余的 `/tmp` 子路径）
  - 影响：`/api/map/knowledge/files` 读取 `data/tmp/Knowledge/metadata.json`；`/api/map/knowledge/file-download` / `file-preview` 仍按 `KNOWLEDGE_DIR` 解析相对路径；`/api/map/knowledge-chat` 通过 `TMP_DIR` 注入 `knowledge_root`，仍指向真实知识库根
- **审计/地图工具**：`app/features/audit_document_agent/tools/tools.py`、`app/shared/tools/skills/map_agent/MapTools.py`（2026-06-24 从 `app/features/map_agent/tools/MapTools.py` 迁移）、`app/features/Tagent/Tagent.py` 等同步更新
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
│   ├── skills/             # Skill 系统（schema / 加载 / 提示词渲染 / bootstrap / prompt 构造 / load_skill 工具）
│   │   ├── schemas.py      # SkillInfo / SkillsConfig Pydantic 模型
│   │   ├── loader.py       # SkillDiscovery：扫描并解析 SKILL.md
│   │   ├── prompt.py       # render_available_skills_block：渲染 <available_skills> XML 块
│   │   ├── service.py      # SkillsService：skill 注册中心（全局单例 + agent 维度多实例）
│   │   ├── bootstrap.py    # BootstrapProvider：按优先级读取 bootstrap.md 并包裹 <EXTREMELY_IMPORTANT>
│   │   ├── message_transformer.py  # SkillsAwarePrompt：构造含 bootstrap + available_skills 的系统提示词
│   │   ├── tool.py         # load_skill：LangChain @tool 装饰的 skill 加载工具
│   │   └── __init__.py     # 包初始化
│   ├── tools/              # 工具基类和 MCP 适配器
│   └── router.py           # 核心路由（文件上传/下载）
├── features/               # 功能模块（各 Agent）
│   ├── contract_host_agent/    # 合同主办 Agent
│   ├── contract_document_agent/ # 合同文档 Agent
│   ├── contract_approval_agent/ # 合同审批 Agent
│   ├── DevOps_agent/           # DevOps Agent
│   ├── AI_Coding_Check_agent/  # AI 代码检查 Agent
    ├── audit_document_agent/   # 审计文档 Agent
    ├── sandbox_agent/          # 沙箱 Agent（已重构为 subagent 工具模式，见核心工具）
    └── Tagent/                 # T Agent
├── routers/                # 全局管理路由（2026-06-23 新增）
│   ├── __init__.py           # 包初始化
│   ├── mcp_admin_router.py   # MCP Admin 路由（CRUD + toggle + refresh methods）
│   ├── agent_router.py       # 统一 Agent 路由（Task 13，/api/agent/chat|list|agents-md）
│   ├── knowledge_router.py   # 知识库路由（2026-06-24 从 map_router 迁移，/api/map/knowledge/* + /api/map/knowledge-chat）
│   └── _stream_helper.py     # SSE 流式响应辅助（完整迁移自 map_router，agent_router 与 knowledge_router 复用）
├── shared/                 # 共享模块
│   ├── routers/           # 路由
│   │   ├── auth_router.py    # 认证路由（登录、注册、验证码、refresh、validate）
│   │   ├── session_router.py # 会话管理路由
│   │   ├── user_router.py    # 用户管理路由
│   │   └── file_router.py    # 文件管理路由
│   ├── tools/             # 共享工具（注册表 + 中间件 + MCP 配置）
│   │   ├── __init__.py       # 包初始化
│   │   ├── registry.py       # ToolRegistry + @register_tool 装饰器（按 agent 维度注册工具，供 AgentConfig.get_tools() 查询）
│   │   ├── mcp/              # MCP 服务器配置（config.yaml.example）
│   │   ├── middleware/       # 工具中间件（DockerSandboxBackend / EncodingSafeFileSearch 等）
│   │   └── skills/           # 按 agent 维度组织的工具模块（@register_tool 装饰）
│   │       └── map_agent/    # map_agent 工具（MapTools.py，8 个地图工具）
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
│       │   ├── session_path_manager.py  # session 上传目录日期化管理
│       │   ├── fileTransfer.py          # 文件清理/列出
│       │   ├── file_upload_handler.py   # 上传处理
│       │   └── pdfToImage.py            # PDF 转图片
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
门户导航场景下颁发给第三方 iframe 的"子 refresh-token"存储表。子 token 与正常 refresh_token 等效，但独立存储便于独立撤销与审计。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 记录ID |
| token_hash | VARCHAR(255) UNIQUE | Portal Refresh Token 的 SHA256 哈希值 |
| user_id | INTEGER FK → users | 用户ID |
| username | VARCHAR(100) | 用户名（冗余用于审计） |
| expires_at | TIMESTAMP | 过期时间（默认 24 小时） |
| revoked | BOOLEAN DEFAULT FALSE | ~~软删除标志（已废弃，逻辑上改为物理删除，不再使用）~~ |
| created_at | TIMESTAMP DEFAULT NOW() | 创建时间 |

### agents 表（2026-06-23 新增，2026-06-24 升级 config_schema 三层结构）
统一智能体架构的运行时配置表，存储智能体元信息、状态 schema、上下文 schema 及 MCP 标签等。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 智能体ID |
| name | VARCHAR(100) UNIQUE | 智能体唯一标识名 |
| display_name | VARCHAR(200) | 显示名称 |
| description | TEXT | 描述 |
| agents_md_path | VARCHAR(500) | AGENTS.md 配置文件路径 |
| state_schema | JSONB DEFAULT '{}' | **遗留**状态 schema（兼容旧版本，由 config_schema.state_fields 拆分同步写入） |
| context_schema | JSONB DEFAULT '{}' | **遗留**上下文 schema（兼容旧版本，由 config_schema.context_fields 拆分同步写入） |
| **config_schema** | **JSONB DEFAULT '{}'** | **2026-06-24 新增**：三层嵌套结构，覆盖 AgentConfig dataclass 字段 + state/context 字段 |
| mcp_tags | JSONB DEFAULT '[]' | MCP 标签列表 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| sort_order | INT DEFAULT 0 | 排序权重 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### config_schema 三层嵌套结构（2026-06-24 重构）

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

### agent_tool_bindings 表（2026-06-23 新增）
智能体与工具的绑定关系表，多对多映射。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 绑定ID |
| agent_name | VARCHAR(100) | 智能体名称 |
| tool_name | VARCHAR(100) | 工具名称 |
| is_enabled | BOOLEAN DEFAULT TRUE | 是否启用该绑定 |
| sort_order | INT DEFAULT 0 | 排序权重 |
| created_at | TIMESTAMP | 创建时间 |
| | UNIQUE(agent_name, tool_name) | 唯一约束：同一智能体同一工具仅一条绑定 |

### agent_skill_bindings 表（2026-06-23 新增）
智能体与 skill 的绑定关系表，多对多映射。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 绑定ID |
| agent_name | VARCHAR(100) | 智能体名称 |
| skill_name | VARCHAR(100) | skill 名称 |
| is_enabled | BOOLEAN DEFAULT TRUE | 是否启用该绑定 |
| sort_order | INT DEFAULT 0 | 排序权重 |
| created_at | TIMESTAMP | 创建时间 |
| | UNIQUE(agent_name, skill_name) | 唯一约束：同一智能体同一 skill 仅一条绑定 |

### map_agent 种子脚本（2026-06-23 新增，2026-06-24 修复 Bug B）

**文件位置**: `app/migrations/seed_map_agent.py`（含 `app/migrations/__init__.py` 包初始化）

向 `agents` / `agent_tool_bindings` / `agent_skill_bindings` 表写入 map_agent 初始配置，幂等可重复执行。

| 函数 | 说明 |
|------|------|
| `seed_map_agent(db)` | 核心种子函数。先 `SELECT` 判断 agents 表是否已有 map_agent，已存在则 UPDATE，不存在则 INSERT；工具/skill 绑定使用 `ON CONFLICT DO UPDATE` 幂等写入 |
| `main()` | 脚本入口，从 `DATABASE_URL` 环境变量（默认 `postgresql://postgres:postgres@localhost:5432/feature_agent`）读取连接并执行种子 |

**map_agent 配置常量**:
- `MAP_AGENT_STATE_SCHEMA`（**2026-06-24 修复**：补全原 MapAgentState 全部 5 个扩展字段 map_center / map_zoom / map_markers / map_layer / map_polygons，与原 MapAgentConfig.py 保持一致）：map_center={"latitude":0,"longitude":0} / map_zoom=10 / map_markers=[] / map_layer="standard" / map_polygons=[]
- `MAP_AGENT_CONTEXT_SCHEMA`（**2026-06-24 修复**：清空为 `{}`，原 `knowledge_root` 字段已删除；基类保留字段由 `dynamic_schema._BASE_CONTEXT_DEFAULTS` 兜底）
- `MAP_AGENT_TOOLS`: explore / query_knowledge / get_current_time / generate_report / save_business_info / ask_user_question / sandbox / load_skill / read_skill_file（9 个）
- `MAP_AGENT_SKILLS`: data-skill（1 个）

**2026-06-24 修复背景**：原 seed 脚本 MAP_AGENT_STATE_SCHEMA 只存了 `map_zoom` 一个字段，缺失 4 个扩展字段（map_center / map_markers / map_layer / map_polygons）。修复后重新执行 `python -m app.migrations.seed_map_agent` 会用完整 schema 覆盖已存在记录。**2026-06-24 后续整合**：原 `app/migrations/fix_map_agent_schema.sql`（SQL 辅助迁移脚本）已合并到 `app/migrations/init_all_tables.sql` 的 v3 章节（2026-06-24），运维只需执行 `init_all_tables.sql` 一次即可完成建表 + map_agent schema 修复。

**执行方式**: `python -m app.migrations.seed_map_agent` 或 `psql -U postgres -d feature_agent -f app/migrations/init_all_tables.sql`

**测试**: `app/tests/shared/test_seed_map_agent.py`（3 用例：可导入 / INSERT 路径 / UPDATE 幂等路径）

### mcp_server_configs 种子脚本（2026-06-24 新增）

**文件位置**: `app/migrations/seed_mcp_servers.py`

从 `app/shared/tools/mcp/config.yaml` 加载 MCP server 配置，写入 `mcp_server_configs` 表。**幂等**：表已有数据时跳过导入（与 lifespan `seed_from_yaml_if_empty` 行为一致）。

| 函数 | 说明 |
|------|------|
| `seed_mcp_servers(db)` | 核心种子函数。先 `SELECT name FROM mcp_server_configs` 判断表是否非空，非空则跳过；空则复用 `McpConfigService.seed_from_yaml_if_empty()` 导入 YAML 种子，返回本次实际写入条数 |
| `main()` | 脚本入口，从 `DATABASE_URL` 环境变量（默认 `postgresql://postgres:postgres@localhost:5432/feature_agent`）读取连接并执行种子 |

**执行方式**: `python -m app.migrations.seed_mcp_servers`

**测试**: `app/tests/shared/test_seed_mcp_servers.py`（4 用例：可导入 / 表非空跳过 / YAML 导入端到端 / YAML 为空不抛异常）

### _load_yaml_seed str→Path 修复（2026-06-24 bug 修复）

**问题**: `app/shared/utils/agent/mcp_service.py::_load_yaml_seed` 把 `settings.mcp.mcp_config_path`（Pydantic str 字段）直接传给 `mcpClient.shared.config_loader.load_mcp_config(config_path)`，后者调用 `config_path.exists()` 抛 `AttributeError: 'str' object has no attribute 'exists'`，导致：
- lifespan 启动时 `seed_from_yaml_if_empty` 静默失败（异常被 try/except 吃成 warning）
- `mcp_server_configs` 表永远为空
- 必须手工运行 `python -m app.migrations.seed_mcp_servers` 补种

**修复**: `_load_yaml_seed` 入口处 `config_path = Path(settings.mcp.mcp_config_path)` 显式转 Path。修复后 lifespan 自动种子正常工作。

**测试**: `app/tests/shared/utils/agent/test_mcp_service.py`（**17 用例**，2026-06-24 从 9 增至 17）新增：
- `test_load_yaml_seed_passes_path_to_loader` — 验证传给 `load_mcp_config` 的是 `Path` 实例
- `test_load_yaml_seed_returns_empty_on_missing_file` — 验证 YAML 不存在时返回空 dict

### McpConfigService JSONB 防御性反序列化（2026-06-24 bug 修复）

**问题**: `McpConfigService` 的 `list_servers` / `get_server` / `create_server` / `update_server` 4 个读路径直接 `dict(row)` 返回 row，asyncpg 默认不注册 JSONB codec，导致 `tags` / `progress_reporting` / `tool_config` / `sampling` / `command` 5 个 JSONB 字段以 str 形式返回给前端。前端遍历 dict 失败 → `/api/admin/mcp/servers` 列表为空。

**修复**: `McpConfigService` 新增静态方法 `_decode_jsonb(value, default)`（与 `AgentConfigService._decode_jsonb` 同实现）与类方法 `_decode_row(row)`，4 个读路径全部改为 `self._decode_row(row)`。`_decode_row` 按 `_JSONB_FIELDS` 元组统一解码 5 个 JSONB 字段，None 用合理默认值（`tags=[]` / `command=None` / 其他 `{"enabled": False}`）。

**测试**: `app/tests/shared/utils/agent/test_mcp_service.py` 新增 6 用例（17 用例总数）：
- `test_decode_jsonb_none_returns_default` — None 入参走 default
- `test_decode_jsonb_str_parses_json` — str 入参 json.loads
- `test_decode_jsonb_dict_list_passthrough` — dict/list 入参原样返回（兼容 codec 已注册场景）
- `test_decode_row_decodes_all_jsonb_fields` — 所有 JSONB 字段批量解码
- `test_decode_row_handles_none_jsonb` — None 字段走合理默认值
- `test_list_servers_decodes_str_jsonb` — 端到端：list_servers 从 str JSONB 解析为 list/dict

### mcp_server_configs 表（2026-06-23 新增）
MCP 服务器配置表，从 YAML 迁移至数据库管理。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 配置ID |
| name | VARCHAR(100) UNIQUE | 服务器唯一名称 |
| display_name | VARCHAR(200) | 显示名称 |
| type | VARCHAR(20) | 服务器类型（sse/stdio 等） |
| url | VARCHAR(500) | SSE 模式的 URL |
| command | JSONB | stdio 模式的启动命令 |
| timeout | INT DEFAULT 5 | 连接超时（秒） |
| read_timeout | INT DEFAULT 300 | 读取超时（秒） |
| tags | JSONB DEFAULT '[]' | 标签列表 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| progress_reporting | JSONB DEFAULT '{"enabled": false}' | 进度上报配置 |
| tool_config | JSONB | 工具注入配置（enable_injection、default_param_keys、hidden_param_keys、unwrap_result） |
| sampling | JSONB DEFAULT '{"enabled": false}' | 采样配置 |
| methods_synced_at | TIMESTAMP | 方法列表最后同步时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### mcp_server_methods 表（2026-06-23 新增）
MCP 服务器方法列表表，用于运行时方法管理。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 方法ID |
| server_name | VARCHAR(100) | 所属服务器名称 |
| method_name | VARCHAR(200) | 方法名称 |
| enabled | BOOLEAN DEFAULT TRUE | 是否启用 |
| description | TEXT | 方法描述 |
| created_at | TIMESTAMP | 创建时间 |
| | UNIQUE(server_name, method_name) | 唯一约束：同一服务器同一方法仅一条记录 |

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
|   ├ GET /{session_id}/messages | | 获取会话历史消息（从 LangGraph Checkpoint 恢复，默认 50 条；**2026-06-16 改造：返回 messages 中按时序插入 `type:"subagent"` 元素，承载 sandbox/explore 子智能体的完整轨迹**） |
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
| /api/map | knowledge_router | 地图 Agent（2026-06-24 从 map_router 迁移到 `app/routers/knowledge_router.py`） |
|   ├ GET /knowledge/files | | 获取知识库文件元数据（自动扫描 Knowledge 目录） |
|   ├ GET /knowledge/file-download | | 下载知识库文件 |
|   ├ GET /knowledge/file-preview | | 知识库文件预览（支持 .doc 自动转 .docx） |
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
- 工作目录: `data/upload/{session_id}`（2026-06-12 路径重构，原 `app/data/upload/...` 已迁移到项目根 `data/`；2026-06-18 修正：去掉冗余的 `/sandbox` 子目录，与 session 上传目录保持一致）
- **workspace 统一创建入口**: `app/core/tools/SandboxTools.py` 负责根据 `session_id` 创建 `data/upload/{session_id}` 目录，然后显式传入 `DockerSandboxMiddleware` / `DockerSandboxBackend`。后端/中间件不再自行创建工作目录，未传入有效 workspace 时抛出 `ValueError`。
- 默认镜像: `python:3.12-alpine`
- 资源限制: 内存 512MB，CPU 100%，无网络
- 支持流式事件: `tool_start` / `tool_progress` / `tool_stop`
- Docker 不可用降级: 通过 `SANDBOX_FALLBACK_TO_LOCAL` 控制是否降级到 `LocalShellBackend` 本地执行（默认 `false`，保持安全边界）

**依赖**:
- `DockerSandboxMiddleware` / `DockerSandboxBackend`: `app/shared/tools/middleware/docker_sandbox_backend.py`

### BaseFilesystemTool（2026-06-18 新增，2026-06-20 改造）

**文件位置**: `app/core/tools/base/BaseFilesystemTool.py`

**功能**: 封装文件系统子智能体的通用执行逻辑：创建子智能体、流式执行、事件推送、用户停止信号感知、结果提取与异常处理。

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

**结果提取规则（2026-06-20 改造）**:
- 子智能体执行完成后，统一从循环内累计的 `all_messages` 中提取最后一条 `AIMessage` 的文本内容作为最终结果。
- 不再使用 `response_format` / `structured_response`，`explore` 与 `query_knowledge` 均按此规则返回结果。
- 若 `all_messages` 为空或未包含有效 AIMessage，使用兜底字符串 `"子智能体执行完成，但未获取到文本回复。"` 并记录 `logger.warning`。
- `_extract_last_ai_text` 通过消息类型名字符串 `"AIMessage"` 识别，兼容测试环境 Mock。

**依赖**:
- `EncodingSafeFileSearchMiddleware`: `app/shared/tools/middleware/encoding_safe_file_search.py`
- `FilesystemMiddleware` / `FilesystemBackend`: `deepagents`
- `get_async_checkpointer`: `app/shared/utils/memory/checkpoint.py`
- `get_current_request`: `app/core/tools/_stop_signal.py`

### explore 工具（2026-06-18 重构）

**文件位置**: `app/core/tools/FilesystemReadTools.py`

**功能**: 启动文件系统探索子智能体，读取当前 session 上传目录 `data/upload/{session_id}` 中的文件并分析。

**变更**:
- 移除原 `knowledge_root` 分支，`explore` 仅保留最基础的 session 文件读取能力。
- 通用执行逻辑迁移到 `BaseFilesystemTool`，`explore` 仅负责解析 `session_id`、构造 `root_path`、实例化 `BaseFilesystemTool` 并调用 `arun`。
- **当 session 上传目录为空（用户未上传任何文件）时，`explore` 不再启动子智能体，而是直接返回包含 `"未找到文件"` 的 ToolMessage Command，避免 `ValueError` 异常上抛影响主流程。**
- 知识库检索能力由 `app/shared/tools/skills/map_agent/MapTools.py` 中的 `query_knowledge` 工具承担（2026-06-24 从 `app/features/map_agent/tools/MapTools.py` 迁移）。

### query_knowledge 工具（2026-06-18 新增；2026-06-24 迁移到新架构）

**文件位置**: `app/shared/tools/skills/map_agent/MapTools.py`

**功能**: 启动知识库检索子智能体，在配置的知识库目录中搜索并读取文档。

**使用方式**: 通过 `@register_tool(agent="map_agent")` 注册到 ToolRegistry，供 AgentConfigService 按 agent_name 加载，仅在地图 Agent 场景可用。

**实现细节**:
- 通过 `runtime.context["knowledge_root"]` 获取目标知识库路径，由调用方（如 `/api/map/knowledge-chat`，实现在 `app/routers/knowledge_router.py`）在 AgentContext 中注入。
- 调用 `BaseFilesystemTool(...).arun(prompt, runtime, root_path)` 复用通用子智能体执行逻辑。
- 未配置 `knowledge_root` 时直接返回错误 `Command`，避免子智能体在无效路径上运行。
- 已注册为子智能体工具（`subagent_registry.SUBAGENT_TOOL_NAMES` 包含 `query_knowledge`），前端 `sseParser.js` 的 `SUBAGENT_META` 同步了图标与标签。

**扩展方式**:
- 未来需要查询其他知识库时，可新增一个工具函数，仅修改 `root_path` 来源（如从 `runtime.context["other_knowledge_root"]` 读取），并复用同一个 `BaseFilesystemTool`。

## Agent max_summary_tokens 防御性调整（2026-06-24 bug 修复）

**问题**: `app/core/agent/agent.py` 通过 `langmem.short_term.SummarizationNode` 实现自动摘要，langmem 严格校验 `max_summary_tokens < max_tokens`（在 `_preprocess_messages` 中）。`AgentConfig` 三个相关字段（`max_tokens` / `max_tokens_before_summary` / `max_summary_tokens`）默认值都是 `999999999`，导致 `999999999 < 999999999 == False`，触发 `ValueError: max_summary_tokens must be less than max_tokens`，整个聊天流程崩溃。

**修复**: `Agent.__init__` 在读取 `config.max_summary_tokens` 后立即防御性调整：
- 若 `max_summary_tokens >= max_tokens`，则 `max_summary_tokens = max(1, max_tokens // 2)`
- 同时 `logger.warning` 记录原值与调整后值，便于排查
- 用户已自定义且 `max_summary_tokens < max_tokens` 时保持原值不动

**代码位置**: [app/core/agent/agent.py:130-142](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/core/agent/agent.py#L130-L142)

**测试**: `app/tests/core/agent/test_max_summary_tokens_adjustment.py`（**5 用例**，2026-06-24 新增）：
- `test_default_values_get_adjusted_to_half` — 默认 999999999 → 调整为 499999999
- `test_user_customized_summary_keeps_value` — 用户显式设小（2000 < 8000）保持原值
- `test_user_inverted_values_get_adjusted` — 用户设反（16000 > 8000）触发调整
- `test_adjustment_logs_warning` — 调整时记录 warning 日志
- `test_equal_values_at_smaller_scale` — 小规模（100 == 100 → 50）也工作

## Agent 聊天并发控制（2026-06-15 扩展：动态排队提示 + HITL 早期释放；2026-06-22 严格 FIFO 重构）

**文件位置**: `app/core/concurrency/chat_concurrency_dependency.py` + `app/core/concurrency/agent_concurrency_queue.py`

**功能**: 限制同时处理的 Agent 聊天请求数，超出最大并发数时进入 FIFO 内存队列等待，并向**前端实时推送排队人数提示**。

**配置项**:
- `AGENT_CHAT_MAX_CONCURRENCY` — Agent 聊天接口最大并发数，超出时进入内存队列等待，默认 1（`settings.agent_chat_max_concurrency`）。
- 排队事件推送间隔 `QUEUE_POLL_INTERVAL_SECONDS = 1.0`（依赖内常量，硬编码）。

### 2026-06-22 严格 FIFO 修复（核心 bug 修复）

> **踩坑记录**：早期实现使用 `asyncio.Semaphore` + `slot_freed` Event 唤醒多个 waiter，存在以下乱序现象：
> 1. **后入队先获得**：多个 waiter 被 `slot_freed.set()` 同时唤醒后，`asyncio.Semaphore` FIFO 内部队列与 enqueue 顺序可能不一致，导致排在后面的请求先进入会话
> 2. **同时进入**：被唤醒的多个 waiter 几乎同时竞争 semaphore，前端看到「前面还有 1 位」但多个请求同时通过
> 3. **HITL resume 插队**：U3 触发 HITL 后释放槽位，U3 的 resume 请求与已排队的 U2 同时竞争槽位，resume 抢走槽位导致 U2 卡死
>
> 修复方案：放弃 `asyncio.Semaphore`，改用 `_Waiter.future` + FIFO deque，每个 waiter 独立 Future，release() 严格按 FIFO 顺序唤醒第一个有效 waiter。

**修复要点**：
- `AgentConcurrencyQueue` 内部用 `_waiters: Deque[_Waiter]` 维护严格 FIFO 队列
- 每个 `_Waiter` 持有 `asyncio.Future`，release() 只唤醒队首 waiter 并 `set_result(None)`，不惊群
- acquire() 时若自己是队首且槽位空闲则立即获得；否则 await future（精确唤醒，无竞争）
- release() 转移许可给下一个 waiter 时 `active_count` 不变（先减后加改为直接转移），消除瞬时空窗
- 失败的/已取消的 waiter 自动顺延下一个，不会卡死队列
- HTTP 模式也强制 enqueue 后再判定 position，杜绝非流式请求绕过 SSE FIFO 队列插队

### 双模式依赖（2026-06-15 重构，2026-06-22 强化）

`chat_concurrency_dependency(request, mode="sse" | "http")` 异步生成器：

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **SSE 模式**（默认） | `/api/agent/chat`、`/api/map/knowledge-chat` | 所有请求统一先 enqueue；只有 `position == 1` 且槽位空闲时才尝试 acquire；获取许可后 yield `ready` 事件 + `None` 让路由继续；通过 `await release_done.wait()` 阻塞直到路由主动释放（HITL 场景）或 finally 兜底 |
| **HTTP 模式** | `/api/contract/chat` 等非流式接口 | 强制先 enqueue；只有 `position == 1` 且槽位空闲时获取许可；否则抛 `HTTPException(429, detail={error,waiting_count,active_count,max_concurrency,message})`；无需等待时直接 yield None |

### AgentConcurrencyQueue 接口（2026-06-22 改造）

- `enqueue(task)`：预注册 task 到 FIFO 等待队列（不阻塞），幂等
- `enqueue_time(task)`：返回指定 task 的入队时间戳（`time.monotonic()`）
- `position(task)`：返回 FIFO 队列位置（1-based，0=已激活，-1=未注册）
- `snapshot(task)`：返回 `{active_count, waiting_count, max_concurrency, position, enqueue_time, timestamp}`
- `acquire(task)`：获取许可；只有队首 waiter 且槽位空闲时立即获得，否则 await Future 阻塞
- `release(task)`：FIFO 顺序唤醒下一个有效 waiter（active_count 不出现先减后加瞬时窗口）
- `slot_freed`：槽位释放事件，保留供 SSE 轮询兼容
- 内部维护 `_waiters: Deque[_Waiter]` 与 `_waiter_index: Dict[asyncio.Task, _Waiter]`；取消时通过 `_remove_waiter` 回滚计数

### SSE 轮询即时唤醒（2026-06-22）

`chat_concurrency_dependency` SSE 模式在排队期间：
1. 先调用 `queue.enqueue()` 预注册当前请求（**确保与 acquire 的 task 是同一个**）
2. 在独立 `acquire_task = asyncio.create_task(queue.acquire(current_task))` 中阻塞
3. 主循环每 `QUEUE_POLL_INTERVAL_SECONDS`（1.0s）推送一次 `waiting` 事件（仅当 `position != 1` 或槽位仍占用时）
4. `asyncio.wait_for(shield(acquire_task), timeout=QUEUE_POLL_INTERVAL_SECONDS)` 在 acquire 完成或 1 秒后唤醒
5. acquire 完成（被 Future 唤醒）后立即跳出循环 yield `ready` + `None`

效果：其他请求 release 后，队首 waiter 在 Future 被 set_result 时**毫秒级**内被唤醒，而不是等待 1s 超时。

### HITL interrupt 早期释放（核心修复）

> **踩坑记录**：HITL interrupt 后如果仅靠依赖 finally 释放许可，前端不主动断开 SSE 连接会导致许可长时间被占，用户 resume 请求会卡在 FIFO 队列。本改造通过**前后端协作**修复。
>
> **2026-06-22 补充**：排队位置 `position` 原在 `acquire()` 阻塞后才写入 `_waiter_tasks`，导致 SSE `waiting` 事件把 `position=0` 传给前端，显示"前面还有 0 位"。现通过 `enqueue()` 预注册， waiting 事件携带的位置与前面实际排队人数一致。
>
> **2026-06-22 强化**：HITL 释放后已通过 FIFO Future 唤醒机制保证 resume 请求不会插队已排队的其他用户，但前端必须严格走 `await reader.cancel()` 配合后端 `release_handle` 释放许可。

**后端机制**：
- 依赖在 acquire 成功后把 `concurrency_release_handle`（可调用对象）挂到 `request.state`
- 路由（`stream_with_concurrency`）在 yield `type='interrupt'` 业务事件**之前**调用 `handle()` 强制释放许可
- finally 兜底：`release_done.wait()` 超时或客户端异常断开时执行 release
- 句柄幂等：多次调用不会重复释放（`release_done.is_set()` 守卫）

**前端机制**：
- 收到 interrupt 事件后**主动 `await reader.cancel()`** 断开 fetch，让后端 StreamingResponse 立即结束
- 配合后端 release_handle，**许可释放 + SSE 连接断开两者都及时发生**
- 缺一不可：仅后端 release 但前端不 cancel → 连接挂着 → finally 兜底延迟；仅前端 cancel 但后端不 release → resume 时排队

### SSE queue 事件协议（2026-06-15 新增）

事件格式（仅追加，不修改既有字段）：

```json
{
  "type": "queue",
  "event": "waiting" | "ready",
  "waiting_count": int,
  "active_count": int,
  "max_concurrency": int,
  "position": int,         // 1-based，ready 时通常为 0
  "timestamp": float       // 快照生成时刻
}
```

老客户端忽略未知 `type=queue` 字段，行为不变（向后兼容）。

### HTTP 429 响应格式

```json
{
  "detail": {
    "error": "queue_full",
    "waiting_count": 1,
    "active_count": 1,
    "max_concurrency": 1,
    "message": "当前并发请求已达上限，请稍后重试"
  }
}
```

### 已接入路由

| 路由 | 类型 | 接入方式 |
|------|------|---------|
| `/api/agent/chat` | SSE | 路由体内手动 `dep = chat_concurrency_dependency(request, mode="sse")` + `stream_with_concurrency(request, dep, business_gen)` 包装 |
| `/api/map/knowledge-chat` | SSE | 同上 |
| `/api/contract/chat` | HTTP | `dependencies=[_chat_concurrency_http_dep()]`（工厂函数，传 `mode="http"`） |
| `/api/contract/doc_chat` | HTTP | 同上 |
| `/api/contract/approval_chat` | HTTP | 同上 |

### 测试覆盖（2026-06-22 新增）

**后端** `app/tests/core/concurrency/`:
- 既有 `test_agent_concurrency_queue.py`（16 用例）+ `test_chat_concurrency_dependency.py`（12 用例）+ `test_stream_with_concurrency.py`（11 用例）全部通过
- **新增** `test_fifo_strict_order.py`（8 用例）：
  - `test_strict_fifo_release_grants_to_first_waiter_only`：4 个 waiter 严格按入队顺序获得许可
  - `test_new_request_does_not_preempt_queued_waiters`：新请求不能绕过已排队 waiter
  - `test_resume_request_does_not_preempt_queued_waiters`：HITL resume 不能插队其他用户
  - `test_simultaneous_waiters_get_serialized`：多个 waiter 同时等待时串行获取
  - `test_cancelled_waiter_does_not_block_queue`：中间的 waiter 取消不会卡死队列
  - `test_release_transfers_to_next_waiter_keeps_active_count`：release 时 active_count 保持
  - `test_release_transfers_to_next_waiter_without_decrement`：释放转移不出现瞬时空窗
  - `test_hitl_release_does_not_preempt_queued_users`：HITL 释放后已排队用户严格 FIFO
- **总测试数**：47 passed / 0 failed

**前端** `web/Agent/src/components/__tests__/`:
- **新增** `KnowledgeChat.streamGuard.spec.js`（5 用例）：
  - `test_knowledge_chat_handleSend_triggers_stop_when_streaming`：流式中 handleSend 触发 handleStop
  - `test_knowledge_chat_handleKeydown_enter_triggers_stop_when_streaming`：流式中 Enter 触发 handleStop
  - `test_knowledge_chat_handleKeydown_calls_handleSend_when_not_streaming`：非流式 Enter 走正常发送分支
  - `test_knowledge_chat_reset_queue_status_resets_to_idle`：resetQueueStatus 正确重置
  - `test_knowledge_chat_send_btn_click_routes_to_stop_when_streaming`：send-btn 流式下点击触发 handleStop

### 通用 SSE 流式包装器 `stream_with_concurrency`（2026-06-15 新增）

**文件位置**：`app/core/concurrency/chat_concurrency_dependency.py`（同模块）

**背景踩坑**：早期版本 `map_router.py` 用 `dep=Depends(chat_concurrency_dependency)` 注入并发控制依赖，**实测发现 FastAPI 对 yield-based dependency 的处理会注入 generator 第一个 yield 的值（dict），不是 generator object**——`_stream_with_queue` 中的 `async for item in dep` 因此抛 `TypeError: 'async for' requires an object with __aiter__ method, got dict`（参见 [fastapi/dependencies/utils.py:543-551](file:///e:/laboratory/AI/Agents/Lib/site-packages/fastapi/dependencies/utils.py#L543-L551) 的 `asynccontextmanager(dependant.call)(**sub_values)` 包装）。

**修复方案**：
- `chat_concurrency_dependency` **不能**作为 `Depends` 使用。SSE 路由必须在路由体内手动调用 `chat_concurrency_dependency(request, mode="sse")` 获取 async generator object
- 通用 `stream_with_concurrency(request, dep, business_gen)` 工具函数负责：
  1. 消费 `dep` yield 链（queue waiting/ready 事件）→ 序列化为 SSE 透传前端
  2. 消费 `business_gen` yield 链（业务 chunk）→ 透传
  3. HITL 关键：检测到 `type='interrupt'` 业务事件时，yield 之前主动调用 `request.state.concurrency_release_handle()` 释放许可
  4. finally 兜底：业务流 / 客户端异常时显式 `await dep.aclose()`，触发 `chat_concurrency_dependency` 的 finally 块做 release 兜底
- 原 `map_router.py` 内私有函数 `_stream_with_queue` / `_is_interrupt_chunk` 已删除并迁移到 concurrency 模块，供所有 SSE 聊天路由复用

**使用方式**（SSE 路由标准模板）：

```python
from app.core.concurrency import chat_concurrency_dependency, stream_with_concurrency

@router.post('/xxx-chat')
async def xxx_chat(request: Request, chat_request: ChatRequest):
    dep = chat_concurrency_dependency(request, mode="sse")  # 手动获取 generator
    return StreamingResponse(
        stream_with_concurrency(request, dep, generate_stream_response(...)),
        media_type="text/event-stream",
    )
```

**`__init__.py` 导出**：`from app.core.concurrency import stream_with_concurrency`

**测试覆盖**：`app/tests/core/concurrency/test_stream_with_concurrency.py`（7 用例：SSE 输出顺序 / aclose 时机 / 异常 finally / interrupt release / 非 interrupt 不 release / 无 aclose 防御 / `_is_interrupt_chunk` 单元测试）

### 前端 `isStreaming` 状态同步（2026-06-22 修复）

**问题**：`KnowledgePage.vue` 将 `isChatStreaming` 作为 prop 传入 `KnowledgeChat.vue`，但 `KnowledgeChat` 在 SSE 流结束 / 用户停止 / HITL 取消后**未通知父组件**，导致 `isChatStreaming` 一旦为 `true` 就无法回到 `false`。多用户排队场景下，用户 1 的请求在队列中等待时前端已显示“生成中”，用户 2 结束会话后用户 1 获得槽位并跑完流，但父级状态仍卡在 `true`，发送按钮永久灰色，新建会话也无法恢复。

**修复**（涉及 `web/Agent/src/components/KnowledgeChat.vue`、`KnowledgePage.vue`、`App.vue`）：
1. `KnowledgeChat.vue` 新增 `stream-end` 事件，在以下路径 emit：
   - `handleSend` 的 `finally`（流自然结束 / 异常 / HTTP 429）
   - `handleStop`（用户点击停止）
   - `handleApprovalCancel`（取消 HITL）
   - `handleApprovalSubmit` 内 `readStream` 的 `finally`（resume 结束 / 再次 interrupt）
   - `handleNewChat`（新建会话时强制清理）
2. `KnowledgeChat.vue` 将 `internalStreaming` 置位时机从 `knowledgeChatStream()` 调用前延后到**拿到 SSE reader 之后**，避免排队 / 握手阶段状态悬空。
3. `KnowledgePage.vue` 绑定 `@stream-end="handleChatStreamEnd"`，`handleNewChat()` 中强制复位 `isChatStreaming`。
4. `App.vue` 的 `newSession()` 与 `handleSessionSwitch()` 在清理前主动 `currentStreamReader.cancel()` 并复位 `isStreaming.value`，避免主应用同样出现状态卡住。

**注意**：后端并发队列本身已有 finally 兜底释放，本次 bug 根因为前端状态机未正确同步，而非队列泄漏。

### 前端流式状态拦截（2026-06-22 强化）

**问题**：在多用户排队场景下，已排队的用户可能因后端槽位释放后未能立即拿到而出现「卡死」状态（`isStreaming=true` 但业务流未真正开始）。此时用户在输入框按 Enter 或点击发送，会创建**第二条 SSE 流**，导致状态进一步混乱。新流的 finally 复位可能清掉旧流未完成的状态，最终表现为「再次输入后恢复正常排队」。

**修复**（涉及 `web/Agent/src/components/KnowledgeChat.vue`、`App.vue`、`KnowledgeApp.vue`）：
1. **KnowledgeChat.vue** `handleSend` 入口增加流式拦截：`if (isCurrentlyStreaming.value) { await handleStop(); return }`，流式状态下不再创建新请求
2. **KnowledgeChat.vue** `handleKeydown` 在流式状态下按 Enter 优先调用 `handleStop()` 而非 `handleSend()`
3. **App.vue / KnowledgeApp.vue** 所有错误路径（含 HTTP 429）必须复位 `isStreaming.value` 与 `currentStreamReader`，避免按钮永久卡死
4. **所有三个组件** 新增 `resetQueueStatus()` 函数，在以下时机重置 `queueStatus` 到 idle：
   - `handleSendMessage` / `handleProfileSend` / `handleSend` 开头（避免上一次 ready 残留）
   - `handleApprovalSubmit` 开头（resume 请求前）
   - `newSession` / `handleSessionSwitch` 中（切换/新建会话时）
5. **App.vue / KnowledgeApp.vue** `isStreaming` 置位时机从 `chatStream()` 调用前延后到**拿到 SSE reader 之后**，避免排队/握手阶段状态长期悬空

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
  - `SANDBOX_FALLBACK_TO_LOCAL` — Docker 不可用时是否降级到本地文件系统执行，默认 `false`（2026-06-18 新增）
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
| 地图 Agent | [app/routers/knowledge_router.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/routers/knowledge_router.py)（`KNOWLEDGE_SYSTEM_PROMPT`，2026-06-24 从 `app/features/map_agent/config/prompts.py` 迁移；Agent 主提示词改由 AGENTS.md + 数据库 agents 表加载） |
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
- **示例**：[app/shared/tools/skills/map_agent/MapTools.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/shared/tools/skills/map_agent/MapTools.py) 中 `set_map_center`、`add_map_marker` 等函数的 docstring

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
- **测试**：
- 后端：`tests/test_ask_user_question.py` 17 个测试（Schema 10 + Tool 2 + HitlCheckNode 5）
- 前端：`web/Agent/src/components/__tests__/HumanApprovalBox.spec.js` 14 个测试
- **2026-06-15 新增 HITL interrupt 卡死修复 + 前后端协作测试**：
  - 后端 `app/tests/core/concurrency/test_chat_concurrency_dependency.py` 新增 9 个用例：`test_sse_dependency_no_queue_event_when_available` / `test_sse_dependency_emits_waiting_event_when_full` / `test_sse_dependency_auto_resumes_after_ready_event` / `test_sse_dependency_release_handle_releases_immediately_on_call` / `test_sse_dependency_release_handle_is_idempotent` / `test_sse_dependency_releases_on_hitl_interrupt_path` / `test_sse_dependency_finally_release_when_handle_never_called` / `test_http_dependency_raises_429_when_full` / `test_http_dependency_yields_none_when_available`
  - 后端 `app/tests/core/concurrency/test_agent_concurrency_queue.py` 新增 4 个用例：`test_queue_snapshot_returns_active_and_waiting` / `test_queue_position_increments_for_later_waiters` / `test_queue_position_decrements_as_others_release` / `test_queue_enqueue_time_records_monotonic`
  - 前端 `web/Agent/src/components/__tests__/QueueStatusBanner.spec.js` 新增 10 个用例
  - 前端 `web/Agent/src/components/__tests__/App.interrupt.spec.js` 新增 4 个用例（**HITL 核心**：`test_handleSendMessage_calls_reader_cancel_on_interrupt` / `test_handleApprovalSubmit_calls_reader_cancel_on_interrupt` / `test_handleSendMessage_no_cancel_on_normal_end` / `test_reader_cancel_swallows_cancel_error`）
  - 前端 `web/Agent/src/utils/__tests__/sseParser.test.js` 新增 3 个 queue 事件用例
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
| `DockerSandboxMiddleware` | `app/shared/tools/middleware/docker_sandbox_backend.py` | 继承 `FilesystemMiddleware`，自动管理 `DockerSandboxBackend`，提供沙箱工具集；**2026-06-18 新增**：Docker 不可用时可按 `SANDBOX_FALLBACK_TO_LOCAL` 配置降级到 `LocalShellBackend` 本地执行 |
| `sandbox` 工具 | `app/core/tools/SandboxTools.py` | `@tool` 装饰的 `sandbox` 函数，通过 `create_deep_agent` 启动沙箱子智能体；2026-06-12 重构：容器化部署配置从 `Settings.get_sandbox_config()` 注入；2026-06-13 扩展：填充 subagent 结构化字段（详见下文 "SubAgent 事件协议"）；**2026-06-16 改造：checkpointer 由进程内 `MemorySaver()` 切换为全局共享 `get_async_checkpointer()`，子智能体 messages 按 `thread_id=tool_call_id` 持久化（PostgreSQL 模式落库，memory 模式进程内共享）** |
| `SandboxSettings` | `app/core/config/settings.py` | Pydantic BaseSettings，管理 11 个 `SANDBOX_*` 环境变量，控制 docker_mode / 镜像 / 资源限制 / 路径前缀 / fallback_to_local |

### 架构变更历史

**2026-06-12 重构**: 从独立 FastAPI 路由 (`/api/sandbox/chat`) 迁移为 core agent 的 subagent 工具模式。
- 删除: `app/features/sandbox_agent/` 目录及所有文件
- 新增: `app/core/tools/SandboxTools.py` 工具函数
- 变更: 从独立 SSE 端点变为通过 core agent 工具链调用

### Docker 容器隔离

- **镜像**：默认 `python:3.12-alpine`，可配置
- **资源限制**：`max_memory_mb`（默认 512MB）、`max_cpu_percent`（默认 100%）
- **网络控制**：`network_enabled=False` 默认关闭网络，防止数据外泄
- **工作目录**：每个 Session 独立 host workspace 为项目根下 `data/upload/{session_id}`，由 `app/core/tools/SandboxTools.py` 统一创建后传入 `DockerSandboxMiddleware` / `DockerSandboxBackend`；容器内通过 Docker volume 映射到固定的 `/workspace`，避免 Windows 路径盘符冒号与 Docker mount 格式冲突。后端不再自行创建工作目录。

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

**Docker 不可用降级（2026-06-18 新增）**：

- 配置项 `SANDBOX_FALLBACK_TO_LOCAL`（默认 `false`）控制 Docker daemon 不可用时是否降级到本地执行
- `false`（默认）：`DockerSandboxMiddleware` 继续抛出 RuntimeError，`sandbox()` 工具返回清晰的 `tool_error` 事件，提示用户 Docker 未运行
- `true`：`DockerSandboxMiddleware` 在 Docker 连接失败时自动切换到底层 `LocalShellBackend`，子智能体在当前进程的本地 `workspace` 继续执行文件/命令操作
- **安全提示**：`true` 模式会失去 Docker 容器隔离，子智能体代码直接在宿主机/应用进程环境运行，仅限开发、测试或完全可信的内网环境使用

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
- **2026-06-17 新增 toggle 行为**：`App.vue` / `KnowledgeApp.vue` 的 `openSubAgentDrawer()` 增加 toggle 逻辑——当抽屉已打开且点击的 subagent 与 `currentSubAgent.toolCallId` 相同时调用 `closeSubAgentDrawer()` 关闭抽屉；点击不同 subagent 时仍切换抽屉内容。subagent 唯一标识沿用 `toolCallId`（同一执行周期内稳定）。这样用户连续点击同一张 subagent 卡片即可在「打开 / 关闭」之间快速切换，无需专门定位抽屉的 X 按钮。事件链本身（`SubAgentCard click → MessageBubble emit('open-subagent-drawer')`）未变化，仅 `App.vue` / `KnowledgeApp.vue` 的事件处理器增加了 toggle 分支。`SubAgentDrawer.vue` / `SubAgentCard.vue` / `MessageBubble.vue` 不需要任何改动

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

> **目标**：子智能体（sandbox / explore / query_knowledge 等）的执行过程在父 AI 聊天气泡中折叠为 `SubAgentCard` 卡片；点击卡片从右侧 push 出 `SubAgentDrawer` 详情面板，展示父提问 + 子智能体内部消息流 + 沙箱摘要 + 沙箱事件时间线（tool='sandbox' 时）。
>
> **2026-06-14 改造**：`SandboxProgress` / `SandboxDrawer` / `SandboxEventItem` 已删除并合并；子智能体卡片从"会话末尾堆放"改为"嵌入 `timeline.tool` 块内按时序渲染"。
> **2026-06-14-2 修复**：`update` 事件（`hitl_check` / `summarize` / `llm_call` 等节点状态）不再落入父气泡"思考过程"区；`update` SSE payload 统一附加 `thread_id`（空字符串）与 `langgraph_node`（节点名）字段，与 `custom` / `message` 事件格式保持一致。
> **2026-06-18 改造**：子智能体展示元信息（icon/label）由后端统一维护并下发，前端 `sseParser.js` 不再硬编码 `SUBAGENT_META`。

### 沙箱 workspace 统一创建约束（2026-06-18 新增）

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

| 字段 | 类型 | 出现时机 | 说明 |
|------|------|---------|------|
| `thread_id` | `str` | 全部 | 子 agent 标识（== `tool_call_id`），便于前端按 id 维护 subagent 列表 |
| `parent_prompt` | `str` | `tool_start` | 父 agent 传给子 agent 的 prompt（用于抽屉顶部"父提问"区） |
| `child_messages` | `list[dict]` | `tool_progress` | 子 agent 当前累积的全部 messages，结构化（langchain 对象 → dict） |
| `final_messages` | `list[dict]` | `tool_stop` | tool_stop 时的最终消息快照（结构同 `child_messages`），覆盖到 `messages` 字段 |
| `meta` | `dict` | `tool_start` / history | 子智能体展示元信息 `{icon, label}`，由后端 `app/core/tools/subagent_registry.py` 统一维护并下发；前端首次收到后缓存复用 |

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
| `app/core/tools/SandboxTools.py` | `tool_start` / `tool_progress` / `tool_stop` / `tool_error` 事件 data 追加 `thread_id` + `parent_prompt` + `child_messages` / `final_messages`；**2026-06-18 新增**：`tool_start` 携带 `meta`（icon/label） |
| `app/core/tools/base/BaseFilesystemTool.py` | **2026-06-18 新增**：`tool_start` 携带 `meta`（icon/label），支持 explore / query_knowledge 等文件系统子智能体 |
| `app/core/tools/FilesystemReadTools.py` | `tool_start` / `tool_progress` / `tool_stop` / `tool_error` 事件 data 追加 `thread_id` + `parent_prompt` + `child_messages` / `final_messages`；并新增 `all_messages` 累积逻辑（从 `updates` 模式 `node_name.messages` 提取） |
| `app/core/tools/subagent_registry.py` | **2026-06-18 新增**：`SUBAGENT_META` 与 `get_subagent_meta()`，作为前后端统一的子智能体展示元信息事实来源 |
| `app/shared/utils/memory/checkpoint_history.py` | **2026-06-18 新增**：历史消息 `type:"subagent"` 元素携带 `meta`（icon/label） |
| `app/routers/knowledge_router.py` | `custom` 模式 SSE yield 时在顶层追加 `thread_id` 字段（从 `data.data.thread_id` / `data.tool_call_id` 推导），**老客户端忽略未知字段不破坏**；`updates` 模式同步追加 `thread_id`（空字符串）与 `langgraph_node`（节点名）字段，统一 SSE 格式（2026-06-24 从 `app/features/map_agent/router/map_router.py` 迁移） |
| `app/core/tools/events.py` | 注释追加新字段文档（实现不动） |
| `app/tests/core/tools/test_subagent_message_extractor.py`（**新增**） | 22 个 pytest 用例：role 分类 / content 归一化 / 三种 tool_call 来源 / 边界条件 |
| `app/tests/shared/utils/memory/test_checkpoint_history_subagent.py`（**2026-06-16 新增**） | 17 个 pytest 用例：`_is_ai_message` 类型名匹配 / `_extract_ai_tool_call_ids` 三种来源 / `get_subagent_history` 含 include_tool / 空 thread_id / thread 不存在 / `collect_subagent_thread_ids_for_cleanup` 去重 / 无 tool_calls / `merge_main_and_subagent_messages` 含/无 subagent / 无 raw |
| `app/tests/shared/test_session_messages_subagent.py`（**2026-06-16 新增**） | 6 个整合测试：合并子智能体 / 无 tool_call 不插入 / 401 / 403 / limit 作用于合并后总数 / delete 清理子 thread |

### 前端改动文件

**2026-06-14-2 修复**：

| 文件 | 改动 |
|------|------|
| `web/Agent/src/utils/sseParser.js` | `processSSEEvent` 的 `update` case 显式跳过 `hitl_check` 节点；`isSubAgentMessage` 增加 `metadata.lc_agent_name` / `metadata.langgraph_node` 多维度判定，防御 tool_start 与 message 到达顺序抖动的 race condition；调用点同步透传 metadata；**2026-06-18 改造**：删除硬编码 `SUBAGENT_META`，新增 `subagentMetaCache`，`getSubAgentMeta` 从后端下发的 `meta` 字段读取并缓存，未知工具回退兜底 |
| `web/Agent/src/utils/__tests__/subAgentParser.test.js` | 新增 6 个用例：`hitl_check` update 不进入 thinking / timeline；`isSubAgentMessage` 通过 `lc_agent_name` / `langgraph_node` 识别子智能体；`message` 事件在 `lc_agent_name=sandbox` 时不写入父气泡；**2026-06-18 新增**：meta 缓存 / 兜底 / 非法输入防护测试 |
| `web/Agent/src/utils/__tests__/sseParser.subagentHistory.test.js` | **2026-06-18 新增**：历史 subagent 元素 `meta` 缓存测试 |
| `app/tests/core/tools/test_subagent_registry.py` | **2026-06-18 新增**：`SUBAGENT_META` / `get_subagent_meta` 覆盖与兜底测试 |

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
- `custom` 事件 `data` 字典内仅**追加** `thread_id` / `parent_prompt` / `child_messages` / `final_messages` / `meta` 字段
- SSE 顶层 `{type, data}` **追加** `thread_id` 字段
- `update` 事件顶层追加 `langgraph_node` 字段（节点名），`thread_id` 统一为空字符串（updates 模式下无法精确获取子线程 ID，仅用于格式统一）
- 老客户端标准 JSON 解析**忽略未知字段**，行为不变

### 历史消息 subAgents 字段（2026-06-16 实现）

**2026-06-16 改造**：子智能体历史通过 LangGraph Checkpoint 持久化，完整还原。

**核心问题**（已解决）：
- 原 SandboxTools / FilesystemReadTools 在子智能体 `create_deep_agent()` 时使用进程内 `MemorySaver()` 实例，工具返回后内存释放
- 前端切会话调 `fetchSessionMessages` 时，sandbox / explore 等子智能体的 messages 全部丢失
- 仅主智能体的 HumanMessage/AIMessage 可恢复，`subAgents` 数组为空，`SubAgentCard` 无法渲染历史轨迹

**改造方案**（核心：复用 LangGraph 原生 checkpointer）：
- 子智能体的 thread_id == 父 LLM 调该工具时的 `tool_call_id`（沿用 2026-06-15 已有的设计）
- `create_deep_agent(checkpointer=await get_async_checkpointer())` 切换为全局共享 checkpointer
- 全局 checkpointer 同时被主智能体使用（共享同一张 `checkpoints` 表），LangGraph 自动按 thread_id 隔离
- PostgreSQL 模式：子智能体 messages 落库，跨进程跨重启可恢复
- 内存模式：单进程内可恢复，重启清空（与原行为一致）

**实现路径**：
| 文件 | 改动 |
|------|------|
| `app/core/tools/SandboxTools.py:842` | `MemorySaver()` → `await get_async_checkpointer()` |
| `app/core/tools/FilesystemReadTools.py:249` | `MemorySaver()` → `await get_async_checkpointer()` |
| `app/shared/utils/memory/checkpoint_history.py` | 新增 4 个静态/类方法：`get_subagent_history` / `merge_main_and_subagent_messages` / `collect_subagent_thread_ids_for_cleanup` / `_is_ai_message` / `_extract_ai_tool_call_ids`；改造 `_convert_message_to_dict` 兼容 `type(msg).__name__` 匹配（防御测试 Mock） |
| `app/shared/routers/session_router.py` | `get_session_messages` 重写：从 `graph.aget_state()` 拿原始 LangChain 消息 → 转换为主消息列表 → 调用 `merge_main_and_subagent_messages` 按时序插入子智能体消息；`delete_session` / `admin_delete_session` 在删主 thread 前调用 `collect_subagent_thread_ids_for_cleanup` 遍历 AIMessage.tool_calls，逐个 `adelete_thread(sub_tid)` |
| `app/tests/shared/test_session_messages_subagent.py`（新增） | 6 个整合测试：合并子智能体 / 无 tool_call 不插入 / limit 作用于合并后总数 / 401 / 403 / delete 清理子 thread |
| `app/tests/shared/utils/memory/test_checkpoint_history_subagent.py`（新增） | 17 个单元测试：`_is_ai_message` / `_extract_ai_tool_call_ids`（OpenAI/Anthropic/content_blocks 三种来源）/ `get_subagent_history` / `merge_main_and_subagent_messages` / `collect_subagent_thread_ids_for_cleanup` |

**返回结构（前端兼容，老字段保留）**：
```json
{
  "session_id": "...",
  "messages": [
    {"id": "...", "type": "user", "role": "user", "content": "..."},
    {"id": "...", "type": "ai", "role": "assistant", "content": "...",
     "tool_calls": [{"name": "sandbox", "id": "call_xxx", "args": {}}]},
    // === 2026-06-16 新增：按时序紧跟的子智能体消息流 ===
    {"type": "subagent", "role": "subagent",
     "thread_id": "call_xxx", "tool": "sandbox",
     "parent_message_id": "ai-msg-1",
     "messages": [...], "total": 5,
     // 2026-06-18 新增：展示元信息由后端统一提供
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

**2026-06-16-2 修复：历史 subagent 卡片渲染不显示**：
- **核心问题**：`MessageBubble` 中 `subAgentsByGroup` 通过 `mergedTimeline.tool` group 查找 subAgent；后端 `_convert_message_to_dict` **不会**把 `AIMessage.tool_calls` 写入 `timeline.tool`，因此历史恢复时 timeline 完全没有 tool group → `subAgentsByGroup` 返回空 → `<SubAgentCard>` 不渲染
- **修复方案（前端兼容优先，零后端变更）**：
  1. `web/Agent/src/components/MessageBubble.vue` 新增 2 个 computed + 2 个独立渲染位：
     - `hasTimelineToolGroupContainingSubAgents`：守卫变量，避免双卡片
     - `orderedSubAgentsForRender`：**仅**过滤 `isHistory === true` 的 subAgent（流式响应不会被抢渲染）
     - timeline 模式（v-if=hasTimeline 块内）模板最后新增 `<div class="timeline-subagent-list-history">` 渲染位
     - 降级模式（v-else 块内）同样新增渲染位
     - 新增 CSS：`.timeline-subagent-list-history { margin-top: 8px; }`
  2. `web/Agent/src/utils/sseParser.js` `convertSubAgentHistoryToAiSubAgent` 增强：
     - 新增 `extractFirstUserPrompt(messages)` 内部工具：从 `messages` 列表首条 `type/role === 'user'` 消息的 `content`（支持字符串 / 内容块列表）兜底提取 `parentPrompt`
     - 后端暂未返回 `parent_prompt` 字段时，SubAgentCard 顶部"父提问预览"不再为空
- **设计原则**：
  - 流式响应（`isHistory` 缺省）仍走 `subAgentsByGroup` 路径，不受新代码影响
  - 历史恢复（`isHistory === true`）走新增独立入口，与 `subAgentsByGroup` 互斥（`hasTimelineToolGroupContainingSubAgents` 守卫）
  - 完全前端修复，不影响后端 API 契约，向后兼容

**测试结果（2026-06-16-2 累计）**：
- 后端：`pytest app/tests/shared/...` 26 个相关测试全部通过；不影响 58 个 sandbox / 38 个 subagent 相关既有测试
- 前端：`vitest` 302/305 通过；
  - `sseParser.subagentHistory.test.js` 23 个（新增 8 个 parentPrompt 兜底用例）
  - `MessageBubble.spec.js` 32 个（新增 5 个独立渲染位用例）
  - 3 个 `App.interrupt.spec.js` 失败为预存在问题（端口 3000 未启动，与本改造无关）

**2026-06-16-3 修复：普通工具误渲染为 SubAgentCard**

**根因**：`merge_main_and_subagent_messages` 对所有 `tool_call` 无差别生成 `type:"subagent"` 元素，未判断 `tool` 是否属于子智能体工具集。普通工具（如 `generate_report`）的 tool_call 也会被错误包装，前端 `isSubAgentHistoryItem` 仅校验 `type` 和 `thread_id`，无 tool 过滤，最终渲染为 `SubAgentCard`（点击触发 `SubAgentDrawer`），而非期望的 `ToolCallCard`（"普通工具 N 步 已完成" 样式）。

**修复**：仅改后端，前端代码与测试均不动（按用户决策）。
- 新建 [app/core/tools/subagent_registry.py](file:///e:/laboratory/AI/Agents/feature-agent-core/app/core/tools/subagent_registry.py) 作为子智能体工具**集中注册表**（single source of truth）：
  - 常量 `SUBAGENT_TOOL_NAMES = frozenset({"sandbox", "explore", "query_knowledge"})`（不可变，防止运行期误改）
  - 函数 `is_subagent_tool(name) -> bool`（大小写不敏感、输入防御）
  - 文件顶部 docstring 详细描述"新增子智能体工具的标准流程（5 步）"和"与前端 `web/Agent/src/utils/sseParser.js` 的 `SUBAGENT_TOOLS` 同步约束"
- 修改 [app/shared/utils/memory/checkpoint_history.py](file:///e:/laboratory/AI/Agents/feature-agent-core/app/shared/utils/memory/checkpoint_history.py)：
  - `merge_main_and_subagent_messages` 仅对注册表内工具的 `tool_call` 反查子 thread 历史
  - `collect_subagent_thread_ids_for_cleanup` 同步过滤（避免删除会话时尝试清理普通工具 thread_id + 噪音日志）
- 测试同步（仅后端，新增 12 个用例）：
  - 新建 [app/tests/core/tools/test_subagent_registry.py](file:///e:/laboratory/AI/Agents/feature-agent-core/app/tests/core/tools/test_subagent_registry.py)（**8 用例**：注册表内容 + is_subagent_tool 正/反例 + 大小写 + 输入防御 + frozenset 不可变）
  - [app/tests/shared/utils/memory/test_checkpoint_history_subagent.py](file:///e:/laboratory/AI/Agents/feature-agent-core/app/tests/shared/utils/memory/test_checkpoint_history_subagent.py) 新增 **3 用例**（merge 过滤 + collect 过滤 + 纯普通工具场景）
  - [app/tests/shared/test_session_messages_subagent.py](file:///e:/laboratory/AI/Agents/feature-agent-core/app/tests/shared/test_session_messages_subagent.py) 新增 **1 端到端用例**

**兼容性**：
- API 契约不变（仅修改返回的 `messages` 列表内容，少一些 `type:"subagent"` 元素）
- 前端代码与测试均不动（按用户决策），历史脏数据继续渲染为 SubAgentCard 但**新数据正确**
- 旧历史脏数据随会话自然淘汰（用户重新聊天后新数据正确）

**与前端 `SUBAGENT_TOOLS` 的同步机制**：
注册表文件顶部 docstring 明确列出"新增子智能体工具的标准流程"5 步骤，其中第 3 步强制要求同步修改 `web/Agent/src/utils/sseParser.js` 的 `SUBAGENT_META` 与 `SUBAGENT_TOOLS`。当前注册的 `sandbox` / `explore` / `query_knowledge` 已与前端常量对齐；`query_knowledge` 采用与 `explore` 相同的书本/文档图标与"知识库"标签。

**测试结果（2026-06-16-3 累计）**：
- 后端 `pytest`：8 + 20 + 7 = 35 个相关测试全部通过
- 全量 `pytest app/tests/`：359 passed / 2 failed，2 个失败为 pre-existing 问题（`test_config.py` 中 `test_llm_settings_default_values` 受 `.env` 中 `model_type="anthropic"` 干扰、`test_settings_agent_chat_max_concurrency_default` 默认值与 settings.py 不一致），均与本次修复无关
- 前端：未新增任何测试（按用户决策）

**2026-06-17 修复：多子智能体历史只返回最后一个（索引错位）**

**根因**：`merge_main_and_subagent_messages` 用 `enumerate(raw_main_messages)` 的 `idx` 直接访问 `main_messages[idx]`，但 `main_messages` 已过滤 ToolMessage（[session_router.py:397-401](file:///e:/laboratory/AI/Agents/feature-agent-core/app/shared/routers/session_router.py#L397-L401)），raw 与 main 长度不一致，导致：
1. 中间位置的 AI 消息的 `tool_calls` 落到 `main_messages[idx]`（User 类型）→ `type != "ai"` 触发 `continue`，**该 AI 触发的子智能体被丢失**
2. 末尾 AI 消息因 `idx >= len(main_messages)` 触发 `break`，**末尾子智能体直接被丢弃**
3. 多个子智能体场景下，最终 `merged_messages` 中只剩"恰好对齐"到正确位置的那一个，表现为"只返回最后一个"

**修复方案**（[app/shared/utils/memory/checkpoint_history.py:332-375](file:///e:/laboratory/AI/Agents/feature-agent-core/app/shared/utils/memory/checkpoint_history.py#L332-L375)）：
- 不再用 `raw idx` 索引 `main_messages`
- 改为：分别收集 `raw` 与 `main` 中所有 AI 消息的位置列表，按出现顺序一一配对
- `parent_message_index` 记录 **main 索引**，确保合并阶段 `grouped[main_idx]` 正确插入
- `paired_count = min(len(raw_ai), len(main_ai))` 兜底，避免极端边界越界

**兼容性**：
- API 契约完全不变（响应结构、`type:"subagent"` 元素形态、`parent_message_id` / `thread_id` / `tool` 字段名一致）
- 前端零改动
- 旧历史脏数据自然淘汰

**测试新增（仅后端）**：
- `app/tests/shared/utils/memory/test_checkpoint_history_subagent.py` 新增 **2 个单元测试**：
  - `test_merge_with_interleaved_tool_messages_multiple_subagents`：raw 流含 2 个 ToolMessage + 2 个子智能体（sandbox/explore），验证 8 条合并结果顺序与 `parent_message_id` 归属
  - `test_merge_with_interleaved_tool_messages_last_subagent_preserved`：raw 长度 > main 长度，验证不再 break，末尾 explore 子智能体保留
- `app/tests/shared/test_session_messages_subagent.py` 新增 **1 个端到端测试**：
  - `test_messages_multiple_subagents_with_tool_messages`：通过 mock checkpointer + mock map_agent graph，验证 `GET /api/session/{id}/messages?limit=100` 在多子智能体 + ToolMessage 场景下 `total == 8`，每条 subagent 元素 `parent_message_id` 正确指向对应 AI

**测试结果（2026-06-17 累计）**：
- 后端 `pytest`：22 (test_checkpoint_history_subagent) + 8 (test_session_messages_subagent) = **30 个相关测试全部通过**
- 全量 `pytest app/tests/`：**363 passed / 1 failed**（与 2026-06-16-3 记录相同，pre-existing 失败 `test_settings_agent_chat_max_concurrency_default` 默认值 1 vs 期望 3 受 `.env` 干扰，与本次修复无关）
- 前端：零改动

**2026-06-22 修复：SSE 路由"精确延迟中断"避免 orphan tool_calls**

**核心问题**（用户反馈）：
- 用户在 /plan 会话中点击"停止"按钮
- 父 LLM 的 AIMessage 已被 checkpoint 持久化（包含 `tool_calls`）
- 工具/子智能体尚未返回 `ToolMessage`
- 上层 SSE 路由立即 `return` 切断 `astream`，LangGraph ToolNode 被取消，`ToolMessage` 永远不写入 state
- 下次会话恢复进入 `llm_call` 节点时，messages 序列不合法，Anthropic API 返回 `invalid params, tool call result does not follow tool call (2013)`

**用户决策**：
- "如果在前端单击了中断按钮，但是当前子智能体在运行，这个时候不能完成中断，需要子智能体执行完再单击中断可以中断"
- "不是都跑完，是其中的普通工具或者子智能体跑完"
- "核心防御：pre_llm 节点 这个不添加"

**修复方案**（SSE 路由"精确延迟中断"）：
- 检测到客户端断开 → 仅标记 `disconnect_requested = True`，**不** return
- 跳过 `messages` 模式（不再 yield LLM token 给已断开的前端）
- 继续消费 `updates` 模式
- 当 `data["tools"]["messages"]` 包含 ToolMessage 时 → 当前工具/子智能体完成 → `disconnect_executed = True` → `break` 真正中断
- 依赖 LangGraph ToolNode 的"全或无"语义（context7 查询确认 `asyncio.gather` 等所有 tool_calls 完成才 yield 节点结果），多工具并行时所有工具都跑完才中断

**LangGraph ToolNode 全或无语义（context7 查询关键发现）**：
- `ToolNode.ainvoke` 用 `asyncio.gather(*coros)` 并发执行所有 tool_calls
- `outputs = await asyncio.gather(*coros)` 等待所有协程完成
- `return self._combine_tool_outputs(outputs, input_type)` 合并所有工具输出
- 因此"tools 节点完成 chunk"隐含"所有并行 tool_calls 都已执行完"，**不**需要额外数量校验

**实现路径**：
| 文件 | 改动 |
|------|------|
| `app/features/map_agent/router/map_router.py` | `generate_stream_response` 主循环重构：原立即 `return` 改为标记 `disconnect_requested`；新增 `disconnect_executed` 标志；`messages` 模式 / 非组合模式 chunk 在 `disconnect_requested` 时 `continue` 跳过；`updates` 模式新增检测 `data["tools"]["messages"]` 包含 ToolMessage → 设置 `disconnect_executed = True` → `break` 真正中断；新增 yield `client_disconnected` 标记事件；循环结束 yield `end` 事件前新增延迟中断完成日志 |
| `app/tests/features/map_agent/test_map_router_disconnect.py` | 重构为 9 个测试：原"立即断开"测试替换为"单工具延迟断开"（4 个 yield：LLM update + client_disconnected + tools update + end）；新增"多工具并行延迟断开"（验证 3 个 ToolMessage 一次性出现时触发断开）；新增"非 tools 节点 update 不触发断开"（验证 summarize / hitl_check 节点被 yield 但不触发断开）；新增"disconnect 后跳过 messages 模式"；保留原有"未断开跑完"、"无 request 兼容"测试 |
| `app/tests/features/map_agent/test_map_router_subagent_stop.py` | `test_router_disconnect_propagates_to_main_astream` 测试预期更新：原期望 `chunk_count == 2`（立即跳出）改为 `chunk_count == 5`（所有 5 个 llm_call chunk 都被消费，因为没有 tools 节点完成触发断开） |

**关键约束**：
- **不**新增 pre_llm 节点 / orphan_tool_fix 工具（用户明确否决）
- **不**修改 `agent.py` / `checkpoint_history.py`（主路径 SSE 路由修复足够覆盖 99% 场景）
- **不**修改子智能体内部 `is_disconnected` 检测逻辑（与本次修复协同工作：子智能体检测断开 → break → 构造 stopped_by_user ToolMessage → 写入 state；SSE 路由在 tools 节点完成时检测到 ToolMessage 真正断开）
- **不**引入 60s 宽限期（用户已否决）
- **不**做"超过 X 工具数量时强制中断"的数量校验（依赖 LangGraph ToolNode 的"全或无"语义保证）

**API 兼容性**：
- 既有 SSE 事件类型 `update` / `custom` / `message` / `end` / `error` / `interrupt` 不变
- 新增 `client_disconnected` 事件类型（前端可忽略，老客户端无影响）
- 前端零改动（用户决策）

**测试结果（2026-06-22 累计）**：
- 后端 `pytest app/tests/features/map_agent/test_map_router_disconnect.py`：9 passed
- 后端 `pytest app/tests/features/map_agent/test_map_router_subagent_stop.py`：4 passed, 1 skipped（async 测试需 pytest-asyncio 插件）
- 后端 `pytest app/tests/core/tools/test_sandbox_tools.py` + `test_filesystem_read_tools.py`：49 passed, 1 skipped（Docker 不可用）
- 前端：零改动

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
- **Admin 管理**（2026-06-23 / 2026-06-24 新增）：
  - `UserSettingsDialog.vue`：admin 角色可访问的「用户设置与管理」对话框；包含 6 个 Tab —— `profile`（个人设置）/ `user-management`（用户管理）/ `online-monitor`（在线监控）/ `session-query`（会话查询）/ `mcp-management`（MCP 管理，调用 `McpServerManager.vue`）/ `agent-management`（智能体管理，2026-06-24 新增，调用 `AgentManager.vue`）
  - `McpServerManager.vue`：MCP server CRUD + 方法列表 + 启禁用切换（前后端）
  - `AgentManager.vue`（**2026-06-24 新增**）：智能体管理 Tab 内容；左侧智能体列表 + 右侧三组可编辑表格（AgentConfig 字段 / State 字段 / Context 字段）；支持完整 CRUD：
    - **新增智能体**：弹窗表单（8 字段）+ 内嵌 config_schema 编辑器；调用 `fetchAgentConfigFieldTemplates` 获取 AgentConfig 字段模板做下拉选择
    - **编辑字段**：每组表格独立增删改；section = `root` / `state_fields` / `context_fields`；通过 `updateAdminAgentConfigSchema` / `addAdminAgentConfigField` / `deleteAdminAgentConfigField` 增量更新
    - **删除智能体**：含确认弹窗（保留历史会话）
    - **启用/禁用开关**：右上角 switch，立即调用 `setAdminAgentEnabled`，不进入「未保存修改」队列
- **Subagent 折叠与抽屉（2026-06-13 新增，2026-06-14 改造）**：
  - `SubAgentCard.vue`：通用子智能体折叠卡片（含沙箱），**2026-06-14 改造后挂在父 AI 气泡的 `timeline.tool` 块内**（按 toolCallId 匹配，遵循事件流时序，不再堆在会话末尾）；工具图标 + 父 prompt 预览 + 状态徽章 + 耗时 + 消息数 + "查看详情" 入口；点击 emit('click', subAgent)
  - `SubAgentDrawer.vue`：通用子智能体详情 Push Drawer；**2026-06-14 改造合并原 `SandboxDrawer` 职责**（`SandboxProgress` / `SandboxDrawer` / `SandboxEventItem` 三个组件已删除），沙箱专属摘要与事件时间线 **2026-06-15 再次精简后整段移除**；分层展示父 prompt / HumanMessage / AIMessage（含 tool_calls 决策区） / ToolMessage 三类消息 + 底部耗时/消息数/工具调用次数摘要；`renderMessageContent` 扩展支持 LangChain 0.3+ 多模态 ContentBlock（text / thinking / tool_use / tool_result）
- **普通工具卡片（2026-06-15 新增）**：
  - `ToolCallCard.vue`：普通（非 subagent）工具调用专属卡片，与 `SubAgentCard` 视觉风格对齐；**关键差异：不触发抽屉**（普通工具没有子智能体消息流），body 以"步骤"形式逐步展示每条 SSE 事件（tool_start / tool_progress / tool_stop / tool_error）；头部扳手图标在 `status='running'` 时使用 SubAgentCard 同款 `subagentIconBounce` 闪动动画；默认 `running` 展开、`success/error` 折叠
- **动态排队提示横幅（2026-06-15 新增）**：
  - `QueueStatusBanner.vue`：**挂在 ChatArea 与 InputBox 之间**（用户要求位置），实时显示 Agent 聊天接口的并发排队状态；黄色系背景 + 橙色感叹号图标 + 位置 badge（带 2s pulse 动画）；Props：`queueStatus: {event, waitingCount, activeCount, maxConcurrency, position, timestamp}` + `isVisible: Boolean`；进场 `slide-down 200ms` / 退场 `fade-out 200ms`；数据由后端 SSE `queue` 事件（`onQueueEvent` 回调）或 HTTP 429 响应驱动
- **视图**（`src/views/`）：`LoginView.vue`、`RegisterView.vue`

### 工具函数（src/utils）

- **`api.js`**：登录/注册/验证码/登出/refresh/validate；会话创建/列表/删除/详情/标题/附件/消息；文件上传（普通 + 分片 + base64）/下载/列表/删除；SSE `chatStream`（Task 15 起改用 `/api/agent/chat`，新增 `agentName` 参数默认 `map_agent`）/ `knowledgeChatStream`（仍用 `/api/map/knowledge-chat`）；`X-Session-ID` 头注入；附件元数据组装
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
  - `api.mcp.test.js`（2026-06-23 新增，同日扩展）：MCP 管理 API 封装（**18** 用例 = 8 happy-path URL/方法/请求体验证 + 1 `updateMcpServer` PUT body + 9 失败路径验证 `detail` 错误消息）
  - `sseParser.test.js`：SSE 解析（含 Python 字面量兼容）
  - `subAgentParser.test.js`（2026-06-13 新增，2026-06-14 扩展）：subagent 解析（custom 事件维护 subAgents 列表 + sandbox_summary 合并 + 工具函数，**14** 用例）
  - `SubAgentCard.spec.js`（2026-06-13 新增，2026-06-14 扩展）：折叠卡片（**11** 用例）
  - `SubAgentDrawer.spec.js`（2026-06-13 新增，2026-06-14 扩展，2026-06-15 精简）：独立 Push Drawer（**19** 用例）
  - `MessageBubble.spec.js`（**2026-06-14 新增**）：timeline.tool 内按 toolCallId 渲染 SubAgentCard 等（5 用例）
- **项目历史**：后端 17/17 + 前端 73/73 全部通过（参见 "HITL 流程" 章节）
- **2026-06-13 更新**：后端新增 `test_subagent_message_extractor.py` 22 用例通过；前端 SubAgentCard/SubAgentDrawer/subAgentParser 共 29 用例通过；累计前端 111/111 全量通过
- **2026-06-16 更新**：子智能体历史持久化实现完成。后端新增 2 个测试文件（`test_checkpoint_history_subagent.py` 17 用例 + `test_session_messages_subagent.py` 6 用例）全部通过；前端新增 `sseParser.subagentHistory.test.js` 15 用例全部通过；累计前端 281/284 通过（3 个 `App.interrupt.spec.js` 失败为预存在问题，与本改造无关）
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
  - **Bug 修复（核心）**：`MessageBubble.vue` 的 `subAgentsByGroup` computed **未过滤非 subagent 工具事件**，导致 `sseParser.updateSubAgentFromCustomEvent` 对所有 tool 名都创建 subAgents 条目（含普通工具），普通工具（如「生成报告」）会被 `getSubAgentsForGroup` 按 toolCallId 匹配并渲染为 `SubAgentCard`，点击触发 `SubAgentDrawer`。修复：在 `subAgentsByGroup` 循环中增加 `if (!isSubAgentItem(item)) continue` 过滤（判断 `item.data.tool` 是否属于 SUBAGENT_TOOLS），仅 subagent 工具（sandbox / explore / query_knowledge）才走 SubAgentCard 路径
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

- **2026-06-15 聊天并发排队提示 + HITL interrupt 卡死修复**：
  - **后端变更**（`app/core/concurrency/`）：
    - `agent_concurrency_queue.py` 新增 `enqueue_time()` / `position()` / `snapshot()` 方法与 `_waiter_tasks` / `_enqueue_times` 内部状态
    - `chat_concurrency_dependency.py` 改造为双模式（`mode="sse" | "http"`）+ HITL 早期释放句柄 `request.state.concurrency_release_handle`
    - `map_router.py` 新增 `_stream_with_queue` 生成器，在 yield interrupt 业务事件前调用 release_handle
    - `contract_router.py` 新增 `_chat_concurrency_http_dep()` 工厂函数，传 `mode="http"`
  - **前端变更**（`web/Agent/src/`）：
    - 新增 `components/QueueStatusBanner.vue`（动态排队提示横幅）
    - `App.vue` / `KnowledgeApp.vue` / `components/KnowledgeChat.vue` 集成 queueStatus 状态机 + onQueueEvent 回调 + HITL reader.cancel + 429 处理
    - `utils/sseParser.js` 新增 `QUEUE_EVENT_TYPES` / `isQueueEvent` + `processSSEEvent` 第三参 `callbacks.onQueueEvent`
    - `utils/api.js` `chatStream` / `knowledgeChatStream` 错误处理扩展：保留 `err.status` / `err.detail`
  - **测试新增**：后端 `test_agent_concurrency_queue.py` +4 用例 / `test_chat_concurrency_dependency.py` +9 用例（HITL 核心：`test_sse_dependency_releases_on_hitl_interrupt_path`）；前端 `QueueStatusBanner.spec.js` +10 用例 / `App.interrupt.spec.js` +4 用例（HITL 核心：`test_handleSendMessage_calls_reader_cancel_on_interrupt`） / `sseParser.test.js` +3 用例。累计前端约 +17 → **223/223 全量通过**（Vite build 成功，后端约 +13 → **143 passed**）

- **2026-06-15 第八次：知识库气泡与输入框宽度对齐修复**（用户反馈缩小时气泡比输入框宽）：
  - **根因**：`KnowledgeApp.vue` 的 `.chat-input-area`（`padding: 16px 40px 24px`）内部包了带相同 padding 的 `ProfileInputBox`（`.profile-input-box-container` `padding: 16px 40px 24px`），合计 80px 水平内边距，而 `.chat-body` 仅 40px，缩小时输入框比气泡窄 40px
  - **修复**：`.chat-input-area` 的 `padding` 从 `16px 40px 24px` 改为 `0`，由内部的 `ProfileInputBox`/`HumanApprovalBox` 自持完整 padding
  - **KnowledgeChat.vue**：`.chat-body` padding 从 `16px`（仅 16px 水平间距）改为 `24px 40px`（与主界面 ChatArea 对齐）；`.messages-container` 追加 `max-width: 900px; margin: 0 auto;`（原缺失导致无宽度约束）
  - **测试**：219/222 通过（3 个 pre-existing failure 为 `App.interrupt.spec.js` happy-dom AbortError 环境问题）；Vite build 成功

- **2026-06-15 第九次：聊天停止按钮（中断 LLM 生成）**（用户需求：大模型生成过程中可点击按钮中断）：
  - **核心设计**：发送按钮在 `isStreaming=true` 时切换为「停止按钮」，点击触发 `reader.cancel()` 断开 SSE 连接；后端 `map_router.py` 在 `async for chunk` 主循环检测 `request.is_disconnected()`，客户端断开时立即 `return` 跳出 LangGraph `astream`，避免无效算力消耗。停止按钮使用与发送按钮**相同的 `--color-accent` 紫色调**（仅图标和缩放阴影脉冲动画区分），保持「同一按钮的两种状态」视觉一致性。
  - **后端改动**（`app/features/map_agent/router/map_router.py`）：
    - `generate_stream_response` 签名追加 `request: Request = None` 形参（默认值 None 保持向后兼容）
    - `async for chunk in stream` 循环开头加 `request.is_disconnected()` 检测：客户端断开时 `logger.info` 记录 + `return` 跳出循环
    - `/api/map/chat` 与 `/api/map/knowledge-chat` 两个端点（4 个 call site：正常 + resume × 2 端点）都传 `request=request`
  - **前端改动**（3 条聊天路径全覆盖）：
    - **`web/Agent/src/components/InputBox.vue`**（主聊天 App.vue 路径）：
      - `canSend` 计算属性移除 `if (props.isStreaming) return false` 分支（停止按钮必须可点）
      - `defineEmits` 追加 `'stop'` 事件
      - 按钮模板改为三态 class：`send-mode` / `stop-mode` / `disabled`，按 `isStreaming` 切换图标（`send-icon` 纸飞机 vs `stop-icon` 实心方块 rect 5,5-15,15）
      - `:disabled` 改为 `!canSend && !isStreaming`（流式时按钮可点）
      - 监听 `isStreaming` prop：流式时 click → `emit('stop')`，非流式时 click → `handleSend()`
    - **`web/Agent/src/components/ProfileInputBox.vue`**（KnowledgeApp.vue 独立 SPA 路径）：同款改造
    - **`web/Agent/src/components/KnowledgeChat.vue`**（App.vue → KnowledgePage → KnowledgeChat Tab 路径）：
      - 内部自持 `currentReader`（替代原 `let reader = null`），`handleSend` + `handleApprovalSubmit` 都改用 `currentReader`
      - 新增 `handleStop()` 函数：cancel reader + 标记 AI 消息 ended + 追加 `[生成已被用户中止]` + `internalStreaming = false`
      - 按钮模板同款三态切换
    - **`web/Agent/src/App.vue`**：
      - 提取模块级 `let currentStreamReader = null`（替代原 `let reader = null`，让 handleStopMessage 跨函数访问）
      - `handleSendMessage` + `handleApprovalSubmit` 改用 `currentStreamReader`，finally 块追加 `currentStreamReader = null`
      - 新增 `handleStopMessage()` 函数（与 KnowledgeApp.vue 同款实现）
      - `<InputBox>` 模板追加 `@stop="handleStopMessage"` 监听
    - **`web/Agent/src/KnowledgeApp.vue`**：
      - 模块级 `let currentStreamReader = null` + `startChatStream` 改用 `currentStreamReader`，加 `.finally(() => { currentStreamReader = null })` 兜底
      - 新增 `handleStopMessage()` 函数
      - `<ProfileInputBox>` 两处绑定（welcome section + chat section）都追加 `@stop="handleStopMessage"`
  - **CSS 样式**（3 个 InputBox/ProfileInputBox/KnowledgeChat 同款 `.stop-mode`）：
    - 背景色 `var(--color-accent)`（与发送模式同色，非红色）
    - hover `var(--color-accent-hover)` + 缩放 1.08 + 紫色阴影
    - `stopPulse` keyframes：背景色不变，仅 `transform: scale(1) ↔ scale(1.06)` + `box-shadow` 0px ↔ 8px 扩散
    - 图标 14×14 白色实心方块（rect 5,5 10×10 rx=1.5）
  - **停止后 UI 反馈**：AI 消息 `ended = true` + `isThinkingActive = false` + `text` 字段末尾追加 `\n\n[生成已被用户中止]`（用 `text.includes()` 防重复）
  - **测试新增**（按 HARD RULE 同步）：
    - **后端**：`app/tests/features/map_agent/test_map_router_disconnect.py`（**5 用例**）
      - P0 `test_generate_stream_response_importable` / `test_generate_stream_response_signature_accepts_request`
      - P1 `test_generate_stream_response_stops_on_client_disconnect`（mock `is_disconnected` 第二次返回 True，验证只 yield 1 个 chunk 后跳出）
      - P1 `test_generate_stream_response_runs_to_end_when_not_disconnected`（mock 始终 False，验证 yield 全部 chunks + end 事件）
      - P1 `test_generate_stream_response_works_without_request`（request=None 向后兼容）
    - **前端**（4 个新 spec 文件，共 **28 用例**）：
      - `web/Agent/src/components/__tests__/InputBox.stop.spec.js`（**7 用例**）：importable / 发送模式图标 / 停止模式图标 / 流式点击 emit('stop') / 非流式点击不 emit('stop') / 无输入 disabled / 流式 enabled
      - `web/Agent/src/components/__tests__/ProfileInputBox.stop.spec.js`（**7 用例**）：与 InputBox 同款
      - `web/Agent/src/components/__tests__/KnowledgeChat.stop.spec.js`（**6 用例**）：importable / 发送模式 / 内部流式时 stop-mode / `handleStop` 取消 reader + 标记消息 + 不重复追加标记 + 非流式 noop
      - `web/Agent/src/components/__tests__/App.stop.spec.js`（**8 用例**）：覆盖 App.vue + KnowledgeApp.vue 的 `handleStopMessage` 行为（cancel 调用 / 错误吞掉 / 无 reader / 空 messages / 不重复标记等）
  - **兼容性说明**：
    - 第三方 iframe / portal 调用方不感知 stop 按钮（不会主动 stop 时按原行为运行到底）
    - HITL 场景：HITL interrupt 走 `await currentStreamReader.cancel()` 路径与 stop 按钮共用，最终都会触发后端 `is_disconnected()` + LangGraph 跳出
    - 排队场景：客户端断开后 `dep.aclose()` 触发 `chat_concurrency_dependency` finally 释放许可，无需额外处理
  - **测试结果**：后端 5/5 通过；前端 28/28 新增用例通过（其他 pre-existing failures 维持不变）；Vite build 成功

### 2026-06-16 KnowledgeApp 回归修复：`startChatStream` 外层 `.finally()` 与 read() 递归产生竞态

**背景**：上述停止按钮提交（e940ee1）在 `KnowledgeApp.vue:startChatStream` 链式末尾追加了 `.finally(() => { currentStreamReader = null })`，**导致 KnowledgeApp 独立 SPA 模式下用户输入任何问题都立即显示「不好意思，刚刚出了点小故障，可以晚点再问我一遍。」**。

**根因（Promise 链微任务竞态）**：
1. `startChatStream` 原实现：`.then(stream => { currentStreamReader = ...; read() }).catch(...).finally(() => { currentStreamReader = null })`
2. `read()` 内部**同步**调用 `currentStreamReader.read().then(...)` 启动异步流读取后立即 return
3. 外层 `.then(stream => { ...; read() })` 同步部分 resolve → 微任务阶段 `.finally` 立即执行 → `currentStreamReader = null`
4. 网络数据到达 → `read()` 内部 `.then` 回调执行 → `read()` 递归调用 `currentStreamReader.read()` → **`currentStreamReader` 已是 `null`** → 抛 `TypeError`
5. 外层 `.catch` 捕获 → `aiMsg.error = '不好意思，刚刚出了点小故障...'` → MessageBubble 显示固定错误文案

**为什么 App.vue / KnowledgeChat 正常**：它们使用 `async/await + while(true) { await currentStreamReader.read() } + try/catch/finally` 模式，`finally` 在 `try` 完整走完才执行，**不会与 read() 递归产生竞态**。

**修复**（`web/Agent/src/KnowledgeApp.vue`）：
- `startChatStream` 重构为 `async/await + while(true) + try/catch/finally` 模式，与 App.vue / KnowledgeChat 保持一致
- 删除外层 `.then().catch().finally()` 链式 + 嵌套 `read()` 递归
- `finally` 中清理 `currentStreamReader` 与重置 `isStreaming`
- `handleProfileSend` / `handleApprovalSubmit` 改为 `await startChatStream(...)`
- `try` 内单事件 `JSON.parse` 失败时 `console.warn` 记录日志，便于排查（不影响后续事件处理）

**附带清理**（`web/Agent/src/components/KnowledgeChat.vue` `handleApprovalSubmit` 内 readStream）：
- readStream 本来就使用 `async/await + try/catch/finally` 模式，**不存在 finally 竞态**
- 仅追加 `JSON.parse` 失败时的 `console.warn` 日志，与 KnowledgeApp 重构保持防御一致性

**测试新增**：`web/Agent/src/components/__tests__/KnowledgeApp.stream.spec.js`（**11 用例**）：
- P0：`test_start_chat_stream_normal_completion_does_not_set_error` / `test_start_chat_stream_finally_runs_after_all_reads_finally`（核心：验证 finally 在所有 read 后才执行）/ `test_start_chat_stream_reader_error_sets_error_msg`
- P1：`test_start_chat_stream_multiple_chunks_accumulates_text` / `test_start_chat_stream_handles_interrupt_without_error` / `test_start_chat_stream_thinking_blocks_written` / `test_start_chat_stream_handles_end_event` / `test_start_chat_stream_handles_parse_error_gracefully` / `test_start_chat_stream_clears_reader_in_finally` / `test_start_chat_stream_empty_stream_completes`
- P2：`test_start_chat_stream_simulates_real_message_example_txt`（模拟 message例子.txt 多 chunk 场景：16 个 thinking 增量 + signature + 9 个 text 增量，验证完整文本"你好！请问有什么可以帮你的？" 与 thinking 累加"用户再次说"你好"，这只是一个问候。"）+ `test_start_chat_stream_chunks_split_across_boundary`

**测试结果**：新增 11/11 通过；全量 269 测试中 266 通过（3 个 pre-existing failures 来自 `App.interrupt.spec.js` 的 happy-dom `ReadableStream.cancel()` 兼容性，与本修复无关）

## 子智能体停止机制（2026-06-15 扩展）

**背景**：上一节"停止按钮（中断 LLM 生成）"仅停止主智能体的 LangGraph astream，但子智能体（sandbox / explore）工具函数内的 `for chunk in child_agent.stream(...)` 是同步 for 循环，没有任何停止信号感知。子智能体会一直运行直到自然结束，消耗 LLM token、占用 Docker 容器，停止按钮无法真正中断。

**目标**：让前端停止按钮的 `reader.cancel()` 信号穿透到子智能体层，使前端停止按钮真正中断所有 LLM 生成。

### 核心机制：contextvars 传递 Request

**新增文件**：`app/core/tools/_stop_signal.py`

通过 ``contextvars.ContextVar`` 在主路由入口挂 FastAPI Request，工具函数（sandbox / explore）内通过 ``get_current_request()`` 取出，调用 ``await request.is_disconnected()`` 检测客户端断开。

- asyncio 任务在同一 context 内自动继承 ContextVar，多请求并发时各请求独立隔离，无竞态
- 同步工具函数也能兼容（先 `get_current_request()` 取出 Request，在需要时 `await is_disconnected()`）
- finally 块必须 reset，避免后续请求继承到错误的 request 引用导致内存泄漏 + 跨请求误判

**API**：

```python
from app.core.tools._stop_signal import (
    set_current_request,   # 主路由入口：挂 request
    reset_current_request, # finally 块：清理（传 token）
    get_current_request,   # 工具函数：取出（可能为 None）
)
```

### sandbox / explore 工具 async 化

**`app/core/tools/SandboxTools.py`** + **`app/core/tools/FilesystemReadTools.py`** + **`app/features/map_agent/tools/MapTools.py`** 改造：

- ``def sandbox`` → ``async def sandbox``（同步 for → async for + astream）
- ``def explore`` → ``async def explore``（同上）
- astream 循环内每 ``_STOP_CHECK_INTERVAL = 5`` 个 chunk 检查一次 ``request.is_disconnected()``
- 客户端断开时立即 break + 推送 ``tool_stop`` 事件，``data.status = "stopped_by_user"``（区别于 "success" / "failure"）
- sandbox 停止时**必须 cleanup middleware**（Docker 容器清理），避免容器残留

**停止事件数据格式**（`tool_stop` 事件）：

```json
{
  "status": "stopped_by_user",
  "result": { "answer": "子智能体已被用户中止", ... },
  "duration_ms": ...,
  "final_summary": { "current_step": 0, "status_message": "已被用户中止", ... },
  "thread_id": "...",
  "final_messages": [...],   // 保留 subagent 字段，前端仍能看到中间消息
  "parent_prompt": "..."
}
```

### map_router 挂载 ContextVar

**`app/features/map_agent/router/map_router.py`** 改造：

- `generate_stream_response` 函数入口 `set_current_request(request)`，把 FastAPI Request 挂到 ContextVar
- finally 块 `reset_current_request(cv_token)`，避免后续请求继承错误引用
- 即使 `is_disconnected()` 触发 return 提前退出，也保证清理

### 客户端状态显示

**`web/Agent/src/components/SubAgentCard.vue`** + **`web/Agent/src/components/ToolCallCard.vue`** 改造：

- 新增 ``status === 'stopped_by_user'`` 状态映射：显示"已中止"文本
- 新增 CSS class ``.stopped_by_user``：橙色徽章（区别于 success 绿色、error 红色、running 紫色）
- stopped_by_user 状态**静态显示**（无 pulse 动画），与 running 区分

**`web/Agent/src/utils/sseParser.js`** 改造：

- `updateSubAgentFromCustomEvent` 中 tool_stop 事件状态判定逻辑扩展：
  - 优先级（向后兼容）：`stopped_by_user` > `error` / `failure` > 其他（含无 status / `success`）→ success
  - 旧事件无 status 字段默认 success（向后兼容普通工具 tool_stop）

### 测试覆盖

**新增测试文件**：

| 文件 | 用例数 | 覆盖 |
|------|--------|------|
| `app/tests/core/tools/test_stop_signal.py` | 10 | contextvar 基础读写、set/reset 语义、并发隔离、异常 finally 兜底 |
| `app/tests/core/tools/test_subagent_stop.py` | 7 | sandbox 5 用例 + explore 2 用例：客户端断开、客户端未断开、无 request 场景、subagent 字段保留、Command ToolMessage 内容 |
| `app/tests/features/map_agent/test_map_router_subagent_stop.py` | 5 | generate_stream_response 挂载/清理 ContextVar、disconnect 跳出循环、无 request 兼容、并发请求隔离 |

**更新测试文件**：

| 文件 | 改动 |
|------|------|
| `app/tests/core/tools/test_sandbox_tools_config.py` | `stream` → `astream`，`SandboxTools.sandbox` → `asyncio.run(SandboxTools.sandbox(...))`（async 适配） |
| `app/tests/core/tools/test_sandbox_no_text_reply_fix.py` | 同上 + 同步生成器 → async 生成器 |
| `web/Agent/src/components/__tests__/SubAgentCard.spec.js` | 新增 2 用例：stopped_by_user 状态显示"已中止" + 徽章 class + 无 pulse 动画 |
| `web/Agent/src/components/__tests__/ToolCallCard.spec.js` | 新增 2 用例：stopped_by_user 状态显示"已中止" + 徽章 class |

**conftest.py 扩展**（支撑 explore 测试）：

- 新增 mock `langchain.agents` / `langchain.agents.middleware` / `langchain.agents.middleware.types` 模块
- 把 `FilesystemMiddleware` / `FilesystemBackend` 也注册到 `deepagents` 顶层（`from deepagents import FilesystemMiddleware` / `from deepagents.backends import FilesystemBackend`）
- `_FilesystemBackend.__init__` 接受任意参数（explore 工具传 `root_dir` / `virtual_mode`）
- `langchain_core.tools.tool = lambda *args, **kwargs: lambda func: func`（encoding_safe_file_search 依赖）

### 兼容性

- **旧工具 tool_stop 事件**（无 status 字段）：默认 success 状态（向后兼容）
- **HuggingFace 客户端**：不感知停止按钮，行为不变
- **HITL 场景**：与现有 interrupt 路径共存（前端 `reader.cancel()` 触发后端 `is_disconnected()`，主 astream 跳出后子智能体也跳出）
- **第三方 iframe / portal 调用方**：不感知停止按钮，按原行为运行到底

### 已知工程实践

- **conftest 下 @tool 是 identity**：`@tool` 装饰器在 conftest 中被 mock 为 `lambda *args, **kwargs: lambda func: func`，所以 `sandbox` / `explore` 在测试环境就是原 async 函数。生产环境（conftest 不生效时）`@tool` 会把 async 函数包装为 `StructuredTool` 并保留 `.coroutine` 指向原函数。两种环境下 `asyncio.run(SandboxTools.sandbox(prompt, runtime))` 都能工作
- **MagicMock 属性赋值**：`mock_agent.astream = fake_astream` 后，`mock_agent.astream` 返回 fake_astream，调用 `mock_agent.astream(args, kwargs)` 拿 async generator object。`call_args_list` 记录的是直接调用，需要用 `mock_writer.return_value.call_args_list` 才能拿到 sandbox/explore 函数内部 `writer(...)` 的调用
- **contextvar reset LIFO 语义**：`set(A) → token1, set(B) → token2, reset(token2) → get() == A, reset(token1) → get() == default`

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
- **`tests/integration/`**：端到端集成测试
  - `test_end_to_end_auth.py`：认证流程（注册→登录→validate→logout）
  - `test_agent_chat_e2e.py`：`/api/agent/chat` 端到端测试（2 用例：SSE 流式响应正常返回 / 未知 agent 返回 404）

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

## Skill 系统（2026-06-20 设计中，2026-06-21 落地，v2 bootstrap 配置化 + 子智能体覆盖）

从 opencode skill 系统迁移而来的 LangChain/LangGraph 等价实现，提供可按需加载的工作流指引（如 brainstorming、TDD、debugging 等），通过 `<EXTREMELY_IMPORTANT>` 包裹的 bootstrap 引导模型调用 `load_skill` 工具。**v2 关键变化**：bootstrap 改为配置化 markdown 文件读取；新增子智能体 `skills/` 与 `config/bootstrap.md` 覆盖机制；删除 using-superpowers 特殊处理。

### 模块位置

```
app/core/skills/
├── __init__.py                 # 导出 SkillsService / BootstrapProvider / load_skill / read_skill_file / SkillsAwarePrompt / render_available_skills_block；当前对未落地的子模块使用 try/except 条件导入
├── schemas.py                  # SkillInfo / SkillsConfig（新增 bootstrap_path 字段）
├── loader.py                   # SkillDiscovery（扫描 + frontmatter 解析，用 PyYAML 自实现，**不引入 python-frontmatter**）
├── bootstrap.py                # BootstrapProvider：按 4 级优先级读取 bootstrap.md 并用 <EXTREMELY_IMPORTANT> 包裹
├── tool.py                     # load_skill（按名称加载 SKILL.md 正文+文件清单） + read_skill_file（按绝对路径读取 skill 目录下的资源文件）
└── bootstrap.md                # 系统默认 bootstrap 内容（Tool Mapping）
```

### 默认扫描根（全局维度，后扫描覆盖先扫描）

| 根 | 说明 |
|---|---|
| `<project>/app/skills/**/SKILL.md` | 项目内置 skill，由代码仓库管理 |
| `<project>/.agents/skills/**/SKILL.md` | 兼容 opencode 外部规范 |
| `settings.skills_paths`（逗号分隔） | 用户运行时扩展，支持 `~/` 展开、绝对路径、相对项目根 |

### 子智能体覆盖机制（v2 新增）

| 路径 | 作用 | 与全局的关系 |
|---|---|---|
| `app/features/<agent>/skills/<name>/SKILL.md` | 子智能体专属 skill | **完全覆盖**全局默认根扫描（仅扫描该目录，不追加 `app/skills` 与 `.agents/skills`） |
| `app/features/<agent>/config/bootstrap.md` | 子智能体 bootstrap 重写 | 优先级**高于**全局默认 `app/core/skills/bootstrap.md` |
| `app/features/<agent>/config/prompts.py` | Agent 专属提示词（现有） | 不变 |

**两者互相独立**：可单独存在 skills/ 覆盖 skill 扫描，或单独存在 bootstrap.md 覆盖 bootstrap；也可同时存在。

### Skill frontmatter 格式

```yaml
---
name: brainstorming          # 必填，全局唯一
description: |               # 可选；建议填，便于 <available_skills> 展示
  Help turn ideas into fully formed designs...
---
[SKILL 正文 markdown]
```

### 系统提示词拼接（v2：`SkillsAwarePrompt.build()`）

```
┌─────────────────────────────────────────────┐
│  BASE_SYSTEM_PROMPT                         │  ← 通用规则（与现有架构一致）
├─────────────────────────────────────────────┤
│  self.system_prompt + context.system_prompt │  ← Agent 专属 + 动态层（与现有架构一致）
├─────────────────────────────────────────────┤
│  <EXTREMELY_IMPORTANT>...bootstrap.md...</> │  ← 本次新增：工具映射（bootstrap 在前）
├─────────────────────────────────────────────┤
│  <available_skills>...</available_skills>   │  ← 本次新增：列已注册 skill 的 name/description/location
└─────────────────────────────────────────────┘
```

### Bootstrap 优先级链（4 级）

1. **子智能体** `app/features/<agent>/config/bootstrap.md`（最高）
2. **用户自定义全局** `settings.skills_bootstrap_path`（如 `~/my_bootstrap.md`）
3. **系统默认** `app/core/skills/bootstrap.md`（项目仓库内置）
4. **代码内置 fallback** `_FALLBACK_TOOL_MAPPING`（项目实际工具映射字符串，包含 `sandbox` / `explore` / `load_skill` / `todowrite`）

### 与 opencode 的差异

| 项 | opencode | 本项目 |
|---|---|---|
| 权限系统 | `ctx.ask({permission:"skill"})` | **无**；保留 `available(name_filter)` 扩展点 |
| bootstrap 注入点 | unshift 到首条 user message | 拼接到 system_prompt 末尾（语义更清晰，符合 LangChain 角色约定） |
| bootstrap 内容来源 | `using-superpowers` SKILL.md 正文 + 硬编码 Tool Mapping | **配置化 markdown 文件**：4 级优先级链（子智能体 > 用户全局 > 系统默认 > 代码 fallback） |
| 子智能体覆盖 | 无 | **支持**：`app/features/<agent>/skills/` + `config/bootstrap.md` |
| 远程 skill 拉取 | `cfg.skills.urls` + discovery.ts::pull | **不做**（MVP）；后续按 opencode 协议扩展 |
| `.claude/skills` 兼容 | 是 | **否**；项目使用自有 `.agents/skills` 约定 |
| 前置依赖 | TypeScript Runtime | 仅 PyYAML（项目已装），无需新增第三方包 |

### 标签使用约定

| 标签 | 是否用于 skill 系统 | 备注 |
|---|---|---|
| `<EXTREMELY_IMPORTANT>` | ✅ 用于 bootstrap 包裹层 | opencode 仅生成不解析；superpowers 插件约定格式 |
| `<available_skills>` | ✅ 用于能力清单 | opencode 仅生成不解析 |
| `<system-reminder>` | ❌ **不使用** | 项目 `BASE_SYSTEM_PROMPT:54` 已声明该标签是 LangChain 运行时系统提醒专用，不能用作业务包装层 |

### 关键 API

| 函数 | 行为 |
|---|---|
| `SkillsService.get_instance(config, agent_name=None)` | 懒加载；`agent_name=None` 返回全局单例；`agent_name="map_agent"` 返回 agent 维度实例（agent skills/ 覆盖默认根） |
| `SkillsService.get(name)` / `require(name)` / `all()` / `available(filter)` | 注册表访问；`require` 不存在抛 `SkillNotFoundError`（message 含 available 列表） |
| `load_skill(name)`（LangChain `@tool`） | 返回 `Command(update={"messages": [ToolMessage(content=...) ]})`；content 为 `<skill_content name="...">...</skill_content>` XML；错误时同样包装为 Command，content 以 `Error: ...` 开头（不抛异常） |
| `read_skill_file(file_path)`（LangChain `@tool`，**v3 新增**） | 按**绝对路径**读取已注册 skill 目录下的资源文件；解析→白名单（必须在某 skill 的 `base_dir` 内）→大小（≤1 MB）→UTF-8 校验；成功返回 `<skill_file path="file:///..." size="N" parent_skill="...">正文</skill_file>`；失败返回 `Error: ...`。**不**复用 `BaseFilesystemTool`（不启动子智能体）。与 `load_skill` 配合使用：先 `load_skill` 拿 `<file>` 列表，再 `read_skill_file` 读具体文件。 |
| `render_available_skills_block(skills)` | 渲染 `<available_skills>` XML；空列表返回 "No skills are currently available." |
| `BootstrapProvider.render(agent_bootstrap_path, user_global_path)` | 按 4 级优先级读取 bootstrap 内容并用 `<EXTREMELY_IMPORTANT>` 包裹 |
| `SkillsAwarePrompt(base, agent_specific, agent_name=None).build()` | 拼最终 system_prompt 字符串（顺序：base + agent + bootstrap + skills） |

### 测试覆盖

`app/tests/core/skills/`：
- `test_loader.py` — 扫描多根、frontmatter 容错、同名覆盖、路径不存在警告、~/ 展开（10 用例已落地）
- `test_service.py` — 单例、get/require/all/available、SkillNotFoundError 含 available、**agent_name 覆盖逻辑**
- `test_prompt.py` — 空列表/非空列表 XML 格式、特殊字符转义、按 name 排序
- `test_tool.py` — 成功路径、错误路径、base_dir URL、文件清单 limit=10、已适配 Command 解包（`_unwrap` 辅助 + `Command.update["messages"][0].content` 断言）。**v3 新增 9 个 `read_skill_file` 用例**：成功返回 XML 块、文件不存在、目录路径、白名单外、相对路径、超大文件、多 skill parent_skill 识别、UTF-8 解码失败、@tool 装饰器注册验证
- `test_bootstrap.py` — 已落地 8 用例：`<EXTREMELY_IMPORTANT>` 包裹、默认文件读取、缺失文件 fallback、agent 覆盖默认、user_global 覆盖默认、agent 高于 user_global、缺失 agent 回退默认、fallback 含 Tool Mapping 关键字
- `test_message_transformer.py` — **base + agent + bootstrap + skills 拼接顺序**、agent_name 传递

### 环境变量

- `SKILLS_PATHS` — 用户扩展 skill 扫描路径，逗号分隔；空则只用默认根（`app/skills` + `.agents/skills`）
- `SKILLS_BOOTSTRAP_PATH` — 用户自定义全局 bootstrap 文件路径；优先级高于系统默认 `app/core/skills/bootstrap.md`，低于子智能体 `config/bootstrap.md`
- `SKILLS_ENABLED` — 总开关，默认 `true`；`false` 时不扫描、不注入、不注册 `load_skill` 工具

### 演示用子智能体覆盖（2026-06-21 落地；2026-06-24 map_agent 目录删除后失效）

- ~~`app/features/map_agent/skills/_demo/SKILL.md`~~ — 已随 map_agent 目录删除（2026-06-24），地图 Agent 不再有子智能体专属 skill 目录，回退到全局默认扫描
- ~~`app/features/map_agent/config/bootstrap.md`~~ — 已随 map_agent 目录删除（2026-06-24），地图 Agent 回退到系统默认 `app/core/skills/bootstrap.md`
- 验收（历史）：`_llm_call(agent_name="map_agent")` 时 `<available_skills>` 仅含 `map_demo_skill`（全局 skill 被完全覆盖），bootstrap 内容为子智能体文件而非默认
- **2026-06-24 现状**：map_agent 配置改由数据库 agents 表 + AGENTS.md 加载，`agent_name` 通过 `UnifiedAgentConfig.name` 传入；skill 系统按 `agent_name="map_agent"` 查找子智能体目录时不再命中（目录已删除），自动回退到全局默认

### 集成点（2026-06-21 落地）

- `app/core/agent/agent.py::_llm_call`：替换原 `BASE_SYSTEM_PROMPT + agent + context` 拼接为 `SkillsAwarePrompt(base, agent_specific, agent_name=getattr(self, "agent_name", None)).build()`
- `app/core/server.py::lifespan`：启动时调用 `SkillsService.get_instance(settings.skills.to_skills_config())`，清理阶段 `SkillsService.reset()`；启动阶段还在 MCPToolsRegistry 初始化后、SkillsService 初始化前，从 `DatabasePool._pool` 取连接池构造 `AgentConfigService(db, AgentsMdLoader())` 与 `McpConfigService(db)`，分别挂到 `app.state.agent_config_service` / `app.state.mcp_config_service`，并调用 `mcp_config_service.seed_from_yaml_if_empty()` 完成 YAML 种子导入（Task 14，2026-06-23 落地；数据库未启用或初始化失败时降级为 warning，不阻断 lifespan）
- `app/core/config/settings.py`：新增 `SkillsSettings`（含 `skills_paths` / `skills_bootstrap_path` / `skills_enabled` 三个字段 + `to_skills_config()` 方法），并在顶层 `Settings` 中通过 `skills: SkillsSettings` 字段挂载
- `app/core/skills/bootstrap.md`：系统默认 bootstrap 内容，工具映射 + 工具选择决策规则，包含 `sandbox` / `explore` / `load_skill` / `read_skill_file` / `todowrite`
- `app/core/agent/AgentConfig.py::get_tools()`：基类工具列表追加 `explore`（`FilesystemReadTools.py`）、`load_skill` 与 `read_skill_file`（`app/core/skills/tool.py`），使所有 Agent 默认具备文件探索与 skill 加载/读取能力

### Bootstrap 内容要点

系统默认 `app/core/skills/bootstrap.md` 除工具名映射外，还包含强制的 **Tool Selection Rules**：

1. **Skill first**：任何任务开始前先检查 `<available_skills>`；只要存在匹配 skill（即使概率很低），必须先调用 `load_skill(name)` 并遵循其指引。
2. **File exploration fallback**：无匹配 skill 且需要复杂文件搜索/多文档分析时，才使用 `explore`。
3. **Sandbox fallback**：无匹配 skill 且需要隔离执行代码时，才使用 `sandbox`。
4. **Companion files**：`load_skill` 返回的 `<skill_files>` 应通过 `read_skill_file(absolute_path)` 读取，禁止直接读 SKILL.md。

### 主提示词 Skill Priority

`app/core/prompts.py` 的 `BASE_SYSTEM_PROMPT` 在 `# Subagent Strategy` 之前插入 `# Skill Priority (CRITICAL)` 章节，明确：

- 在选择 explore/sandbox/search/read 等通用工具前，必须先检查 `<available_skills>`。
- 只要存在匹配 skill，就必须先 `load_skill`；只有无可用 skill 或无匹配时，才回退到 Subagent Strategy 或其他工具。
- `load_skill` 是加载 skill 的唯一正确方式，禁止用文件系统工具直接读取 SKILL.md。

### 与现有架构的边界

- **不修改** 各 Agent `features/*/config/prompts.py` —— skill 系统独立于 agent 专属提示词
- **修改点**：`app/core/agent/agent.py::_llm_call`（第 293 行 system_prompt 拼接）
- **修改点**：`app/core/config/settings.py`（新增 `SkillsSettings`，约 100 行后）
- **修改点**：`app/core/server.py`（lifespan 中调用 `SkillsService.get_instance()`）
- **新增前置**：各 Agent 子类需在 `__init__` 中显式设置 `self.agent_name = "<dir_name>"`（如 HtAgent → `"contract_host_agent"`），未设置时 SkillsService 回退到全局实例（2026-06-24 map_agent 目录删除后，map_agent 不再有子类，`agent_name` 通过 `UnifiedAgentConfig.name` 由 AgentConfigService 加载）

### 子智能体 name 注入（2026-06-21 落地）

`Agent` 基类通过 `AgentConfig.name` 字段识别子智能体维度，链路：

1. **基类字段**：`app/core/agent/AgentConfig.py` 在 `system_prompt` 旁新增 `name: Optional[str] = field(default=None)`，含义为"Agent 注册名（与 app/features/<dir>/ 目录名一致），用于 skill 系统按子智能体维度隔离；None 时回退到全局 skill 注册表"
2. **基类读取**：`app/core/agent/agent.py::Agent.__init__` 在 `self.system_prompt = config.system_prompt` 之后新增一行 `self.agent_name = config.name`；`agent._llm_call` 通过 `getattr(self, "agent_name", None)` 透传到 `SkillsAwarePrompt`
3. **子智能体覆盖**：6 个 *Config 类在 `state_class` 字段前覆盖基类默认值为字面量（2026-06-24 移除 MapAgentConfig，map_agent 改由数据库 + AGENTS.md 加载，`name` 通过 `UnifiedAgentConfig.name` 传入）：

| 子智能体 | 配置文件 | name 字面量 |
|---|---|---|
| ~~MapAgent~~ | ~~`app/features/map_agent/config/MapAgentConfig.py`~~ | ~~`"map_agent"`~~（2026-06-24 删除，改由数据库 agents 表 + AGENTS.md 加载） |
| HtAgent | `app/features/contract_host_agent/config/HtAgentConfig.py` | `"contract_host_agent"` |
| DocAgent | `app/features/contract_document_agent/config/DocAgentConfig.py` | `"contract_document_agent"` |
| ApprovalAgent | `app/features/contract_approval_agent/config/ApprovalAgentConfig.py` | `"contract_approval_agent"` |
| DevOpsAgent | `app/features/DevOps_agent/config/DevOpsAgentConfig.py` | `"DevOps_agent"` |
| AICodingCheckAgent | `app/features/AI_Coding_Check_agent/config/AICodingCheckConfig.py` | `"AI_Coding_Check_agent"` |
| TAgent | `app/features/Tagent/config/TagentConfig.py` | `"Tagent"` |

4. **包装类不需改动**：5 个包装类（`HtAgent` / `DocAgent` / `ApprovalAgent` / `DevOpsAgent` / `AICodingCheckAgent`）持有的 `self._agent` 是内部 `Agent` 实例，已自动从 `*Config` 拿到 `self.agent_name`；包装类本身不暴露 `agent_name` 属性（2026-06-24 移除 MapAgent 包装类，map_agent 直接通过 `app/routers/knowledge_router.py::get_map_agent()` 构造 `Agent` 实例）
5. **测试**：`app/tests/core/agent/test_agent_name_propagation.py`（2026-06-24 精简为 3 用例）覆盖：基类默认 None / 6 个子 Config 字面量 / Agent.__init__ 透传（移除了依赖 MapAgentConfig 的 2 个用例）

**演示效果**（历史，2026-06-24 map_agent 目录删除后不再适用）：`_llm_call(agent_name="map_agent")` 时 `<available_skills>` 含 `map_demo_skill`（来自 `app/features/map_agent/skills/_demo/SKILL.md`），bootstrap 块取 `app/features/map_agent/config/bootstrap.md`（而非默认 `app/core/skills/bootstrap.md`）。**2026-06-24 现状**：map_agent 不再有子智能体专属 skill 目录，回退到全局默认扫描。

### agent_name 透传到工具 & 降级查找（2026-06-22 落地）

**背景**：`load_skill` / `read_skill_file` 工具原实现直接调用 `SkillsService.get_instance()`（无 `agent_name` 参数），只拿到全局单例，导致 agent 专属目录（如 `app/features/map_agent/skills/data-skill/`）下的 skill 永远找不到，工具返回 `Error: Skill "data-skill" not found. Available skills: none`。修复采用 LangChain 推荐的 `ToolRuntime.state` 通道（context7 文档 + 项目内 MapTools.py/BaseTools.py 共 11 处已有 `runtime.state.get(...)` 用法），把 agent 身份以 state 字段方式注入，**不** 修改 `AgentContext`（保持不可变配置语义）。

**改动链路**：

1. **State 字段**：`app/core/agent/AgentConfig.py::AgentState` 新增 `agent_name: Optional[str] = None` 字段；工具通过 `runtime.state.get("agent_name")` 读取
2. **注入位置**：包装类构造初始 state 时写入 `agent_name="<dir_name>"`（如 `app/features/map_agent/MapAgent.py::stream()` 中 `MapAgentState(..., agent_name="map_agent")`，与 `*AgentConfig.name` 默认值保持一致；2026-06-24 map_agent 目录删除后，map_agent 的 `agent_name` 通过 `UnifiedAgentConfig.name` 由 AgentConfigService 从数据库加载，`Agent.__init__` 透传到 `self.agent_name`）
3. **不修改**：`AgentContext`（用户明确要求保持不可变配置语义）；`SkillsService._scan` 覆盖策略；`SkillsAwarePrompt` 内部取值链路（已通过 `Agent.self.agent_name` 走通）

**降级查找约定**（`app/core/skills/tool.py` 新增 4 个辅助函数）：

| 函数 | 行为 |
|---|---|
| `_get_agent_name(runtime)` | 安全读取 `runtime.state.get("agent_name")`，缺失/异常时返回 None |
| `_resolve_skill_with_fallback(name, agent_name)` | 先 `SkillsService.get_instance(agent_name=...).get(name)`；命中即返回；未命中或 agent_name 为空再 `SkillsService.get_instance().get(name)` |
| `_merged_available(agent_name)` | 合并 agent 维度 + 全局维度的 skill 名称（去重 + 排序），用于 `SkillNotFoundError.message` |
| `_resolve_all_skills(agent_name)` | 合并 agent 维度 + 全局维度的 SkillInfo 列表（agent 优先），用于 `read_skill_file` 白名单校验 |

**降级顺序**：`agent 维度 SkillsService` → `全局 SkillsService`。**不修改** `SkillsService._scan` 中"agent_name 传入时完全覆盖默认根"的扫描策略——降级在工具层做，不影响 service 层语义。

**验收**：
- `pytest app/tests/core/skills/ -v` 通过 65 用例（含新增 6 个降级查找场景：agent 命中直接返回 / agent 缺失降级 / 两侧均缺返回 Error 含合并 available 列表 / 白名单接受 agent 维度文件 / 白名单接受全局维度文件 / state 缺失安全降级）
- 启动日志中 `SkillsService initialized with N global skill(s)` 仍为 0（全局根 `app/skills` + `.agents/skills` 在本仓库不存在，符合预期）
- `<available_skills>` 列表继续由 `SkillsAwarePrompt` 通过 `SkillsService.get_instance(agent_name="map_agent").all()` 渲染，已包含 `data-skill`

### 设计/计划文档

- 设计：[docs/superpowers/specs/2026-06-20-skill-system-design.md](../docs/superpowers/specs/2026-06-20-skill-system-design.md)（v2 修订版待同步）
- 计划：[docs/superpowers/plans/2026-06-20-skill-system.md](../docs/superpowers/plans/2026-06-20-skill-system.md)（v2 已同步）

## 动态 State/Context 构建器（2026-06-23 新增）

根据数据库 `agents` 表的 `state_schema` / `context_schema` JSON 配置动态生成 `AgentState` / `AgentContext` 的子类，支持子智能体按需扩展状态/上下文字段而无需修改基类代码。

### 模块位置

```
app/shared/utils/agent/
├── __init__.py              # 空包初始化
└── dynamic_schema.py        # 动态 schema 构建器核心实现
```

### 核心 API

| 函数 | 作用 |
|---|---|
| `build_agent_state(agent_name, state_schema)` | 根据 `state_schema` JSON 生成 `AgentState` 子类包装器，类名格式 `{PascalCase}AgentState`（如 `map_agent` → `MapAgentAgentState`） |
| `build_agent_context(agent_name, context_schema)` | 根据 `context_schema` JSON 生成 `AgentContext` 子类包装器，类名格式 `{PascalCase}AgentContext` |
| `build_context(agent_name, context_schema, request)` | 运行时构造 context 实例，从 `request` 读取 `session_id` / `store_id` / `context_overrides` |

### 合并逻辑

- **基类字段保留**：`AgentState` / `AgentContext` 基类所有字段注解原样继承
- **保留字段（RESERVED_STATE_FIELDS / RESERVED_CONTEXT_FIELDS）**：schema 中同名字段仅允许重写默认值，不可重写类型注解
- **非保留字段**：schema 中的新字段追加类型注解（通过 `TYPE_MAP` 映射 `str/int/float/bool/dict/list`）和默认值
- **2026-06-24 新增 基类保留字段运行时默认值兜底**（修复 Bug A）：`build_agent_state` / `build_agent_context` 在构造 defaults 字典时，先用 `_BASE_STATE_DEFAULTS`（8 字段：error_limit=5 / limit=25 / file_chunk_read_progress=1 / tool_progress={} / intermediate_results={} / pending_question=None / question_answers=[] / agent_name=None）和 `_BASE_CONTEXT_DEFAULTS`（6 字段：session_id="default" / namespace={} / store_id="default" / image_ids=[] / host_session_id=None / process_data={}）作为兜底，调用方只需传 messages / session_id 等必需字段。**三级优先级**：调用方 kwargs > schema 重写 > 基类默认值

### TypedDict 默认值运行时应用

TypedDict 原生不在运行时应用字段默认值（默认值仅用于类型检查），且 `typing_extensions._TypedDictMeta` 元类硬编码了 `__call__`，无法通过自定义元类覆写。因此采用工厂包装器 `_TypedDictWithDefaults`：

- 用 `type(AgentState)`（即 `_TypedDictMeta`）创建真实 TypedDict 子类（保留 `__annotations__` / `__required_keys__` / `__optional_keys__`）
- 用 `_TypedDictWithDefaults` 包装该类，在 `__call__` 中实例化后补全缺失字段的默认值
- 包装器透传 `__name__` / `__annotations__`，对调用方透明
- **可变默认值隔离**：对 `dict` / `list` 类型默认值使用 `copy.deepcopy`，避免多个实例共享同一对象引用导致跨实例污染
- **返回类型**：`build_agent_state` / `build_agent_context` 返回 `Callable`（包装器实例）而非原生 `type`，调用方应将其视为可调用对象

### build_context 关键字冲突处理

`build_context` 在构造 context 实例时显式传入 `session_id` / `store_id`，若 `request.context_overrides` 中也包含这些保留字段（`RESERVED_CONTEXT_FIELDS`），会触发 `TypeError: got multiple values for keyword argument`。因此构造前会过滤 `context_overrides` 中的保留字段，确保显式传入值优先。

### 测试

- 路径：`app/tests/shared/utils/agent/test_dynamic_schema.py`（**18 用例**，2026-06-24 从 12 扩展为 18）
- 本地 conftest：`app/tests/shared/utils/agent/conftest.py` 覆盖根 conftest 中 `langgraph.graph.MessagesState = Mock()`，提供真实 TypedDict 基类，确保 `AgentState` 正确继承 TypedDict 而非 Mock
- 覆盖：模块可导入 / 子类字段追加 / 基类字段保留 / 保留字段跳过 / 默认值覆盖 / context 子类生成 / context 基类字段保留 / 运行时实例构造 / 保留字段集合校验 / 可变默认值隔离 / context 关键字冲突过滤 / **基类保留字段默认值自动补全**（新增 6 用例：state 最小 schema 兜底 / 空 schema 兜底 / context 兜底 / 调用方 kwargs 优先 / map_agent 完整 schema 端到端 / schema 重写保留字段）

## AGENTS.md 加载器（2026-06-23 新增）

从文件系统读取 `agents/<agent_name>/AGENTS.md` 纯 markdown 内容，供 `AgentConfigService`（Task 12）作为 `system_prompt` 注入 LLM。带内存缓存，避免重复磁盘 IO。

### 模块位置

```
app/shared/utils/agent/
├── __init__.py              # 空包初始化
├── dynamic_schema.py        # 动态 schema 构建器（Task 3）
├── agents_md_loader.py      # AGENTS.md 加载器（Task 4）
├── mcp_service.py           # MCP 配置 CRUD 服务（Task 5）
└── agent_config_service.py  # Agent 配置加载服务（Task 12）
```

### 核心 API

| 类 / 方法 | 作用 |
|---|---|
| `AgentsMdLoader` | AGENTS.md 文件加载器，带内存缓存 |
| `AgentsMdLoader.load(agents_md_path)` | 加载指定路径的 AGENTS.md 内容；首次读取磁盘并缓存，后续直接返回缓存；文件不存在抛 `FileNotFoundError` |
| `AgentsMdLoader.clear_cache()` | 清空缓存，admin 更新 AGENTS.md 后调用以刷新 |

### 设计要点

- **内存缓存**：`Dict[str, str]` 以路径为键，同一路径只读一次磁盘
- **错误处理**：文件不存在时抛 `FileNotFoundError`，错误消息格式 `AGENTS.md not found at: {path}`
- **编码**：统一使用 `utf-8` 读取
- **刷新机制**：`clear_cache()` 供 admin 更新 AGENTS.md 后手动刷新，下次 `load()` 重新读取磁盘

### 数据库关联

`agents` 表的 `agents_md_path` 字段（`VARCHAR(500)`）存储 AGENTS.md 文件路径，由 `AgentConfigService` 读取后传给 `AgentsMdLoader.load()`。

### 测试

- 路径：`app/tests/shared/utils/agent/test_agents_md_loader.py`（5 用例）
- 覆盖：模块可导入 / 读取 markdown 内容 / 缓存命中（同路径第二次加载走缓存）/ 文件不存在抛 FileNotFoundError / clear_cache 后重新加载读取最新内容

### map_agent AGENTS.md 文件（Task 11，2026-06-23 新增；2026-06-24 改造）

首个落地于 `agents/<agent_name>/AGENTS.md` 约定的纯 markdown 提示词文件，供 `AgentsMdLoader` 读取后作为 `system_prompt` 注入 LLM。

**文件位置**: `agents/map_agent/AGENTS.md`

**内容章节**（2026-06-24 改造：从原"身份与职责 / 可用工具 / 可用 Skill / Skill 使用指南 / 行为规范"重写为直接来自 `agents/map_agent/prompts.py` 的提示词片段，并追加精简的"Agent Capability"+"load_skill 使用方法"）:

| 章节 | 作用 |
|------|------|
| Task Rules | 工具选择规则与 ask_user_question 使用约束（来自 prompts.py `DEFAULT_SYSTEM_PROMPT`） |
| TOOL DESCRIPTION / `### explore` | explore 工具的使用场景、优先级与返回值限制（来自 prompts.py `MAP_AGENT_SYSTEM_PROMPT` 头部） |
| TOOL DESCRIPTION / `### load_skill` | 通用约束：这两个工具仅在触发 skill 时使用；未触发 skill 时不要用它们，查找仍走 `explore` |
| Agent Capability | 英文声明核心能力（合规性审查 + 项目预审，关键术语保留中文）+ 具体触发条件：调用 `load_skill("hgsc")` + `read_skill_file(absolute_path)` 获取详情 |

**纯 markdown 原则**: 不包含 `state_schema` / `context_schema` / `TypedDict` 等运行时配置（这些在数据库 `agents` 表中），仅包含 LLM 可见的提示词内容。

**内容测试**:

- 路径：`app/tests/shared/utils/agent/test_agents_md_content.py`（4 用例，2026-06-24 由 5 用例精简）
- 覆盖：文件存在 / 包含 Task Rules 章节 / 包含 TOOL DESCRIPTION 章节（含 explore 工具说明） / 不包含 state 字段定义（纯 markdown 原则）

### hgsc skill（2026-06-24 新增）

**文件位置**: `app/skills/hgsc/skill.md`（frontmatter `name: hgsc`）

合规性审查（Compliance Review）与项目预审（Project Pre-review）工作流 skill，内容来源于 `agents/map_agent/prompts.py::MAP_AGENT_SYSTEM_PROMPT` 第 22-55 行（Workflow / 合规性审查步骤 / Task Examples / Output Requirements）。Workflow 部分描述"合规性审查"四步流程：上下文收集 → explore 验证附件 → ask_user_question 确认 → save_business_info 持久化 → quality_inspection_analysis → generate_report；原文为英文，保留英文原文。

## AgentConfigService 配置加载服务（Task 12，2026-06-23 新增）

从数据库 `agents` 表 + AGENTS.md 文件加载完整 Agent 配置，封装为 `UnifiedAgentConfig` 实例供 `agent_router` 使用。是连接数据库配置和运行时 Agent 的核心服务，整合 `dynamic_schema` + `agents_md_loader` 两个模块的输出。

### 模块位置

```
app/shared/utils/agent/agent_config_service.py
```

### 核心 API

| 类 / 方法 | 作用 |
|---|---|
| `UnifiedAgentConfig` | 统一智能体配置 dataclass（name / display_name / description / system_prompt / state_class / context_class / mcp_tags / enabled_tool_names / enabled_skill_names / agents_md_path） |
| `AgentNotFoundError` | 智能体未找到或已禁用时抛出的异常 |
| `AgentConfigService(db, agents_md_loader)` | 构造器，参数 `db` 需支持异步 `fetch` / `fetchrow` / `execute`，`agents_md_loader` 为 `AgentsMdLoader` 实例 |
| `AgentConfigService.get_agent_config(agent_name)` | 异步加载完整配置：查询 agents 表 → 加载 AGENTS.md → 构建 state/context 类 → 加载 tool/skill 绑定，返回 `UnifiedAgentConfig` |
| `AgentConfigService.list_agents()` | 异步列出所有启用智能体（仅返回 name / display_name / description 摘要） |
| `AgentConfigService.create_agent(config)` | Admin 创建智能体（INSERT INTO agents RETURNING *） |
| `AgentConfigService.bind_tool(agent_name, tool_name, enabled)` | 绑定/解绑工具（upsert agent_tool_bindings） |
| `AgentConfigService.bind_skill(agent_name, skill_name, enabled)` | 绑定/解绑 skill（upsert agent_skill_bindings） |

### 设计要点

- **enabled 校验在 Python 层**：SQL 查询不携带 `AND enabled = TRUE`，而是在 Python 中通过 `row.get("enabled", False)` 判断，便于在 mock 测试中精确控制返回值
- **字段安全访问**：`display_name` / `description` / `state_schema` / `context_schema` / `mcp_tags` 均通过 `row.get(...)` 或 `or {}` / `or []` 兜底，避免 KeyError
- **create_agent 输入校验**：`create_agent` 方法在执行 INSERT 前校验必需键（name / display_name / agents_md_path），缺失时抛出 `KeyError`；docstring 明确文档化该异常
- **日志记录**：`get_agent_config`（成功/未找到）、`create_agent`、`bind_tool`、`bind_skill` 均通过 `logger.info` / `logger.warning` 记录关键路径
- **绑定列表过滤**：`enabled_tool_names` / `enabled_skill_names` 通过 `r.get("is_enabled")` 过滤，且在访问 `r["skill_name"]` 前校验 `"skill_name" in r`，避免 mock 返回同一列表时键缺失引发 KeyError
- **state_class / context_class 类型**：`UnifiedAgentConfig.state_class` / `context_class` 类型注解为 `Callable`（而非 `type`），因 `build_agent_state` / `build_agent_context` 返回的是 `_TypedDictWithDefaults` 包装器实例
- **JSONB 字段防御性反序列化**（2026-06-24 新增）：`state_schema` / `context_schema` / `mcp_tags` 三个 JSONB 字段读取后先经 `AgentConfigService._decode_jsonb(value, default)` 静态方法处理。asyncpg 默认不注册 JSONB codec，DB 返回 `str`（JSON 字符串）；若将来连接池注册了 codec 则返回 `dict` / `list`。两种情况均需兼容：None 走 default；str 用 `json.loads` 解析（失败回退 default 并 warning）；dict/list 原样返回
- **依赖模块**：`dynamic_schema.build_agent_state` / `build_agent_context`（Task 2）+ `agents_md_loader.AgentsMdLoader.load`（Task 4）

### 数据库关联

| 表 | 用途 |
|---|---|
| `agents` | 主表，存储 name / display_name / description / agents_md_path / state_schema / context_schema / mcp_tags / enabled / sort_order |
| `agent_tool_bindings` | 工具绑定表，存储 agent_name / tool_name / is_enabled / sort_order |
| `agent_skill_bindings` | skill 绑定表，存储 agent_name / skill_name / is_enabled / sort_order |

### 测试

- 路径：`app/tests/shared/utils/agent/test_agent_config_service.py`（**15 用例**，2026-06-24 从 9 增至 15）
- 覆盖：模块可导入 / 从数据库和 AGENTS.md 加载完整配置 / agent 不存在抛 AgentNotFoundError / agent 禁用抛 AgentNotFoundError / list_agents 只返回启用智能体 / 加载 skill 绑定 / create_agent 插入并返回新行 / bind_tool 执行 upsert / bind_skill 执行 upsert / **JSONB 防御性反序列化**：`test_decode_jsonb_none_returns_default` / `test_decode_jsonb_str_parses_json` / `test_decode_jsonb_dict_passthrough` / `test_decode_jsonb_list_passthrough` / `test_decode_jsonb_invalid_str_falls_back_to_default` / `test_get_agent_config_decodes_str_jsonb_fields`（端到端：mock db 返回 str JSONB 也能正确解析为 dict/list）
- 异步测试使用 `asyncio.run()` 包装（非 pytest-asyncio）
- Mock 使用 `unittest.mock.AsyncMock` 和 `MagicMock`

## MCP 配置 CRUD 服务（2026-06-23 新增）

提供 MCP server 配置的数据库 CRUD 操作，供 `mcp_admin_router`（Task 6）调用；启动时若 `mcp_server_configs` 表为空，从 YAML 种子文件导入（由 `server.py` lifespan Task 14 触发，已落地）。

### 模块位置

```
app/shared/utils/agent/mcp_service.py
```

### 核心 API

| 类 / 方法 | 作用 |
|---|---|
| `McpServerConfig` | MCP 服务器配置 dataclass（name、display_name、type、url、command、timeout、read_timeout、tags、enabled、progress_reporting、tool_config、sampling） |
| `McpConfigService(db)` | CRUD 服务构造器，参数 `db` 需支持异步 `fetch` / `fetchrow` / `execute` |
| `list_servers()` | 列出所有 server 配置（按 created_at 排序） |
| `get_server(name)` | 获取单个 server 配置，不存在返回 None |
| `create_server(config)` | 新增 server；name 已存在抛 `ValueError` |
| `update_server(name, config)` | 更新 server；不存在抛 `ValueError` |
| `delete_server(name)` | 删除 server 及关联 methods（先删 mcp_server_methods 再删 mcp_server_configs） |
| `toggle_server(name, enabled)` | 启用/禁用 server |
| `list_methods(server_name)` | 列出 server 下所有 method（按 method_name 排序） |
| `toggle_method(server_name, method_name, enabled)` | 启用/禁用单个 method |
| `upsert_methods(server_name, methods)` | 批量 upsert method 列表并更新 methods_synced_at |
| `refresh_methods_from_server(server_name)` | 从 MCPToolsRegistry 拉取最新 method 列表并调用 upsert_methods 保存；server 不存在抛 `ValueError` |
| `seed_from_yaml_if_empty()` | 表为空时从 YAML 种子文件导入；非空跳过 |
| `_load_yaml_seed()` | 从 `app.core.config.config.settings.mcp.mcp_config_path` 加载 YAML；导入失败返回空 dict |

### 设计要点

- **存在性校验**：`create_server` 先调 `get_server` 检查 name 是否已存在，存在则抛 `ValueError`，避免依赖 DB 唯一约束报错
- **JSONB 字段序列化**：`command` / `tags` / `progress_reporting` / `tool_config` / `sampling` 在写入前用 `json.dumps` 序列化
- **YAML 种子容错**：`_load_yaml_seed` 捕获所有异常（如 `app.core.config.config` 或 `mcpClient.shared.config_loader` 不存在），失败时返回空 dict 并记录 warning
- **关联删除**：`delete_server` 先删子表 `mcp_server_methods` 再删主表 `mcp_server_configs`

### 数据库关联

- 主表：`mcp_server_configs`（见上方 "mcp_server_configs 表"）
- 子表：`mcp_server_methods`（见上方 "mcp_server_methods 表"）

### 测试

- 路径：`app/tests/shared/utils/agent/test_mcp_service.py`（9 用例）
- 覆盖：模块可导入 / list_servers 返回行 / get_server 返回单条 / create_server 写入（mock fetchrow 两次：存在性检查返回 None + INSERT RETURNING 返回行）/ delete_server 删除主子表 / toggle_server 更新 enabled / list_methods 返回行 / toggle_method 更新 enabled / seed_from_yaml_if_empty 空表导入（mock _load_yaml_seed）

## MCP Admin Router（2026-06-23 新增）

提供 MCP server 配置的 HTTP API，前缀 `/api/admin/mcp`，在 `app/main.py::register_routers` 中注册。调用 `McpConfigService`（Task 5）执行数据库操作，通过 `request.app.state.mcp_config_service` 获取服务实例（lifespan 集成在 Task 14 已落地）。

### 模块位置

```
app/routers/
├── __init__.py              # 空包初始化
└── mcp_admin_router.py      # MCP Admin 路由
```

### 路由清单

| 方法 | 路径 | 状态码 | 说明 |
|---|---|---|---|
| GET | `/api/admin/mcp/servers` | 200 | 列出所有 MCP server 配置 |
| POST | `/api/admin/mcp/servers` | 201 | 新增 server；name 已存在返回 409 |
| PUT | `/api/admin/mcp/servers/{name}` | 200 | 更新 server 配置；不存在返回 404 |
| DELETE | `/api/admin/mcp/servers/{name}` | 204 | 删除 server 及关联 methods |
| POST | `/api/admin/mcp/servers/{name}/toggle` | 200 | 启用/禁用 server（query 参数 `enabled`） |
| GET | `/api/admin/mcp/servers/{name}/methods` | 200 | 列出 server 下所有 method |
| POST | `/api/admin/mcp/servers/{name}/refresh-methods` | 200 | 从 MCP server 拉取最新 method 列表；失败返回 502 |
| POST | `/api/admin/mcp/servers/{name}/methods/{method}/toggle` | 200 | 启用/禁用单个 method（query 参数 `enabled`） |

### 设计要点

- **服务获取**：`_get_service(request)` 从 `app.state.mcp_config_service` 获取 `McpConfigService` 实例；未初始化时抛 500
- **错误映射**：`ValueError` → 409（create，name 冲突）/ 404（update，不存在）；`refresh_methods` 失败 → 502
- **refresh_methods_from_server**：`McpConfigService` 新增方法，通过 `MCPToolsRegistry.get_tools_with_server(server=name)` 获取已注册工具列表，转换为 method 记录后调用 `upsert_methods` 保存

### 测试

- 路径：`app/tests/routers/test_mcp_admin_router.py`（11 用例）
- 本地 conftest：`app/tests/routers/conftest.py`（mock `filesystem_encoding_fix.apply_fix` 为 no-op + 注入 `mcp_config_service` 实例）
- 覆盖：模块可导入 / 7 个路由注册检查 / list_servers 返回 200 / create_server 返回 201 / delete_server 返回 204 / toggle_server 返回 200

## 统一 Agent Router（2026-06-23 新增，Task 13）

提供统一 Agent HTTP API，前缀 `/api/agent`，在 `app/main.py::register_routers` 中注册。调用 `AgentConfigService`（Task 12）加载配置，通过 `Agent`（`app/core/agent/agent.py`）执行流式对话。SSE 流式逻辑提取到 `_stream_helper.py` 供复用。

### 模块位置

```
app/routers/
├── __init__.py              # 空包初始化
├── mcp_admin_router.py      # MCP Admin 路由
├── agent_router.py          # 统一 Agent 路由（Task 13）
└── _stream_helper.py        # SSE 流式响应辅助（完整迁移自 map_router，Task 24）
```

### 路由清单

| 方法 | 路径 | 状态码 | 说明 |
|---|---|---|---|
| POST | `/api/agent/chat` | 200 | 统一聊天接口（SSE 流式响应）；agent 不存在返回 404 |
| GET | `/api/agent/list` | 200 | 列出所有启用的智能体 |
| GET | `/api/agent/{agent_name}/agents-md` | 200 | 获取指定 agent 的 AGENTS.md 内容（system_prompt）；不存在返回 404 |

### 设计要点

- **服务获取**：`_get_service(request)` 从 `app.state.agent_config_service` 获取 `AgentConfigService` 实例；未初始化时抛 500（与 mcp_admin_router 模式一致）
- **SSE 复用**：`_stream_helper.generate_stream_response` 完整迁移自 map_router.py（Task 24，2026-06-23），保留全部 SSE 处理逻辑：ContextVar 挂载/清理（子智能体停止信号）、精确延迟中断（disconnect 标记 + tools 节点完成时真正断开）、HITL 中断检测（多模式兼容）+ `_extract_interrupt_requests`、updates/custom/messages 三种 stream_mode 差异化处理、thread_id/langgraph_node 透传、`stream_format_context.format_message` 格式化；统一签名 `(agent, input_state, context, session_id, request)`，供 agent_router 与 map_router knowledge-chat 复用
- **SSE 响应头**：`StreamingResponse` 显式设置 `Cache-Control: no-cache` / `Connection: keep-alive` / `X-Accel-Buffering: no`，防止 Nginx 等反向代理缓冲 SSE 流
- **ChatRequest 模型**：Pydantic BaseModel，字段含 message / session_id / agent_name（默认 map_agent）/ attachments（暂未实现，预留字段）/ resume（HITL 恢复）/ context_overrides
- **context_overrides 过滤**：构造 context 实例前过滤 `RESERVED_CONTEXT_FIELDS`（session_id / store_id / namespace 等），避免与显式传入的 session_id 关键字参数冲突（TypeError: got multiple values for keyword argument）
- **Agent 构造**：chat 端点从 `UnifiedAgentConfig` 提取 name / system_prompt / state_class / context_class 构造 `AgentConfig`，并通过 `get_async_checkpointer()` 注入全局 checkpointer（支持 resume 与多轮对话状态持久化），实例化 `Agent` 并调用 `await agent.__ainit__()` 完成异步初始化；初始化过程包裹 try/except，失败时抛 500
- **输入状态**：resume 存在时构造 `Command(resume=...)`，否则构造 `state_class(messages=[HumanMessage(...)])`
- **2026-06-24 修复 Bug A（state 缺基类保留字段）**：原 chat 端点构造 `input_state = state_class(messages=[...])` 时未传 `error_limit` / `limit` / `agent_name` 等基类保留字段，导致 state 实例缺失。修复由 `dynamic_schema._BASE_STATE_DEFAULTS` 包装器在实例化时自动补全（详见"动态 State/Context 构建器"章节）。路由层调用方只需传必需字段（`messages` / `session_id`），无需重复传入保留字段。三级优先级：调用方 kwargs > schema 重写 > 基类默认值
- **Session 中间件**：`/api/agent/` 前缀在 `SESSION_REQUIRED_PREFIXES` 中，所有端点需 `X-Session-ID` 头并通过 `session_cache.verify_session` 校验
- **错误映射**：`AgentNotFoundError` → 404；Agent 初始化异常 → 500

### 前端切换（Task 15，2026-06-23 落地）

- **`web/Agent/src/utils/api.js::chatStream`** 从 `/api/map/chat` 切换到 `/api/agent/chat`，函数签名追加第 5 个参数 `agentName = 'map_agent'`，请求体新增 `agent_name` 字段
- **向后兼容**：`App.vue` 两处 call site（正常发送 + HITL resume）均使用 3-4 个参数，依赖默认值 `map_agent`，无需改动
- **`knowledgeChatStream` 不变**：仍使用 `/api/map/knowledge-chat`（知识库聊天暂未纳入统一 Agent 架构）
- **测试**：`web/Agent/src/utils/__tests__/api.agent-chat.test.js` 3 个用例（URL 切换 / agent_name 传参 / 默认值）

### 后端旧端点清理（Task 21，2026-06-23 落地）

- **`app/features/map_agent/router/map_router.py`**：移除 `@router.post('/chat')` 端点及 `chat` 函数（约 110 行），旧 `/api/map/chat` 已被 `/api/agent/chat` 替代；保留 `knowledge/files`、`knowledge/file-download`、`knowledge/file-preview`、`knowledge-chat` 端点。**Task 24（2026-06-23）** 进一步移除本地 `generate_stream_response` 与 `_extract_interrupt_requests`（约 285 行），knowledge-chat 端点改用 `app.routers._stream_helper.generate_stream_response`（统一签名），通过 `MapAgent.get_agent()` 获取底层 Agent 并直接构造 `input_state`（`MapAgentState` 或 `Command(resume=...)`）与 `MapAgentContext`。**2026-06-24 后续迁移**：整个 `app/features/map_agent/` 目录删除，上述 4 个 knowledge 端点迁移到 `app/routers/knowledge_router.py`，`MapAgent`/`MapAgentState`/`MapAgentContext` 改由 `AgentConfigService` + `UnifiedAgentConfig` + `dynamic_schema` 动态生成
- **`app/features/map_agent/config/prompts.py`**：移除死代码 `MAP_AGENT_SYSTEM_PROMPT`（随 /chat 端点移除已无引用）
- **`app/features/map_agent/client.py`**：`MapAgentClient.chat_stream` URL 从 `/api/map/chat` 更新为 `/api/agent/chat`，新增 `agent_name` 参数（默认 `map_agent`）
- **`app/tests/conftest.py`**：新增全局 mock `filesystem_encoding_fix.apply_fix` 为 no-op，支持根级测试导入 `app.main`
- **测试**：`app/tests/test_main_routes_registered.py` 3 用例（mcp_admin_router 注册 / agent_router 注册 / 旧 /api/map/chat 已移除）

## Agent Admin Router（2026-06-24 新增）

提供智能体的完整 CRUD + config_schema 三层结构管理 API，前缀 `/api/admin/agents`，admin 权限（复用 `require_admin`）。在 `app/main.py::register_routers` 中注册。

### 端点清单

| 方法 | 路径 | 状态码 | 说明 |
|---|---|---|---|
| GET | `/api/admin/agents` | 200 | 列出所有 agent（含 config_schema 完整数据） |
| GET | `/api/admin/agents/check-name?name=xxx` | 200 | name 唯一性预校验（返回 `{available: bool}`） |
| POST | `/api/admin/agents/validate-md-path` | 200 | 校验 AGENTS.md 路径是否存在 |
| GET | `/api/admin/agents/field-templates` | 200 | 获取 AgentConfig 字段模板列表（前端新增字段时下拉选择） |
| GET | `/api/admin/agents/{name}` | 200 | 获取单个 agent 完整配置（含 agent_config_overrides 拆分结果） |
| POST | `/api/admin/agents` | 201 | 新增智能体；name 已存在返回 409；AGENTS.md 不存在返回 400 |
| DELETE | `/api/admin/agents/{name}` | 204 | 删除智能体（级联清理 agent_tool_bindings / agent_skill_bindings 关联） |
| PUT | `/api/admin/agents/{name}/enabled` | 200 | 启用 / 禁用单个智能体（body: `{enabled: bool}`） |
| PUT | `/api/admin/agents/{name}/config-schema` | 200 | 全量替换 config_schema |
| POST | `/api/admin/agents/{name}/config-schema/field` | 200 | 增量添加字段（body: `{section, field_name, field_def}`） |
| DELETE | `/api/admin/agents/{name}/config-schema/field` | 200 | 增量删除字段（query: `section + field_name`） |

**section 取值**：`root`（顶层 AgentConfig 字段）/ `state_fields`（state 扩展字段）/ `context_fields`（context 扩展字段）

### 设计要点

- **保留字段校验**：`config_schema` 顶层不能包含 `state_class` / `context_class` / `checkpointer` / `store`（运行时对象），由 `service.update_agent_config_schema` 和 `create_agent` 在写库前校验
- **name 唯一性**：DB UNIQUE 约束 + service 层预检 + admin API 409 Conflict 响应
- **AGENTS.md 路径**：必须在 service 层 `Path.is_file()` 校验失败返回 400（防止脏数据写入）
- **field_def 校验**：必须包含 `type` 键，type 必须在 `TYPE_MAP` 支持的类型中（`str`/`int`/`float`/`bool`/`dict`/`list`）
- **错误映射**：`_handle_agent_error` 统一转换 service 异常（AgentAlreadyExistsError → 409 / AgentNotFoundError → 404 / ValueError → 400 / FileNotFoundError → 400 / KeyError → 400）
- **Pydantic 模型**：`CreateAgentRequest` 强制 name 格式 `[a-z0-9_]{3,50}` / `display_name` 1-200 字符 / `field_name` Python 标识符格式；`AddFieldRequest.section` 自由字符串（由 service 校验）；`SetEnabledRequest.enabled` bool
- **测试**：`app/tests/routers/test_agent_admin_router.py` 16 用例（P0 导入 / 路由注册 / 字段模板 / 校验 / CRUD / 鉴权 403）；`app/tests/routers/conftest.py` 新增 `_init_db`（注入 `app.state.db` MagicMock）和 `_mock_user_db_for_admin_auth`（根据 username 返回 role）两个 autouse fixture

### 2026-06-24 修复：401 Unauthorized 误诊（AttributeError）

**症状**：访问"智能体管理"页时 `GET /api/admin/agents` 返回 401 Unauthorized，前端展示"会话无效，请重新登录"。

**根因**：
- `app/routers/agent_admin_router.py` 的 `list_agents` / `get_agent` 端点直接访问 `request.app.state.db`。
- `app/core/server.py` lifespan **从未**初始化 `app.state.db`（只初始化 `app.state.agent_config_service` / `mcp_config_service` / `mcp_registry`）。
- 抛出的 `AttributeError: 'State' object has no attribute 'db'` 被 `app/shared/utils/auth/Safety.py::auth_middleware` 的 `try/except Exception` 吞掉，统一伪装成 401 → 误导前端"会话无效"。
- `app/tests/routers/conftest.py::_init_db` 用 `MagicMock()` 注入 `app.state.db` 掩盖了生产 bug，导致测试通过、生产 500/401。

**修复方案**（架构重构路线，用户选择）：
- **新增 2 个 `AgentConfigService` 公共方法**：
  - `list_all_agents_admin()`：admin 专用列表，**包含禁用项**（与现有 `list_agents` 的"仅启用"语义保持隔离，不破坏 `agent_router` 聊天端点），返回全字段
  - `get_agent_admin(agent_name)`：admin 专用详情，**不校验 `enabled`**（允许查看已禁用项），不加载 AGENTS.md（避免无谓 IO），返回 dict + `agent_config_overrides` 拆分
- **重构 router 端点**：`list_agents` / `get_agent` 改走 `service.list_all_agents_admin()` / `service.get_agent_admin(name)`，**完全消除 `app.state.db` 直接访问**。
- **不动 `auth_middleware`**：用户明确要求保持现有异常处理范围不变（修复后路由不再抛 AttributeError，问题自然消除）。
- **不动 `server.py` lifespan**：不追加 `app.state.db = db_pool`，与架构重构方向一致（lifespan 只初始化"有 service 包装"的状态）。

**端到端验证**（修复后）：
- `POST /api/auth/login-api` → 200 + access_token
- `GET /api/admin/agents` → 200 + JSON list（如 `[{"name":"map_agent","enabled":true,...}]`）
- `GET /api/admin/agents/map_agent` → 200 + JSON dict + `agent_config_overrides` 已拆分

**测试同步**：
- `app/tests/routers/test_agent_admin_router.py`：原有 2 个 CRUD 用例的 mock 路径从 `app.state.db` 改为 `service._db`（先注入 MagicMock 再挂 fetch/fetchrow）
- `app/tests/shared/utils/agent/test_agent_config_service.py`：**新增 5 个用例** `test_list_all_agents_admin_returns_all_fields` / `test_list_all_agents_admin_orders_by_sort_order_then_name` / `test_get_agent_admin_returns_full_config_with_overrides` / `test_get_agent_admin_raises_not_found` / `test_get_agent_admin_handles_non_dict_config_schema`
- `app/tests/routers/conftest.py::_init_db` 注释更新为"**仅供历史兼容保留**"，标注"agent_admin_router 重构后已不直接访问 app.state.db"

**后续防御**：
- `_init_db` fixture 保留 autouse=True 防止其他测试目录有隐藏依赖；同时与生产环境（lifespan 不再初始化 app.state.db）行为保持一致——如果未来某路由又错误地直接访问 `app.state.db`，本 fixture 至少让测试能跑出端点（路由层在生产仍会 AttributeError，便于早发现）。

### SSE 流式逻辑完整迁移（Task 24，2026-06-23 落地）

将 `map_router.py::generate_stream_response` 的**全部** SSE 处理逻辑（约 285 行）完整迁移到 `app/routers/_stream_helper.py`，不做任何简化。

**迁移内容**：
- ContextVar 挂载/清理（`set_current_request` / `reset_current_request`）：子智能体工具（sandbox / explore）通过 `get_current_request()` 检测客户端断开
- 精确延迟中断（2026-06-22 改造）：`disconnect_requested` + `disconnect_executed` 双标记，检测到断开后继续消费 updates 直到 "tools" 节点完成（ToolMessage 写入 state）才真正 break，避免 orphan tool_calls
- HITL 中断检测（多模式兼容）：直接 dict `{"__interrupt__": [...]}` / tuple `("updates", {"__interrupt__": [...]})` / 嵌套 `("updates", {"node": {"__interrupt__": [...]}})` 三种格式
- `_extract_interrupt_requests`：解析 LangGraph `Interrupt` 对象为结构化 dict
- updates 模式：附加 `thread_id`（空字符串）与 `langgraph_node`（节点名）字段
- custom 模式：从 `data.data.thread_id` / `data.tool_call_id` 推导 `thread_id` 透传到 SSE 顶层
- messages 模式：`stream_format_context.format_message` 格式化 + 跳过 ToolMessage + 断开后跳过
- `client_disconnected` 事件：断开时 yield 标记事件
- `recursion_limit=100`（与原 map_router 一致）

**统一签名**：`generate_stream_response(agent, input_state, context, session_id, request)`
- `agent`：Agent 实例（需实现 `stream(input_state, context, config, stream_mode)` 方法）
- `input_state`：`AgentState` 或 `Command(resume=...)`
- `context`：AgentContext 实例
- `session_id`：会话 ID
- `request`：FastAPI Request（可为 None 兼容非 HTTP 上下文）

**map_router.py knowledge-chat 端点改造**（2026-06-23 Task 24 状态；2026-06-24 已进一步迁移到 `knowledge_router.py`）：
- 通过 `await get_map_agent()` 获取 MapAgent 实例
- 通过 `await map_agent.get_agent()` 获取底层 Agent 实例
- 直接构造 `input_state`：resume 场景 `Command(resume=...)`，正常场景 `MapAgentState(messages=[HumanMessage(...)], agent_name="map_agent")`
- 直接构造 `context_instance`：`MapAgentContext(session_id=..., store_id=..., knowledge_root=TMP_DIR, system_prompt=KNOWLEDGE_SYSTEM_PROMPT, geometry_data=...)`
- 调用 `_stream_helper.generate_stream_response(agent, input_state, context_instance, session_id, request)`
- **2026-06-24 后续迁移**：`map_router.py` 已删除，knowledge-chat 端点迁移到 `app/routers/knowledge_router.py`；`get_map_agent()` 改为通过 `AgentConfigService.get_agent_config("map_agent")` 获取 `UnifiedAgentConfig`，再构造 `Agent(agent_config)` + `await agent.__ainit__()`；`MapAgentState`/`MapAgentContext` 改由 `dynamic_schema`（`build_agent_state`/`build_agent_context`）动态生成

**测试迁移**：
- `test_map_router_disconnect.py`：9 用例，导入目标从 `map_router` 改为 `_stream_helper`，调用签名改为 `(agent, input_state, context, session_id, request)`，mock 对象从 `get_map_agent` 改为直接传入 `fake_agent`
- `test_map_router_subagent_stop.py`：5 用例（1 skipped），同上适配
- 全部 23 passed / 1 skipped（async 测试需 pytest-asyncio 插件，预存在问题）

### 测试

- 路径：`app/tests/routers/test_agent_router.py`（6 用例）
- 本地 conftest：`app/tests/routers/conftest.py` 追加 `_init_agent_config_service`（注入 `AgentConfigService(db=None, agents_md_loader=AgentsMdLoader())`）+ `_mock_session_cache_for_agent`（mock `session_cache.verify_session` 返回 True）两个 autouse fixture
- 覆盖：模块可导入 / 3 个路由注册检查 / list_agents 返回 200 / get_agents_md 返回 content
- 测试通过 monkeypatch 替换 `AgentConfigService.list_agents` / `get_agent_config`，HTTP 请求带 `X-Session-ID` 头绕过 Session 校验

## MCPToolsRegistry 运行时管理增强（2026-06-23 新增）

为 `MCPToolsRegistry`（`app/core/tools/mcp_registry.py`）新增 5 个异步方法，支持运行时动态管理 MCP server 配置，无需重启应用。供 `mcp_admin_router`（Task 6）及 `McpConfigService.refresh_methods_from_server` 调用。

### 模块位置

```
app/core/tools/mcp_registry.py
```

### 核心 API

| 方法 | 作用 |
|---|---|
| `add_server(name, config)` | 运行时新增 server 配置；存入 `_server_configs`，客户端已初始化时尝试连接，失败仅 warning |
| `update_server(name, config)` | 更新 server 配置；覆盖旧配置，客户端已初始化时先 remove 再 add 重建连接 |
| `remove_server(name)` | 移除 server；从 `_server_configs` 删除配置并断开连接，配置不存在静默忽略 |
| `toggle_server(name, enabled)` | 启用/禁用 server；更新 `_server_configs[name]["enabled"]` 字段 |
| `toggle_method(server_name, method_name, enabled)` | 启用/禁用单个 method；更新 `_server_configs[server_name]["methods"][method_name]["enabled"]` 字段 |

### 设计要点

- **容错策略**：所有方法在客户端未初始化（`_client is None` 或 `_initialized is False`）时仅更新 `_server_configs`，不抛异常
- **异常隔离**：客户端连接/断开失败时仅记录 warning 日志，不向上抛出，保证配置至少被持久化
- **静默忽略**：`toggle_server` / `toggle_method` 在 server 或 method 不存在时静默忽略，不抛 KeyError
- **方法位置**：5 个方法插入在 `refresh_tools` 之后、`shutdown` 之前

### 测试

- 路径：`app/tests/core/tools/test_mcp_registry_runtime.py`（9 用例）
- 覆盖：5 个方法存在性检查 / add_server 存储配置 / remove_server 删除配置 / toggle_server 更新 enabled / toggle_method 更新 method enabled
- 测试特点：直接构造 `MCPToolsRegistry()` 实例（构造器无重初始化），通过 `asyncio.run()` 调用异步方法

## 前端 MCP 管理 API 封装（2026-06-23 新增，Task 8）

在 `web/Agent/src/utils/api.js` 末尾追加 9 个导出函数，对应后端 `mcp_admin_router`（Task 6）的 8 个端点 + Agent 列表端点。所有函数复用已有的 `fetchWithAuth` 包装器（自动注入 `Authorization: Bearer` 与 `X-Session-ID`，401 自动重试）。

### 模块位置

```
web/Agent/src/utils/
├── api.js                              # 追加 9 个 MCP/Agent API 函数
└── __tests__/
    └── api.mcp.test.js                 # MCP API 测试（8 用例）
```

### 函数清单

| 函数 | HTTP 方法 | 路径 | 说明 |
|---|---|---|---|
| `listMcpServers()` | GET | `/api/admin/mcp/servers` | 列出所有 MCP server 配置 |
| `createMcpServer(config)` | POST | `/api/admin/mcp/servers` | 新增 server；body 为 JSON 配置 |
| `updateMcpServer(name, config)` | PUT | `/api/admin/mcp/servers/{name}` | 更新 server 配置 |
| `deleteMcpServer(name)` | DELETE | `/api/admin/mcp/servers/{name}` | 删除 server；无返回值 |
| `toggleMcpServer(name, enabled)` | POST | `/api/admin/mcp/servers/{name}/toggle?enabled={bool}` | 启用/禁用 server |
| `listMcpMethods(name)` | GET | `/api/admin/mcp/servers/{name}/methods` | 列出 server 下所有 method |
| `refreshMcpMethods(name)` | POST | `/api/admin/mcp/servers/{name}/refresh-methods` | 刷新 method 列表 |
| `toggleMcpMethod(serverName, method, enabled)` | POST | `/api/admin/mcp/servers/{name}/methods/{method}/toggle?enabled={bool}` | 启用/禁用单个 method |
| `fetchAgentList()` | GET | `/api/agent/list` | 获取可用 Agent 列表（供 MCP 配置页绑定） |

### 设计要点

- **复用 fetchWithAuth**：所有函数通过 `fetchWithAuth` 发起请求，自动处理鉴权与 401 重试，无需重复实现
- **URL 编码**：`name` / `method` 路径参数使用 `encodeURIComponent` 编码，防止特殊字符破坏 URL
- **错误处理**：`createMcpServer` 解析后端 `detail` 字段抛出具体错误信息；其余函数抛 `HTTP {status}` 通用错误
- **deleteMcpServer**：唯一无返回值的函数（204 No Content），不调用 `response.json()`

### 测试

- 路径：`web/Agent/src/utils/__tests__/api.mcp.test.js`（8 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，通过动态 `import('../api.js')` 使 mock 生效
- 覆盖：listMcpServers URL + 返回值 / createMcpServer body / deleteMcpServer DELETE 方法 / toggleMcpServer enabled 参数 / listMcpMethods URL / refreshMcpMethods POST / toggleMcpMethod enabled 参数 / fetchAgentList URL + 返回值

## 前端 MCP 服务器管理组件（2026-06-23 新增，Task 9）

创建 `McpServerManager.vue` 组件，基于 Task 8 的 8 个 MCP API 函数实现 MCP 服务器的可视化管理界面。

### 模块位置

```
web/Agent/src/components/
├── McpServerManager.vue                          # MCP 服务器管理组件
└── __tests__/
    └── McpServerManager.spec.js                  # 组件测试（6 用例）
```

### 功能要点

- **左侧服务器列表**：展示所有 MCP server，每项含 toggle 开关（启用/禁用）、类型标签、tags
- **右侧详情面板**：三种状态切换
  - 新增/编辑表单（`.server-form`）：支持 sse/stdio/http 三种类型，stdio 类型显示 Command JSON 输入框
  - 服务器详情（`.server-detail`）：展示名称/类型/URL/tags/状态，含编辑/删除按钮
  - 方法列表（`.methods-section`）：含"刷新方法列表"按钮，每个方法可独立 toggle
- **空状态**：无服务器时显示"暂无 MCP 服务器"提示

### 依赖关系

- 复用 Task 8 的 `api.js` 中 8 个 MCP 函数（listMcpServers/createMcpServer/updateMcpServer/deleteMcpServer/toggleMcpServer/listMcpMethods/refreshMcpMethods/toggleMcpMethod）
- 使用 Vue 3 `<script setup>` 语法，`onMounted` 时自动加载服务器列表

### 测试

- 路径：`web/Agent/src/components/__tests__/McpServerManager.spec.js`（6 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，使用 `mount` + `flushPromises` 模式
- 覆盖：组件可导入 / 渲染服务器列表 / 点击服务器项选中 / 点击新增按钮显示表单 / 选中后显示刷新方法按钮 / 空状态提示

## 前端 UserSettingsDialog MCP 管理 Tab 集成（2026-06-23 新增，Task 10）

将 Task 9 的 `McpServerManager.vue` 组件集成到 `UserSettingsDialog.vue` 的 admin Tab 中，让管理员可以在用户设置对话框中管理 MCP 服务器。

### 修改要点

- **import**：在 `UserSettingsDialog.vue` 顶部新增 `import McpServerManager from './McpServerManager.vue'`
- **navItems**：在 admin 分支的 `session-query` 之后追加 `{ id: 'mcp-management', label: 'MCP 管理', icon: '...' }`
- **template**：在 session-query 的 `v-show` div 之后平级追加 `<div v-show="activeTab === 'mcp-management'" class="tab-content mcp-tab-content"><McpServerManager /></div>`，遵循现有 `v-show` 模式（非 `v-else-if`）

### 测试

- 路径：`web/Agent/src/components/__tests__/UserSettingsDialog.mcp.spec.js`（3 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`；因 `UserSettingsDialog` 使用 `<Teleport to="body">`，nav-item 与 tab 内容渲染到 `document.body`，需通过 `document.body.querySelectorAll` / `document.body.querySelector` 查询元素（`wrapper.findAll` / `wrapper.find` 无法穿透 Teleport）
- 覆盖：admin 角色显示 MCP 管理 Tab / 普通用户不显示 MCP 管理 Tab / 点击 MCP Tab 后渲染 `.mcp-server-manager` 组件

## 前端斜杠命令注册表（2026-06-23 新增，Task 16）

新建 `web/Agent/src/utils/commandRegistry.js` 作为前端斜杠命令的统一注册表与分发器。`InputBox.vue` 检测到 `/` 开头输入时调用 `handleCommand`。

### 模块位置

```
web/Agent/src/utils/
├── commandRegistry.js                 # 命令注册表 + handleCommand 分发器
└── __tests__/
    └── commandRegistry.test.js        # 测试（9 用例）
```

### 命令清单

| 命令 | 用法 | 说明 | requiresBackend |
|---|---|---|---|
| `/agent <name>` | `/agent map_agent` | 切换当前会话使用的智能体；找不到时返回可用列表 | true |
| `/agents` | `/agents` | 列出所有可用智能体（调用 `fetchAgentList`） | true |

### 导出 API

| 导出 | 作用 |
|---|---|
| `COMMAND_REGISTRY` | 命令元数据数组，供 InputBox 自动补全/提示 |
| `handleCommand(command, args)` | 命令分发器，返回 `{text, switchAgent?}`；未知命令返回 `未知命令：/<command>` |
| `listAgentsCommand()` | `/agents` 命令实现，返回格式化文本；空列表返回"暂无可用智能体" |

### 设计要点

- **复用 fetchAgentList**：`/agent` 与 `/agents` 均调用 `api.js::fetchAgentList`（GET `/api/agent/list`），返回 `Array<{name, display_name}>`（**无 description 字段**，渲染时只用 name + display_name）
- **错误传播**：`fetchAgentList` 失败时抛出 `Error`（含后端 `detail`），`handleCommand` 与 `listAgentsCommand` 均不吞错，由调用方（InputBox）捕获并展示友好提示
- **requiresBackend 预留字段**：当前未消费，预留给未来离线模式跳过后端调用
- **switchAgent 信号**：`/agent <name>` 成功时返回 `switchAgent` 字段，InputBox 据此切换实际请求的 agent_name

### 测试

- 路径：`web/Agent/src/utils/__tests__/commandRegistry.test.js`（9 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，通过动态 `import('../commandRegistry.js')` 使 mock 生效
- 覆盖：COMMAND_REGISTRY 含 agent+agents / handleCommand 切换智能体 / 未知命令 / 缺参数 / 智能体不存在 / listAgentsCommand 列表非空 / listAgentsCommand 空列表 / listAgentsCommand 网络错误 / handleCommand 后端失败错误传播

### InputBox 集成（2026-06-23 新增，Task 17）

`InputBox.vue` 已接入命令注册表，检测到 `/` 开头输入时走命令分支，不再触发 refreshToken 与文件上传流程。

**改动点**：

1. **import**：新增 `import { handleCommand, COMMAND_REGISTRY } from '../utils/commandRegistry.js'`
2. **计算属性**：新增 `isCommand`（判断 `/` 开头）、`parsedCommand`（统一解析命令名+参数）与 `commandHint`（复用 `parsedCommand` 匹配 COMMAND_REGISTRY 返回描述+用法提示，未知命令返回 `未知命令：/<cmd>`）
3. **emits 声明**：新增 `agent-switched` 事件（`/agent <name>` 成功时携带目标 agent name）
4. **executeCommand 函数**：从 handleSend 抽取的独立命令执行函数；通过 `isExecutingCommand` ref + try/finally 保证命令执行期间 `canSend` 为 false，防止用户重复点击发送导致重复触发
5. **handleSend 命令分支**：在函数开头检测 `text.startsWith('/')`，命中时调用 `executeCommand(text)` 后提前 return；不进入 refreshToken 流程
6. **template**：textarea 后新增 `<div v-if="isCommand" class="command-hint">{{ commandHint }}</div>`
7. **CSS**：新增 `.command-hint` 样式（accent 色 + accent-light 背景 + radius-sm 圆角）

**测试**：

- 路径：`web/Agent/src/components/__tests__/InputBox.command.spec.js`（7 用例）
- 测试策略：mount InputBox + mock `global.fetch`（按 URL 分发 `/api/auth/refresh` 与 `/api/agent/list`）+ mock `global.localStorage`
- 覆盖：普通文本触发 send 且不触发 agent-switched / `/` 开头显示命令提示 / `/agent map_agent` 命令触发 agent-switched 事件 / 未知命令显示未知命令提示 / `/agent non_exist` 不触发切换且 send 含「不存在」 / `/api/agent/list` 返回非 ok 时 send 含「命令执行失败」 / `/agents` 命令 send 含智能体列表

### App.vue agentName 状态管理（2026-06-23 新增，Task 18）

`App.vue` 新增 `agentName` 响应式状态，承接 InputBox 的 `agent-switched` 事件，并将当前激活智能体名称透传到 `chatStream` 调用。

**改动点**：

1. **状态**：新增 `const agentName = ref('map_agent')`（位于 `currentPage` 之前），默认 `map_agent`，与后端 `agents` 表 `name` 字段一致
2. **事件处理**：新增 `handleAgentSwitched(name)` 函数（位于 `handleToolAction` 之后），含空值/类型守卫与同值短路；更新 `agentName.value` 并打印日志
3. **chatStream 透传**：`handleSendMessage` 与 `handleApprovalSubmit` 两处 `chatStream` 调用均追加第 5 参数 `agentName.value`，确保发送消息与 resume 都携带当前激活智能体
4. **template 绑定**：`<InputBox>` 新增 `@agent-switched="handleAgentSwitched"` 事件监听

**测试**：

- 路径：`web/Agent/src/components/__tests__/App.agent-switch.spec.js`（2 用例）
- 测试策略：mount App.vue + mock `global.fetch`（按 URL 分发 `/api/auth/refresh` 与 `/api/auth/validate` 使 `authReady=true`，InputBox 得以渲染）+ mock `global.localStorage`；通过 `findComponent({ name: 'InputBox' }).vm.$emit('agent-switched', ...)` 模拟子组件事件
- 覆盖：App.vue 有 agentName 状态默认 `map_agent` / 监听 agent-switched 事件后 agentName 更新为目标值

