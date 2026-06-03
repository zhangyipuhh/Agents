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
├── html/clint/            # 前端静态文件
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
- Refresh Token 在服务端数据库存储哈希值，支持主动撤销
- Admin 强制下线操作仅清除目标用户的 Refresh Token，保留 Session 记录以便审计查询
- 登出时：删除数据库记录 + 清除 Cookie
- 密码修改时：删除该用户所有 Refresh Token 记录（强制所有设备重新登录）

## 数据库设计

### users 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PRIMARY KEY | 用户ID |
| username | VARCHAR(100) UNIQUE | 用户名 |
| password_hash | VARCHAR(255) | bcrypt 密码哈希 |
| role | VARCHAR(20) DEFAULT 'user' | 角色（admin/user） |
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

## API 路由汇总

| 前缀 | 模块 | 说明 |
|------|------|------|
| /api/auth | auth_router | 认证（登录、注册、验证码、refresh、validate、logout） |
|   ├ POST /login | | 登录：返回 access_token(JSON) + refresh_token(HttpOnly Cookie) |
|   ├ POST /refresh | | 刷新：从 Cookie 读取 refresh_token 换取新 access_token |
|   ├ GET /validate | | 验证：检查 Authorization Bearer token 的有效性 |
| /api/users | user_router | 用户管理（列表、删除、改密码、改用户名） |
|   ├ GET / | | 用户列表（admin 专用） |
|   ├ DELETE /{id} | | 删除用户（admin 专用） |
|   ├ POST /{id}/kick | | 强制用户下线（admin 专用，仅清除 Refresh Token） |
|   ├ GET /online | | 在线用户列表（admin 专用） |
|   ├ GET /{id}/sessions | | 指定用户会话列表（admin 专用） |
| /api/session | session_router | 会话管理（创建、删除、列表、详情、标题、附件、消息） |
|   ├ DELETE /admin/{session_id} | | Admin 强制删除任意会话 |
|   ├ GET /admin/search | | Admin 按用户名搜索会话 |
| /api/files | file_router | 文件管理（上传、下载、删除、列表、PDF转图片） |
| /api/contract | contract_router | 合同主办 Agent |
| /api/map | map_router | 地图 Agent |
| /api/ai-coding-check | ai_coding_check_router | AI 代码检查 Agent |

## 环境变量

- `AUTH_STORAGE_MODE` — 存储模式（postgres/memory）
- `DATABASE_URL` — PostgreSQL 连接字符串
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
- 全量：后端 17/17 + 前端 73/73 全部通过
