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

### 中间件执行顺序

1. `CORSMiddleware` — 跨域处理
2. `auth_middleware` — 验证 Access Token（所有非白名单路径）
3. `session_auth_middleware` — 验证 Session（仅聊天相关路径）

### 安全措施

- Access Token payload 包含 `type: "access"`，Refresh Token 包含 `type: "refresh"`
- Refresh Token 不可用于普通 API（auth_middleware 拒绝 type=refresh）
- Access Token 不可用于 refresh 接口（refresh 接口拒绝 type=access）
- Refresh Token 通过 HttpOnly Cookie 传递，前端 JS 无法读取
- Cookie 属性：`HttpOnly; SameSite=Strict; Secure; Path=/api/auth; Max-Age=86400`
- Refresh Token 在服务端数据库存储哈希值，支持主动撤销
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
| /api/session | session_router | 会话管理（创建、删除、列表、详情、标题、附件、消息） |
| /api/files | file_router | 文件管理（上传、下载、删除、列表、PDF转图片） |
| /api/contract | contract_router | 合同主办 Agent |
| /api/map | map_router | 地图 Agent |
| /api/ai-coding-check | ai_coding_check_router | AI 代码检查 Agent |

## 环境变量

- `AUTH_STORAGE_MODE` — 存储模式（postgres/memory）
- `DATABASE_URL` — PostgreSQL 连接字符串
- 其他 LLM API Key 等
