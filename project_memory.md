# 项目记忆文档

## 项目概述

Agent User Management 是一个基于 FastAPI 的 AI Agent 管理平台，提供用户认证、会话管理、文件管理、多 Agent 功能等。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **数据库**: PostgreSQL（通过 asyncpg），支持 Memory 模式降级
- **认证**: JWT（双 Token 体系：Access Token + Refresh Token）
- **AI**: LangGraph + LangChain，支持多种 LLM 模型（版本详见下方 "AI 依赖版本与文档约定"）
- **工具**: MCP（Model Context Protocol）工具集成

### AI 依赖版本与文档约定

#### LangChain / LangGraph 全家桶版本（锁定自 `app/requirements.txt`）

| 包                                | 版本   | 用途                                                 |
| --------------------------------- | ------ | ---------------------------------------------------- |
| `langchain`                     | 1.2.16 | LangChain 1.x 主包（统一入口）                       |
| `langchain-core`                | 1.3.2  | 核心抽象（Message、Runnable、@tool 等）              |
| `langchain-classic`             | 1.0.2  | LangChain 1.x 兼容层（旧链式 API、AgentExecutor 等） |
| `langchain-community`           | 0.4.1  | 社区工具/向量库集成                                  |
| `langchain-text-splitters`      | 1.1.1  | 文本切分器                                           |
| `langchain-openai`              | 1.1.6  | OpenAI / 兼容 OpenAI 协议模型                        |
| `langchain-anthropic`           | 1.4.2  | Anthropic Claude                                     |
| `langchain-google-genai`        | 4.2.2  | Google Gemini                                        |
| `langchain-deepseek`            | 1.0.1  | DeepSeek                                             |
| `langchain-ollama`              | 1.0.1  | Ollama 本地模型                                      |
| `langchain-mcp-adapters`        | 0.2.1  | MCP 工具适配为 LangChain 工具                        |
| `langchain-protocol`            | 0.0.14 | 协议层（实验）                                       |
| `langgraph`                     | 1.1.10 | LangGraph 主包（图编排、Checkpoint、Store）          |
| `langgraph-checkpoint`          | 4.1.1  | Checkpoint 抽象基类与内存实现                        |
| `langgraph-checkpoint-postgres` | 3.1.1  | PostgreSQL Checkpoint 后端                           |
| `langgraph-prebuilt`            | 1.0.13 | 预构建节点（ToolNode、create_react_agent 等）        |
| `langgraph-sdk`                 | 0.3.1  | LangGraph 远程部署 SDK                               |
| `langmem`                       | 0.0.30 | 长期记忆扩展                                         |
| `langsmith`                     | 0.7.38 | LangSmith 追踪/评估 SDK                              |
| `deepagents`                    | 0.5.5  | LangChain 官方 subagent 库（沙箱 Agent 依赖）        |

## 数据目录约定

运行时数据目录位于**项目根**（非 `app/` 内），便于与代码解耦并避免被打入 Docker 镜像。

```
data/                          # 项目根运行时数据目录（原 app/data）
├── Knowledge/                 # 知识库数据（地图 Agent）
│   ├── metadata.json
│   ├── sync_metadata.py
│   └── tmp/                   # 临时缓存（doc 转换、large_tool_results）
├── upload/                    # 用户上传原文件（按日期 + session_id 分目录；"不使用文件夹"场景）
│   ├── session_index.json     # session_id -> 日期目录的映射索引
│   └── yyyy/mm/dd/{session_id}/
├── project/                   # 2026-06-30 新增：项目文件夹原文件（按日期 + project_uuid 分目录）
│   └── yyyy/mm/dd/{project_uuid}/
├── tmp/
│   ├── upload/yyyy/mm/dd/{session_id}/    # 上传文件的 .md 转换结果（与 upload 平行）
│   └── project/yyyy/mm/dd/{project_uuid}/            # 2026-06-30 新增：项目文件夹解析缓存
├── download/                  # 用户下载文件（按 session_id 分目录）
├── upload_chunks/             # 分片上传临时目录（按 file_id 分目录）
└── demonstration/download/    # 演示模式专用下载目录
```

### 路径常量集中管理（2026-06-29 新增，2026-06-30 扩展）

`app/core/config/paths.py` 是项目内所有数据目录绝对路径的**唯一真相源**：
- `KNOWLEDGE_DIR` = `<项目根>/data/Knowledge` —— 知识库检索根目录
- `METADATA_FILE` = `<项目根>/data/tmp/Knowledge/metadata.json` —— 知识库元数据缓存
- `TMP_DIR` = `KNOWLEDGE_DIR` 别名（兼容历史）
- `PROJECT_ROOT` = `<项目根>/data/project` —— 2026-06-30 新增；项目文件夹原文件根目录
- `PROJECT_TMP_ROOT` = `<项目根>/data/tmp/project` —— 2026-06-30 新增；项目文件夹解析缓存根目录
- `resolve_project_dir(relative_path: str) -> Path` —— 2026-07-01 新增；将相对路径解析为 `<项目根>` 下的绝对路径，空字符串抛 `ValueError`
- `resolve_project_tmp_dir(relative_path: str) -> Path` —— 2026-07-01 新增；将 `data/project/...` 形式的相对路径映射为 `<项目根>/data/tmp/project/...` 绝对路径，空字符串抛 `ValueError`
- `resolve_tmp_mirror_path(original_path: str | Path) -> Path | None` —— 2026-07-07 新增；将 `data/...` 下的原文件路径映射为 `<项目根>/data/tmp/.../.md` 镜像路径，不在 `data/` 下时返回 `None`，扩展名统一替换为 `.md`
- `app/shared/utils/files/project_path_manager.py` —— 2026-07-01 重构；`get_project_upload_dir(relative_path, create=False)` 与 `get_project_tmp_upload_dir(relative_path, create=False)` 不再自行计算项目根，统一委托给上述 `resolve_project_dir` / `resolve_project_tmp_dir`，入参由 `project_uuid` 改为完整的相对路径（如 `data/project/2026/07/01/uuid`）
- `app/shared/utils/files/fileTransfer.py` —— 2026-07-01 同步改造；`delete_session` 处理 `project_id` 时直接读取 `project['relative_path']` 并传入 `get_project_upload_dir` / `get_project_tmp_upload_dir`，不再使用 `project['uuid']` 推导路径
- `app/core/router/file_upload_router.py` —— 2026-07-01 同步改造；`uploadfile` 与 `merge-chunks` 的 project 分支均改为读取 `project['relative_path']` 并传入 `get_project_upload_dir` / `get_project_tmp_upload_dir`，docstring 路径示例同步更新为日期化格式；2026-07-01 新增 `DELETE /api/core/attachments` 端点，按 `stored_path` 批量删除 `.md` 缓存、原文件及 `attachments` 记录，并校验 session_id/project_id 归属
- `app/shared/tools/middleware/filesystem_encoding_fix.py` —— 2026-07-01 确认：`_patched_read` 与 `_patched_python_search` 基于 `data/` → `data/tmp/` 前缀映射，天然兼容 `data/project/yyyy/mm/dd/{uuid}/` ↔ `data/tmp/project/yyyy/mm/dd/{uuid}/` 的日期化项目目录，无需额外修改；**2026-07-07 改造**：`_patched_read` 仅对 `pdf/docx/xlsx/md/txt` 扩展名重定向到 `.md` 缓存，非文档类扩展名（如 `.py/.json`）直接读取 `self.cwd` 下的原文件；新增 `_patched_write` 并在 `apply_fix()` 中注册，写入 `pdf/docx/xlsx/md/txt` 时同步生成 `data/tmp/.../.md` 镜像
- `app/shared/tools/middleware/docker_sandbox_backend.py` —— 2026-07-07 改造：`DockerSandboxBackend` 重写 `write`/`awrite`，直接在当前 Python 进程（宿主机侧）写入 workspace 并同步生成 `.md` 镜像，避免 `BaseSandbox.write` 在 Docker 容器内执行 preflight 路径检查时可能无法识别宿主机路径的问题，同时支持 Docker 与 local fallback 模式

**禁止**在业务代码中通过 `os.path.dirname(__file__)` 自行计算项目根；**禁止**通过 `runtime.context["knowledge_root"]` 传递路径（该字段已废弃）。

### Docker 部署 - agents/ 目录（2026-07-09 新增）

agents 表 `agents_md_path` 字段存储**相对路径**（如 `agents/project/AGENTS.md`），容器内 CWD=`/app`，`AgentsMdLoader.load()` 通过 `Path.is_file()` 判断时依赖 CWD 能解析到仓库根 `agents/` 目录。

**最终镜像/卷配置**：

- `app/Dockerfile`：`COPY agents/ /app/agents/` 把仓库根 `agents/` 打进镜像 `/app/agents/`，保证 `docker compose up` 启动即可访问
- `docker-compose.yml`：在 `agents` 服务 volumes 段追加 `- ./agents:/app/agents:rw`，运行时覆盖镜像内文件，便于开发期修改 `AGENTS.md` 后立即生效（AgentsMdLoader 有 `clear_cache()` 但此处未依赖，卷挂载 + 重启即可）；同时不需要 `docker compose build` 重建镜像

**根因**：原 Dockerfile 只 `COPY app/ /app/app/`，未把仓库根 `agents/` 入镜像 → docker 启动后 `get_agent_config()` 触发 `_loader.load('agents/project/AGENTS.md')` → `FileNotFoundError`。

### 项目文件夹（2026-06-30 新增）

用户在聊天框下拉框选择「新建空白项目」或「使用现有文件夹」后，会话文件会落到独立的 `data/project/yyyy/mm/dd/{project_uuid}/` 目录。`projects` 表通过 `relative_path` 字段持久化存储该相对路径（从 `data` 开始，如 `data/project/2026/07/01/uuid`），作为项目文件夹物理路径的唯一真相源；读取时优先从 `ProjectDB` 内存缓存获取，写入时同步更新数据库与内存缓存。详细设计见下文「项目文件夹方案」章节。

通用规则见 `AGENTS.md` "Path Management Rules"。

### asyncpg JSONB codec（2026-07-01 新增）

`app/core/database.py::DatabasePool.initialize()` 创建连接池时通过 `init` 回调
注册 JSONB / JSON 列类型 codec，使 asyncpg 自动将 JSONB 列反序列化为 Python
原生对象（list / dict）而非默认的 JSON 字符串。

- **注册方式**：`await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')`，`json` 同理；`_init_connection` 作为 `asyncpg.create_pool(init=cls._init_connection)` 回调
- **影响范围**：全项目所有 JSONB 字段均自动按 Python 原生类型返回，包括：
  - `users.allowed_agents`
  - `agents.config_schema` / `agents.tool_bindings` / `agents.skill_bindings` / `agents.mcp_tags` / `agents.state_schema` / `agents.context_schema`
  - `agent_tool_bindings.*`（含 `tool_type` 等元数据）
  - `conversation_records.tool_calls`
  - `tools.args_schema`
- **写入端约定**：保留 `$N::jsonb` 显式 cast + `json.dumps(...)` 调用（asyncpg 会先 dumps 再入库，与 codec 无冲突；未来单独 PR 清理）
- **防御性兜底**：`UserDB.list_users` / `get_user_by_username` / `get_user_by_id` 三处 postgres 返回路径统一调用 `_coerce_allowed_agents()`，把 JSONB 字符串 / 异常 JSON / 原生 list 规整为合法 list，避免 codec 注册失败或单测 stub 字符串值时下游 Pydantic 校验失败
- **修复触发**：2026-07-01 `GET /api/users` 返回 500 —— Pydantic 校验 `UserResponse.allowed_agents` 时收到 `str '[]'` 而非 `list`
- **测试**：
  - `app/tests/shared/test_user_db_postgres_jsonb.py` —— 7 用例覆盖 postgres 分支 JSONB 字符串 / 空串 / 非法 JSON / 原生 list / 未命中记录
  - `app/tests/core/test_database_jsonb_codec.py` —— 2 用例覆盖 `_init_connection` 行为 + `initialize` 源码静态分析
  - `app/tests/shared/test_user_router.py` —— 追加 `test_list_users_returns_200_with_native_list_allowed_agents` 路由契约测试

## 项目架构

```
app/
├── core/                    # 核心模块
│   ├── server.py           # FastAPI 应用配置（生命周期、中间件、CORS）
│   ├── config/settings.py  # 配置管理
│   ├── database.py         # 数据库连接池
│   ├── prompts.py          # 通用基类系统提示词（BASE_SYSTEM_PROMPT），已包含时间处理策略：当用户问题涉及时间/日期/相对时间（如“今天”“最近N年”“过去N个月”）时，必须首先调用 get_current_time 工具获取当前时间，并将相对时间转换为绝对时间范围后，再写入子任务 prompt（如 query_knowledge），禁止直接传递含相对时间的原始问题
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
├── routers/                # 全局管理路由
│   ├── __init__.py           # 包初始化
│   ├── mcp_admin_router.py   # MCP Admin 路由（CRUD + toggle + refresh methods）
│   ├── agent_router.py       # 统一 Agent 路由（，/api/agent/chat|list|agents-md）
│   ├── knowledge_router.py   # 知识库路由
│   ├── tool_admin_router.py  # Tool Admin 路由
│   ├── skill_admin_router.py # Skill Admin 路由
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
│   │       ├── map_agent/    # map_agent 工具（MapTools.py，11 个工具：8 地图 + query_knowledge + generate_report + save_business_info；配套 config/ 子目录承载报告配置）
│   │       └── project/      # project 智能体工具（ProjectTools.py，8 个工具：intent_clarification / project_doc_query / project_doc_outline / project_doc_write / project_doc_workflow / manage_project_log / append_change_log / generate_project_docx）
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
│       │   ├── project_path_manager.py  # 项目文件夹路径管理（委托 resolve_project_dir / resolve_project_tmp_dir）
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
│   │   ├── components/ChatArea.vue  # 2026-07-02 修正：标题栏与消息区改为 flex 分栏布局，
│   │   │                              标题栏不再使用 sticky，消息内容不会被标题栏压盖
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

## Agent 统一构造入口（2026-06-29 新增）

### `AgentConfigService.build_agent_instance()`

**位置**：`app/shared/utils/agent/agent_config_service.py::build_agent_instance()`

**职责**：所有 chat 路由的统一构造入口，封装「取配置 → 构造 context/state → 构造 AgentConfig → 初始化 Agent」完整流程。

**调用方**：
- `app/routers/agent_router.py::chat()` —— 通用 Agent 聊天（2026-06-29 已迁移）
- （后续）其他 chat 路由可逐步迁移到该入口

**关键参数**：
| 参数 | 类型 | 说明 |
|---|---|---|
| `agent_name` | `Optional[str]` | 智能体名称（None 使用默认配置） |
| `session_id` | `str` | 会话 ID |
| `message` | `Optional[str]` | 用户消息（resume 场景可为空） |
| `context_overrides` | `Optional[Dict]` | context 字段覆盖（保留字段自动过滤） |
| `resume` | `Optional[Dict]` | HITL 恢复参数 |
| `state_class_kwargs` | `Optional[Dict]` | 透传给 state_class 的额外 kwargs |
| `system_prompt_override` | `Optional[str]` | 覆盖 system_prompt |

**返回**：`(Agent, AgentContext, Union[AgentState, Command])` 三元组

**内部流程**：
1. `await self.get_agent_config(agent_name)` → `UnifiedAgentConfig`（继承缓存机制）
2. 过滤 `context_overrides` 中保留字段 → 构造 `context_class(session_id=..., **safe_overrides)`
3. resume 时构造 `Command(resume=...)`，否则构造 `state_class(messages=[HumanMessage(content=...)], **state_class_kwargs)`
4. **过滤 `enabled_skill_names`**：通过注入的 `_skill_service` 校验每个 skill 在 DB `skills` 表中是否注册且 `enabled=True`；未注册或已禁用的 skill 从列表移除并记录 `logger.warning`
5. `await get_async_checkpointer()` + `await get_async_store()` → 注入 `AgentConfig`
6. `AgentConfig(..., enabled_skill_names=filtered, tools=config.tools, ...)` → `Agent(agent_config).__ainit__()`

**当前限制**：
- HumanMessage 固定为 `HumanMessage(content=message)`，不支持自定义构造
- knowledge_router.py::knowledge_chat() 暂未迁移到 build_agent_instance()（需要 `HumanMessage.additional_kwargs` 注入 attachments，超出本方法能力范围），但已于 2026-06-29 修补 `enabled_skill_names=config.enabled_skill_names` 传入，避免 SkillsAwarePrompt 回退到加载全部 skill
- get_map_agent() 同样已修补 `enabled_skill_names` 传入
- 后续如有需求可扩展 `human_message_factory` 参数

**设计原则**：
- router 只做 HTTP 适配层职责（参数提取、错误转换、SSE 响应包装、session.agent_type 自动绑定）
- service 层封装所有 Agent 构造逻辑（单一出入口）
- 任何新增 Agent 路由必须调用此方法，禁止复制 Agent 构造代码

**测试覆盖**：
- `app/tests/shared/utils/agent/test_agent_config_service.py` —— 14 个 build_agent_instance 用例（新增：过滤已禁用 skill / 过滤未注册 skill）
- `app/tests/routers/test_agent_router.py` —— 4 个用例（chat 调用 build_agent_instance / 404 映射 / 500 映射 / router 不再 import Agent）
- `app/tests/routers/test_knowledge_router.py` —— 1 个用例（验证 knowledge_chat 端点构造 AgentConfig 时传入 enabled_skill_names）

## 认证体系（双 Token）

### Token 类型

| Token         | 有效期  | Payload type        | 客户端存储                                         | 服务端存储                                  | 用途                                             |
| ------------- | ------- | ------------------- | -------------------------------------------------- | ------------------------------------------- | ------------------------------------------------ |
| Access Token  | 30 分钟 | `type: "access"`  | 前端内存（JS 变量）                                | 无（纯 JWT 无状态）                         | 所有 API 请求的 `Authorization: Bearer` 认证   |
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
  - `/api/session/{id}/export/markdown` — 导出会话完整对话为 Markdown（含子智能体轨迹）
  - `/api/session/{id}/files/*` — 会话文件空间（树形结构、预览、下载）
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
- **智能体选择权限**：`users.allowed_agents` 控制每个用户可在 `/command` 下拉中选择的智能体；空列表表示不可选择任何智能体；该限制对所有角色（含 admin）生效
  - 前端 `InputBox.vue` 的 `filteredAgents` 按 `allowedAgents` 过滤；后端 `/api/agent/list` 按 `request.state.allowed_agents` 过滤；`/api/agent/chat` 对非 `default` 的 `agent_name` 做 403 校验
  - 认证响应 `/api/auth/validate` 与 `JWTAuth.authenticate` 均透传 `allowed_agents`

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
  - [docs/third-party-api-integration-guide.md](file:///e:/laboratory/AI/Agents/agent-user-mangerment/docs/third-party-api-integration-guide.md) — 第三方后端 API 接入完整指南（**非 iframe 场景**，v2.0 重构后无需 portal 子 token）
  - [docs/refresh-token-misunderstanding.md](file:///e:/laboratory/AI/Agents/agent-user-mangerment/docs/refresh-token-misunderstanding.md) — Refresh Token 调研澄清报告

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
| agent_name | VARCHAR(100) FK → agents(name) | 目标智能体 |
| prompt | TEXT | 定时触发时发送给智能体的提示词 |
| cron_expression | VARCHAR(100) | 5 段 crontab 表达式，如 `0 9 * * *` |
| timezone | VARCHAR(64) | IANA 时区，默认 `Asia/Shanghai` |
| enabled | BOOLEAN | 是否启用 |
| created_by_user_id | INTEGER FK → users(id) | 创建人，用于后台执行时创建 session |
| context_overrides | JSONB | 注入 AgentContext 的扩展字段，默认 `{}` |
| max_concurrent_runs | INT | 单任务并发配置，默认 1 |
| last_run_at / next_run_at | TIMESTAMP | 最近运行与下次运行时间 |
| created_at / updated_at | TIMESTAMP | 创建与更新时间 |

`agent_task_runs` 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | SERIAL PRIMARY KEY | 执行记录 ID |
| schedule_id | INTEGER FK → agent_task_schedules(id) | 所属定时任务 |
| session_id | VARCHAR(100) | 本次触发创建的新会话 ID |
| agent_name | VARCHAR(100) | 执行时智能体名称快照 |
| prompt_snapshot | TEXT | 执行时提示词快照 |
| status | VARCHAR(32) | `pending` / `running` / `success` / `failed` / `skipped` |
| trigger_type | VARCHAR(32) | `scheduled` / `manual` |
| scheduled_at / started_at / finished_at | TIMESTAMP | 计划、开始、结束时间 |
| duration_ms | INTEGER | 执行耗时毫秒 |
| output_text | TEXT | 最后一条 AI 消息文本 |
| error_message | TEXT | 失败或跳过原因 |
| created_at | TIMESTAMP | 记录创建时间 |

**接口**：`app/routers/task_scheduler_router.py`，前缀 `/api/admin/task-schedules`，全部受 `require_admin` 保护；提供列表、详情、新建、更新、删除、启停、立即运行与执行历史查询。

**服务**：`app/shared/utils/agent/task_scheduler_service.py::TaskSchedulerService`，由 lifespan 真实初始化到 `app.state.task_scheduler_service`；测试中只能注入真实 service 实例，不允许通过 `app.state.db = MagicMock()` 虚构生产不存在的依赖。

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

## 项目文件夹方案（2026-06-30 新增）

### 设计目标

用户从聊天框下拉框选择"进入项目工作"后：
- 上传的文件落到独立的项目目录（与 session 目录完全隔离）
- 同一项目可被多个 session 共享（多 session 协作）
- 沙箱 / explore / audit 等工具能读取项目目录里的文件
- 历史会话切换时自动恢复项目选择

### 完整语义模型

| 操作 | sessions.project_id | projects.uuid | 物理路径 |
|------|---------------------|---------------|----------|
| 用户新建项目"Daily-work"（无 session） | NULL | `proj-uuid-a` | `data/project/2026/07/06/proj-uuid-a/` |
| session 1111 绑定到项目 1 | 1 | `proj-uuid-a` | `data/project/2026/07/06/proj-uuid-a/`（共享项目目录）|
| session 2222 绑定到项目 1 | 1 | `proj-uuid-a` | `data/project/2026/07/06/proj-uuid-a/`（共享项目目录）|
| session 2222 切回不使用文件夹 | NULL | - | `data/upload/.../2222/` |
| 旧历史会话（无 project） | NULL | - | `data/upload/.../session_id/` |

**关键点**：项目是独立实体，`projects.uuid` 不再与 session_id 绑定；多 session 通过 `sessions.project_id` 关联到同一项目目录。

### 路径查找策略

```python
# session_path_manager.get_session_upload_dir(session_id, project_id=None)
if project_id:
    project = ProjectDB.get_project_by_id(project_id)
    return get_project_upload_dir(project['relative_path'])  # data/project/yyyy/mm/dd/{uuid}/
# 无 project_id：原 session 路径
return data/upload/yyyy/mm/dd/{session_id}/
```

**有 project_id 就用 project_id，没有再用 session_id**——兼容旧 session 逻辑。项目目录按 `projects.relative_path` 解析，不再直接用 `uuid` 推导。

### 关键模块

| 模块 | 职责 |
|------|------|
| `app/shared/utils/project/project_db.py` | ProjectDB 两级缓存（参照 SessionDB 模式） |
| `app/shared/utils/files/project_path_manager.py` | 项目独立目录路径解析 |
| `app/shared/routers/project_router.py` | 项目 CRUD + session 绑定/解绑 API |
| `session_auth_middleware` | 中间件注入 `request.state.project_id` |
| `app/routers/agent_router.py::chat` | 把 project_id 注入 `context_overrides` |
| `AgentContext.project_id` | 工具通过 `runtime.context.get("project_id")` 读取 |
| `app/shared/utils/files/fileTransfer.py` | 2026-07-01 新增：`build_session_file_tree` 构建会话/项目文件树；`resolve_session_file_path` 解析并校验文件路径（防路径遍历）；`_get_preview_mode` / `read_session_file_content` 支持文本/图片/Office/PDF 预览；`delete_session` 同步支持项目目录清理

### 工具透传链

`AgentContext.project_id` → 各工具通过 `runtime.context.get("project_id")` 读取 → 透传给 `get_session_upload_dir(session_id, project_id=project_id)`

已透传的工具：
- `SandboxTools.py` —— 沙箱 workspace
- `FilesystemReadTools.py` —— 文件检索
- `file_upload_handler.py` —— 文件处理
- `fileTransfer.py` —— 文件上传/下载/删除
- `pdfToImage.py` —— PDF 转图片
- `audit_document_agent/tools/tools.py` —— 审计 parse_transaction

### 前端集成

| 组件 | 职责 |
|------|------|
| `ProjectDropdown.vue` | 紧挨着 InputBox 上方的下拉框（顶部只读预览 + 3 个动作 + 锁定支持） |
| `ProjectDialog.vue` | 双模式弹窗（create / pick）；create 模式点击保存后 emit `created`，弹窗关闭由父组件控制 |
| `App.vue` | `currentProject` 状态机 + handleSessionSwitch 恢复 + newSession 纯前端重置（2026-07-XX 改造）+ `canEditProject` 锁定判定 + `ensureSessionForFirstOp` 按需建 session + `handleProjectCreate` 成功后关闭弹窗并刷新按钮文案 |

### 前端 Session 创建时机改为「首次交互时」（2026-07-XX 改造）

**动机**：原实现中点击「新建任务」按钮或刷新页面都会触发 `/api/session/create`，产生大量"用户未实际交互"的空 session 入库，污染 DB 与侧边栏。

**新规则**：

- **首次进入页面 / 刷新页面**：**不**自动建 session；`sessionId` 保持空字符串，侧边栏无激活项、无"新对话"条目。
- **点击「新建任务」按钮（Sidebar 菜单 / InputBox 的 `@new-chat` 等）**：仅做纯前端页面重置（清 messages / attachments / agentName / sessionTitle / SubAgentDrawer / SessionFileDrawer / approvalMode / `toolStopPending` / `queueStatus`），**不**调 `/api/session/create`。
- **session 的实际创建延后到真正需要后端的入口**：
  1. **首条消息发送**（`handleSendMessage` 在 `chatStream` 前先 `await ensureSessionForFirstOp(projectIdForChat)`）
  2. **发送时存在文件附件**：选择文件本身只进入本地列表，点击发送后 `InputBox::handleSend` 先 `await props.ensureSession(projectIdForUpload)`，再统一上传文件；并发上传由 `createNewSession` 自带的 `isCreatingSession / pendingSessionPromise` 防重锁收敛到 1 次后端调用。2026-07-07 修正：禁止纯附件发送，必须有文本才能触发发送与上传。
  3. **首次斜杠命令**：命令结果走 `emit('send', result.text, [])` 进入 `handleSendMessage` → 命中第 ① 点。

- **项目选择/创建本身不触发 session 创建**（2026-07-06 修正）：项目是独立实体，`App.vue::handleProjectPick` / `handleProjectCreate` / `handleProjectSelectNone` 不再以 `sessionId.value` 是否存在为前提。无 session 时仅更新前端 `currentProject` 状态；有 session 时才调用 `/api/project/session/bind` 或 `/api/project/session/unbind` 同步当前会话的项目关联。未建 session 时若用户发送首条消息 / 上传文件，`ensureSessionForFirstOp(currentProject.id)` 会一并把项目 ID 带到 `/api/session/create`。

**实现要点**：

- `App.vue` 删除原 `ensureSession()`，`onMounted` 仅保留 `checkAuth()`。
- `App.vue` 新增 `ensureSessionForFirstOp(projectId)`：若 `sessionId.value` 已存在则短路返回；否则 `createNewSession('session_id', projectId)` → 同步 `sessionId.value` / `sessionTitle` → `refreshSessionTitle` 异步刷新真实标题 → `sidebarRef.loadSessionList()` 刷新侧边栏。
- `App.vue::handleApprovalSubmit` 加防御性 early-return：缺 `sessionId` 时直接退出（实际不会触发，因为触达 HITL 必然先经历 `handleSendMessage`）。
- `App.vue::handleProjectPick` / `handleProjectCreate` / `handleProjectSelectNone`（2026-07-06 修正）：项目是独立实体，选择/创建/解绑项目不再以 `sessionId.value` 为前提。无 session 时仅更新前端 `currentProject` / `currentAttachments` 状态；有 session 时才调用 `/api/project/session/bind` 或 `/api/project/session/unbind` 同步当前会话的项目关联。创建项目时 `createProject(name)` 不再传入 `session_id` 作为 uuid，由后端独立生成。`handleProjectCreate` 对返回值做防御性读取，成功设置 `currentProject` 后由父组件关闭弹窗，确保按钮文案实时刷新；`handleProjectPick` 对入参做基础校验。
- `App.vue` 模板 `<InputBox :ensure-session="ensureSessionForFirstOp" ... />`。纯文本发送时 `ensureSession` 不在 InputBox 内调用，仍由 `App.vue::handleSendMessage` 负责按需创建 session；仅当 InputBox 内存在待上传文件时才在发送流程中调用 `ensureSession`。
- `InputBox.vue` 新增状态 `isUploading`：发送上传期间禁用发送按钮，避免重复触发。
- `InputBox.vue` 选择文件后仅加入 `selectedFiles`（状态 `pending`），不立即上传；`addFiles` 完成时若存在有效文件即 `emit('project-lock-change', true)`，防止用户在发送前切换项目导致附件挂接到错误 projectId。
- `InputBox.vue::handleSend` 新流程：① 检查必须有文本；② 刷新 token；③ 若存在 `pending` 文件则 `await props.ensureSession(projectIdForUpload)` 创建/获取 session 并挂接 projectId；④ 调用 `startUpload` 统一上传；⑤ 任一文件失败则提示错误并中断发送；⑥ 全部成功后 `emit('send', text, uploadedFiles)` 并清空输入框与文件列表。
- `InputBox.vue::startUpload` 移除内部 `ensureSession` 调用，仅执行分片上传，并返回 `uploadFileInChunks` 的 Promise 以支持 `handleSend` 中 `Promise.all` 等待。
- `InputBox.vue::removeFile` 对 `pending` 文件仅本地移除，不调用 `deleteAttachments`；删除后 `selectedFiles` 为空时 `emit('project-lock-change', false)`。
- `Sidebar.vue` 的 `currentSessionId` 默认值已为 `''`，与历史 session_id 比较时天然不匹配；空 session 时不高亮任何条目，无需额外改动。

**影响面**：

- 后端 `/api/session/create` 接口契约不变；`createNewSession` 自带的防重复锁机制复用。
- `KnowledgeApp.vue` / `KnowledgePage.vue` 维持独立链路（独立 `knowledge_session_id`），本次未在范围内，逻辑保持原状。
- 项目选择器锁定（`canEditProject`）语义扩展：新建任务（messages 空且无成功上传文件）→ 可编辑；首条消息发送成功或存在成功上传文件 → 锁定（详见「项目选择器锁定逻辑」章节）。

### 后端 `/api/agent/list` 加入 Session 白名单（2026-07-XX 配套）

**动机**：前端按需建 session 改造后，`<InputBox onMounted>` 调 `fetchAgentList()`（`GET /api/agent/list`）时 `localStorage.session_id` 为空 → 后端 `session_auth_middleware` 命中 `SESSION_REQUIRED_PREFIXES`（`/api/agent/`）→ 抛 400 "缺少 X-Session-ID 请求头"，导致侧边栏"项目 / 智能体下拉"等首屏交互失效。

**新规则**：

- `app/shared/utils/auth/Safety.py::SESSION_WHITELIST_PREFIXES` 追加 `"/api/agent/list"`（与 `/api/session/list` 同模式：精确前缀匹配）。
- `list_agents` 路由**不依赖 session 隔离**，仅读 `request.state.allowed_agents`（来自 JWT），跳过 X-Session-ID 校验。
- `/api/agent/chat` 仍命中 `SESSION_REQUIRED_PREFIXES`（`/api/agent/`），保持 session 校验不变（按需建 session 的核心保证）。

**实现要点**：

- `app/shared/utils/auth/Safety.py`：`SESSION_WHITELIST_PREFIXES` 列表末尾追加 `"/api/agent/list"` + 注释。
- `app/routers/agent_router.py::list_agents` docstring 补充"不依赖 session_id 隔离"说明。
- `app/tests/routers/test_agent_router.py` 新增 2 个回归测试：
  - `test_list_agents_works_without_session_id`：不带 `X-Session-ID` 头调用 `GET /api/agent/list` → 期望 200。
  - `test_agent_chat_still_requires_session_id`：不带 `X-Session-ID` 头调 `POST /api/agent/chat` → 期望 400，验证白名单精确前缀不会误伤 `chat`。

**影响面**：

- 与 `/api/agent/list` 同语义的 `/api/session/list` / `/api/project/list` 早就走白名单或自然放行，行为对齐。
- 前端 `InputBox::loadAgents()` / `fetchAgentList()` 调用链路不变；冷启动 / 按需建 session 阶段 `GET /api/agent/list` 自动 200，智能体下拉正常工作。

### 项目选择器锁定逻辑（2026-07-01 新增，2026-07-06 扩展）

**规则**：

- 新建会话、`messages` 数组为空且不存在已选文件时 → 项目选择器**可编辑**
- 一旦该会话成功发送过一条消息（或被恢复的历史会话本身有消息）→ 项目选择器**永久锁定**（同一会话再也不能改项目）
- 仅选择文件（未发送）→ 项目选择器**锁定**（2026-07-07 修正：只要 `selectedFiles` 非空即锁定，避免发送前切换项目导致附件挂接到错误 projectId）
- 删除所有已选文件且 `messages` 仍为空 → 项目选择器**恢复可编辑**（2026-07-07 修正：删除后 `selectedFiles` 为空即解锁）
- 切到历史会话时 → 若历史消息数 > 0，**锁定**；若历史为空，**仍可编辑**（允许给从未发过消息的空会话补绑项目）
- 历史会话 `fetchSessionMessages` 失败时 → **默认锁定**（保守策略，避免未知状态下误操作）
- `streaming` 中 → 仍按 `disabled` 短路（与锁定独立，两个维度均可独立触发 disable）

**实现**：

- `App.vue` 新增 `historyLoadFailed = ref(false)`、`projectLockedByUpload = ref(false)` 与派生 `canEditProject = computed(() => isEmptyState.value && !historyLoadFailed.value && !projectLockedByUpload.value)`
- `App.vue::handleSessionSwitch` 入口重置 `historyLoadFailed`，catch 块置 true
- `App.vue::newSession` 重置 `historyLoadFailed` 与 `projectLockedByUpload`
- `App.vue` 模板：`<InputBox :project-locked="!canEditProject" @project-lock-change="projectLockedByUpload = $event" ... />`
- `InputBox.vue` 新增 prop `projectLocked`，透传给 `<ProjectDropdown :locked="projectLocked" />`；新增计算属性 `hasSelectedFiles`（`selectedFiles.length > 0`），并在选择文件时 `emit('project-lock-change', true)`、删除后列表为空时 `emit('project-lock-change', false)`
- `ProjectDropdown.vue` 新增 prop `locked`，与 `disabled` 通过 `effectiveDisabled = computed(() => disabled || locked)` 合并；`toggleDropdown()` 短路 `effectiveDisabled`；按钮 `:disabled="effectiveDisabled"`、class `disabled` 同步
- **视觉**：复用现有 `.disabled` 样式（灰 + not-allowed），不新增图标（设计决策：避免与 streaming 状态视觉混淆，用户可通过 hover tooltip "项目已锁定" 知晓原因）

**测试**（Vitest，全过）：

- `web/Agent/src/components/__tests__/ProjectDropdown.locked.spec.js` — `locked=true` 时按钮 disabled、点击不开下拉、已选项 label 保留可见、`disabled || locked` 任一为 true 都短路
- `web/Agent/src/components/__tests__/InputBox.locked.spec.js` — `projectLocked` prop 透传到 `ProjectDropdown.locked`，默认值 false，与 `isStreaming` 解耦
- `web/Agent/src/components/__tests__/InputBox.upload-lock.spec.js` — 2026-07-07 改造：选择文件后立即 emit `project-lock-change(true)`；仅选文件无文本时 `canSend=false` 且不上传/不创建 session；有文本+文件时发送才调用 `ensureSession`（携带 projectId）、上传文件并 emit `send`；删除全部文件后 emit `project-lock-change(false)`
- `web/Agent/src/components/__tests__/App.project-lock.spec.js` — `canEditProject` 派生：初始 true、恢复历史会话后 false、history 拉取失败默认锁定 false、`newSession` 重置回 true、`projectLocked` 透传到 InputBox；存在已选文件时 `projectLockedByUpload` 为 true 导致 `canEditProject` 为 false

### 前端 chat 请求体显式携带 project_id（2026-07-01 新增）

为消除 chat 时对 `sessions.project_id` 隐式链路的完全依赖，前端在调用 `chatStream` / `knowledgeChatStream` 时把当前项目 ID **显式放进请求 body 的 `context_overrides.project_id` 字段**，与 `newSession` 显式传 `projectId`（`App.vue:301`）的设计保持一致（"显式优于隐式"）。

**前端改动**：

- **`web/Agent/src/utils/api.js`**：`chatStream` / `knowledgeChatStream` 签名扩展 `projectId` 参数（向后兼容，默认 `null`）；body 把原本硬编码的 `geometry_data: {}` 合并进 `context_overrides.geometry_data`（`chatStream`），把 `projectId` 在非 null 时注入 `context_overrides.project_id`。
- **`web/Agent/src/App.vue`**：`handleSendMessage`（行 442）/ `handleApprovalSubmit` resume（行 539）调 `chatStream` 时从 `currentProject.value.id` 取出传入。
- **`web/Agent/src/KnowledgeApp.vue`**：本次未接入（无 `currentProject` ref）；仍依赖 `session_auth_middleware` 注入 `request.state.project_id` 兜底。
- **`web/Agent/src/components/KnowledgeChat.vue`**：本次未修改；调 `knowledgeChatStream` 时不传 `projectId`，等 `knowledge_router.py` 后续改造。

**后端透传路径（2026-07-01 简化）**：

1. 前端 `chatStream` body `context_overrides.project_id` → `ChatRequest.context_overrides`（`agent_router.py:56`）→ `agent_router` 仅做空值过滤（`_EMPTY_VALUES`）后透传 `build_agent_instance`。
2. `agent_config_service.py::build_agent_instance` 通过 `RESERVED_CONTEXT_FIELDS` 过滤 `safe_overrides` 后注入 `context_class(**safe_overrides)`。
3. **2026-07-01 移除 `project_id` 字段后**：`AgentContext` 不再预声明 `project_id`（见下节），`RESERVED_CONTEXT_FIELDS` 也同步移除该键；`project_id` 作为"自定义上下文键"由前端经 `context_overrides` 注入，运行时经 TypedDict dict 落到 `runtime.context.get("project_id")` 供 `SandboxTools` / `FilesystemReadTools` 等工具读取。

**修改文件（2026-07-01）**：

- `web/Agent/src/utils/api.js` —— `chatStream` / `knowledgeChatStream` 扩签名 + body 改造
- `web/Agent/src/App.vue` —— `handleSendMessage` / `handleApprovalSubmit` resume 传 `projectId`
- `app/core/agent/AgentContext.py` —— **删除** `project_id: Optional[int] = None` 字段（含 import 调整）；类文档注释说明 `project_id` 由调用方通过 `context_overrides` 显式注入
- `app/shared/utils/agent/dynamic_schema.py` —— 从 `RESERVED_CONTEXT_FIELDS` 移除 `"project_id"`（不再属于基类保留字段）
- `app/shared/utils/agent/agent_config_service.py::build_agent_instance` —— 回退特殊处理，恢复通用 `context_class(session_id=..., **safe_overrides)` 形式
- `app/routers/agent_router.py::chat` —— 回退 `request.state.project_id` 合并逻辑（删除 `getattr(request.state, "project_id", None)` 与 merged_overrides 合并分支），改纯透传 `chat_request.context_overrides`；保留 `_EMPTY_VALUES` 空值过滤

**未修改（保持兼容）**：

- `app/shared/utils/auth/Safety.py::session_auth_middleware` —— 仍向 `request.state.project_id` 注入值（`app/core/router/file_upload_router.py` 上传/合并分片路由还在用 `request.state.project_id`）
- `app/routers/knowledge_router.py` —— 本次不同步（用户决策）
- `get_session_upload_dir(session_id, project_id=...)` 工具链不变
- `app/routers/file_upload_router.py` —— 上传路径仍依赖 `request.state.project_id`（这是 HTTP 路由层而非 agent runtime 层，链路不同）

**测试覆盖**：

- 前端 Vitest `web/Agent/src/utils/__tests__/api.agent-chat.test.js` 共 10 用例全过（4 旧 + 6 新）
- 后端 pytest `app/tests/routers/test_agent_router.py` 共 30 用例全过（含重写的 `test_chat_context_overrides_project_id_passed_through` / `test_chat_context_overrides_without_project_id_is_empty` / `test_chat_context_project_id_reaches_agent_context_runtime` 三个新语义用例）

**设计原则**：「显式优于隐式」；前端 `context_overrides` 通道作为唯一透传路径，移除 agent runtime 对基类字段的硬编码依赖；任何自定义上下文键（如 `project_id` / `geometry_data` / `audit_root` 等）都通过同一通道注入，符合 `RESERVED_CONTEXT_FIELDS` 的本意（仅过滤与显式 `cls(...)` 构造参数冲突的基类字段）。

### 关键设计决策：为什么删除 AgentContext.project_id

**原状态**：2026-06-30 新增 `project_id: Optional[int] = None` 字段，同时错误归入 `RESERVED_CONTEXT_FIELDS`，导致 `safe_overrides` 过滤永远剥除该键，前端透传失败。

**新设计（2026-07-01）**：
- `AgentContext` 不预声明任何"运行时可能用到的业务字段"（如 `project_id`）；
- 所有运行时业务上下文键均由前端通过 `context_overrides` 显式注入；
- TypedDict 运行时仍允许任意额外键（dict 不受 type 注解限制），所以工具侧 `runtime.context.get("project_id")` 仍能正常工作；
- `RESERVED_CONTEXT_FIELDS` 仅保留真正需要保护的"基类构造参数"（`session_id` 等），不再混入业务字段。

**好处**：
1. 任何新业务键（不限于 `project_id`）都可走同一透传通道，无需修改 AgentContext / RESERVED_CONTEXT_FIELDS / agent_config_service 三处。
2. 前端完全控制透传内容，后端不再做隐式合并/兜底，链路更清晰。
3. 避免"基类字段 + 保留字段集合"双源同步维护的不一致风险（如本次 RESERVED_CONTEXT_FIELDS 与 AgentContext 的 project_id 不一致 bug）。

## API 路由汇总

| 前缀                                | 模块                   | 说明                                                                                                                                                                                  |
| ----------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| /api/auth                           | auth_router            | 认证（验证码、注册、登录、刷新、验证、登出、门户子 refresh_token）                                                                                                                    |
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
| ├ POST /login                      |                        | 用户登录（验证码校验，返回 access_token + Set-Cookie refresh_token）                                                                                                                  |
| ├ POST /login-api                  |                        | API 程序化登录（免验证码，返回 access_token + Set-Cookie refresh_token）                                                                                                              |
| ├ POST /refresh                    |                        | 刷新 Access Token（读取顺序：X-Refresh-Token 头 > body {refresh_token} > HttpOnly Cookie；同时查 refresh_tokens 与 portal_refresh_tokens）                                            |
| ├ GET /validate                    |                        | 验证 Access Token 有效性（返回 username、role、user_id）                                                                                                                              |
| ├ POST /logout                     |                        | 用户登出（清除 Refresh Token + Cookie + Session + 撤销该用户所有 portal_refresh_tokens）                                                                                              |
| ├ POST /issue-portal-refresh-token |                        | 颁发门户子 refresh_token（需 Bearer access_token；用于门户导航页推送第三方 iframe）                                                                                                   |
| /api/users                          | user_router            | 用户管理（列表、创建、更新、删除、踢人、改密码、改用户名、资料）                                                                                                                      |
| ├ GET /                            |                        | 用户列表（admin 专用）                                                                                                                                                                |
| ├ POST /                           |                        | Admin 创建用户                                                                                                                                                                        |
| ├ GET /online                      |                        | 在线用户列表（admin 专用）                                                                                                                                                            |
| ├ PUT /{user_id}                   |                        | Admin 更新用户资料                                                                                                                                                                    |
| ├ DELETE /{user_id}                |                        | 删除用户（admin 专用，同时清除该用户所有 Session）                                                                                                                                    |
| ├ POST /{user_id}/kick             |                        | 强制用户下线（admin 专用，清除 Refresh Token 并标记 Session 为 kicked）                                                                                                               |
| ├ GET /{user_id}/sessions          |                        | 指定用户会话列表（admin 专用）                                                                                                                                                        |
| ├ PUT /{user_id}/password          |                        | 修改密码（修改后强制清除所有 Refresh Token）                                                                                                                                          |
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
| /mcp                                | mcp_router             | MCP 服务器工具调用                                                                                                                                                                    |
| ├ GET /servers                     |                        | 列出所有已连接的 MCP 服务器及其工具                                                                                                                                                   |
| ├ POST /call                       |                        | 调用指定 MCP 服务器的工具                                                                                                                                                             |
| ├ GET /tools/{server_name}         |                        | 列出指定 MCP 服务器的工具详情                                                                                                                                                         |

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

## Agent 聊天并发控制

**文件位置**: `app/core/concurrency/chat_concurrency_dependency.py` + `app/core/concurrency/agent_concurrency_queue.py`

**功能**: 限制同时处理的 Agent 聊天请求数，超出最大并发数时进入 FIFO 内存队列等待，并向**前端实时推送排队人数提示**。

**配置项**:

- `AGENT_CHAT_MAX_CONCURRENCY` — Agent 聊天接口最大并发数，超出时进入内存队列等待，默认 1（`settings.agent_chat_max_concurrency`）。
- 排队事件推送间隔 `QUEUE_POLL_INTERVAL_SECONDS = 1.0`（依赖内常量，硬编码）。

### 严格 FIFO 队列设计

**设计要点**

- `AgentConcurrencyQueue` 内部用 `_waiters: Deque[_Waiter]` 维护严格 FIFO 队列
- 每个 `_Waiter` 持有 `asyncio.Future`，release() 只唤醒队首 waiter 并 `set_result(None)`，不惊群
- acquire() 时若自己是队首且槽位空闲则立即获得；否则 await future（精确唤醒，无竞争）
- release() 转移许可给下一个 waiter 时 `active_count` 不变（先减后加改为直接转移），消除瞬时空窗
- 失败的/已取消的 waiter 自动顺延下一个，不会卡死队列
- HTTP 模式也强制 enqueue 后再判定 position，杜绝非流式请求绕过 SSE FIFO 队列插队

### 双模式依赖

`chat_concurrency_dependency(request, mode="sse" | "http")` 异步生成器：

| 模式                       | 触发条件                                         | 行为                                                                                                                                                                                                                  |
| -------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SSE 模式**（默认） | `/api/agent/chat`、`/api/map/knowledge-chat` | 所有请求统一先 enqueue；只有 `position == 1` 且槽位空闲时才尝试 acquire；获取许可后 yield `ready` 事件 + `None` 让路由继续；通过 `await release_done.wait()` 阻塞直到路由主动释放（HITL 场景）或 finally 兜底 |
| **HTTP 模式**        | `/api/contract/chat` 等非流式接口              | 强制先 enqueue；只有 `position == 1` 且槽位空闲时获取许可；否则抛 `HTTPException(429, detail={error,waiting_count,active_count,max_concurrency,message})`；无需等待时直接 yield None                              |

### AgentConcurrencyQueue 接口

- `enqueue(task)`：预注册 task 到 FIFO 等待队列（不阻塞），幂等
- `enqueue_time(task)`：返回指定 task 的入队时间戳（`time.monotonic()`）
- `position(task)`：返回 FIFO 队列位置（1-based，0=已激活，-1=未注册）
- `snapshot(task)`：返回 `{active_count, waiting_count, max_concurrency, position, enqueue_time, timestamp}`
- `acquire(task)`：获取许可；只有队首 waiter 且槽位空闲时立即获得，否则 await Future 阻塞
- `release(task)`：FIFO 顺序唤醒下一个有效 waiter（active_count 不出现先减后加瞬时窗口）
- `slot_freed`：槽位释放事件，保留供 SSE 轮询兼容
- 内部维护 `_waiters: Deque[_Waiter]` 与 `_waiter_index: Dict[asyncio.Task, _Waiter]`；取消时通过 `_remove_waiter` 回滚计数

### SSE 轮询即时唤醒

`chat_concurrency_dependency` SSE 模式在排队期间：

1. 先调用 `queue.enqueue()` 预注册当前请求（**确保与 acquire 的 task 是同一个**）
2. 在独立 `acquire_task = asyncio.create_task(queue.acquire(current_task))` 中阻塞
3. 主循环每 `QUEUE_POLL_INTERVAL_SECONDS`（1.0s）推送一次 `waiting` 事件（仅当 `position != 1` 或槽位仍占用时）
4. `asyncio.wait_for(shield(acquire_task), timeout=QUEUE_POLL_INTERVAL_SECONDS)` 在 acquire 完成或 1 秒后唤醒
5. acquire 完成（被 Future 唤醒）后立即跳出循环 yield `ready` + `None`

效果：其他请求 release 后，队首 waiter 在 Future 被 set_result 时**毫秒级**内被唤醒，而不是等待 1s 超时。

### HITL interrupt 早期释放（核心修复）

**后端机制**：

- 依赖在 acquire 成功后把 `concurrency_release_handle`（可调用对象）挂到 `request.state`
- 路由（`stream_with_concurrency`）在 yield `type='interrupt'` 业务事件**之前**调用 `handle()` 强制释放许可
- finally 兜底：`release_done.wait()` 超时或客户端异常断开时执行 release
- 句柄幂等：多次调用不会重复释放（`release_done.is_set()` 守卫）

**前端机制**：

- 收到 interrupt 事件后**主动 `await reader.cancel()`** 断开 fetch，让后端 StreamingResponse 立即结束
- 配合后端 release_handle，**许可释放 + SSE 连接断开两者都及时发生**
- 缺一不可：仅后端 release 但前端不 cancel → 连接挂着 → finally 兜底延迟；仅前端 cancel 但后端不 release → resume 时排队

### SSE queue 事件协议

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

| 路由                            | 类型 | 接入方式                                                                                                                               |
| ------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/agent/chat`             | SSE  | 路由体内手动 `dep = chat_concurrency_dependency(request, mode="sse")` + `stream_with_concurrency(request, dep, business_gen)` 包装 |
| `/api/map/knowledge-chat`     | SSE  | 同上                                                                                                                                   |
| `/api/contract/chat`          | HTTP | `dependencies=[_chat_concurrency_http_dep()]`（工厂函数，传 `mode="http"`）                                                        |
| `/api/contract/doc_chat`      | HTTP | 同上                                                                                                                                   |
| `/api/contract/approval_chat` | HTTP | 同上                                                                                                                                   |

### 测试覆盖

**后端** `app/tests/core/concurrency/`:

- 既有 `test_agent_concurrency_queue.py`（16 用例）+ `test_chat_concurrency_dependency.py`（12 用例）+ `test_stream_with_concurrency.py`（11 用例）全部通过
- **新增** `test_fifo_strict_order.py`（8 用例）：

**前端** `web/Agent/src/components/__tests__/`:

- **新增** `KnowledgeChat.streamGuard.spec.js`（5 用例）：
  - `test_knowledge_chat_handleSend_triggers_stop_when_streaming`：流式中 handleSend 触发 handleStop
  - `test_knowledge_chat_handleKeydown_enter_triggers_stop_when_streaming`：流式中 Enter 触发 handleStop
  - `test_knowledge_chat_handleKeydown_calls_handleSend_when_not_streaming`：非流式 Enter 走正常发送分支
  - `test_knowledge_chat_reset_queue_status_resets_to_idle`：resetQueueStatus 正确重置
  - `test_knowledge_chat_send_btn_click_routes_to_stop_when_streaming`：send-btn 流式下点击触发 handleStop

### 通用 SSE 流式包装器 `stream_with_concurrency`

**文件位置**：`app/core/concurrency/chat_concurrency_dependency.py`（同模块）

**设计要点**（`stream_with_concurrency`）

- `chat_concurrency_dependency` **不能**作为 `Depends` 使用。SSE 路由必须在路由体内手动调用 `chat_concurrency_dependency(request, mode="sse")` 获取 async generator object
- 通用 `stream_with_concurrency(request, dep, business_gen)` 工具函数负责：
  1. 消费 `dep` yield 链（queue waiting/ready 事件）→ 序列化为 SSE 透传前端
  2. 消费 `business_gen` yield 链（业务 chunk）→ 透传
  3. HITL 关键：检测到 `type='interrupt'` 业务事件时，yield 之前主动调用 `request.state.concurrency_release_handle()` 释放许可
  4. finally 兜底：业务流 / 客户端异常时显式 `await dep.aclose()`，触发 `chat_concurrency_dependency` 的 finally 块做 release 兜底
- `_stream_with_queue` / `_is_interrupt_chunk` 已迁移到 concurrency 模块，供所有 SSE 聊天路由复用

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

### 前端 `isStreaming` 状态同步

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

### 前端流式状态拦截

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

## 记忆存储（Memory）

### Checkpointer 全局单例（短期记忆 / thread-level）

- **文件位置**：[`app/shared/utils/memory/checkpoint.py`](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/shared/utils/memory/checkpoint.py)
- **获取函数**：`await get_async_checkpointer() -> BaseCheckpointSaver`
- **两种模式**（按 `DatabasePool.is_enabled()` 即 `AUTH_STORAGE_MODE=postgres` 自动选择）：
  - `AsyncPostgresSaver`（Postgres 模式）— 数据持久化到 PG，调用 `setup()` 创建 `checkpoints` 表
  - `MemorySaver`（Memory 模式）— 数据存储在内存中
- **生命周期**：
  - 启动：lifespan 阶段调用一次完成初始化
  - 关闭：`close_global_checkpointer()` 关闭 psycopg 连接池
  - 测试：`reset_global_checkpointer()` 清空单例
- **依赖注入点**：`app/routers/agent_router.py::chat` 与 `app/features/contract_host_agent/router/contract_router.py` 均通过 `get_async_checkpointer()` 获取

### Store 全局单例（长期记忆 / cross-thread）

- **文件位置**：[`app/shared/utils/memory/store.py`](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/shared/utils/memory/store.py)（2026-06-26 新增）
- **获取函数**：`await get_async_store() -> BaseStore`
- **两种模式**（按 `DatabasePool.is_enabled()` 自动选择）：
  - `AsyncPostgresStore`（Postgres 模式）— 数据持久化到 PG，调用 `setup()` 创建 `store` / `store_migrations` 表
  - `InMemoryStore`（Memory 模式）— 数据存储在内存中
- **与 checkpointer 的关系**：
  - 各自维护**独立**的 psycopg 连接池（`max_size=20`），不复用以避免两边相互锁定导致死锁
  - 共享同一个 DSN（`DatabasePool.get_dsn()`）与凭据
- **生命周期**：
  - 启动：懒加载，首次 `await get_async_store()` 时完成初始化
  - 关闭：`close_global_store()` 关闭 store 自建的 psycopg 连接池
  - 测试：`reset_global_store()` 清空单例（不关闭连接池）
- **依赖注入点**：
  - `app/routers/agent_router.py::chat` — 构造 `AgentConfig(store=store, ...)`
  - `app/features/contract_host_agent/HtAgent.py:40-44` — 通过 `HtAgent.__init__(self, checkpointer, store, store_id, ...)` 透传
  - `app/features/contract_host_agent/router/contract_router.py:37` — 模块级 `store = InMemoryStore()` 单例（feature 内使用）
- **设计决策**（2026-06-26 修复）：
  - 原 `agent_router.py::chat` 缺失 `store=` 注入，导致走统一 router 路径的 agent：
    1. 多模态图片回填失败（`_llm_call` 中 `self.store is None` 短路）
    2. LangGraph Store 语义关闭（`workflow.compile(store=None)`）
    3. 工具内 `self.store.put(...)` 写入的跨会话数据对后续 agent 不可见
  - 修复方案：路由层显式 `await get_async_store()` 注入 `AgentConfig.store=store`，与 `HtAgent` 路径行为对齐
  - `store` 字段在 `RESERVED_CONFIG_FIELDS` 中，禁止通过 `config_schema` 覆盖，必须由路由层显式注入（设计硬约束）

### `key_value_memory_store`（独立的键值包装类）

- **文件位置**：[`app/shared/utils/memory/key_value_memory_store.py`](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/shared/utils/memory/key_value_memory_store.py)
- **用途**：提供 `set / get / append / extend / delete / exists / update` 语义的便捷包装，**不与** `AgentConfig.store` 挂钩
- **使用方**：`app/features/audit_document_agent/tools/tools.py`（独立于 LangGraph Store）
- **与 Store 全局单例的关系**：两套独立机制，**不互通**。`key_value_memory_store` 用于非 LangGraph 场景的键值持久化，`get_async_store()` 用于 LangGraph 内部 Store 抽象

### `document_memory_store`（文档记忆存储）

- **文件位置**：[`app/shared/utils/memory/document_memory_store.py`](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/shared/utils/memory/document_memory_store.py)
- **用途**：封装文档解析结果的存储（合同条款、成交确认书图片等），供审计文档 agent 使用
- **使用方**：`app/features/audit_document_agent/tools/tools.py`

## 环境变量

- `AUTH_STORAGE_MODE` — 存储模式（postgres/memory）
- `DATABASE_URL` — PostgreSQL 连接字符串
- `PORTAL_REFRESH_TOKEN_TTL_SECONDS` — 门户子 refresh_token 有效期（秒），默认 86400 = 24 小时
- `VITE_API_TARGET` — 前端 Vite 代理目标地址（开发用），默认 `http://localhost:8001`
- ~~`VITE_PORTAL_NAV_CONFIG`~~ — 已废弃，门户导航配置迁移到 `public/app-config.json` 运行时配置
- `AGENT_CHAT_MAX_CONCURRENCY` — Agent 聊天接口最大并发数，超出时进入内存队列等待，默认 3
- **沙箱容器化配置**：
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
  - `SANDBOX_FALLBACK_TO_LOCAL` — Docker 不可用时是否降级到本地文件系统执行，默认 `false`
- **文件解析（远程解析 + 大小限制）**：
  - `FILE_PARSER_ENABLED` — 是否启用远程解析（`true`/`false`），默认 `false`
  - `FILE_PARSER_SERVER_URL` — 远程解析服务地址，默认 `http://mineru-openai-server:30000`
  - `FILE_PARSER_OUTPUT_FORMAT` — 输出格式 `json` 或 `md`，默认 `json`
  - `FILE_PARSER_API_URL` — 远程解析 API 地址
  - `FILE_PARSER_MAX_RETRIES` — 最大轮询重试次数，默认 60
  - `FILE_PARSER_POLL_INTERVAL` — 轮询间隔（秒），默认 2.0
  - `FILE_PARSER_TIMEOUT` — 请求超时时间（秒），默认 300
  - `FILE_PARSER_MAX_FILE_SIZE` — 上传文件最大大小（**MB，整数**，下限 1），默认 `3`。2026-07-13 新增：前后端共用上传大小上限，原前端硬编码 50MB 已被替换为读取本配置；后端在 `/api/core/uploadfile` 与 `/api/core/merge-chunks` 内做 413 校验；前端通过 `GET /api/core/upload-config` 拉取后做客户端预校验
- 其他 LLM API Key 等

## 提示词三层架构

整个项目的系统提示词采用**三层分层设计**，各层职责分离，通过 Agent 基类自动拼接，确保通用规则统一维护、专用逻辑各 Agent 独立管理。

### 架构概述

| 层级   | 文件位置                                   | 形式                             | 职责                                      |
| ------ | ------------------------------------------ | -------------------------------- | ----------------------------------------- |
| 第一层 | `app/core/prompts.py`                    | `BASE_SYSTEM_PROMPT` 字符串    | 所有智能体共享的通用规则                  |
| 第二层 | `app/features/{agent}/config/prompts.py` | `DEFAULT_SYSTEM_PROMPT` 字符串 | 单个 Agent 的角色、工作流程、工具组合策略 |
| 第三层 | `app/features/{agent}/tools/*.py`        | 工具函数 docstring               | 每个工具的具体用途、调用时机、参数说明    |

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

| Agent             | 提示词文件                                                                                                                                                                                                                                                                 |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 地图 Agent        | [app/routers/knowledge_router.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/routers/knowledge_router.py)（`KNOWLEDGE_SYSTEM_PROMPT`） |
| 合同主办 Agent    | [app/features/contract_host_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/contract_host_agent/config/prompts.py)                                                                                                                |
| 合同文档 Agent    | [app/features/contract_document_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/contract_document_agent/config/prompts.py)                                                                                                        |
| 合同审批 Agent    | [app/features/contract_approval_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/contract_approval_agent/config/prompts.py)                                                                                                        |
| DevOps Agent      | [app/features/DevOps_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/DevOps_agent/config/prompts.py)                                                                                                                              |
| AI 代码检查 Agent | [app/features/AI_Coding_Check_agent/config/prompts.py](file:///e:/laboratory/AI/Agents/agent-user-mangerment/app/features/AI_Coding_Check_agent/config/prompts.py)                                                                                                            |

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

| 层级   | 应该写什么                                                | 不应该写什么                                                               |
| ------ | --------------------------------------------------------- | -------------------------------------------------------------------------- |
| 第一层 | 所有 Agent 通用的行为规则、工具使用规范、输出格式约束     | Agent 特有的业务逻辑、具体工具名称                                         |
| 第二层 | 该 Agent 的角色定义、工作流程、工具选择策略、业务判断标准 | 通用工具调用规范（如"不要同时调用多个工具"）、通用输出约束（如"保持简洁"） |
| 第三层 | 单个工具的调用时机、参数含义、参数组合、返回值说明        | 业务工作流程、工具之间的协调策略                                           |

**维护建议**：

- 修改第一层时需谨慎，变更会影响**所有 Agent**
- 第二层各 Agent 独立维护，互不影响
- 第三层随工具功能迭代同步更新 docstring，确保模型获取最新工具描述

## HITL 流程

**工具**：`app/core/tools/HumanInTheLoopTools.py` 中的 `ask_user_question`（替代旧的 `request_human_approval`）

**数据契约**：

- 入参：Pydantic 约束的 `AskUserQuestionInput`（1-4 个 Question，每个 2-4 个 Option，header ≤ 12、label ≤ 30、description ≤ 200）
- 中断 payload：`{"action": "ask_user_question", "questions": [...]}`（LangGraph `interrupt()` 直接传 dict）
- 恢复值：`Command(resume={"answers": [[...], [...]]})`（每题一个 label 数组）
- State 字段：`pending_question: dict`、`question_answers: list`（用 `Overwrite` 追加）

**节点**：`app/core/agent/agent.py:hitl_check_node` 收到 `pending_question` 后调 `interrupt()`，恢复时构造 `HumanMessage` 回灌（保持 HumanMessage 模式避免 `tool_call_id` 风险）

**前端**：

- `web/Agent/src/components/HumanApprovalBox.vue`：多 Tab 切换 + 虚拟 Other 项 + 多选模式 + 全局 `canSubmit` 门控
- 提交事件：`emit('submit', { answers: string[][] })`
- `web/Agent/src/App.vue:extractApprovalData`：直接读 `req.value?.questions`

**测试**：

- 后端：`tests/test_ask_user_question.py` 17 个测试（Schema 10 + Tool 2 + HitlCheckNode 5）
- 前端：`web/Agent/src/components/__tests__/HumanApprovalBox.spec.js` 14 个测试
- 并发控制：`app/tests/core/concurrency/test_chat_concurrency_dependency.py`、`test_agent_concurrency_queue.py`
- 队列 UI：`web/Agent/src/components/__tests__/QueueStatusBanner.spec.js`
- 中断处理：`web/Agent/src/components/__tests__/App.interrupt.spec.js`
- SSE 解析：`web/Agent/src/utils/__tests__/sseParser.test.js`
- 核心工具：`app/tests/core/tools/test_human_in_the_loop_tools.py`、`test_base_tools.py`、`test_mcp_tool_adapter.py`

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

| 入口文件           | 挂载组件                                          | 部署路径       | 用途                                                                                                 |
| ------------------ | ------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------- |
| `index.html`     | `App.vue`（`src/main.js`）                    | `/`          | 主聊天界面 + 知识库 Tab（Sidebar 切换 currentPage）                                                  |
| `knowledge.html` | `KnowledgeApp.vue`（`src/knowledge-main.js`） | `/knowledge` | 知识库独立页（文件侧栏 + 聊天）                                                                      |
| `portal.html`    | `PortalApp.vue`（`src/portal-main.js`）       | `/portal`    | 门户导航（顶部蓝色导航栏 + iframe 嵌入 `/knowledge`）                                              |
| `login.html`     | `LoginView`（`src/login-main.js`）            | `/login`     | 登录页统一入口（`App.vue` / `PortalApp.vue` 不再内联渲染 `LoginView`；由 `/login` 唯一承载） |

三个入口共享 `src/components`、`src/utils`、`src/styles`，构建后产出三个独立的 JS Chunk。

### Portal 入口 Tab 标题驱动（2026-06-30 落地）

`portal.html` 的浏览器 Tab 标题跟随运行时配置 `web/Agent/public/app-config.json` 的 `brandTitle` 字段：

- **首帧（编译期）**：`portal.html` 的静态 `<title>` 已被同步为 `brandTitle` 的默认值（`沈阳市自然资源和规划"一点通"`），避免首帧 Tab 标题闪烁为无关文案
- **运行时覆盖**：`PortalApp.vue` 的 `onMounted` 在 `checkAuth()` 之前 `await loadAppConfig()` 拉取最新 `brandTitle`，加载完成后 `document.title = appConfig.brandTitle`，支持配置变更无需重新构建即生效
- **配置缺失时**：fetch 失败或字段缺失均不报错，保留默认 `brandTitle`，Tab 标题不会出现空白
- **依赖模块**：`src/config/portal.js::loadAppConfig()` + `src/config/portal.js::getNavItems()`；调用方为 `PortalApp.vue` 单入口（其他入口不消费本逻辑，避免重复 fetch）
- **变更影响**：仅前端 SPA，无后端/数据库 schema 改动；`init_all_tables.sql` 无需同步

### 组件清单（src/components）

- **根组件**：`App.vue`（主）、`KnowledgeApp.vue`（知识库）、`PortalApp.vue`（门户）、`KnowledgePage.vue`（旧版，被 `KnowledgeApp.vue` 替代，仍保留以兼容旧引用）
- **登录入口**：`login.html` + `src/login-main.js`（独立 Vite 入口；承载 `LoginView`；由 `redirectToLogin()` 跳到 `/login?redirect=...` 统一访问）
- **聊天**：`ChatArea.vue`、`InputBox.vue`、`MessageBubble.vue`、`SkillTags.vue`、`HumanApprovalBox.vue`、`TopBar.vue`
  - `ChatArea.vue`（2026-07-01 新增，2026-07-02 修正头部 sticky + 改为撑满主区宽度与贴顶，2026-07-02 二次修正 header 内部居中，2026-07-02 三次修复滚动按钮「跳一下又回到原位」竞态）：顶部显示会话名称（`sessionName`）与绿色文件夹图标按钮；头部使用 `position: sticky` 固定在聊天区域顶部，不随消息滚动；header **外层** `.chat-area-header` 撑满主区宽度（背景色铺满两侧），**内层** `.chat-area-header-inner` 与下方 `.messages-container` 一致采用 `max-width: 900px + margin: 0 auto + padding: 0 40px` 居中布局，实现"外层连接两侧 + 内容向中间靠拢与聊天区对齐"；紧贴主区顶部（去掉 chat-area 顶 padding、改为 header 外层 padding: 8px 0），与左侧 sidebar-logo 形成水平对齐节奏；点击图标 emit `open-session-file-drawer` 事件，由 `App.vue` 打开右侧会话文件抽屉
  - **2026-07-02 滚动按钮修复**（仅 ChatArea.vue 单文件改动）：右下角 `.scroll-buttons-wrapper` 内的 `scroll-to-top-btn` / `scroll-to-bottom-btn` 之前包裹 `<transition name="fade">`，结合 `scrollTo({ behavior: 'smooth' })` 在 click 同一帧触发时，leave 动画的 reflow/repaint 会中断 in-flight smooth 滚动，导致 scrollTop 回弹到原值（用户反馈「会话跳了一下又回到原位」）；修复方案：① 去掉两层 `<transition>` 包裹，依赖 v-show 的 display 切换（无动画）；② `scrollToBottom` / `scrollToTop` 改为直接赋值 `chatContainer.value.scrollTop`（瞬时），并用 `nextTick` 包裹读取最新 `scrollHeight`；③ 移除 `handleScrollToBottomClick` 中间函数；④ 删除 `.fade-enter-active / .fade-leave-active / .fade-enter-from / .fade-leave-to` CSS（保留为注释占位，避免误用恢复原 bug）；⑤ `onMounted` 中 `scrollToBottom('auto')` 改为无参调用。若未来需要按钮淡入淡出动画，必须改用 `<transition-group>` 包整组按钮并配合 RAF/nextTick 调度，**禁止**再次对单按钮用 `<transition>` + `v-show` + `scrollTo({ behavior: 'smooth' })` 同帧触发。
- **文件**：`FileList.vue`、`FilePreview.vue`、`FolderTree.vue`、`FileManagerModal.vue`
  - `SessionFileDrawer.vue`（2026-07-01 新增，2026-07-07 追加文件下载入口，2026-07-07 三次迭代：UUID 抽取 → stored_path → fetch blob）：右侧可拖拽宽度的抽屉，仅展示当前会话/项目文件空间中的原文件目录；复用 `FolderTree.vue`，点击文件 emit `file-click`；**下载入口（2026-07-07）**：根级与嵌套子文件节点均渲染 `<button class="download-btn">`（Lucide 三段式下载图标）；外层文件节点由 `<button>` 改为 `<div role="button" tabindex="0" @keydown.enter/space>` 以规避 HTML 按钮嵌套违规；**v1（已废弃）**：抽 `extractFileUuid(file.path)` 调 `GET /api/files/download/{file_uuid}` —— 工作空间文件并非都经过 UUID 命名，basename 是原中文名时抽出即原名，必 404；**v2（已废弃）**：用 `file.stored_path || file.path` 拼 `<a download>` 直链调 `GET /api/session/{sessionId}/files/download?stored_path=...` —— `<a>` 触发的导航请求不携带 `Authorization` 自定义头，被 `auth_middleware` 直接 401 拒绝（终端日志 2026-07-07 984-1007 行确认）；**v3（当前）**：保持 v2 的 URL 与 `sessionId`/`stored_path` 参数，但**改用 `fetchWithAuth` 拉 blob → `URL.createObjectURL` → 临时 `<a download>` 触发原生下载**；`fetchWithAuth` 自动注入 `Authorization: Bearer <jwt>` 与 `X-Session-ID`，并自动处理 401 刷新重试；下载文件名优先解析后端 `Content-Disposition: filename*=UTF-8''<encoded>` 头，fallback 到 `file.name`；`SessionFileDrawer` 新增 `sessionId` prop 由 `App.vue` 通过 `:session-id="sessionId.value"` 注入；`FolderTree` 同步加 `sessionId` prop 并递归透传；CSS 新增 `.file-row` / `.file-row-main` / `.download-btn` 三段，hover 用 `--color-accent-light` 背景 + `--color-accent` 边框。**不修改后端**。详见计划文档 `.trae/documents/workspace-drawer-download-feature.md`
  - `FilePreviewModal.vue`（2026-07-01 新增）：文件预览弹窗，复用 `FilePreview.vue`；支持点击遮罩层、按 ESC 键关闭；为避免弹窗标题与 `FilePreview.vue` 自身标题重复，弹窗内调用 `FilePreview` 时传入 `:show-header="false"`
  - `FilePreview.vue`：文件预览面板组件，新增 `showHeader` prop（默认 `true`），用于控制是否渲染内部标题栏和关闭按钮
- **知识库**：`KnowledgeChat.vue`、`ProfileInputBox.vue`
- **公共**：`Sidebar.vue`、`HelloWorld.vue`、`UserSettingsDialog.vue`
  - `Sidebar.vue`（2026-07-02 调整）：侧边栏「项目」分组默认展开，其下各项目内的会话列表默认折叠，点击项目头部可切换展开/折叠
- **Admin 管理**：
  - `UserSettingsDialog.vue`：admin 角色可访问的「用户设置与管理」对话框；包含 8 个 Tab —— `profile`（个人设置）/ `user-management`（用户管理）/ `online-monitor`（在线监控）/ `session-query`（会话查询）/ `agent-management`（智能体管理，调用 `AgentManager.vue`）/ `mcp-management`（MCP 管理，调用 `McpServerManager.vue`）/ `tool-management`（工具管理，调用 `ToolManager.vue`）/ `skill-management`（Skill 管理，调用 `SkillManager.vue`）。其中 `session-query` Tab 为两级视图：人员列表 → 点击人员进入该用户的会话列表；会话表格支持复选框批量选择、批量删除、单条导出 Markdown，点击会话标题弹出历史消息对话框，使用 `MessageBubble` 渲染完整消息（含 `ToolCallCard` 工具卡片与 `SubAgentCard` 子智能体卡片）
    - **历史会话详情弹窗布局**：
      1. **居中显示**：历史会话详情弹窗使用 `.dialog-overlay--centered`（flex + 居中对齐）+ `.dialog-overlay--centered > .dialog-card`（position:relative + 圆角 + max-height:90vh），宽度 800px；主弹窗（用户设置与管理）仍铺满全屏
      2. **子智能体抽屉就地打开**：历史弹窗内的 `SubAgentCard` 点击后不再冒泡到 `App.vue`，而是在弹窗内就地打开独立的 `<SubAgentDrawer>`（`historySubAgentDrawerVisible` / `historyCurrentSubAgent` 状态控制）
      3. **左右并排布局（2026-07-04）**：header 下方新增 `.history-dialog-main` flex-row 容器，左侧 `.history-dialog-body` 保留会话消息流，右侧通过 Teleport 挂载 `SubAgentDrawer`，两者同时可见；废弃原 `.history-dialog-body--collapsed` 折叠隐藏方案
      4. **抽屉消息区滚动（2026-07-04）**：Teleport 到 `.history-dialog-main` 的抽屉使用 `.subagent-drawer--teleported { align-self: stretch; height: auto; min-height: 0; }`，避免弹窗卡片仅有 `max-height` 时 `height:100%` 解析失败导致抽屉被内容撑高、消息区无法滚动
      5. 数据契约：后端 `/api/session/admin/{id}/messages` 返回的 `type:"subagent"` 元素含完整 `messages` 数组（`app/shared/utils/memory/checkpoint_history.py:411-423`），`convertSubAgentHistoryToAiSubAgent`（`sseParser.js:743`）直接转成 `SubAgentDrawer` 所需的 props 结构，无需额外接口
  - `McpServerManager.vue`：MCP server CRUD + 方法列表 + 启禁用切换（前后端）
  - `AgentManager.vue`：智能体管理 Tab 内容；左侧智能体列表 + 右侧 Tab 结构（「基本信息」Tab + 「配置字段」Tab + 「工具绑定」Tab）；支持完整 CRUD：
    - **新增智能体**：弹窗表单（8 字段）+ 内嵌 config_schema 编辑器；调用 `fetchAgentConfigFieldTemplates` 获取字段模板做下拉选择
    - **基本信息 Tab**（2026-06-29 新增）：编辑当前智能体的 `display_name` 和 `description`，调用 `updateAdminAgent(name, {display_name, description})`（PUT `/api/admin/agents/{name}`）保存；保存成功后刷新左侧列表和当前详情头部
    - **编辑字段**：每组表格独立增删改；section = `root` / `state_fields` / `context_fields`；通过 `updateAdminAgentConfigSchema` / `addAdminAgentConfigField` / `updateAdminAgentConfigField` / `deleteAdminAgentConfigField` 增量更新
    - **字段模板下拉选择**：`root` / `state_fields` / `context_fields` 三组均支持「覆盖来源 = 已有字段」时下拉选择对应基类字段（AgentConfig / AgentState / AgentContext），自动填充字段名、类型、默认值
    - **保存策略**：`modified` 字段改用 `PUT /config-schema/field` 直接覆盖，避免旧版"先删后加"导致的数据丢失；`delete` 失败时记录具体字段名并继续处理其他变更，错误信息汇总展示；失败时保留 `pendingChanges` 不自动清空
    - **删除智能体**：含确认弹窗（保留历史会话）
    - **启用/禁用开关**：右上角 switch，立即调用 `setAdminAgentEnabled`，不进入「未保存修改」队列
    - **工具绑定 Tab**（2026-06-25 新增）：右侧第三个 Tab，展示所有可用工具（内置 + MCP）按分类分组，复选框勾选绑定到当前 agent；内置工具分类 = `tools.category`，MCP 工具分类 = `mcp_server.display_name`；工具列表全局缓存（`toolsInitialized`，避免每次切换 agent 重复拉取），切换 agent 时仅重新加载该 agent 的绑定；绑定格式 `{tool_name, tool_type: "builtin"|"mcp", enabled: true, sort_order}`；保存调用 `updateAgentToolBindings(name, bindings)`（PUT 全量替换）；MCP 工具的 `tool_name` = `method_name`（不带 server 前缀，与后端 `mcp_registry.get_tools_with_server` 匹配逻辑一致）；API 函数 `listTools` / `getAgentToolBindings` / `updateAgentToolBindings` 定义在 `api.js`
  - `ToolManager.vue`：工具管理 Tab 内容，挂载于 `UserSettingsDialog.vue` 的 `tool-management` Tab（admin 可见）；左侧已注册工具列表按 `category` 分组（可折叠）+ 右侧详情/扫描结果面板；调用 `listTools` / `scanTools` / `listUnregisteredTools` / `registerTool` / `setToolEnabled` / `deleteTool`（对应后端 `tool_admin_router` 的 `/api/admin/tools/*` 端点）；支持扫描未注册工具、注册弹窗（回填自动解析的只读字段 + 补充 description/category）、启用/禁用 toggle（失败回滚 DOM）、删除（含 confirm）
  - `TaskSchedulerManager.vue`（2026-07-10 新增）：智能体定时任务管理 Tab 内容，挂载于 `UserSettingsDialog.vue` 的 `task-scheduler` Tab（admin 可见）；左侧展示定时任务列表（名称、agent_name、cron、启停状态），右侧表单编辑 `name/description/agent_name/prompt/cron_expression/timezone/enabled/context_overrides`；支持新增、保存、启停、立即运行、删除和最近 50 条执行历史展示；调用 `fetchTaskSchedules` / `createTaskSchedule` / `updateTaskSchedule` / `deleteTaskSchedule` / `setTaskScheduleEnabled` / `triggerTaskSchedule` / `fetchTaskRuns`（对应后端 `task_scheduler_router` 的 `/api/admin/task-schedules/*` 端点）
- **Subagent 折叠与抽屉**：
  - `SubAgentCard.vue`：通用子智能体折叠卡片（含沙箱），挂在父 AI 气泡的 `timeline.tool` 块内（按 toolCallId 匹配，遵循事件流时序）；工具图标 + 父 prompt 预览 + 状态徽章 + 耗时 + 消息数 + "查看详情" 入口；点击 emit('click', subAgent)
  - `SubAgentDrawer.vue`：通用子智能体详情 Push Drawer；分层展示父 prompt / HumanMessage / AIMessage（含 tool_calls 决策区） / ToolMessage 三类消息 + 底部耗时/消息数/工具调用次数摘要；`renderMessageContent` 扩展支持 LangChain 0.3+ 多模态 ContentBlock（text / thinking / tool_use / tool_result）
- **普通工具卡片**：
  - `ToolCallCard.vue`：普通（非 subagent）工具调用专属卡片，与 `SubAgentCard` 视觉风格对齐；**关键差异：不触发抽屉**（普通工具没有子智能体消息流），body 以"步骤"形式逐步展示每条 SSE 事件（tool_start / tool_progress / tool_stop / tool_error）；头部扳手图标在 `status='running'` 时使用 SubAgentCard 同款 `subagentIconBounce` 闪动动画；默认 `running` 展开、`success/error` 折叠
- **动态排队提示横幅**：
  - `QueueStatusBanner.vue`：**挂在 ChatArea 与 InputBox 之间**（用户要求位置），实时显示 Agent 聊天接口的并发排队状态；黄色系背景 + 橙色感叹号图标 + 位置 badge（带 2s pulse 动画）；Props：`queueStatus: {event, waitingCount, activeCount, maxConcurrency, position, timestamp}` + `isVisible: Boolean`；进场 `slide-down 200ms` / 退场 `fade-out 200ms`；数据由后端 SSE `queue` 事件（`onQueueEvent` 回调）或 HTTP 429 响应驱动
- **视图**（`src/views/`）：`LoginView.vue`、`RegisterView.vue`

### 停止按钮 - 中断待生效（toolStopPending，2026-07-06 新增 / 重构）

**两阶段演进**：
- **第一阶段（2026-07-06 上午）**：UI 态从"发送"扩展到"发送/停止/中断待生效"三态，使用 `toolStopPending` 锁 + `reader.cancel()` + `_stream_helper` 延迟中断机制
- **第二阶段（2026-07-06 下午）**：发现 reader.cancel() 仍会导致子智能体被粗暴取消（前端 reader 关闭 = 收不到后续 SSE 事件），改用 **LangGraph 标准做法**：工具内部检测 abort_event + 主动构造 ToolMessage 返回（避免 CancelledError 打断 ToolMessage 写入）

**核心问题与根因**：
- LLM API 报 `tool call result does not follow tool call (2013)` 的根因是：用户点停止 → 前端 `reader.cancel()` → LangGraph `astream` 协程被粗暴取消 → 工具子智能体来不及 return ToolMessage → checkpoint 中 AIMessage 含 tool_calls 但无对应 ToolMessage → 下次会话恢复时 LLM API 报 2013
- 第一阶段（reader.cancel + `_stream_helper` 延迟中断）只解决"前端不丢事件"，但仍让子智能体被 CancelledError 取消 → ToolMessage 写入被打断
- 第二阶段（abort_event 通道）：让工具**自己检测** abort signal，**主动构造** ToolMessage + `return Command` —— 这是 LangGraph 推荐的"工具失败语义"，比 CancelledError 优雅

**核心机制（第二阶段最终态）**：
1. **前端** `handleStopMessage` 调 `POST /api/agent/{sessionId}/abort`（或知识库路径 `/api/map/knowledge/{sessionId}/abort`）→ 后端 `trigger_abort(session_id)` → 全局 dict `_abort_signals[session_id].set()`
2. **后端 `_stream_helper.py`** 入口 `register_abort_signal(session_id)` 创建 event；finally 块 `unregister_abort_signal(session_id)` 清理；`is_disconnected` 检测时同时 `trigger_abort`（双保险）
3. **后端工具**（sandbox / explore）：从 `request.is_disconnected()` 改为 `get_abort_signal(session_id).is_set()`，主循环每 N chunk 检测一次 → 触发 `stopped_by_user` 分支 → **主动构造** `ToolMessage(tool_call_id=...)` 通过 `return Command` 返回
4. **LangGraph** 收到 `Command(update={"messages": [ToolMessage]})` → 正常推进 → yield `tools` 节点 update → yield `end` 事件 → 自然关闭 SSE
5. **前端 SSE while 循环** 识别白名单事件：`end` / `error` / `interrupt` / **`tools` 节点 update 含 ToolMessage**（abort 真正生效的信号）→ 触发 `clearToolStopPending()` + 清 60s 兜底 timer

**为什么不用 reader.cancel() + 延迟中断**：
- reader.cancel() 让前端 SSE 立即 done → 收不到后续任何事件 → `toolStopPending` 锁只能靠 finally 立即清锁 → UI 永远来不及呈现 stop-pending 态
- abort_event 通道不依赖 reader 状态，事件走全局 dict，后端 yield 的 tools 节点 update 仍能到达前端

**为什么不用纯 LangGraph SDK `AsyncGraphRunStream.abort()`**：
- LangGraph 1.x 的 abort 是 SDK 层概念（`client.threads.stream()` 上下文管理器）
- 项目用裸 `agent.graph.astream()` + 手动 SSE 透传，没有用 LangGraph SDK
- 所以自建 `POST /abort` 端点作为"应用层 abort 协议"，核心机制遵循 LangGraph 推荐做法

**60s 兜底 timer 是什么**：
- 防止后端工具卡死在长 I/O（Docker exec 大文件解压、shell 等待），导致 `toolStopPending` 锁永远不清
- 用户点 stop → 启动 60s timer
- 60s 内收到白名单事件 → clearToolStopPending 清掉 timer
- 60s 到期仍未收到 → 强制 `reader.cancel()` + 追加「[工具执行超时，已强制停止]」+ 清锁

**关键文件改动**：
- 后端 `app/core/tools/_stop_signal.py`（Phase 1）：新增全局 dict `_abort_signals` + `register_abort_signal` / `trigger_abort` / `unregister_abort_signal` / `get_abort_signal` 四个函数；保留原有 ContextVar 机制作为 `is_disconnected` 兜底
- 后端 `app/core/tools/SandboxTools.py`（Phase 2）：从 `request.is_disconnected()` 改为 `get_abort_signal(session_id).is_set()`；保留每 5 chunk 检测频率（不激进到每 chunk）；新增进入 stream 前的预检查
- 后端 `app/routers/_stream_helper.py`（Phase 3）：入口 `register_abort_signal` 创建 event；finally 块 `unregister_abort_signal` 清理；`is_disconnected` 检测时同时 `trigger_abort`（双保险）
- 后端 `app/routers/agent_router.py`（Phase 3）：新增 `POST /api/agent/{session_id}/abort` 路由
- 后端 `app/routers/knowledge_router.py`（Phase 3）：新增 `POST /api/map/knowledge/{session_id}/abort` 路由
- 前端 `web/Agent/src/utils/api.js`（Phase 4）：新增 `triggerAbort(sessionId, options)` 函数
- 前端 `web/Agent/src/App.vue`（Phase 4）：模块级 `toolStopPending` ref + `clearToolStopPending` + `startStopTimeout` 函数；`handleStopMessage` 调 `triggerAbort` 而非 `reader.cancel`；SSE while 循环新增"tools 节点 update 含 ToolMessage"识别分支
- 前端 `web/Agent/src/KnowledgeApp.vue`（Phase 4）：同 App.vue 模式（知识库路径 `isKnowledge=true`）
- 前端 `web/Agent/src/components/InputBox.vue`（第一阶段遗留）：`isStopPending` prop + `stop-pending-mode` class + `handleSendBtnClick` 三态分支 + `.stop-pending-badge` 角标

**状态机矩阵**：

| 触发点 | toolStopPending | isStreaming | 说明 |
|--------|----------------|------------|------|
| handleStopMessage 入口（无 pending） | true | 保持 true | 加锁 + 调 triggerAbort + 启动 60s timer |
| handleStopMessage 入口（已 pending） | - | - | 直接 return（重复点击短路） |
| SSE `client_disconnected` 事件 | true | 保持 true | 锁保持（后端在等工具） |
| SSE `tools` 节点 update 含 ToolMessage | false | 保持 true | **新白名单：abort 真正生效** |
| SSE `end` / `error` / `interrupt` 事件 | false | false | 流走完 |
| SSE 流 done=true | false | false | 自然结束 |
| 60s 兜底 timer 到期 | false | false | reader.cancel + 追加「[工具执行超时]」 |
| handleSendMessage catch / finally | false | - | 异常兜底 |
| newSession / handleSessionSwitch | false | false | 切换兜底 |
| handleApprovalCancel | false | false | HITL 取消兜底 |

**测试覆盖（90+ 用例）**：
- 后端 `app/tests/core/tools/test_stop_signal.py`（11 + 10 = 21 用例）：原有 ContextVar 机制 + 新增 abort signals dict 全套测试（register/trigger/unregister 生命周期、idempotent、并发隔离）
- 后端 `app/tests/core/tools/test_sandbox_abort.py`（4 用例，新增）：abort_event 触发 stopped_by_user 分支、is_disconnected 兜底、abort_event 优先于 is_disconnected、正常完成路径
- 后端 `app/tests/routers/test_agent_router_abort.py`（5 用例，新增）：/abort 端点注册、未注册 session 兜底、已注册 session 触发、idempotent、与 agents-md 路由不冲突
- 后端 `app/tests/features/map_agent/test_map_router_disconnect.py`（9 用例，未改）：原有延迟中断机制测试，仍通过
- 后端 `app/tests/features/map_agent/test_map_router_subagent_stop.py`（5 用例，未改）：子智能体停止信号端到端测试，仍通过
- 后端 `app/tests/core/tools/test_sandbox_tools.py`（45 用例，未改）：辅助函数全套，仍通过
- 前端 `web/Agent/src/components/__tests__/InputBox.stop-pending.spec.js`（11 用例）：三态 class 切换、旋转圆环 + badge 渲染、title 文案、canSend 禁用、点击拦截、handleSendBtnClick 三态分支
- 前端 `web/Agent/src/components/__tests__/App.stop-pending.spec.js`（25 用例，含第二阶段扩展）：纯函数复刻 handleStopMessage + clearToolStopPending + shouldClearToolStopPending（识别 end/error/interrupt/tools update）；新增 triggerAbort 调用、60s timer 启动断言
- 前端 `web/Agent/src/components/__tests__/KnowledgeChat.stop.spec.js`（11 用例，扩展）：stop-pending 样式、handleStop 重复点击短路、handleSendBtnClick 拦截、handleNewChat/handleApprovalCancel 入口清锁

**与既有章节关系**：
- 「精确延迟中断」（`_stream_helper.py:101-201`）：后端延迟中断机制仍存在，但**不是 abort 主路径**（仅作 is_disconnected 兜底）；abort 主路径是 abort_event 通道
- 「停止按钮（中断 LLM 生成）」（知识库章节，2026-06-15 新增）：原始"request.is_disconnected() 检测"机制，保留作为非主动关闭场景的兜底
- 「前端 `isStreaming` 状态同步」（并发排队修复）：保持 isStreaming 复位路径不变
- 「ToolNode 错误处理（handle_tool_errors）」（LangGraph 推荐做法）：本节实现与该做法同源 —— 工具失败时主动 return ToolMessage 而非抛异常

### 工具函数（src/utils）

- **`api.js`**：登录/注册/验证码/登出/refresh/validate；会话创建/列表/删除/详情/标题/附件/消息/文件空间；文件上传（普通 + 分片 + base64）/下载/列表/删除；SSE `chatStream`（ 起改用 `/api/agent/chat`，新增 `agentName` 参数默认 `map_agent`）/ `knowledgeChatStream`（仍用 `/api/map/knowledge-chat`）；`X-Session-ID` 头注入；附件元数据组装
  - **会话文件空间 API 段**（2026-07-01 新增）：`fetchSessionFileTree(sessionId)` 获取 `/api/session/{id}/files/tree` 树形结构；`previewSessionFile(sessionId, storedPath)` 获取 `/api/session/{id}/files/preview` 预览数据（文本/Markdown 返回 content，Office/PDF/图片返回 file_url）
  - **Admin 会话管理 API 段**（2026-07-01 新增）：`adminBatchDeleteSessions(sessionIds)` 调用 `DELETE /api/session/admin/batch` 批量删除；`adminFetchSessionMessages(sessionId, limit)` 调用 `GET /api/session/admin/{session_id}/messages` 获取任意会话历史消息；`adminExportSessionMarkdown(sessionId)` 调用 `GET /api/session/admin/{session_id}/export/markdown` 导出 Markdown
  - **工具管理 API 段**（2026-06-25 新增）：`listTools` / `listUnregisteredTools` / `registerTool` / `updateTool` / `deleteTool` / `setToolEnabled` / `scanTools` 对应后端 `tool_admin_router` 的 `/api/admin/tools/*` 端点；`getAgentToolBindings` / `updateAgentToolBindings` / `fetchAgentAvailableTools` 对应后端 `agent_admin_router` 的 `/api/admin/agents/{name}/(tool-bindings|available-tools)` 端点
  - **Skill 管理 API 段**（2026-06-29 新增）：`listSkills` / `listUnregisteredSkills` / `registerSkill` / `updateSkill` / `deleteSkill` / `setSkillEnabled` / `scanSkills` 对应后端 `skill_admin_router` 的 `/api/admin/skills/*` 端点；`getAgentSkillBindings` / `updateAgentSkillBindings` / `fetchAgentAvailableSkills` 对应后端 `agent_admin_router` 的 `/api/admin/agents/{name}/(skill-bindings|available-skills)` 端点；所有函数复用既有 `fetchWithAuth` 包装器（401 自动重试一次）
- **AgentManager Skill 绑定 Tab**（2026-06-29 新增，`web/Agent/src/components/AgentManager.vue`）：在 basic / config / tools 三个 Tab 之外新增 `skills` Tab；调用 `fetchAgentAvailableSkills` 拉取可绑定 skill 后按 category 分组渲染可折叠列表，复用工具绑定 Tab 的折叠/勾选/保存模式；`localSelectedSkillBindings` 用 `{skill_name: {enabled, sort_order}}` 记录勾选；`saveSkillBindings` 按分组顺序生成 sort_order 调用 `updateAgentSkillBindings`；`selectAgent` 切换 agent 时若当前在 skills Tab 则立即重载；切换 skill Tab 由 `onSwitchToSkillsTab` 触发
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
  - `api.mcp.test.js`：MCP 管理 API 封装（**18** 用例 = 8 happy-path URL/方法/请求体验证 + 1 `updateMcpServer` PUT body + 9 失败路径验证 `detail` 错误消息）
  - `sseParser.test.js`：SSE 解析（含 Python 字面量兼容）
  - `subAgentParser.test.js`：subagent 解析（custom 事件维护 subAgents 列表 + sandbox_summary 合并 + 工具函数，**14** 用例）
  - `SubAgentCard.spec.js`：折叠卡片（**11** 用例）
  - `SubAgentDrawer.spec.js`：独立 Push Drawer（**19** 用例）
  - `MessageBubble.spec.js`：timeline.tool 内按 toolCallId 渲染 SubAgentCard 等（5 用例）
  - `UserSettingsDialog.subagent.spec.js`（2026-07-02 新增）：历史会话详情弹窗居中 CSS 回归保护 + 子智能体事件冒泡链路（**5** 用例）


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

核心改动：

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

map_router 实现：

- `generate_stream_response` 函数入口 `set_current_request(request)`，把 FastAPI Request 挂到 ContextVar
- finally 块 `reset_current_request(cv_token)`，避免后续请求继承错误引用
- 即使 `is_disconnected()` 触发 return 提前退出，也保证清理

### 客户端状态显示

**`web/Agent/src/components/SubAgentCard.vue`** + **`web/Agent/src/components/ToolCallCard.vue`** 状态映射：

- `status === 'stopped_by_user'` 状态映射：显示"已中止"文本
- CSS class `.stopped_by_user`：橙色徽章（区别于 success 绿色、error 红色、running 紫色）
- stopped_by_user 状态**静态显示**（无 pulse 动画），与 running 区分

**`web/Agent/src/utils/sseParser.js`** 状态判定：

- `updateSubAgentFromCustomEvent` 中 tool_stop 事件状态判定逻辑优先级（向后兼容）：`stopped_by_user` > `error` / `failure` > 其他（含无 status / `success`）→ success
- 旧事件无 status 字段默认 success（向后兼容普通工具 tool_stop）

### 测试覆盖

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
- **`tests/scripts/`**：项目根 `scripts/` 目录的离线脚本测试
  - `test_seed_tools_from_source.py`：13 用例（AST 装饰器识别 / description 提取 / 路径推断 / 分类推断 / scan_all_tools 端到端 / SQL+JSON 转义 / render_sql upsert / 空列表降级 / CLI --dry-run / CLI --output），通过 `monkeypatch` 隔离 `TOOL_ROOTS` / `PROJECT_ROOT` 到 `tmp_path`，不污染真实工程文件
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

### 已知工程实践

- **TestClient.delete() 不支持 `data` / `json` 关键字**：Starlette `TestClient.delete` 显式仅暴露 `params`、`headers`、`cookies` 等；如需发送 JSON body，应改用 `client.request("DELETE", url, headers=..., json=...)`（参见 `app/tests/shared/test_file_router.py::test_delete_files`）
- **PortalRefreshTokenDB 仅暴露物理删除**：使用 `delete_token(token_hash)`，不存在 `revoke_token`（参见 `app/tests/shared/test_portal_refresh_token_db.py`）

## Skill 系统

LangChain/LangGraph 环境下的 Skill 系统，提供可按需加载的工作流指引（如 brainstorming、TDD、debugging 等），通过 `<EXTREMELY_IMPORTANT>` 包裹的 bootstrap 引导模型调用 `load_skill` 工具。核心特性：配置化 markdown bootstrap、子智能体 `skills/` 与 `config/bootstrap.md` 覆盖机制。

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

| 根                                       | 说明                                                   |
| ---------------------------------------- | ------------------------------------------------------ |
| `<project>/app/skills/**/SKILL.md`     | 项目内置 skill，由代码仓库管理                         |
| `<project>/.agents/skills/**/SKILL.md` | 兼容 opencode 外部规范                                 |
| `settings.skills_paths`（逗号分隔）    | 用户运行时扩展，支持 `~/` 展开、绝对路径、相对项目根 |

### 子智能体覆盖机制（v2 新增）

| 路径                                            | 作用                     | 与全局的关系                                                                                  |
| ----------------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------- |
| `app/features/<agent>/skills/<name>/SKILL.md` | 子智能体专属 skill       | **完全覆盖**全局默认根扫描（仅扫描该目录，不追加 `app/skills` 与 `.agents/skills`） |
| `app/features/<agent>/config/bootstrap.md`    | 子智能体 bootstrap 重写  | 优先级**高于**全局默认 `app/core/skills/bootstrap.md`                                 |
| `app/features/<agent>/config/prompts.py`      | Agent 专属提示词（现有） | 不变                                                                                          |

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

### location / base_dir 存储格式（2026-06-30 改为相对项目根的 POSIX 路径）

DB `skills.location` / `skills.base_dir` 字段存储**相对项目根的 POSIX 路径**（统一正斜杠 `/`，无反斜杠），保证 Windows/Linux 跨平台一致。运行时由消费者通过 `SkillRegistryService._to_absolute(path_str, project_root)` 还原为绝对路径再访问文件系统。

| 字段          | 示例值                            | 含义                                      |
| ------------- | --------------------------------- | ----------------------------------------- |
| `location`  | `app/skills/knowledge_ydt/SKILL.md` | SKILL.md 文件相对项目根的 POSIX 路径   |
| `base_dir`  | `app/skills/knowledge_ydt`        | SKILL.md 所在目录相对项目根的 POSIX 路径 |

**写入路径**：

1. `SkillDiscovery._parse()` 扫描后用 `_to_relative(absolute_path, project_root)` 归一化
2. `SkillRegistryService.scan_unregistered()` 返回前再调一次 `_to_relative`（防御性，确保格式一致）
3. `SkillRegistryService.create_skill()` 写入前归一化（防御性，admin 通过 API 传入绝对路径会被自动转换为相对路径）

**消费路径**（按需还原为绝对路径）：

- `app/core/tools/SkillTools.py::load_skill` — `SkillRegistryService._to_absolute(info.base_dir, get_project_root())` 后 `iterdir()`
- `app/core/tools/SkillTools.py::_resolve_skill_root` — 同上后 `path.is_relative_to(root)` 白名单校验

**降级策略**：

- 路径不在 project_root 下（用户扩展路径指向项目外、Windows 跨盘符）：`_to_relative` 降级返回原绝对路径的 POSIX 形式，记录 `logger.debug`
- 解析失败：消费者记录 `logger.warning` 并跳过对应 skill，不抛异常（保证旧库数据兼容）

**SQL 初始化脚本**：`app/migrations/init_all_tables.sql` 中 3 条 INSERT（`bdc_query` / `hgsc` / `knowledge_ydt`）使用相对路径字面量；同脚本追加 3 条 `UPDATE ... WHERE name=... AND location LIKE '%\%'` 历史数据迁移语句（仅迁移仍为 Windows 绝对路径的行）。

### 系统提示词拼接（v2：`SkillsAwarePrompt.build()`）

```
┌─────────────────────────────────────────────┐
│  BASE_SYSTEM_PROMPT                         │  ← 通用规则（与现有架构一致）
├─────────────────────────────────────────────┤
│  self.system_prompt + context.system_prompt │  ← Agent 专属 + 动态层（与现有架构一致）
├─────────────────────────────────────────────┤
│  <EXTREMELY_IMPORTANT>...bootstrap.md...</> │  ← 工具映射（bootstrap 在前）
├─────────────────────────────────────────────┤
│  <available_skills>...</available_skills>   │  ← 列已注册 skill 的 name/description/location
└─────────────────────────────────────────────┘
```

### Bootstrap 优先级链（4 级）

1. **子智能体** `app/features/<agent>/config/bootstrap.md`（最高）
2. **用户自定义全局** `settings.skills_bootstrap_path`（如 `~/my_bootstrap.md`）
3. **系统默认** `app/core/skills/bootstrap.md`（项目仓库内置）
4. **代码内置 fallback** `_FALLBACK_TOOL_MAPPING`（项目实际工具映射字符串，包含 `sandbox` / `explore` / `load_skill` / `todowrite`）

### 与 opencode 的差异

| 项                      | opencode                                                  | 本项目                                                                                         |
| ----------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| 权限系统                | `ctx.ask({permission:"skill"})`                         | **无**；保留 `available(name_filter)` 扩展点                                           |
| bootstrap 注入点        | unshift 到首条 user message                               | 拼接到 system_prompt 末尾（语义更清晰，符合 LangChain 角色约定）                               |
| bootstrap 内容来源      | `using-superpowers` SKILL.md 正文 + 硬编码 Tool Mapping | **配置化 markdown 文件**：4 级优先级链（子智能体 > 用户全局 > 系统默认 > 代码 fallback） |
| 子智能体覆盖            | 无                                                        | **支持**：`app/features/<agent>/skills/` + `config/bootstrap.md`                     |
| 远程 skill 拉取         | `cfg.skills.urls` + discovery.ts::pull                  | **不做**（MVP）；后续按 opencode 协议扩展                                                |
| `.claude/skills` 兼容 | 是                                                        | **否**；项目使用自有 `.agents/skills` 约定                                             |
| 前置依赖                | TypeScript Runtime                                        | 仅 PyYAML（项目已装），无需新增第三方包                                                        |

### 标签使用约定

| 标签                      | 是否用于 skill 系统      | 备注                                                                                           |
| ------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------- |
| `<EXTREMELY_IMPORTANT>` | ✅ 用于 bootstrap 包裹层 | opencode 仅生成不解析；superpowers 插件约定格式                                                |
| `<available_skills>`    | ✅ 用于能力清单          | opencode 仅生成不解析                                                                          |
| `<system-reminder>`     | ❌**不使用**       | 项目 `BASE_SYSTEM_PROMPT:54` 已声明该标签是 LangChain 运行时系统提醒专用，不能用作业务包装层 |

### 关键 API

| 函数                                                                                | 行为                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SkillsService.get_instance(config, agent_name=None)`                             | 懒加载；`agent_name=None` 返回全局单例；`agent_name="map_agent"` 返回 agent 维度实例（agent skills/ 覆盖默认根）                                                                                                                                                                                                                                                                                                       |
| `SkillsService.get(name)` / `require(name)` / `all()` / `available(filter)` | 注册表访问；`require` 不存在抛 `SkillNotFoundError`（message 含 available 列表）                                                                                                                                                                                                                                                                                                                                       |
| `load_skill(name)`（LangChain `@tool`）                                         | 返回 `Command(update={"messages": [ToolMessage(content=...) ]})`；content 为 `<skill_content name="...">...</skill_content>` XML；错误时同样包装为 Command，content 以 `Error: ...` 开头（不抛异常）                                                                                                                                                                                                                 |
| `read_skill_file(file_path)`（LangChain `@tool`）            | 按**绝对路径**读取已注册 skill 目录下的资源文件；解析→白名单（必须在某 skill 的 `base_dir` 内）→大小（≤1 MB）→UTF-8 校验；成功返回 `<skill_file path="file:///..." size="N" parent_skill="...">正文</skill_file>`；失败返回 `Error: ...`。**不**复用 `BaseFilesystemTool`（不启动子智能体）。与 `load_skill` 配合使用：先 `load_skill` 拿 `<file>` 列表，再 `read_skill_file` 读具体文件。 |
| `render_available_skills_block(skills)`                                           | 渲染 `<available_skills>` XML；空列表返回 "No skills are currently available."                                                                                                                                                                                                                                                                                                                                           |
| `BootstrapProvider.render(agent_bootstrap_path, user_global_path)`                | 按 4 级优先级读取 bootstrap 内容并用 `<EXTREMELY_IMPORTANT>` 包裹                                                                                                                                                                                                                                                                                                                                                        |
| `SkillsAwarePrompt(base, agent_specific, agent_name=None, enabled_skill_names=None).build()`                | 拼最终 system_prompt 字符串（顺序：base + agent + bootstrap + skills）；`enabled_skill_names` 为 agent 已启用 skill 名称列表（白名单），None 时不启用过滤（保留旧行为），由 `Agent._llm_call` 从 `self._config.enabled_skill_names` 透传                                                                                                                                                                                                                                                                                                                                                     |

### 测试覆盖

`app/tests/core/skills/`：

- `test_loader.py` — 扫描多根、frontmatter 容错、同名覆盖、路径不存在警告、~/ 展开（10 用例）
- `test_service.py` — 单例、get/require/all/available、SkillNotFoundError 含 available、**agent_name 覆盖逻辑**
- `test_prompt.py` — 空列表/非空列表 XML 格式、特殊字符转义、按 name 排序
- `test_tool.py` — 成功路径、错误路径、base_dir URL、文件清单 limit=10、已适配 Command 解包（`_unwrap` 辅助 + `Command.update["messages"][0].content` 断言）。含 `read_skill_file` 用例：成功返回 XML 块、文件不存在、目录路径、白名单外、相对路径、超大文件、多 skill parent_skill 识别、UTF-8 解码失败、@tool 装饰器注册验证
- `test_bootstrap.py` — 8 用例：`<EXTREMELY_IMPORTANT>` 包裹、默认文件读取、缺失文件 fallback、agent 覆盖默认、user_global 覆盖默认、agent 高于 user_global、缺失 agent 回退默认、fallback 含 Tool Mapping 关键字
- `test_message_transformer.py` — **base + agent + bootstrap + skills 拼接顺序**、agent_name 传递、`enabled_skill_names` 过滤（None→`service.all()` / `[]`→`available(name_filter=[])` / 非空→`available(name_filter=...)`，互斥断言）

### 环境变量

- `SKILLS_PATHS` — 用户扩展 skill 扫描路径，逗号分隔；空则只用默认根（`app/skills` + `.agents/skills`）
- `SKILLS_BOOTSTRAP_PATH` — 用户自定义全局 bootstrap 文件路径；优先级高于系统默认 `app/core/skills/bootstrap.md`，低于子智能体 `config/bootstrap.md`
- `SKILLS_ENABLED` — 总开关，默认 `true`；`false` 时不扫描、不注入、不注册 `load_skill` 工具

### 集成点

- `app/core/agent/agent.py::_llm_call`：`SkillsAwarePrompt(base, agent_specific, agent_name=getattr(self, "agent_name", None), enabled_skill_names=getattr(self._config, "enabled_skill_names", None)).build()`（`UnifiedAgentConfig` 与 `AgentConfig` 均兼容，旧配置实例无该字段时为 `None`）
- `app/core/server.py::lifespan`：启动时调用 `SkillsService.get_instance(settings.skills.to_skills_config())`，清理阶段 `SkillsService.reset()`；启动阶段还在 MCPToolsRegistry 初始化后、SkillsService 初始化前，从 `DatabasePool._pool` 取连接池构造 `AgentConfigService(db, AgentsMdLoader())` 与 `McpConfigService(db)`，分别挂到 `app.state.agent_config_service` / `app.state.mcp_config_service`，并调用 `mcp_config_service.seed_from_yaml_if_empty()` 完成 YAML 种子导入；随后初始化 `ToolRegistryService(db)` 挂到 `app.state.tool_service` 并调用 `preload_all()` 预加载内置工具缓存（单独 try/except，失败不阻断后续逻辑）；接着初始化 `SkillRegistryService(db)` 挂到 `app.state.skill_service` 并调用 `preload_all()` 预加载 skills 缓存（单独 try/except，失败不阻断后续逻辑）；MCPToolsRegistry 初始化完成后，将 `tool_service` / `mcp_registry` / `skill_service` 通过 `set_tool_service` / `set_mcp_registry` / `set_skill_service` 注入到 `AgentConfigService`（每个注入各自 try/except 隔离失败），并调用 `agent_config_service.preload_all()` + `mcp_config_service.preload_all()` 预加载配置缓存（tools=None 延迟加载，保持 MCP 懒加载，整体 try/except 包裹失败降级为 warning）；数据库未启用或初始化失败时降级为 warning，不阻断 lifespan
- `app/core/config/settings.py`：新增 `SkillsSettings`（含 `skills_paths` / `skills_bootstrap_path` / `skills_enabled` 三个字段 + `to_skills_config()` 方法），并在顶层 `Settings` 中通过 `skills: SkillsSettings` 字段挂载
- `app/core/skills/bootstrap.md`：系统默认 bootstrap 内容，工具映射 + 工具选择决策规则，包含 `sandbox` / `explore` / `load_skill` / `read_skill_file` / `todowrite`
- `app/core/agent/AgentConfig.py::get_tools()`：基类 `get_tools()` 完全依赖外部传入的 `tools` 字段（决策 8：基础工具不默认加载，所有工具通过绑定实现）。`AgentConfig` 新增 `tools: Optional[List[Any]] = field(default=None)` 字段；`get_tools()` 返回 `(self.tools or [], ToolNode(...))`，不再硬编码任何默认工具。生产 chat 路径（agent_router）必须传入 `tools=config.tools`；`tools=None` 或 `[]` 时返回空工具列表（agent 无工具可用）。基类已移除 `BaseTools` / `SandboxTools` / `FilesystemReadTools` / `skills.tool` 的 import（改由 ToolRegistryService 通过 tool_bindings 绑定注入）。子类（如 `TagentConfig` / `ApprovalAgentConfig` 等）重写的 `get_tools()` 保留不变（向后兼容），但生产路径通过 `tools=config.tools` 覆盖子类返回值
- `app/core/agent/AgentConfig.py::enabled_skill_names`：`AgentConfig` 新增 `enabled_skill_names: Optional[List[str]] = field(default=None)` 字段（2026-06-29 修复）。由 `AgentConfigService.build_agent_instance()` 从 `UnifiedAgentConfig.enabled_skill_names` 过滤后注入（过滤逻辑：通过 `SkillRegistryService` 校验 DB 注册与启用状态）。`agent.py::_llm_call` 通过 `getattr(self._config, "enabled_skill_names", None)` 读取并传入 `SkillsAwarePrompt`，为 `None` 时回退到加载全部 skill（向后兼容旧配置）

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
- **新增前置**：各 Agent 子类需在 `__init__` 中显式设置 `self.agent_name = "<dir_name>"`（如 HtAgent → `"contract_host_agent"`），未设置时 SkillsService 回退到全局实例

### 子智能体 name 注入

`Agent` 基类通过 `AgentConfig.name` 字段识别子智能体维度，链路：

1. **基类字段**：`app/core/agent/AgentConfig.py` 在 `system_prompt` 旁新增 `name: Optional[str] = field(default=None)`，含义为"Agent 注册名（与 app/features/`<dir>`/ 目录名一致），用于 skill 系统按子智能体维度隔离；None 时回退到全局 skill 注册表"
2. **基类读取**：`app/core/agent/agent.py::Agent.__init__` 在 `self.system_prompt = config.system_prompt` 之后新增一行 `self.agent_name = config.name`；`agent._llm_call` 通过 `getattr(self, "agent_name", None)` 透传到 `SkillsAwarePrompt`
3. **子智能体覆盖**：6 个 *Config 类在 `state_class` 字段前覆盖基类默认值为字面量：

| 子智能体           | 配置文件                                                               | name 字面量                                                                    |
| ------------------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| ~~MapAgent~~      | ~~`app/features/map_agent/config/MapAgentConfig.py`~~               | ~~`"map_agent"`~~ |
| HtAgent            | `app/features/contract_host_agent/config/HtAgentConfig.py`           | `"contract_host_agent"`                                                      |
| DocAgent           | `app/features/contract_document_agent/config/DocAgentConfig.py`      | `"contract_document_agent"`                                                  |
| ApprovalAgent      | `app/features/contract_approval_agent/config/ApprovalAgentConfig.py` | `"contract_approval_agent"`                                                  |
| DevOpsAgent        | `app/features/DevOps_agent/config/DevOpsAgentConfig.py`              | `"DevOps_agent"`                                                             |
| AICodingCheckAgent | `app/features/AI_Coding_Check_agent/config/AICodingCheckConfig.py`   | `"AI_Coding_Check_agent"`                                                    |
| TAgent             | `app/features/Tagent/config/TagentConfig.py`                         | `"Tagent"`                                                                   |

4. **包装类不需改动**：5 个包装类（`HtAgent` / `DocAgent` / `ApprovalAgent` / `DevOpsAgent` / `AICodingCheckAgent`）持有的 `self._agent` 是内部 `Agent` 实例，已自动从 `*Config` 拿到 `self.agent_name`；包装类本身不暴露 `agent_name` 属性
5. **测试**：`app/tests/core/agent/test_agent_name_propagation.py`覆盖：基类默认 None / 6 个子 Config 字面量 / Agent.__init__ 透传（移除了依赖 MapAgentConfig 的 2 个用例）

**现状**：map_agent 不再有子智能体专属 skill 目录，回退到全局默认扫描。

### agent_name 透传到工具 & 降级查找

**背景**：`load_skill` / `read_skill_file` 工具原实现直接调用 `SkillsService.get_instance()`（无 `agent_name` 参数），只拿到全局单例，导致 agent 专属目录（如 `app/features/map_agent/skills/data-skill/`）下的 skill 永远找不到，工具返回 `Error: Skill "data-skill" not found. Available skills: none`。修复采用 LangChain 推荐的 `ToolRuntime.state` 通道（context7 文档 + 项目内 MapTools.py/BaseTools.py 共 11 处已有 `runtime.state.get(...)` 用法），把 agent 身份以 state 字段方式注入，**不** 修改 `AgentContext`（保持不可变配置语义）。

**设计要点**：

1. **State 字段**：`app/core/agent/AgentConfig.py::AgentState` 新增 `agent_name: Optional[str] = None` 字段；工具通过 `runtime.state.get("agent_name")` 读取
2. **注入位置**：包装类构造初始 state 时写入 `agent_name="<dir_name>"`（如 `app/features/map_agent/MapAgent.py::stream()` 中 `MapAgentState(..., agent_name="map_agent")`，与 `*AgentConfig.name` 默认值保持一致；map_agent 的 `agent_name` 通过 `UnifiedAgentConfig.name` 由 AgentConfigService 从数据库加载，`Agent.__init__` 透传到 `self.agent_name`）
3. **不修改**：`AgentContext`（用户明确要求保持不可变配置语义）；`SkillsService._scan` 覆盖策略；`SkillsAwarePrompt` 内部取值链路（已通过 `Agent.self.agent_name` 走通）

**降级查找约定**（`app/core/tools/SkillTools.py` 新增 4 个辅助函数，原 `app/core/skills/tool.py` 已迁出）：

| 函数                                               | 行为                                                                                                                                           |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `_get_agent_name(runtime)`                       | 安全读取 `runtime.state.get("agent_name")`，缺失/异常时返回 None                                                                             |
| `_resolve_skill_with_fallback(name, agent_name)` | 先 `SkillsService.get_instance(agent_name=...).get(name)`；命中即返回；未命中或 agent_name 为空再 `SkillsService.get_instance().get(name)` |
| `_merged_available(agent_name)`                  | 合并 agent 维度 + 全局维度的 skill 名称（去重 + 排序），用于 `SkillNotFoundError.message`                                                    |
| `_resolve_all_skills(agent_name)`                | 合并 agent 维度 + 全局维度的 SkillInfo 列表（agent 优先），用于 `read_skill_file` 白名单校验                                                 |

**降级顺序**：`agent 维度 SkillsService` → `全局 SkillsService`。**不修改** `SkillsService._scan` 中"agent_name 传入时完全覆盖默认根"的扫描策略——降级在工具层做，不影响 service 层语义。

### 设计/计划文档

- 设计：[docs/superpowers/specs/2026-06-20-skill-system-design.md](../docs/superpowers/specs/2026-06-20-skill-system-design.md)
- 计划：[docs/superpowers/plans/2026-06-20-skill-system.md](../docs/superpowers/plans/2026-06-20-skill-system.md)

## 动态 State/Context 构建器

根据数据库 `agents` 表的 `state_schema` / `context_schema` JSON 配置动态生成 `AgentState` / `AgentContext` 的子类，支持子智能体按需扩展状态/上下文字段而无需修改基类代码。

### 模块位置

```
app/shared/utils/agent/
├── __init__.py              # 空包初始化
└── dynamic_schema.py        # 动态 schema 构建器核心实现
```

### 核心 API

| 函数                                                   | 作用                                                                                                                                         |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_agent_state(agent_name, state_schema)`        | 根据 `state_schema` JSON 生成 `AgentState` 子类包装器，类名格式 `{PascalCase}AgentState`（如 `map_agent` → `MapAgentAgentState`） |
| `build_agent_context(agent_name, context_schema)`    | 根据 `context_schema` JSON 生成 `AgentContext` 子类包装器，类名格式 `{PascalCase}AgentContext`                                         |
| `build_context(agent_name, context_schema, request)` | 运行时构造 context 实例，从 `request` 读取 `session_id` / `store_id` / `context_overrides`                                           |

### 合并逻辑

- **基类字段保留**：`AgentState` / `AgentContext` 基类所有字段注解原样继承
- **保留字段（RESERVED_STATE_FIELDS / RESERVED_CONTEXT_FIELDS）**：schema 中同名字段仅允许重写默认值，不可重写类型注解
- **非保留字段**：schema 中的新字段追加类型注解（通过 `TYPE_MAP` 映射 `str/int/float/bool/dict/list`）和默认值

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

- 路径：`app/tests/shared/utils/agent/test_dynamic_schema.py`（18 用例）
- 本地 conftest：`app/tests/shared/utils/agent/conftest.py` 覆盖根 conftest 中 `langgraph.graph.MessagesState = Mock()`，提供真实 TypedDict 基类，确保 `AgentState` 正确继承 TypedDict 而非 Mock
- 覆盖：模块可导入 / 子类字段追加 / 基类字段保留 / 保留字段跳过 / 默认值覆盖 / context 子类生成 / context 基类字段保留 / 运行时实例构造 / 保留字段集合校验 / 可变默认值隔离 / context 关键字冲突过滤 / **基类保留字段默认值自动补全**

## AGENTS.md 加载器

从文件系统读取 `agents/<agent_name>/AGENTS.md` 纯 markdown 内容，供 `AgentConfigService`作为 `system_prompt` 注入 LLM。带内存缓存，避免重复磁盘 IO。

### 模块位置

```
app/shared/utils/agent/
├── __init__.py              # 空包初始化
├── dynamic_schema.py        # 动态 schema 构建器
├── agents_md_loader.py      # AGENTS.md 加载器
├── mcp_service.py           # MCP 配置 CRUD 服务
├── tool_service.py          # 工具注册中心服务（DB tools 表 CRUD + 缓存 + ast 扫描）
└── agent_config_service.py  # Agent 配置加载服务
```

### 核心 API

| 类 / 方法                               | 作用                                                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `AgentsMdLoader`                      | AGENTS.md 文件加载器，带内存缓存                                                                        |
| `AgentsMdLoader.load(agents_md_path)` | 加载指定路径的 AGENTS.md 内容；首次读取磁盘并缓存，后续直接返回缓存；文件不存在抛 `FileNotFoundError` |
| `AgentsMdLoader.clear_cache()`        | 清空缓存，admin 更新 AGENTS.md 后调用以刷新                                                             |

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

### map_agent AGENTS.md 文件

首个落地于 `agents/<agent_name>/AGENTS.md` 约定的纯 markdown 提示词文件，供 `AgentsMdLoader` 读取后作为 `system_prompt` 注入 LLM。

**文件位置**: `agents/map_agent/AGENTS.md`

**内容章节**:

| 章节                                 | 作用                                                                                                                                                 |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Task Rules                           | 工具选择规则与 ask_user_question 使用约束（来自 prompts.py `DEFAULT_SYSTEM_PROMPT`）                                                               |
| TOOL DESCRIPTION /`### explore`    | explore 工具的使用场景、优先级与返回值限制（来自 prompts.py `MAP_AGENT_SYSTEM_PROMPT` 头部）                                                       |
| TOOL DESCRIPTION /`### load_skill` | 通用约束：这两个工具仅在触发 skill 时使用；未触发 skill 时不要用它们，查找仍走 `explore`                                                           |
| Agent Capability                     | 英文声明核心能力（合规性审查 + 项目预审，关键术语保留中文）+ 具体触发条件：调用 `load_skill("hgsc")` + `read_skill_file(absolute_path)` 获取详情 |

**纯 markdown 原则**: 不包含 `state_schema` / `context_schema` / `TypedDict` 等运行时配置（这些在数据库 `agents` 表中），仅包含 LLM 可见的提示词内容。

**内容测试**:

- 路径：`app/tests/shared/utils/agent/test_agents_md_content.py`（4 用例）
- 覆盖：文件存在 / 包含 Task Rules 章节 / 包含 TOOL DESCRIPTION 章节（含 explore 工具说明） / 不包含 state 字段定义（纯 markdown 原则）

### hgsc skill

**文件位置**: `app/skills/hgsc/skill.md`（frontmatter `name: hgsc`）

合规性审查（Compliance Review）与项目预审（Project Pre-review）工作流 skill，内容来源于 `agents/map_agent/prompts.py::MAP_AGENT_SYSTEM_PROMPT` 第 22-55 行（Workflow / 合规性审查步骤 / Task Examples / Output Requirements）。Workflow 部分描述"合规性审查"四步流程：上下文收集 → explore 验证附件 → ask_user_question 确认 → save_business_info 持久化 → quality_inspection_analysis → generate_report；原文为英文，保留英文原文。

### knowledge_ydt skill

**文件位置**: `app/skills/knowledge_ydt/SKILL.md`（frontmatter `name: knowledge_ydt`）

知识库查询工作流 skill，供 `agents/knowledge_ydt/AGENTS.md` 调用。每次知识库查询前必须先 `load_skill("knowledge_ydt")` 并遵循其流程：

1. **识别意图**：区分事实查询与辅助决策。
2. **判断附件依赖**：若问题涉及具体项目、合同、条款或约束，先使用 `explore` 从当前 session 上传目录提取关键信息；否则直接基于对话上下文查询。
3. **调用 `query_knowledge`**：将提取出的附件信息与会话上下文合并，构造详细查询任务。
4. **返回结果**：事实查询类返回原文；辅助决策类返回决策结论 + 决策依据。

**配套 AGENTS.md**: `agents/knowledge_ydt/AGENTS.md` 已精简为只保留 Task Rules、Agent Capability 和 Tool Priority，强制要求每次知识库查询必须先加载 `knowledge_ydt` skill。

### project-doc 套件

2026-07-02 新增：从外部 skill 套件迁移到 `app/skills/` 的 7 个项目文档相关 skill，统一处理软件工程项目文档（策划表、需求、设计、计划、测试、验收、部署、培训等）。

| Skill | 文件位置 | 核心职责 |
|---|---|---|
| `project-doc-overview` | `app/skills/project-doc-overview/SKILL.md` | 套件总览与入口调度说明，供模型理解 7 个 skill 的关系与 dispatch 规则 |
| `project-doc-hub` | `app/skills/project-doc-hub/SKILL.md` | 用户提出“项目 + 文档”请求时的调度入口，按意图分流到 query/outline/write/workflow |
| `project-doc-query` | `app/skills/project-doc-query/SKILL.md` | 回答项目事实类问题与 PMO 决策建议，强制使用 PMP/PRINCE2/系统分析师三层框架 |
| `project-doc-outline` | `app/skills/project-doc-outline/SKILL.md` | 为 10 种软件工程交付物生成章节级大纲（无正文） |
| `project-doc-write` | `app/skills/project-doc-write/SKILL.md` | 在已有大纲基础上严格基于项目资料填充正文，生成决策建议 |
| `project-doc-workflow` | `app/skills/project-doc-workflow/SKILL.md` | 端到端 4 步流水线检查清单（hub → query → outline → write → save-to-disk） |
| `intent-clarification` | `app/skills/intent-clarification/SKILL.md` | 统一澄清协议：任何需要向用户确认的问题都必须先调用该 skill |

**迁移改造要点**（相对原外部套件）：
- 原 `scripts/` 目录未迁移，所有文件读取统一改为调用 `explore(...)`；
- SKILL.md 中删除了 `python scripts/...` 等 CLI 调用示例与 `scripts/` 路径引用；
- 保留 YAML frontmatter、核心理念（no-fabrication、澄清顺序、文档类型分类）与 `references/` 原文；
- 变更日志/主日志写入改用文件写入工具直接操作 `.project/<项目号>/` 下文件。

### project 智能体（2026-07-02 新增）

`project` 是统一智能体架构下的项目文档专用智能体，入口为 `agents/project/AGENTS.md`，与 `map_agent` 平行挂在 `agents` 表 `name='project'` 一行。激活关键词包括「项目文档/项目材料/实施方案/生成大纲/写文档/更新文档/项目查询/交付物/里程碑/评审计划」等。

**核心能力**：
- 通过 `intent_clarification` 工具按统一澄清协议向用户发起 1-4 个结构化问题，所有需要追问的场景都必须先调用该工具，禁止以纯文本回复。
- 通过 `load_skill(...)` / `read_skill_file(...)` 加载 project-doc 套件 skill（`project-doc-overview` / `project-doc-hub` / `project-doc-query` / `project-doc-outline` / `project-doc-write` / `project-doc-workflow`）与 `intent-clarification`。
- 通过 `explore(...)` 读取项目文件夹（`data/project/<project_id>/`）原文件，禁止以脚本/CLI 方式直接读文件。
- 通过 `manage_project_log` / `append_change_log` 维护项目操作日志与变更记录。
- 通过 `generate_project_docx` 将生成的 Markdown 正文转 Word（.docx），落盘到 `data/download/{session_id}/<时间戳>.docx`，返回 `download_url`。
- 严格禁止虚构人名/日期/数字/工具名/角色签字表/文档状态/框架标签，所有数据必须来自项目材料或用户确认。

**8 个内置工具**（`app/shared/tools/skills/project/ProjectTools.py`）：

| 工具 | 类型 | 说明 |
|---|---|---|
| `intent_clarification` | builtin | 统一澄清协议；返回 `Command(update={"pending_question": ..., "messages": ...})` |
| `project_doc_query` | builtin | 项目事实查询（async）；调度 `explore` 检索项目文件夹 |
| `project_doc_outline` | builtin | 按文档类型生成章节大纲（async）；支持从项目现有 docx 提取格式模板 |
| `project_doc_write` | builtin | 在已有大纲上填充正文（async） |
| `project_doc_workflow` | builtin | 端到端工作流编排检查清单（hub → query → outline → write → save） |
| `manage_project_log` | builtin | 维护 `.project/project_log.md`（append / read） |
| `append_change_log` | builtin | 追加变更记录到 `.project/变更记录.md` |
| `generate_project_docx` | builtin | Markdown → docx，落盘到 `data/download/{session_id}/` |

**绑定 7 个 skill**（`agents.skill_bindings` JSONB 字段）：`project-doc-overview` / `project-doc-hub` / `project-doc-query` / `project-doc-outline` / `project-doc-write` / `project-doc-workflow` / `intent-clarification`。

**文件布局**：
- `agents/project/AGENTS.md` —— 智能体入口与任务规则
- `app/skills/project-doc-*/SKILL.md` + `references/` —— 7 个 skill 元数据与参考文档（references 原文迁移，未合并到 SKILL.md）
- `app/shared/tools/skills/project/ProjectTools.py` —— 8 个 `@tool` 工具实现
- `app/shared/tools/skills/project/__init__.py` —— 工具包导出
- `app/migrations/seed_project_agent.py` —— 数据库种子脚本（写入 agents / agent_tool_bindings / skills）
- ~~`app/migrations/seed_project_skills.sql`~~ —— **已废弃（2026-07-10）**：原为独立 skills 表种子 SQL，曾被 `init_all_tables.sql` 末尾 `\i` 引用。因 `\i` 是 psql 命令行专属元命令，pgAdmin/Navicat/DBeaver 等 GUI 工具不识别、执行时报"语法错误 在 \"\\\" 或附近的"并终止整个 BEGIN 事务。已将其全部内容**内联**到 `app/migrations/init_all_tables.sql` 末尾（保留原注释头说明），并删除独立文件
- `scripts/generate_project_skills_seed.py` —— 重新生成 skills 种子 SQL 段的工具脚本（解析 SKILL.md frontmatter + 正文，输出幂等 INSERT）。注意：2026-07-10 合并后，本脚本输出目标应改为追加到 `init_all_tables.sql` 而非写独立文件
- `app/tests/shared/tools/skills/project/test_project_tools.py` —— 11 个 P0/P1 单测（覆盖导入/注册、Pydantic 入参校验、文件落盘、docx 落盘）

**DB 种子执行**：
```powershell
$env:DATABASE_URL = (Get-Content .env | Select-String "^DATABASE_URL=").Line.Split("=",2)[1]
python -m app.migrations.seed_project_agent
```
幂等：重复执行会 UPDATE 已存在的 agents 记录、刷新 skills 记录、刷新 agent_tool_bindings。

## AgentConfigService 配置加载服务

从数据库 `agents` 表 + AGENTS.md 文件加载完整 Agent 配置，封装为 `UnifiedAgentConfig` 实例供 `agent_router` 使用。是连接数据库配置和运行时 Agent 的核心服务，整合 `dynamic_schema` + `agents_md_loader` 两个模块的输出。

**2026-06-25 重构**：新增进程内缓存层 + 工具延迟加载语义，读方法优先读缓存，写方法写 DB 后同步刷新或失效缓存；新增 `set_tool_service` / `set_mcp_registry` 依赖注入入口供 lifespan 注入工具加载依赖。

### 模块位置

```
app/shared/utils/agent/agent_config_service.py
```

### 核心 API

| 类 / 方法                                                          | 作用                                                                                                                                                                               |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `UnifiedAgentConfig`                                             | 统一智能体配置 dataclass（name / display_name / description / system_prompt / state_class / context_class / mcp_tags / enabled_tool_names / enabled_skill_names / agents_md_path / config_schema / **tools** / **_agent_row**）。`tools` 为工具实例列表（None 表示未加载，[] 表示已加载但无绑定）；`_agent_row` 保存原始 DB 行字典供 `_load_tools` 使用（repr=False） |
| `AgentNotFoundError`                                             | 智能体未找到或已禁用时抛出的异常                                                                                                                                                   |
| `AgentAlreadyExistsError`                                        | 新增智能体时名称重复时抛出的异常                                                                                                                                                   |
| `AgentConfigService(db, agents_md_loader)`                       | 构造器，参数 `db` 需支持异步 `fetch` / `fetchrow` / `execute`，`agents_md_loader` 为 `AgentsMdLoader` 实例；初始化空缓存 `_cache` / `_default_config` + `_cache_lock` / `_tools_lock`（asyncio.Lock）+ `_tool_service` / `_mcp_registry` / `_skill_service`（默认 None，由 lifespan 注入） |
| `set_tool_service(tool_service)`                                 | 注入 `ToolRegistryService` 实例（由 lifespan 调用），供 `_load_tools` 按 tool_name 加载内置 `@register_tool` 工具实例                                                              |
| `set_mcp_registry(registry)`                                     | 注入 `MCPToolsRegistry` 实例（由 lifespan 调用），供 `_load_tools` 按 tool_name / mcp_tags 加载 MCP server 工具实例                                                                |
| `set_skill_service(skill_service)`                               | 注入 `SkillRegistryService` 实例（由 lifespan 调用），供 `get_available_skills` 列出可绑定的 skill 元数据                                                                         |
| `preload_all()`                                                  | 预加载所有启用 agent 配置到 `_cache`（tools=None 延迟加载）；启动时由 lifespan 调用；单个 agent 加载失败记录 warning 并跳过                                                         |
| `get_agent_config(agent_name)`                                   | 异步加载完整配置（带缓存 + 工具延迟加载）：1) agent_name 为空查 `_default_config` 缓存；2) 命名 agent 先查 `_cache`；3) 未命中调 `_load_from_db` 写入缓存；缓存命中但 tools=None 时用 `_tools_lock` 保护触发 `_load_tools`（double-check 模式）。**agent_name 为空时返回框架默认配置（AgentState/AgentContext 基类，system_prompt 为空由 Agent 内部回退到 BASE_SYSTEM_PROMPT）** |
| `_load_from_db(agent_name)`                                      | 从 DB 加载单个 agent 配置（不含工具实例，tools=None）；`enabled_skill_names` 从 `agents.skill_bindings` JSONB 字段直接解码，不再查询 `agent_skill_bindings` 表；返回的 `_agent_row` 保存原始 DB 行字典 |
| `_load_tools(agent_row)`                                         | 延迟加载工具实例：优先从 `tool_bindings` JSONB 加载（builtin 走 `_tool_service.get_tool_by_name`，mcp 走 `_mcp_registry.get_tools_with_server`，**mcp 绑定走 `server.method` 复合名解析**——`_parse_mcp_tool_name` 拆出 server / method，调 `get_tools_with_server(server=, names=[method])`；无 method 即无 server 前缀时记录 warning 并跳过）；`tool_bindings` 为空时回退到 `mcp_tags` 过滤 MCP 工具；依赖未注入时返回 [] |
| `_parse_mcp_tool_name(tool_name)`                                | 静态方法解析 MCP 工具绑定的 `server.method` 复合名：`"amap.search"` → `("amap", "search")`；`"search"`（无 `.`）→ `("search", "")`；`"amap.sub.search"` → `("amap", "sub.search")`（仅按第一个 `.` 分割）；`""` → `("", "")`。调用方应通过 `if not method_name` 判断是否缺少 server 前缀 |
| `list_agents()`                                                  | 异步列出所有启用智能体（仅返回 name / display_name / description 摘要）                                                                                                            |
| `create_agent(config)`                                           | Admin 创建智能体（先 SELECT 检查重名，再 INSERT INTO agents RETURNING *）；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                              |
| `delete_agent(agent_name)`                                       | Admin 删除智能体；写 DB 后调 `_invalidate_cache(name)` 使缓存失效                                                                                                                  |
| `set_agent_enabled(agent_name, enabled)`                         | 启用/禁用智能体；enabled=True 调 `_refresh_cache`，enabled=False 调 `_invalidate_cache`                                                                                            |
| `update_agent_config_schema(agent_name, schema)`                 | 全量替换 config_schema（同步拆解到 state_schema / context_schema）；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                                    |
| `add_agent_config_field(agent_name, section, field_name, field_def)` | 向 config_schema 指定 section（root / state_fields / context_fields）追加字段；内部调 `update_agent_config_schema`                                                                |
| `delete_agent_config_field(agent_name, section, field_name)`     | 从 config_schema 指定 section 删除字段；内部调 `update_agent_config_schema`                                                                                                        |
| `bind_tool(agent_name, tool_name, enabled)`                      | 绑定/解绑工具（upsert agent_tool_bindings）；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                                                            |
| `bind_skill(agent_name, skill_name, enabled)`                    | **已废弃**。原绑定/解绑 skill（曾 upsert agent_skill_bindings 表）逻辑已停止执行，调用时仅记录 `logger.warning` 提示使用 `update_skill_bindings` 全量替换接口（直接更新 `agents.skill_bindings` JSONB 字段）。`agent_skill_bindings` 表本身已于 2026-06-30 从 `init_all_tables.sql` 移除 |
| `update_tool_bindings(agent_name, bindings)`                     | 全量更新 agents 表 `tool_bindings` JSONB 字段（工具绑定快照）；写 DB 后调 `_refresh_cache(name)` 同步缓存；agent 不存在抛 `AgentNotFoundError`                                     |
| `get_tool_bindings(agent_name)`                                  | 读取 agents 表 `tool_bindings` JSONB 字段并解码返回列表；agent 不存在抛 `AgentNotFoundError`；字段为空返回 `[]`                                                                       |
| `update_skill_bindings(agent_name, bindings)`                    | 全量更新 agents 表 `skill_bindings` JSONB 字段（skill 绑定快照，格式 `[{"skill_name": str, "enabled": bool, "sort_order": int}]`）；写 DB 后调 `_refresh_cache(name)` 同步缓存；agent 不存在抛 `AgentNotFoundError` |
| `get_skill_bindings(agent_name)`                                 | 读取 agents 表 `skill_bindings` JSONB 字段并解码返回列表；agent 不存在抛 `AgentNotFoundError`；字段为空返回 `[]`                                                                      |
| `get_available_skills()`                                         | 通过注入的 `SkillRegistryService.list_skills()` 获取全部 skill 元数据，过滤 `enabled=False`，返回 `{name, display_name, category, description}` 列表；未注入时返回 `[]` 并记录 warning |
| `_refresh_cache(agent_name)`                                     | 从 DB 重新加载单个 agent 到 `_cache`（tools=None 延迟加载）；DB 中不存在或已禁用则从缓存移除（供写方法同步缓存，不主动抛异常）                                                       |
| `_invalidate_cache(agent_name)`                                  | 从 `_cache` 移除单个 agent（供 delete_agent / set_agent_enabled(False) 失效缓存）；幂等，不访问 DB                                                                                  |
| `invalidate_all_cache()`                                         | 清空全部缓存（含 `_default_config`），供 MCP server 配置变更时调用（MCP 变更可能影响所有 agent 的工具列表）                                                                          |

### 缓存层设计要点（2026-06-25 新增）

- **进程内缓存**：`_cache` 为 `Dict[str, UnifiedAgentConfig]`，启动时由 `preload_all()` 预加载所有启用 agent；`_default_config` 缓存框架默认配置（agent_name 为空时使用）
- **延迟加载语义**：`tools=None` 表示工具尚未加载，`tools=[]` 表示已加载但无工具绑定；首次 `get_agent_config` 时才触发 `_load_tools`，保持 MCP 懒加载语义
- **double-check 模式**：`get_agent_config` 命中缓存但 `tools=None` 时，用 `_tools_lock` 保护触发 `_load_tools`，防止并发请求重复加载工具
- **缓存同步策略**：写方法（create / update / bind 等）写 DB 后调 `_refresh_cache` 同步缓存；delete / disable 调 `_invalidate_cache` 使缓存失效；MCP 变更调 `invalidate_all_cache` 清空全部
- **工具加载优先级**：`_load_tools` 优先从 `tool_bindings` JSONB 加载（builtin 走 `_tool_service`，mcp 走 `_mcp_registry`，**mcp 工具名约定 `server.method` 复合格式**——通过 `_parse_mcp_tool_name` 拆解后用 `get_tools_with_server(server=, names=[method])` 过滤加载）；`tool_bindings` 为空时回退到 `mcp_tags` 过滤 MCP 工具
- **无默认工具**：基础工具需预先注册到 `tools` 表并通过 `tool_bindings` 绑定才会加载；`tool_bindings` 和 `mcp_tags` 都为空时返回空列表，不再隐式注入任何默认工具
- **skill 绑定加载**：`enabled_skill_names` 不再查询 `agent_skill_bindings` 表，改由 `_load_from_db` 解码 `agents.skill_bindings` JSONB 字段并过滤 `enabled=True` 的 `skill_name` 得到；`build_agent_instance()` 构造 `AgentConfig` 前，进一步通过注入的 `_skill_service`（`SkillRegistryService`）校验每个 skill 在 DB `skills` 表中的注册与启用状态，未注册或已禁用的 skill 从列表移除并记录 warning
- **AgentConfig.get_tools() 依赖外部传入**：`AgentConfig.get_tools()` 完全依赖外部传入的 `self.tools`（由 `AgentConfigService._load_tools` 加载并写入 `UnifiedAgentConfig.tools`），自身不做任何工具发现/加载逻辑
- **MCP 工具加载**：`MCPToolsRegistry.get_tools_with_server` 为同步方法（内部用线程池），`_load_tools` 直接调用无需 await
- **依赖注入**：`_tool_service` / `_mcp_registry` / `_skill_service` 默认为 None，由 lifespan 调用 `set_tool_service` / `set_mcp_registry` / `set_skill_service` 注入；未注入时 `_load_tools` / `get_available_skills` 返回 []（向后兼容旧测试）

### 设计要点

- **enabled 校验在 Python 层**：SQL 查询不携带 `AND enabled = TRUE`，而是在 Python 中通过 `row.get("enabled", False)` 判断，便于在 mock 测试中精确控制返回值
- **字段安全访问**：`display_name` / `description` / `state_schema` / `context_schema` / `mcp_tags` 均通过 `row.get(...)` 或 `or {}` / `or []` 兜底，避免 KeyError
- **create_agent 输入校验**：`create_agent` 方法在执行 INSERT 前校验必需键（name / display_name / agents_md_path），缺失时抛出 `KeyError`；docstring 明确文档化该异常；先 SELECT 检查重名，已存在抛 `AgentAlreadyExistsError`
- **日志记录**：`get_agent_config`（成功/未找到）、`create_agent`、`bind_tool`、`bind_skill`（废弃 warning）、`update_tool_bindings`、`update_skill_bindings`、`preload_all`、`invalidate_all_cache` 均通过 `logger.info` / `logger.warning` 记录关键路径
- **绑定列表过滤**：`enabled_tool_names` 通过 `r.get("is_enabled")` 过滤；`enabled_skill_names` 从 `agents.skill_bindings` JSONB 列表过滤 `enabled=True` 的 `skill_name`。访问字段前均做存在性校验，避免 mock 返回缺失键引发 KeyError
- **state_class / context_class 类型**：`UnifiedAgentConfig.state_class` / `context_class` 类型注解为 `Callable`（而非 `type`），因 `build_agent_state` / `build_agent_context` 返回的是 `_TypedDictWithDefaults` 包装器实例
- **JSONB 字段防御性反序列化**：`state_schema` / `context_schema` / `mcp_tags` / `tool_bindings` / `skill_bindings` 五个 JSONB 字段读取后先经 `AgentConfigService._decode_jsonb(value, default)` 静态方法处理。asyncpg 默认不注册 JSONB codec，DB 返回 `str`（JSON 字符串）；若将来连接池注册了 codec 则返回 `dict` / `list`。两种情况均需兼容：None 走 default；str 用 `json.loads` 解析（失败回退 default 并 warning）；dict/list 原样返回
- **依赖模块**：`dynamic_schema.build_agent_state` / `build_agent_context` + `agents_md_loader.AgentsMdLoader.load`

### 数据库关联

| 表                       | 用途                                                                                                                            |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `agents`               | 主表，存储 name / display_name / description / agents_md_path / state_schema / context_schema / config_schema / mcp_tags / tool_bindings（JSONB 快照）/ skill_bindings（JSONB 快照）/ enabled / sort_order |
| `agent_tool_bindings`  | 工具绑定表（关系型），存储 agent_name / tool_name / is_enabled / sort_order；`tool_bindings` JSONB 为该表的快照缓存，避免每次加载都联表查 |

### 测试

- 路径：`app/tests/shared/utils/agent/test_agent_config_service.py`（101 用例）
- 覆盖：模块可导入 / 从数据库和 AGENTS.md 加载完整配置 / agent 不存在抛 AgentNotFoundError / agent 禁用抛 AgentNotFoundError / list_agents 只返回启用智能体 / 从 `agents.skill_bindings` JSONB 加载 skill 绑定 / create_agent 插入并返回新行 / bind_tool 执行 upsert / **bind_skill 已废弃且不执行 SQL** / **JSONB 防御性反序列化** / **三层嵌套 config_schema 解析** / **set_tool_service / set_mcp_registry / set_skill_service 依赖注入** / **preload_all 预加载** / **_refresh_cache / _invalidate_cache / invalidate_all_cache 缓存同步** / **get_agent_config 缓存命中与未命中路径** / **_load_tools 内置工具 / MCP 工具 / mcp_tags 回退 / 空绑定** / **_parse_mcp_tool_name 复合名解析 + _load_tools MCP server.method 绑定加载** / **update_tool_bindings / update_skill_bindings 更新 DB 与缓存** / **get_tool_bindings / get_skill_bindings / get_available_skills 读取与过滤** / **写方法缓存同步验证** / **UnifiedAgentConfig 新字段（tools / _agent_row）** / **_convert_server_config DB 元数据过滤** / **_load_tools 异步路径调用（验证 get_tools_with_server_async）** / **build_agent_instance 统一构造入口**
- 异步测试使用 `asyncio.run()` 包装（非 pytest-asyncio）
- Mock 使用 `unittest.mock.AsyncMock` 和 `MagicMock`；写方法测试通过 `service._refresh_cache = AsyncMock()` 隔离缓存同步逻辑

## MCP 配置 CRUD 服务

提供 MCP server 配置的数据库 CRUD 操作，供 `mcp_admin_router`调用；启动时若 `mcp_server_configs` 表为空，从 YAML 种子文件导入（由 `server.py` lifespan 触发）。

### 模块位置

```
app/shared/utils/agent/mcp_service.py
```

### 核心 API

| 类 / 方法                                            | 作用                                                                                                                                                |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `McpServerConfig`                                  | MCP 服务器配置 dataclass（name、display_name、type、url、command、timeout、read_timeout、tags、enabled、progress_reporting、tool_config、sampling） |
| `McpConfigService(db)`                             | CRUD 服务构造器，参数 `db` 需支持异步 `fetch` / `fetchrow` / `execute`；初始化空缓存 `_cache` + `_cache_lock`（asyncio.Lock）              |
| `preload_all()`                                    | 预加载所有 server 配置到 `_cache`（按 created_at 排序，先清空旧缓存）；启动时由 lifespan 调用                                                       |
| `list_servers()`                                   | 列出所有 server 配置（按 created_at 排序）；优先读缓存，缓存为空时从 DB 加载并回填缓存                                                              |
| `get_server(name)`                                 | 获取单个 server 配置，不存在返回 None；优先读缓存，未命中时从 DB 加载并写入缓存                                                                     |
| `create_server(config)`                            | 新增 server；name 已存在抛 `ValueError`；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                                |
| `update_server(name, config)`                      | 更新 server；不存在抛 `ValueError`；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                                     |
| `delete_server(name)`                              | 删除 server 及关联 methods（先删 mcp_server_methods 再删 mcp_server_configs）；写 DB 后调 `_invalidate_cache(name)` 使缓存失效                       |
| `toggle_server(name, enabled)`                     | 启用/禁用 server；写 DB 后调 `_refresh_cache(name)` 同步缓存（enabled 字段变更）                                                                   |
| `list_methods(server_name)`                        | 列出 server 下所有 method（按 method_name 排序）                                                                                                    |
| `toggle_method(server_name, method_name, enabled)` | 启用/禁用单个 method                                                                                                                                |
| `upsert_methods(server_name, methods)`             | 批量 upsert method 列表并更新 methods_synced_at                                                                                                     |
| `refresh_methods_from_server(server_name)`         | 从 MCPToolsRegistry 拉取最新 method 列表并调用 upsert_methods 保存；server 不存在抛 `ValueError`                                                  |
| `seed_from_yaml_if_empty()`                        | 表为空时从 YAML 种子文件导入；非空跳过                                                                                                              |
| `_load_yaml_seed()`                                | 从 `app.core.config.config.settings.mcp.mcp_config_path` 加载 YAML；导入失败返回空 dict                                                           |
| `_refresh_cache(name)`                             | 从 DB 重新加载单个 server 到 `_cache`；DB 中不存在则从缓存移除（供写方法同步缓存）                                                                  |
| `_invalidate_cache(name)`                          | 从 `_cache` 移除单个 server（供 delete_server 失效缓存）；幂等，不访问 DB                                                                           |
| `_clear_cache()`                                   | 清空所有缓存（供测试隔离缓存状态）                                                                                                                  |

### 设计要点

- **存在性校验**：`create_server` 先调 `get_server` 检查 name 是否已存在，存在则抛 `ValueError`，避免依赖 DB 唯一约束报错
- **JSONB 字段序列化**：`command` / `tags` / `progress_reporting` / `tool_config` / `sampling` 在写入前用 `json.dumps` 序列化
- **YAML 种子容错**：`_load_yaml_seed` 捕获所有异常（如 `app.core.config.config` 或 `mcpClient.shared.config_loader` 不存在），失败时返回空 dict 并记录 warning
- **关联删除**：`delete_server` 先删子表 `mcp_server_methods` 再删主表 `mcp_server_configs`
- **缓存层（2026-06-25 新增）**：`_cache` 为 server name -> config dict 的进程内缓存，`_cache_lock`（asyncio.Lock）保护并发写。读方法（`list_servers` / `get_server`）优先读缓存，未命中回退 DB 并回填；写方法（create/update/toggle）写 DB 后调 `_refresh_cache` 重新加载，delete 调 `_invalidate_cache` 失效。读方法返回浅拷贝，外部修改不影响缓存内部状态。`preload_all` 启动时预加载，按 created_at 排序保证缓存遍历顺序与 DB 一致

### 数据库关联

- 主表：`mcp_server_configs`（见上方 "mcp_server_configs 表"）
- 子表：`mcp_server_methods`（见上方 "mcp_server_methods 表"）

### 测试

- 路径：`app/tests/shared/utils/agent/test_mcp_service.py`（35 用例）
- 覆盖：模块可导入 / list_servers 返回行 / get_server 返回单条 / create_server 写入并同步缓存（mock fetchrow 三次：存在性检查 + INSERT RETURNING + _refresh_cache）/ delete_server 删除主子表并失效缓存 / toggle_server 更新 enabled 并同步缓存 / list_methods 返回行 / toggle_method 更新 enabled / seed_from_yaml_if_empty 空表导入（mock _load_yaml_seed）/ **缓存层测试**：__init__ 缓存字段 / preload_all 预加载并清空旧缓存 / _refresh_cache 加载单个 server / _refresh_cache DB 不存在时移除 / _invalidate_cache 幂等移除且不访问 DB / _clear_cache 清空 / list_servers 缓存命中返回浅拷贝 / list_servers 缓存未命中回退 DB 并回填 / get_server 缓存命中返回浅拷贝 / get_server 缓存未命中回填 / get_server 不存在返回 None / delete_server 失效缓存

## ToolRegistryService 工具注册中心服务

从 DB `tools` 表加载工具元数据 + 动态导入工具模块获取 `@tool` 实例，提供工具的 CRUD、缓存、未注册扫描能力。供 admin router 和 AgentConfigService 使用。

### 模块位置

```
app/shared/utils/agent/tool_service.py
```

### 核心 API

| 类 / 方法                                            | 作用                                                                                                                                                |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ToolInfo`                                         | 工具信息 dataclass（name / display_name / category / description / module_path / file_path / args_schema / return_description / function_description / enabled / tool_instance） |
| `ToolNotFoundError`                                | 工具未找到时抛出                                                                                                                                    |
| `ToolAlreadyExistsError`                           | 工具名称重复时抛出                                                                                                                                  |
| `ToolRegistryService(db)`                          | 服务构造器，参数 `db` 需支持异步 `fetch` / `fetchrow` / `execute`；初始化 `_cache: Dict[str, ToolInfo]` + `_cache_lock`（asyncio.Lock，延迟创建） |
| `preload_all()`                                    | 预加载**所有**工具到缓存（含禁用项）：动态导入 `app/core/tools/` + `app/shared/tools/skills/` 下所有 .py 模块 → 从 `ToolRegistry._tools` 获取实例；**若 `@register_tool` 缺失，回退到 `module_path` 动态 `importlib + getattr` 获取 `@tool` 实例** → 关联 DB 记录 → 原子替换缓存 |
| `list_tools()`                                     | 列出所有工具（优先读缓存，缓存为空回退 DB 查询全量）；返回 dict 列表（不含 tool_instance），含禁用项                                                |
| `get_tool_by_name(name)`                           | 获取单个工具（优先读缓存，未命中查 DB 并回填）；返回 `ToolInfo`（含 tool_instance），不存在返回 None                                                |
| `get_tools_by_names(names)`                        | 批量获取工具实例列表（`@tool` 装饰的函数）；跳过不存在、tool_instance=None 或 **enabled=False** 的工具                                             |
| `create_tool(config)`                              | 注册新工具；name 已存在抛 `ToolAlreadyExistsError`；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                     |
| `update_tool(name, config)`                        | 更新工具全量字段；不存在抛 `ToolNotFoundError`；写 DB 后调 `_refresh_cache(name)` 同步缓存                                                         |
| `delete_tool(name)`                                | 删除工具；不存在抛 `ToolNotFoundError`；写 DB 后调 `_invalidate_cache(name)` 失效缓存                                                              |
| `set_tool_enabled(name, enabled)`                  | 启用/禁用工具；不存在抛 `ToolNotFoundError`；写 DB 后调 `_refresh_cache(name)` 同步缓存（enabled=FALSE 时仍保留在缓存中）                           |
| `scan_unregistered()`                              | 用 ast.parse 扫描 `app/core/tools/` + `app/shared/tools/skills/` 下 .py 文件，找出 `@tool` 装饰函数，与 DB 已注册名对比，返回未注册列表            |
| `_refresh_cache(name)`                             | 从 DB 重新加载单个工具到缓存；DB 不存在时从缓存移除，存在时无论 enabled 状态均写入缓存                                                              |
| `_invalidate_cache(name)`                          | 从缓存移除单个工具（幂等，不访问 DB）                                                                                                                |
| `_clear_cache()`                                   | 清空所有缓存（供测试用）                                                                                                                            |

### 设计要点

- **缓存存储全部工具（含禁用项）**：`preload_all` 从 DB 读取所有 tools 记录，确保缓存是 DB 完整镜像；运行时调用方（`get_tools_by_names` / `agent_config_service._load_tools`）按需过滤 `enabled=True`
- **tool_instance 双源获取**：`preload_all` 先从 `ToolRegistry._tools`（`@register_tool` 注册表）获取实例；若缺失（纯 `@tool` 未加 `@register_tool` 的场景），回退到 `_get_tool_instance_from_module(module_path, name)` 通过 `importlib.import_module + getattr` 动态获取 `@tool` 实例，补偿内置工具加载
- **动态导入触发装饰器**：`preload_all` 先 `importlib.import_module` 所有工具模块，触发 `@register_tool` + `@tool` 装饰器执行，再从 `ToolRegistry.list_all()` 获取实例；`@register_tool` 缺失时由模块动态导入兜底
- **ast 扫描识别 @tool**：`scan_unregistered` 用 `ast.parse` 解析源码，支持 `@tool` / `@tool(...)` / `@langchain.tools.tool(...)` 三种装饰器形式；提取参数签名时排除 `runtime` / `self` / `cls` 框架注入参数
- **JSONB 防御性反序列化**：`args_schema` 字段用 `_decode_jsonb` 兼容 asyncpg 未注册 codec（str → json.loads）和已注册 codec（dict 原样返回）两种场景
- **asyncio.Lock 延迟创建**：`_cache_lock` 在首次 `_ensure_lock()` 调用时创建，避免无事件循环时报错，兼容 `asyncio.run()` 测试场景
- **模块导入失败不中断**：`_import_tool_modules` 对每个模块 try/except，失败记录 warning 继续导入下一个
- **项目根路径计算**：`_PROJECT_ROOT = Path(__file__).resolve().parents[4]`（tool_service.py → app/shared/utils/agent/ → 项目根）

### 工具源码根目录

| 目录                          | 内容                                                |
| ----------------------------- | --------------------------------------------------- |
| `app/core/tools/`             | 基础工具（BaseTools.py / SandboxTools.py / MCP 适配器等） |
| `app/shared/tools/skills/`    | 按 agent 维度组织的工具模块（map_agent/MapTools.py 等）  |

### 数据库关联

- 主表：`tools`（字段：id / name / display_name / category / description / module_path / file_path / args_schema / return_description / function_description / enabled / sort_order / created_at / updated_at）
- 关联：`ToolRegistry._tools`（`app/shared/tools/registry.py`）按 name 关联 DB 记录与运行时工具实例

### 测试

- 路径：`app/tests/shared/utils/agent/test_tool_service.py`（53 用例）
- 覆盖：模块可导入 / ToolInfo 字段 / 常量正确性 / _decode_jsonb（None/str/dict/invalid）/ _decode_row / _build_tool_info（有注册实例 / 无注册实例 / **module_path 回退获取 @tool 实例**）/ _get_tool_instance_from_module（模块不存在 / 属性不存在）/ list_tools（缓存命中/回退 DB）/ get_tool_by_name（缓存命中/未命中回填/不存在）/ get_tools_by_names（返回实例/跳过缺失和未注册）/ create_tool（写入+刷新缓存/重复抛异常/缺 name 抛 KeyError）/ update_tool（更新+刷新/不存在抛异常）/ delete_tool（删除+失效缓存/不存在抛异常）/ set_tool_enabled（更新+刷新/不存在抛异常）/ _has_tool_decorator（@tool/@tool(...)/@xxx.tool(...)/非@tool/无装饰器）/ _extract_args_schema（排除框架参数/含默认值/无注解用 Any）/ _extract_return_description（有/无注解）/ _scan_file_for_tools（扫描 BaseTools.py 找到 5 个 @tool / 排除 runtime）/ scan_unregistered（返回未注册工具）/ _refresh_cache（加载启用/移除禁用/移除缺失）/ _invalidate_cache（移除/幂等）/ _clear_cache / preload_all（加载启用工具/跳过禁用/调用 _import_tool_modules）/ _tool_info_to_dict（排除 tool_instance）

## 三层缓存架构

Agent 运行时配置加载采用四层进程内缓存架构，由四个独立 service 各自维护缓存，启动时由 `app/core/server.py::lifespan` 统一预加载，写操作后同步刷新或失效缓存，避免每次请求都查 DB。

### 缓存层级

| 层级 | Service | 缓存对象 | 缓存键 | 缓存字段 |
| ---- | ------- | -------- | ------ | -------- |
| 1 | `AgentConfigService` | `UnifiedAgentConfig`（含 tools 列表） | `agent_name` | `_cache: Dict[str, UnifiedAgentConfig]` + `_default_config` |
| 2 | `McpConfigService` | MCP server 配置字典 | server `name` | `_cache: Dict[str, dict]` |
| 3 | `ToolRegistryService` | 内置工具实例 + 元数据（`ToolInfo`） | tool `name` | `_cache: Dict[str, ToolInfo]` |
| 4 | `SkillRegistryService` | skill 元数据（`SkillRow`） | skill `name` | `_cache: Dict[str, SkillRow]` |

### 启动预加载

`lifespan` 按顺序调用四个 service 的 `preload_all()`：
1. `McpConfigService.preload_all()` — 预加载所有 MCP server 配置
2. `ToolRegistryService.preload_all()` — 动态导入工具模块触发 `@register_tool` + `@tool` 装饰器，从 `ToolRegistry._tools` 获取实例并关联 DB 记录，缓存**全部** tools 记录（含禁用项）
3. `SkillRegistryService.preload_all()` — 从 DB `skills` 表读取所有 skill 记录，构造 `SkillRow` 后缓存**全部** skills 记录（含禁用项）
4. `AgentConfigService.preload_all()` — 预加载所有启用 agent 配置到 `_cache`（`tools=None` 延迟加载），并注入 `ToolRegistryService` / `MCPToolsRegistry` 依赖供后续工具加载

### 缓存刷新策略

- **写 DB 后同步刷新缓存**：所有 service 的写方法（create / update / delete / toggle / bind 等）写 DB 后立即调 `_refresh_cache(name)` 重新加载该条目到缓存，或调 `_invalidate_cache(name)` 从缓存移除
- **MCP 变更级联失效**：MCP server 配置变更（create / update / delete / toggle）后，`mcp_admin_router` 调用 `AgentConfigService.invalidate_all_cache()` 清空全部 agent 缓存（MCP 变更可能影响所有 agent 的工具列表）
- **工具变更级联失效**：工具注册/更新/删除/启停后，`tool_admin_router` 调用 `AgentConfigService.invalidate_all_cache()` 清空全部 agent 缓存（工具变更影响 agent 工具列表）
- **skill 变更级联失效**：skill 注册/更新/删除/启停后，`skill_admin_router` 调用 `AgentConfigService.invalidate_all_cache()` 清空全部 agent 缓存（skill 变更影响 agent 可用 skill 列表）

### 工具延迟加载（保持 MCP 懒加载）

- `AgentConfigService.preload_all` 预加载 agent 配置时 `tools=None`（未加载）
- 首次 `get_agent_config` 命中缓存但 `tools=None` 时，用 `_tools_lock` 保护触发 `_load_tools`（double-check 模式防止并发重复加载）
- `_load_tools` 优先从 `tool_bindings` JSONB 加载（builtin 走 `ToolRegistryService`，mcp 走 `MCPToolsRegistry`）；`tool_bindings` 为空时回退到 `mcp_tags` 过滤 MCP 工具
- `tools=[]` 表示已加载但无工具绑定；`tools=None` 表示尚未加载

## MCP Admin Router

提供 MCP server 配置的 HTTP API，前缀 `/api/admin/mcp`，在 `app/main.py::register_routers` 中注册。调用 `McpConfigService`执行数据库操作，通过 `request.app.state.mcp_config_service` 获取服务实例（lifespan 集成）。

### 模块位置

```
app/routers/
├── __init__.py              # 空包初始化
└── mcp_admin_router.py      # MCP Admin 路由
```

### 路由清单

| 方法   | 路径                                                      | 状态码 | 说明                                             |
| ------ | --------------------------------------------------------- | ------ | ------------------------------------------------ |
| GET    | `/api/admin/mcp/servers`                                | 200    | 列出所有 MCP server 配置                         |
| POST   | `/api/admin/mcp/servers`                                | 201    | 新增 server；name 已存在返回 409                 |
| PUT    | `/api/admin/mcp/servers/{name}`                         | 200    | 更新 server 配置；不存在返回 404                 |
| DELETE | `/api/admin/mcp/servers/{name}`                         | 204    | 删除 server 及关联 methods                       |
| POST   | `/api/admin/mcp/servers/{name}/toggle`                  | 200    | 启用/禁用 server（query 参数 `enabled`）       |
| GET    | `/api/admin/mcp/servers/{name}/methods`                 | 200    | 列出 server 下所有 method                        |
| POST   | `/api/admin/mcp/servers/{name}/refresh-methods`         | 200    | 从 MCP server 拉取最新 method 列表；失败返回 502 |
| POST   | `/api/admin/mcp/servers/{name}/methods/{method}/toggle` | 200    | 启用/禁用单个 method（query 参数 `enabled`）   |

### 设计要点

- **服务获取**：`_get_service(request)` 从 `app.state.mcp_config_service` 获取 `McpConfigService` 实例；未初始化时抛 500
- **Registry 同步**：4 个写端点（create / update / delete / toggle）DB 操作后通过 `_get_registry(request)` 获取 `MCPToolsRegistry` 并调用对应方法（add_server / update_server / remove_server / toggle_server）热更新，registry 调用失败仅 warning 不阻断
- **缓存失效**：4 个写端点在 registry 同步后调用 `_invalidate_agent_config_cache(request)` 清空 `AgentConfigService` 全部缓存（MCP 变更影响 agent 工具列表）；服务未初始化时静默跳过
- **错误映射**：`ValueError` → 409（create，name 冲突）/ 404（update，不存在）；`refresh_methods` 失败 → 502
- **refresh_methods_from_server**：`McpConfigService` 新增方法，通过 `MCPToolsRegistry.get_tools_with_server(server=name)` 获取已注册工具列表，转换为 method 记录后调用 `upsert_methods` 保存

### 测试

- 路径：`app/tests/routers/test_mcp_admin_router.py`（22 用例）
- 本地 conftest：`app/tests/routers/conftest.py`（mock `filesystem_encoding_fix.apply_fix` 为 no-op + 注入 `mcp_config_service` 实例）
- 覆盖：模块可导入 / 7 个路由注册检查 / list_servers 返回 200 / create_server 返回 201 / delete_server 返回 204 / toggle_server 返回 200 / 4 个写端点 registry 同步 / _build_config_dict 字段 / _invalidate_agent_config_cache 辅助函数可导入 / 4 个写端点缓存失效 / service 缺失时降级

## Tool Admin Router

提供工具注册中心（ToolRegistryService）的 HTTP API，前缀 `/api/admin/tools`，在 `app/main.py::register_routers` 中注册。所有端点通过 `Depends(require_admin)` 进行 admin 权限校验（router 级别）。调用 `ToolRegistryService` 执行 DB 操作与缓存管理，通过 `request.app.state.tool_service` 获取服务实例（lifespan 集成）。

### 模块位置

```
app/routers/
├── __init__.py              # 空包初始化
├── mcp_admin_router.py      # MCP Admin 路由
├── agent_admin_router.py    # Agent Admin 路由
└── tool_admin_router.py     # Tool Admin 路由
```

### 路由清单

| 方法   | 路径                                    | 状态码 | 说明                                                       |
| ------ | --------------------------------------- | ------ | ---------------------------------------------------------- |
| GET    | `/api/admin/tools`                    | 200    | 列出所有已注册工具（优先读缓存，缓存为空回退 DB 全量）     |
| GET    | `/api/admin/tools/unregistered`       | 200    | 列出未注册工具文件（ast 扫描源码目录）                     |
| POST   | `/api/admin/tools`                    | 201    | 注册新工具；name 已存在返回 409；缺必填字段返回 422        |
| PUT    | `/api/admin/tools/{name}`             | 200    | 更新工具配置；不存在返回 404                               |
| DELETE | `/api/admin/tools/{name}`             | 204    | 删除工具；不存在返回 404                                   |
| PUT    | `/api/admin/tools/{name}/enabled`     | 200    | 启用/禁用工具（请求体 `{"enabled": bool}`）；不存在返回 404 |
| POST   | `/api/admin/tools/scan`               | 200    | 扫描未注册工具文件（与 GET /unregistered 功能相同，POST 语义） |

### 请求体模型

| 模型                  | 字段                                                                                                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ToolCreateRequest`   | name（必填）/ display_name / category（必填）/ description / module_path（必填）/ file_path（必填）/ args_schema / return_description / function_description / enabled（默认 True）/ sort_order（默认 0） |
| `ToolUpdateRequest`   | display_name / category / description / args_schema / return_description / function_description / enabled / sort_order（全部 Optional，exclude_none=True 后传给 service；未传入字段保持数据库原值）                          |
| `ToolEnabledRequest`  | enabled（bool，必填）                                                                                                                                                                              |

### 设计要点

- **权限校验**：router 级别 `dependencies=[Depends(require_admin)]`，非 admin 用户返回 403（与 agent_admin_router 模式一致）
- **服务获取**：`_get_service(request)` 从 `app.state.tool_service` 获取 `ToolRegistryService` 实例；未初始化时抛 500
- **错误映射**：`ToolNotFoundError` → 404；`ToolAlreadyExistsError` → 409；`KeyError` / `ValueError` → 400；其他 → 500
- **update_tool 语义**：`ToolUpdateRequest` 用 `exclude_none=True` 序列化，仅传非 None 字段；service 层 `update_tool` 先查出现有记录，再将传入字段覆盖到原记录上执行 UPDATE（部分更新语义，未传入字段保持数据库原值）
- **scan 与 unregistered**：`POST /scan` 与 `GET /unregistered` 功能相同，均调用 `scan_unregistered()`；POST 语义供前端「主动触发扫描」按钮使用
- **生产对等初始化**：`app.state.tool_service` 由 `app/core/server.py::lifespan` 构造（db_pool 存在时），单独 try/except 包裹，失败不阻断后续逻辑

### 测试

- 路径：`app/tests/routers/test_tool_admin_router.py`（29 用例 = 25 原有 + 4 热加载新增：create/update/delete/set_tool_enabled 后 `agent_config_service.invalidate_all_cache` 被调）
- 本地 conftest：`app/tests/routers/conftest.py::_init_tool_service` autouse fixture 注入 `ToolRegistryService(db=None)` 实例（生产对等初始化点：`app/core/server.py::lifespan` 第 122-131 行）
- 覆盖：模块可导入 / 7 个路由注册检查 / list_tools 返回 200 / list_unregistered 返回 200 / create_tool 返回 201 / update_tool 返回 200 / delete_tool 返回 204 / set_tool_enabled 返回 200 / scan 返回 200 / create_tool 冲突返回 409 / update_tool 不存在返回 404 / delete_tool 不存在返回 404 / set_tool_enabled 不存在返回 404 / 非 admin 访问返回 403（3 个端点）/ service 未初始化返回 500（2 个端点）/ 缺必填字段返回 422 / **4 个写操作后 agent_config 缓存失效验证**

## Skill Admin Router

提供 skill 注册中心（SkillRegistryService）的 HTTP API，前缀 `/api/admin/skills`，在 `app/main.py::register_routers` 中注册。所有端点通过 `Depends(require_admin)` 进行 admin 权限校验（router 级别）。调用 `SkillRegistryService` 执行 DB 操作与缓存管理，通过 `request.app.state.skill_service` 获取服务实例。

### 模块位置

```
app/routers/
├── __init__.py              # 空包初始化
├── mcp_admin_router.py      # MCP Admin 路由
├── agent_admin_router.py    # Agent Admin 路由
├── tool_admin_router.py     # Tool Admin 路由
└── skill_admin_router.py    # Skill Admin 路由
```

### 路由清单

| 方法   | 路径                                    | 状态码 | 说明                                                       |
| ------ | --------------------------------------- | ------ | ---------------------------------------------------------- |
| GET    | `/api/admin/skills`                    | 200    | 列出所有已注册 skill（优先读缓存，缓存为空回退 DB 全量）   |
| GET    | `/api/admin/skills/unregistered`       | 200    | 列出未注册 skill 文件（扫描 SKILL.md）                     |
| POST   | `/api/admin/skills`                    | 201    | 注册新 skill；name 已存在返回 409；缺必填字段返回 422      |
| PUT    | `/api/admin/skills/{name}`             | 200    | 更新 skill 配置；不存在返回 404                            |
| DELETE | `/api/admin/skills/{name}`             | 204    | 删除 skill；不存在返回 404                                 |
| PUT    | `/api/admin/skills/{name}/enabled`     | 200    | 启用/禁用 skill（请求体 `{"enabled": bool}`）；不存在返回 404 |
| POST   | `/api/admin/skills/scan`               | 200    | 扫描未注册 skill 文件（与 GET /unregistered 功能相同，POST 语义） |

### 请求体模型

| 模型                  | 字段                                                                                                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SkillCreateRequest`  | name（必填）/ display_name / category（必填）/ description / location / base_dir / content / enabled（默认 True）/ sort_order（默认 0）                                                          |
| `SkillUpdateRequest`  | display_name / category / description / location / base_dir / content / enabled / sort_order（全部 Optional，exclude_none=True 后传给 service；未传入字段保持数据库原值）                |
| `SkillEnabledRequest` | enabled（bool，必填）                                                                                                                                                                              |

### 设计要点

- **权限校验**：router 级别 `dependencies=[Depends(require_admin)]`，非 admin 用户返回 403
- **服务获取**：`_get_service(request)` 从 `app.state.skill_service` 获取 `SkillRegistryService` 实例；未初始化时抛 500
- **错误映射**：`SkillNotFoundError` → 404；`SkillAlreadyExistsError` → 409；`KeyError` / `ValueError` → 400；其他 → 500
- **update_skill 语义**：`SkillUpdateRequest` 用 `exclude_none=True` 序列化，仅传非 None 字段；service 层 `update_skill` 先查出现有记录，再将传入字段覆盖到原记录上执行 UPDATE（部分更新语义，未传入字段保持数据库原值）
- **scan 与 unregistered**：`POST /scan` 与 `GET /unregistered` 功能相同，均调用 `scan_unregistered()`；POST 语义供前端「主动触发扫描」按钮使用
- **缓存失效**：create / update / delete / set_skill_enabled 四个写操作后调用 `_invalidate_agent_config_cache(request)`，清空 `AgentConfigService` 全部缓存（skill 变更影响 agent 可用 skill 列表）
- **生产对等初始化**：`app.state.skill_service` 由 `app/core/server.py::lifespan` 构造（db_pool 存在时），单独 try/except 包裹，失败不阻断后续逻辑

### 测试

- 路径：`app/tests/routers/test_skill_admin_router.py`（1 用例：模块可导入 / router 实例存在）

## 统一 Agent Router

提供统一 Agent HTTP API，前缀 `/api/agent`，在 `app/main.py::register_routers` 中注册。调用 `AgentConfigService`加载配置，通过 `Agent`（`app/core/agent/agent.py`）执行流式对话。SSE 流式逻辑提取到 `_stream_helper.py` 供复用。

### 模块位置

```
app/routers/
├── __init__.py              # 空包初始化
├── mcp_admin_router.py      # MCP Admin 路由
├── agent_router.py          # 统一 Agent 路由
└── _stream_helper.py        # SSE 流式响应辅助
```

### 路由清单

| 方法 | 路径                                  | 状态码 | 说明                                                              |
| ---- | ------------------------------------- | ------ | ----------------------------------------------------------------- |
| POST | `/api/agent/chat`                   | 200    | 统一聊天接口（SSE 流式响应）；agent 不存在返回 404                |
| GET  | `/api/agent/list`                   | 200    | 列出所有启用的智能体                                              |
| GET  | `/api/agent/{agent_name}/agents-md` | 200    | 获取指定 agent 的 AGENTS.md 内容（system_prompt）；不存在返回 404 |

### 设计要点

- **服务获取**：`_get_service(request)` 从 `app.state.agent_config_service` 获取 `AgentConfigService` 实例；未初始化时抛 500（与 mcp_admin_router 模式一致）
- **SSE 复用**：`_stream_helper.generate_stream_response` 完整迁移自 map_router.py，保留全部 SSE 处理逻辑：ContextVar 挂载/清理（子智能体停止信号）、精确延迟中断（disconnect 标记 + tools 节点完成时真正断开）、HITL 中断检测（多模式兼容）+ `_extract_interrupt_requests`、updates/custom/messages 三种 stream_mode 差异化处理、thread_id/langgraph_node 透传、`stream_format_context.format_message` 格式化；统一签名 `(agent, input_state, context, session_id, request)`，供 agent_router 与 map_router knowledge-chat 复用
- **SSE 响应头**：`StreamingResponse` 显式设置 `Cache-Control: no-cache` / `Connection: keep-alive` / `X-Accel-Buffering: no`，防止 Nginx 等反向代理缓冲 SSE 流
- **ChatRequest 模型**：Pydantic BaseModel，字段含 message / session_id / **agent_name（`Optional[str] = None`，为空时由后端使用框架默认配置）** / attachments（暂未实现，预留字段）/ resume（HITL 恢复）/ context_overrides
- **默认智能体**：`agent_name` 为 `None` 或空字符串时，`AgentConfigService.get_agent_config` 返回默认 `UnifiedAgentConfig`，使用 `AgentState` / `AgentContext` 基类、`system_prompt=""`（Agent 内部拼接 `BASE_SYSTEM_PROMPT`），不绑定任何工具或 skill；配置获取统一收敛到 service 层，路由层无独立 else 默认分支
- **context_overrides 过滤**：构造 context 实例前过滤 `RESERVED_CONTEXT_FIELDS`（session_id / store_id / namespace 等），避免与显式传入的 session_id 关键字参数冲突（TypeError: got multiple values for keyword argument）
- **context_overrides 空值过滤（2026-06-30 新增）**：router 在合并 `context_overrides` 到 `merged_overrides` 时，自动过滤 `None / "" / [] / {}` 等容器型空值键，避免覆盖 agent context_class 字段默认值（如 `MapAgentContext.geometry_data = {}`）。设计为**通用机制**，不针对任何具体 agent 或字段硬编码键名 —— 任意子智能体的 context 扩展字段（如 map_agent 的 `geometry_data`、audit_document_agent 的 `audit_root`）都能通过 `context_overrides` 注入；仅当值"实际为空"时才过滤。注：bool `False` / 数字 `0` 不在过滤范围（避免误杀业务 bool/int 字段）。前端契约：子智能体特有字段（如 `geometry_data`）应通过 `context_overrides.geometry_data` 传递，而非提升为顶层字段。
- **Agent 构造**：chat 端点从 `UnifiedAgentConfig` 提取 name / system_prompt / state_class / context_class / **tools** 构造 `AgentConfig`（`tools=config.tools` 由 AgentConfigService 从 DB + MCP registry 加载），并通过 `get_async_checkpointer()` 注入全局 checkpointer（支持 resume 与多轮对话状态持久化），实例化 `Agent` 并调用 `await agent.__ainit__()` 完成异步初始化；初始化过程包裹 try/except，失败时抛 500
- **输入状态**：resume 存在时构造 `Command(resume=...)`，否则构造 `state_class(messages=[HumanMessage(...)])`
- **Session 中间件**：`/api/agent/` 前缀在 `SESSION_REQUIRED_PREFIXES` 中，所有端点需 `X-Session-ID` 头并通过 `session_cache.verify_session` 校验
- **错误映射**：`AgentNotFoundError` → 404；Agent 初始化异常 → 500

## Agent Admin Router

提供智能体的完整 CRUD + config_schema 三层结构管理 API，前缀 `/api/admin/agents`，admin 权限（复用 `require_admin`）。在 `app/main.py::register_routers` 中注册。

### 端点清单

| 方法   | 路径                                             | 状态码 | 说明                                                                     |
| ------ | ------------------------------------------------ | ------ | ------------------------------------------------------------------------ |
| GET    | `/api/admin/agents`                            | 200    | 列出所有 agent（含 config_schema 完整数据）                              |
| GET    | `/api/admin/agents/check-name?name=xxx`        | 200    | name 唯一性预校验（返回 `{available: bool}`）                          |
| POST   | `/api/admin/agents/validate-md-path`           | 200    | 校验 AGENTS.md 路径是否存在                                              |
| GET    | `/api/admin/agents/field-templates?section=`   | 200    | 获取字段模板列表；section=`root` 返回 AgentConfig 模板，`state_fields` 返回 AgentState 模板，`context_fields` 返回 AgentContext 模板（前端新增字段时下拉选择） |
| GET    | `/api/admin/agents/{name}`                     | 200    | 获取单个 agent 完整配置（含 agent_config_overrides 拆分结果）            |
| POST   | `/api/admin/agents`                            | 201    | 新增智能体；name 已存在返回 409；AGENTS.md 不存在返回 400                |
| DELETE | `/api/admin/agents/{name}`                     | 204    | 删除智能体（级联清理 agent_tool_bindings 关联；skill 绑定走 agents.skill_bindings JSONB 字段，无独立表） |
| PUT    | `/api/admin/agents/{name}`                     | 200    | 更新智能体基本信息（body:`{display_name, description}`）                 |
| PUT    | `/api/admin/agents/{name}/enabled`             | 200    | 启用 / 禁用单个智能体（body:`{enabled: bool}`）                        |
| PUT    | `/api/admin/agents/{name}/config-schema`       | 200    | 全量替换 config_schema                                                   |
| POST   | `/api/admin/agents/{name}/config-schema/field` | 200    | 增量添加字段（body:`{section, field_name, field_def}`）                |
| PUT    | `/api/admin/agents/{name}/config-schema/field` | 200    | 直接覆盖已存在字段（body:`{section, field_name, field_def}`）          |
| DELETE | `/api/admin/agents/{name}/config-schema/field` | 200    | 增量删除字段（query:`section + field_name`）；字段不存在时幂等返回 200 |
| GET    | `/api/admin/agents/{name}/tool-bindings`       | 200    | 获取工具绑定列表（返回 `{agent_name, tool_bindings: List}`）；agent 不存在返回 404 |
| PUT    | `/api/admin/agents/{name}/tool-bindings`       | 200    | 全量替换工具绑定列表（body:`{bindings: List<ToolBindingItem>}`）；agent 不存在返回 404 |
| GET    | `/api/admin/agents/{name}/available-tools`     | 200    | 获取该 agent 可绑定的工具列表（内置 + MCP）；返回 `{agent_name, builtin: [...], mcp: [...]}`。MCP 项的 `tool_name` 为 `server.method` 复合名（用于保存到 tool_bindings） |
| GET    | `/api/admin/agents/{name}/skill-bindings`      | 200    | 获取 skill 绑定列表（返回 `{agent_name, skill_bindings: List}`）；agent 不存在返回 404 |
| PUT    | `/api/admin/agents/{name}/skill-bindings`      | 200    | 全量替换 skill 绑定列表（body:`{bindings: List<SkillBindingItem>}`）；agent 不存在返回 404 |
| GET    | `/api/admin/agents/{name}/available-skills`    | 200    | 获取该 agent 可绑定的 skill 列表；返回 `{agent_name, skills: [{name, display_name, category, description}]}` |

**section 取值**：`root`（顶层 AgentConfig 字段）/ `state_fields`（state 扩展字段）/ `context_fields`（context 扩展字段）

### 设计要点

- **保留字段校验**：`config_schema` 顶层不能包含 `state_class` / `context_class` / `checkpointer` / `store`（运行时对象），由 `service.update_agent_config_schema` 和 `create_agent` 在写库前校验
- **name 唯一性**：DB UNIQUE 约束 + service 层预检 + admin API 409 Conflict 响应
- **AGENTS.md 路径**：必须在 service 层 `Path.is_file()` 校验失败返回 400（防止脏数据写入）
- **field_def 校验**：必须包含 `type` 键，type 必须在 `TYPE_MAP` 支持的类型中（`str`/`int`/`float`/`bool`/`dict`/`list`）
- **错误映射**：`_handle_agent_error` 统一转换 service 异常（AgentAlreadyExistsError → 409 / AgentNotFoundError → 404 / ValueError → 400 / FileNotFoundError → 400 / KeyError → 400）
- **Pydantic 模型**：`CreateAgentRequest` 强制 name 格式 `[a-z0-9_]{3,50}` / `display_name` 1-200 字符 / `field_name` Python 标识符格式；`UpdateAgentRequest` 含 `display_name`（必填，1-200 字符）和 `description`（可选，max_length=500）；`AddFieldRequest.section` 自由字符串（由 service 校验）；`SetEnabledRequest.enabled` bool；`ToolBindingItem`（tool_name 必填 / tool_type 默认 "builtin" / enabled 默认 True / sort_order 默认 0）；`ToolBindingsRequest.bindings` List[ToolBindingItem]；`SkillBindingItem`（skill_name 必填 / enabled 默认 True / sort_order 默认 0）；`SkillBindingsRequest.bindings` List[SkillBindingItem]
- **测试**：`app/tests/routers/test_agent_admin_router.py` 46 用例（原 35 + skill-bindings 4 用例 + available-skills 2 用例 + 路由注册 1 用例更新）；`app/tests/routers/conftest.py` 新增 `_init_db`（注入 `app.state.db` MagicMock）和 `_mock_user_db_for_admin_auth`（根据 username 返回 role）两个 autouse fixture












### 测试

- 路径：`app/tests/routers/test_agent_router.py`（10 用例）
- 本地 conftest：`app/tests/routers/conftest.py` 追加 `_init_agent_config_service`（注入 `AgentConfigService(db=None, agents_md_loader=AgentsMdLoader())`）+ `_mock_session_cache_for_agent`（mock `session_cache.verify_session` 返回 True）两个 autouse fixture
- 覆盖：模块可导入 / 3 个路由注册检查 / list_agents 返回 200 / get_agents_md 返回 content / chat 传入 tools=config.tools / chat tools=None 不报错
- 测试通过 monkeypatch 替换 `AgentConfigService.list_agents` / `get_agent_config`，HTTP 请求带 `X-Session-ID` 头绕过 Session 校验

## MCPToolsRegistry 运行时管理增强

为 `MCPToolsRegistry`（`app/core/tools/mcp_registry.py`）新增 5 个异步方法，支持运行时动态管理 MCP server 配置，无需重启应用。供 `mcp_admin_router`及 `McpConfigService.refresh_methods_from_server` 调用。

### 模块位置

```
app/core/tools/mcp_registry.py
```

### 核心 API

| 方法                                                 | 作用                                                                                                |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `add_server(name, config)`                         | 运行时新增 server 配置；存入 `_server_configs`，客户端已初始化时尝试连接，失败仅 warning          |
| `update_server(name, config)`                      | 更新 server 配置；覆盖旧配置，客户端已初始化时先 remove 再 add 重建连接                             |
| `remove_server(name)`                              | 移除 server；从 `_server_configs` 删除配置并断开连接，配置不存在静默忽略                          |
| `toggle_server(name, enabled)`                     | 启用/禁用 server；更新 `_server_configs[name]["enabled"]` 字段                                    |
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


## 前端 MCP 管理 API 封装

在 `web/Agent/src/utils/api.js` 末尾追加 9 个导出函数，对应后端 `mcp_admin_router`的 8 个端点 + Agent 列表端点。所有函数复用已有的 `fetchWithAuth` 包装器（自动注入 `Authorization: Bearer` 与 `X-Session-ID`，401 自动重试）。

### 模块位置

```
web/Agent/src/utils/
├── api.js                              # 追加 9 个 MCP/Agent API 函数
└── __tests__/
    └── api.mcp.test.js                 # MCP API 测试（8 用例）
```

### 函数清单

| 函数                                             | HTTP 方法 | 路径                                                                     | 说明                                     |
| ------------------------------------------------ | --------- | ------------------------------------------------------------------------ | ---------------------------------------- |
| `listMcpServers()`                             | GET       | `/api/admin/mcp/servers`                                               | 列出所有 MCP server 配置                 |
| `createMcpServer(config)`                      | POST      | `/api/admin/mcp/servers`                                               | 新增 server；body 为 JSON 配置           |
| `updateMcpServer(name, config)`                | PUT       | `/api/admin/mcp/servers/{name}`                                        | 更新 server 配置                         |
| `deleteMcpServer(name)`                        | DELETE    | `/api/admin/mcp/servers/{name}`                                        | 删除 server；无返回值                    |
| `toggleMcpServer(name, enabled)`               | POST      | `/api/admin/mcp/servers/{name}/toggle?enabled={bool}`                  | 启用/禁用 server                         |
| `listMcpMethods(name)`                         | GET       | `/api/admin/mcp/servers/{name}/methods`                                | 列出 server 下所有 method                |
| `refreshMcpMethods(name)`                      | POST      | `/api/admin/mcp/servers/{name}/refresh-methods`                        | 刷新 method 列表                         |
| `toggleMcpMethod(serverName, method, enabled)` | POST      | `/api/admin/mcp/servers/{name}/methods/{method}/toggle?enabled={bool}` | 启用/禁用单个 method                     |
| `fetchAgentList()`                             | GET       | `/api/agent/list`                                                      | 获取可用 Agent 列表（供 MCP 配置页绑定） |

### 设计要点

- **复用 fetchWithAuth**：所有函数通过 `fetchWithAuth` 发起请求，自动处理鉴权与 401 重试，无需重复实现
- **URL 编码**：`name` / `method` 路径参数使用 `encodeURIComponent` 编码，防止特殊字符破坏 URL
- **错误处理**：`createMcpServer` 解析后端 `detail` 字段抛出具体错误信息；其余函数抛 `HTTP {status}` 通用错误
- **deleteMcpServer**：唯一无返回值的函数（204 No Content），不调用 `response.json()`

### 测试

- 路径：`web/Agent/src/utils/__tests__/api.mcp.test.js`（8 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，通过动态 `import('../api.js')` 使 mock 生效
- 覆盖：listMcpServers URL + 返回值 / createMcpServer body / deleteMcpServer DELETE 方法 / toggleMcpServer enabled 参数 / listMcpMethods URL / refreshMcpMethods POST / toggleMcpMethod enabled 参数 / fetchAgentList URL + 返回值

## 前端 MCP 服务器管理组件

创建 `McpServerManager.vue` 组件，基于  的 8 个 MCP API 函数实现 MCP 服务器的可视化管理界面。

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

- 复用  的 `api.js` 中 8 个 MCP 函数（listMcpServers/createMcpServer/updateMcpServer/deleteMcpServer/toggleMcpServer/listMcpMethods/refreshMcpMethods/toggleMcpMethod）
- 使用 Vue 3 `<script setup>` 语法，`onMounted` 时自动加载服务器列表

### 测试

- 路径：`web/Agent/src/components/__tests__/McpServerManager.spec.js`（6 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，使用 `mount` + `flushPromises` 模式
- 覆盖：组件可导入 / 渲染服务器列表 / 点击服务器项选中 / 点击新增按钮显示表单 / 选中后显示刷新方法按钮 / 空状态提示

## 前端 UserSettingsDialog MCP 管理 Tab 集成

将  的 `McpServerManager.vue` 组件集成到 `UserSettingsDialog.vue` 的 admin Tab 中，让管理员可以在用户设置对话框中管理 MCP 服务器。

### 修改要点

- **import**：在 `UserSettingsDialog.vue` 顶部新增 `import McpServerManager from './McpServerManager.vue'`
- **navItems**：在 admin 分支的 `session-query` 之后追加 `{ id: 'mcp-management', label: 'MCP 管理', icon: '...' }`
- **template**：在 session-query 的 `v-show` div 之后平级追加 `<div v-show="activeTab === 'mcp-management'" class="tab-content mcp-tab-content"><McpServerManager /></div>`，遵循现有 `v-show` 模式（非 `v-else-if`）

### 测试

- 路径：`web/Agent/src/components/__tests__/UserSettingsDialog.mcp.spec.js`（3 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`；因 `UserSettingsDialog` 使用 `<Teleport to="body">`，nav-item 与 tab 内容渲染到 `document.body`，需通过 `document.body.querySelectorAll` / `document.body.querySelector` 查询元素（`wrapper.findAll` / `wrapper.find` 无法穿透 Teleport）
- 覆盖：admin 角色显示 MCP 管理 Tab / 普通用户不显示 MCP 管理 Tab / 点击 MCP Tab 后渲染 `.mcp-server-manager` 组件

## 前端斜杠命令注册表

新建 `web/Agent/src/utils/commandRegistry.js` 作为前端斜杠命令的统一注册表与分发器。`InputBox.vue` 检测到 `/` 开头输入时调用 `handleCommand`。

### 模块位置

```
web/Agent/src/utils/
├── commandRegistry.js                 # 命令注册表 + handleCommand 分发器
└── __tests__/
    └── commandRegistry.test.js        # 测试（9 用例）
```

### 命令清单

| 命令              | 用法                 | 说明                                           | requiresBackend |
| ----------------- | -------------------- | ---------------------------------------------- | --------------- |
| `/agent <name>` | `/agent map_agent` | 切换当前会话使用的智能体；找不到时返回可用列表 | true            |
| `/agents`       | `/agents`          | 列出所有可用智能体（调用 `fetchAgentList`）  | true            |

### 导出 API

| 导出                             | 作用                                                                             |
| -------------------------------- | -------------------------------------------------------------------------------- |
| `COMMAND_REGISTRY`             | 命令元数据数组，供 InputBox 自动补全/提示                                        |
| `handleCommand(command, args)` | 命令分发器，返回 `{text, switchAgent?}`；未知命令返回 `未知命令：/<command>` |
| `listAgentsCommand()`          | `/agents` 命令实现，返回格式化文本；空列表返回"暂无可用智能体"                 |

### 设计要点

- **复用 fetchAgentList**：`/agent` 与 `/agents` 均调用 `api.js::fetchAgentList`（GET `/api/agent/list`），返回 `Array<{name, display_name}>`（**无 description 字段**，渲染时只用 name + display_name）
- **错误传播**：`fetchAgentList` 失败时抛出 `Error`（含后端 `detail`），`handleCommand` 与 `listAgentsCommand` 均不吞错，由调用方（InputBox）捕获并展示友好提示
- **requiresBackend 预留字段**：当前未消费，预留给未来离线模式跳过后端调用
- **switchAgent 信号**：`/agent <name>` 成功时返回 `switchAgent` 字段，InputBox 据此切换实际请求的 agent_name

### 测试

- 路径：`web/Agent/src/utils/__tests__/commandRegistry.test.js`（9 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，通过动态 `import('../commandRegistry.js')` 使 mock 生效
- 覆盖：COMMAND_REGISTRY 含 agent+agents / handleCommand 切换智能体 / 未知命令 / 缺参数 / 智能体不存在 / listAgentsCommand 列表非空 / listAgentsCommand 空列表 / listAgentsCommand 网络错误 / handleCommand 后端失败错误传播

### InputBox 集成

`InputBox.vue` 已接入命令注册表，检测到 `/` 开头输入时走命令分支，不再触发 refreshToken 与文件上传流程。

**改动点**：

1. **import**：新增 `import { handleCommand, COMMAND_REGISTRY } from '../utils/commandRegistry.js'`
2. **计算属性**：新增 `isCommand`（判断 `/` 开头）、`parsedCommand`（统一解析命令名+参数）与 `commandHint`（复用 `parsedCommand` 匹配 COMMAND_REGISTRY 返回描述+用法提示，未知命令返回 `未知命令：/<cmd>`）
3. **emits 声明**：新增 `agent-switched` 事件（`/agent <name>` 成功时携带目标 agent name）
4. **executeCommand 函数**：从 handleSend 抽取的独立命令执行函数；通过 `isExecutingCommand` ref + try/finally 保证命令执行期间 `canSend` 为 false，防止用户重复点击发送导致重复触发
5. **handleSend 命令分支**：在函数开头检测 `text.startsWith('/')`，命中时调用 `executeCommand(text)` 后提前 return；不进入 refreshToken 流程
6. **template**：textarea 后新增 `<div v-if="isCommand" class="command-hint">{{ commandHint }}</div>`
7. **CSS**：新增 `.command-hint` 样式（accent 色 + accent-light 背景 + radius-sm 圆角）

### InputBox 智能体快速选择

输入 `/` 后不再仅显示命令提示，而是弹出下拉菜单列出所有可用智能体，选中后以上方标签形式展示，发送消息时自动切换至该智能体。

**改动点**：

1. **placeholder**：默认状态改为 `输入 / 快速使用智能体`；选中智能体后改为 `请输入消息，按「Enter」发送`
2. **数据状态**：新增 `agentList`（智能体列表）、`isLoadingAgents`（加载中）、`selectedAgent`（当前选中智能体）、`showAgentDropdown`（下拉菜单显隐）、`activeAgentIndex`（键盘高亮索引）
3. **loadAgents**：组件内异步调用 `fetchAgentList`（GET `/api/agent/list`）加载智能体列表；已缓存或加载中时跳过
4. **filteredAgents**：computed，输入 `/` 显示全部，输入 `/xxx` 按 name / display_name 过滤
5. **handleInput**：精确输入 `/` 时打开下拉菜单并加载数据；输入 `/xxx` 保持菜单开启（过滤模式）；非 `/` 输入关闭菜单
6. **handleKeydown**：下拉菜单开启时支持 `↓`/`↑` 移动高亮、`Enter` 选中、`Esc` 关闭
7. **selectAgent**：选中后设置 `selectedAgent`，清空输入框，关闭菜单，聚焦 textarea
8. **removeSelectedAgent**：点击标签上的移除按钮清空 `selectedAgent`
9. **handleSend**：存在 `selectedAgent` 时，emit 消息前先 emit `agent-switched`（携带 agent.name），发送后自动清空 `selectedAgent`
10. **handleBlur**：延迟 200ms 关闭下拉菜单，保证 `mousedown` 选中事件先触发
11. **template**：textarea 前新增 `selected-agent-tag`（含 `/` 前缀 + display_name + 移除按钮）与 `agent-dropdown`（loading / 空状态 / 可点击列表项）
12. **CSS**：新增 `.selected-agent-tag`（accent 色边框 + 背景 + 圆角标签）、`.agent-dropdown`（白色浮层 + 阴影 + 圆角 + 最大高度 240px）、`.agent-dropdown-item`（hover/active 高亮）

**测试**：

- 路径：`web/Agent/src/components/__tests__/InputBox.command.spec.js`（11 用例）
- 测试策略：mount InputBox + mock `global.fetch`（按 URL 分发 `/api/auth/refresh` 与 `/api/agent/list`）+ mock `global.localStorage`
- 覆盖：普通文本触发 send 且不触发 agent-switched / `/` 开头显示命令提示 / `/agent map_agent` 命令触发 agent-switched 事件 / 未知命令显示未知命令提示 / `/agent non_exist` 不触发切换且 send 含「不存在」 / `/api/agent/list` 返回非 ok 时 send 含「命令执行失败」 / `/agents` 命令 send 含智能体列表 / 输入 `/` 显示智能体下拉菜单 / 点击下拉菜单项选中后显示标签并清空输入框 / 选中智能体后发送触发 agent-switched 与 send / 移除按钮可清空已选智能体标签

### App.vue agentName 状态管理

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

## scripts/ 目录（2026-06-25 新增）

`scripts/` 用于存放项目级离线辅助脚本，与 `app/` 业务代码隔离。

| 脚本 | 作用 |
| --- | --- |
| `seed_tools_from_source.py` | 扫描 `app/core/tools/` + `app/shared/tools/skills/` 下所有 `.py` 中的 `@tool` 函数，生成幂等的 `INSERT INTO tools ... ON CONFLICT DO NOTHING` SQL 段落到 `app/migrations/init_all_tables.sql` 末尾 |
| `README.md` | scripts 目录说明文档 |

**seed 脚本隔离策略**（`app/tests/scripts/test_seed_tools_from_source.py`）：

- 用 `monkeypatch` 把 `TOOL_ROOTS` / `PROJECT_ROOT` 指向 `tmp_path` 下的伪工程，**真实工程文件零污染**
- 不引入 MagicMock：脚本仅依赖标准库（`ast`/`json`/`argparse`/`pathlib`/`datetime`），全部走真实代码路径；CLI 测试通过 subprocess 真实执行
- Windows 编码兼容：CLI 测试设置 `PYTHONIOENCODING=utf-8` + `errors="replace"`

**测试覆盖**：`app/tests/scripts/test_seed_tools_from_source.py` 13 用例（_has_tool_decorator 识别 / _extract_tool_description / _file_to_module_path / _infer_category / scan_all_tools / _sql_escape / _json_escape / render_sql / CLI dry-run / CLI output-to-file）

## Agent 工具绑定双轨制（2026-06-25 落地）

### 数据流

```
[tool_bindings]  →  AgentConfigService._load_tools
                          ↓
            ┌─────────────┴─────────────┐
            │                           │
   tool_type="builtin"        tool_type="mcp"
            │                           │
  ToolRegistryService       MCPToolsRegistry
   .get_tool_by_name()       .get_tools_with_server(
                                 server="amap",
                                 names=["search"]
                             )
            │                           │
   @tool 装饰函数            MCPToolToLangChainAdapter
            │                           │
            └─────────────┬─────────────┘
                          ↓
                  UnifiedAgentConfig.tools
                          ↓
                AgentConfig(tools=...)
                          ↓
                     Agent.__ainit__
                          ↓
                    self.model.bind_tools
```

### MCP 工具命名约定

`tool_bindings[].tool_name` 用 `server.method` 复合名（例：`amap.search`）：

- 解析：`AgentConfigService._parse_mcp_tool_name("amap.search") → ("amap", "search")`
- 过滤：避免跨 server 命名冲突（多个 server 都提供 `search` method 时精确指定 server）
- 兼容：tool_name 无 `.` 时（如 `search`）会记录 warning 跳过（2026-06-25 修复 `_load_tools` 旧 `if not server_name` 判断错误，应为 `if not method_name`）

### 测试覆盖统计（2026-06-29 更新）

| 测试文件 | 用例数 | 新增（本次） |
| --- | --- | --- |
| `app/tests/shared/utils/agent/test_agent_config_service.py` | 101 | +25（skill 绑定相关：set_skill_service / update_skill_bindings / get_skill_bindings / get_available_skills / bind_skill 废弃 / skill_bindings JSONB 加载等）|
| `app/tests/routers/test_agent_admin_router.py` | 46 | +11（skill-bindings 4 + available-skills 2 + 路由注册更新 1 + 相关调整 4）|
| `app/tests/routers/test_tool_admin_router.py` | 29 | +4（热加载缓存失效 4）|
| `app/tests/routers/test_skill_admin_router.py` | 1 | 1（新建，模块可导入）|
| `app/tests/scripts/test_seed_tools_from_source.py` | 13 | 13（新建）|
| **合计** | **154** | **+1** |
