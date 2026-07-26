# MCP 体系

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

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


