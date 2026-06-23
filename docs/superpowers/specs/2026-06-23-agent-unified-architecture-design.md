# 统一智能体架构 + MCP 注册界面 设计文档

> 日期：2026-06-23
> 状态：设计已确认，待实施
> 验证范围：先做 map_agent 验证，其他 agent 后迁移

---

## 0. 已确认决策

| 编号 | 决策 |
|------|------|
| 1 | 新增 `agent_tool_bindings` / `agent_skill_bindings` 表统一管理绑定 |
| 2 | MCP method 列表在 server 首次注册时拉取一次，注册界面提供"刷新方法列表"按钮 |
| 3 | 数据库迁移追加到现有迁移脚本 |
| 4 | `/api/map/chat` 直接替换为 `/api/agent/chat`，不留兼容 |

附加设计原则：
- **AGENTS.md 是纯 markdown**，写"智能体应该干什么"（角色、职责、可用工具清单、可用 skill、行为规范），不写"软件当前怎么实现"（state 字段、context 字段、tool 绑定等技术细节）。
- **Context / State 字段不放在 AGENTS.md**，统一存数据库 `agents` 表 JSON 字段。
- **保留基类 Python 代码**（`AgentState` / `AgentContext` / `AgentConfig`），子类字段由数据库 JSON 动态构建，子类可重写父类字段。
- **`/command` 只做 `/agent <name>` 智能体切换**，不扩展其他命令。

---

## 1. 设计动机

当前架构存在以下问题：
1. agent 提示词、skill 使用方式分散在 `prompts.py`、`bootstrap.md`、`SKILL.md` 多处。
2. 每个 agent 有独立的 `MapAgentConfig.py` / `MapAgentContext.py`，新增 agent 需要写 3+ 个 Python 文件。
3. MCP 配置只在 YAML 启动时加载，admin 无运行时管理能力。
4. 路由分散（`/api/map/chat`、`/api/contract/chat` 等），前端硬编码。

本次重构目标：
- 一份 `AGENTS.md`（纯 markdown）描述一个 agent 的所有 LLM 可见内容。
- 数据库 `agents` 表存 agent 的运行时配置（state 字段、context 字段、工具绑定、skill 绑定）。
- 基类 `AgentState` / `AgentContext` 保留 Python 代码，子类字段由数据库 JSON 动态构建。
- 统一 `/api/agent/chat` 路由。
- 新增 MCP 注册界面，支持 server 和 method 两级开关。

---

## 2. 目录结构

```
app/
├── core/                              # 保留
│   ├── agent/
│   │   ├── AgentState.py              # 基类（保留）
│   │   ├── AgentContext.py            # 基类（保留）
│   │   ├── agent.py                   # 通用 Agent（改造支持动态 state_class/context_class）
│   │   └── AgentConfig.py             # 基类（保留）
│   └── ...
├── features/                          # 最终目标：删除（map_agent 先迁移验证）
│   ├── map_agent/                     # 验证通过后删除
│   └── ...
├── routers/                           # 新增（与 core 平级）
│   ├── __init__.py
│   ├── agent_router.py                # /api/agent/chat, /api/agent/list
│   └── mcp_admin_router.py            # /api/admin/mcp/*
├── shared/
│   ├── tools/
│   │   ├── registry.py                # 新增 ToolRegistry
│   │   ├── base/                      # 基础工具迁移
│   │   │   ├── BaseTools.py
│   │   │   ├── FilesystemReadTools.py
│   │   │   ├── SandboxTools.py
│   │   │   └── HumanInTheLoopTools.py
│   │   ├── skills/                    # 各 agent 专属工具
│   │   │   └── map_agent/
│   │   │       └── MapTools.py        # 用 @register_tool 装饰
│   │   └── mcp/
│   │       └── config.yaml            # 仅作为初始种子
│   └── utils/
│       └── agent/                     # 新增
│           ├── __init__.py
│           ├── dynamic_schema.py      # 动态构建 state/context
│           ├── agent_config_service.py
│           ├── agents_md_loader.py    # 加载 AGENTS.md 纯 markdown
│           └── mcp_service.py         # MCP 配置 CRUD
├── migrations/
│   └── 2026_06_23_agent_unified.sql   # 新增 5 张表
└── main.py                            # 注册新路由

agents/                                # 项目根新增
└── map_agent/
    └── AGENTS.md                      # 纯 markdown，给 LLM 看

skills/                                # 项目根 skill 目录
└── map_agent/
    └── data-skill/
        └── SKILL.md

web/Agent/
├── src/
│   ├── components/
│   │   ├── McpServerManager.vue       # 新增
│   │   └── UserSettingsDialog.vue     # 增加 MCP 管理 Tab
│   └── utils/
│       ├── api.js                     # 新增 MCP 管理 API + chatStream 改为 /api/agent/chat
│       └── commandRegistry.js         # 只保留 /agent <name>
└── ...
```

---

## 3. 数据库设计

### 3.1 `agents` 表

```sql
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    agents_md_path VARCHAR(500) NOT NULL,        -- agents/map_agent/AGENTS.md
    state_schema JSONB DEFAULT '{}',              -- {"map_center": {"type": "dict", "default": {}}, ...}
    context_schema JSONB DEFAULT '{}',            -- {"knowledge_root": {"type": "str", "default": "data/Knowledge"}, ...}
    mcp_tags JSONB DEFAULT '[]',
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 `agent_tool_bindings` 表

```sql
CREATE TABLE IF NOT EXISTS agent_tool_bindings (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_name, tool_name)
);
```

### 3.3 `agent_skill_bindings` 表

```sql
CREATE TABLE IF NOT EXISTS agent_skill_bindings (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    skill_name VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_name, skill_name)
);
```

### 3.4 `mcp_server_configs` 表

```sql
CREATE TABLE IF NOT EXISTS mcp_server_configs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    type VARCHAR(20) NOT NULL,
    url VARCHAR(500),
    command JSONB,
    timeout INT DEFAULT 5,
    read_timeout INT DEFAULT 300,
    tags JSONB DEFAULT '[]',
    enabled BOOLEAN DEFAULT TRUE,
    progress_reporting JSONB DEFAULT '{"enabled": false}',
    tool_config JSONB DEFAULT '{"enable_injection": true, "default_param_keys": [], "hidden_param_keys": [], "unwrap_result": false}',
    sampling JSONB DEFAULT '{"enabled": false}',
    methods_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

`methods_synced_at` 记录上次 method 列表同步时间，admin 在注册界面可点"刷新方法列表"按钮重新拉取。

### 3.5 `mcp_server_methods` 表

```sql
CREATE TABLE IF NOT EXISTS mcp_server_methods (
    id SERIAL PRIMARY KEY,
    server_name VARCHAR(100) NOT NULL,
    method_name VARCHAR(200) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(server_name, method_name)
);
```

---

## 4. 动态 State / Context 构建

### 4.1 基类（保留现有 `app/core/agent/AgentState.py` / `AgentContext.py`）

```python
# app/core/agent/AgentState.py
class AgentState(MessagesState):
    error_limit: int = 5
    limit: int = 25
    pending_question: dict = None
    question_answers: list = []
    agent_name: Optional[str] = None


# app/core/agent/AgentContext.py
class AgentContext(TypedDict):
    session_id: str = "default"
    store_id: str = "default"
    image_ids: list[str] = []
    host_session_id: Optional[str] = None
    process_data: dict = {}
```

### 4.2 动态构建器 `app/shared/utils/agent/dynamic_schema.py`

```python
RESERVED_STATE_FIELDS = {
    "messages", "error_limit", "limit", "pending_question",
    "question_answers", "agent_name",
}
RESERVED_CONTEXT_FIELDS = {
    "session_id", "store_id", "image_ids",
    "host_session_id", "process_data",
}

TYPE_MAP = {
    "str": str, "int": int, "float": float, "bool": bool,
    "dict": dict, "list": list,
}


def build_agent_state(agent_name: str, state_schema: dict) -> type:
    """根据数据库 state_schema 动态生成 AgentState 子类。

    合并逻辑：
    - 基类 AgentState 的所有字段保留。
    - 数据库 state_schema 中的字段追加（同名则重写默认值）。
    - 保留字段（messages 等）由基类提供，不允许覆盖。
    """
    annotations = {}
    defaults = {}
    for fname, fdef in state_schema.items():
        if fname in RESERVED_STATE_FIELDS:
            continue
        py_type = TYPE_MAP.get(fdef.get("type", "str"), str)
        annotations[fname] = py_type
        if "default" in fdef:
            defaults[fname] = fdef["default"]

    namespace = {**defaults, "__annotations__": annotations}
    return type(f"{agent_name.title()}AgentState", (AgentState,), namespace)


def build_agent_context(agent_name: str, context_schema: dict) -> type:
    """类似 build_agent_state，针对 AgentContext。"""
    annotations = {}
    defaults = {}
    for fname, fdef in context_schema.items():
        if fname in RESERVED_CONTEXT_FIELDS:
            continue
        py_type = TYPE_MAP.get(fdef.get("type", "str"), str)
        annotations[fname] = py_type
        if "default" in fdef:
            defaults[fname] = fdef["default"]

    namespace = {**defaults, "__annotations__": annotations}
    return type(f"{agent_name.title()}AgentContext", (AgentContext,), namespace)


def build_context(agent_name: str, context_schema: dict, request) -> AgentContext:
    """运行时构造 context 实例。"""
    cls = build_agent_context(agent_name, context_schema)
    instance = cls(
        session_id=request.session_id,
        store_id=request.store_id,
        **request.context_overrides,
    )
    return instance
```

**重写父类机制**：动态构造的子类继承基类，基类所有字段保留；如果数据库 JSON 中字段名与基类保留字段冲突（如尝试覆盖 `messages`），构造器跳过。如果尝试覆盖普通字段，子类会通过 `type(name, (base,), dict)` 形成的 MRO 自然覆盖基类同名属性。

---

## 5. AgentConfigService

```python
# app/shared/utils/agent/agent_config_service.py

class AgentConfigService:
    def __init__(self, db, agents_md_loader):
        self._db = db
        self._loader = agents_md_loader

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """根据 agent_name 加载完整配置。

        流程：
        1. 从数据库 agents 表查询。
        2. 读取 AGENTS.md 正文。
        3. 动态构建 state_class / context_class。
        4. 加载工具绑定（从 agent_tool_bindings）。
        5. 加载 skill 绑定（从 agent_skill_bindings）。
        6. 返回 AgentConfig 实例。
        """
        row = await self._db.fetchrow(
            "SELECT * FROM agents WHERE name = $1 AND enabled = TRUE",
            agent_name,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found or disabled")

        system_prompt = self._loader.load(row["agents_md_path"])
        state_class = build_agent_state(agent_name, row["state_schema"])
        context_class = build_agent_context(agent_name, row["context_schema"])

        tool_bindings = await self._db.fetch(
            "SELECT tool_name, is_enabled FROM agent_tool_bindings "
            "WHERE agent_name = $1 ORDER BY sort_order",
            agent_name,
        )
        skill_bindings = await self._db.fetch(
            "SELECT skill_name, is_enabled FROM agent_skill_bindings "
            "WHERE agent_name = $1 ORDER BY sort_order",
            agent_name,
        )

        return AgentConfig(
            name=agent_name,
            system_prompt=system_prompt,
            state_class=state_class,
            context_class=context_class,
            mcp_tags=row["mcp_tags"],
            enabled_tool_names=[
                r["tool_name"] for r in tool_bindings if r["is_enabled"]
            ],
            enabled_skill_names=[
                r["skill_name"] for r in skill_bindings if r["is_enabled"]
            ],
        )

    async def list_agents(self) -> list[dict]:
        """列出所有启用的智能体，供 /agent 命令展示。"""
        rows = await self._db.fetch(
            "SELECT name, display_name, description FROM agents "
            "WHERE enabled = TRUE ORDER BY sort_order"
        )
        return [dict(r) for r in rows]

    async def create_agent(self, config: dict) -> dict:
        """Admin 创建智能体。"""

    async def update_agent(self, name: str, config: dict) -> dict:
        """Admin 更新智能体。"""

    async def delete_agent(self, name: str) -> dict:
        """Admin 删除智能体。"""

    async def bind_tool(self, agent_name: str, tool_name: str, enabled: bool = True) -> dict:
        """绑定/解绑工具。"""

    async def bind_skill(self, agent_name: str, skill_name: str, enabled: bool = True) -> dict:
        """绑定/解绑 skill。"""
```

`AgentConfig.get_tools()` 改造：

```python
def get_tools(self) -> tuple[list, ToolNode]:
    """优先从 ToolRegistry + 数据库绑定加载，回退到代码默认。"""
    from app.shared.tools.registry import ToolRegistry

    static_tools = ToolRegistry.get_tools_for_agent(
        self.name,
        enabled_tool_names=self.enabled_tool_names,
    )
    mcp_tools = MCPToolsRegistry.get_instance().get_tools_with_server(
        tags=self.mcp_tags,
    )

    tools = static_tools + mcp_tools
    return tools, ToolNode(tools, handle_tool_errors=True)
```

---

## 6. ToolRegistry

```python
# app/shared/tools/registry.py

class ToolRegistry:
    _tools: Dict[str, dict] = {}

    @classmethod
    def register(cls, name: str, agent: str, description: str, module_path: str = ""):
        """@register_tool 装饰器。"""
        def decorator(func):
            cls._tools[name] = {
                "func": func,
                "agent": agent,
                "description": description,
                "module_path": module_path or func.__module__,
            }
            return func
        return decorator

    @classmethod
    def get_tools_for_agent(cls, agent_name: str, enabled_tool_names: list[str] = None) -> list:
        """根据 agent_name 和 enabled_tool_names 返回工具列表。"""
        if enabled_tool_names is None:
            return [
                info["func"]
                for info in cls._tools.values()
                if info["agent"] == agent_name
            ]
        return [
            cls._tools[name]["func"]
            for name in enabled_tool_names
            if name in cls._tools and cls._tools[name]["agent"] == agent_name
        ]
```

装饰器使用：

```python
# app/shared/tools/skills/map_agent/MapTools.py
@register_tool(name="set_map_center", agent="map_agent", description="设置地图中心点")
@tool
def set_map_center(latitude: float, longitude: float, runtime: ToolRuntime) -> Command:
    ...
```

---

## 7. AGENTS.md（纯 markdown，写"智能体应该干什么"）

**位置**：`agents/<agent_name>/AGENTS.md`

**内容范围**：
- 智能体的身份、职责、目标用户。
- 可用工具清单（仅写工具名称与用途，不写参数签名）。
- 可用 skill 清单 + 使用指南。
- 行为规范（响应风格、回答格式、特殊约束）。

**不写的内容**：
- state 字段、context 字段等数据结构（由数据库 `agents` 表 JSON 决定）。
- 工具绑定、skill 绑定（由 `agent_tool_bindings` / `agent_skill_bindings` 表决定）。
- 系统提示词分层、架构信息（由基类 + `AgentConfigService` 处理）。

**示例 `agents/map_agent/AGENTS.md`**：

```markdown
# 地图控制智能体

## 身份与职责
你是地图控制智能体，负责地图操作、知识库查询、报告生成。

## 可用工具
| 工具名 | 用途 |
|--------|------|
| set_map_center | 设置地图中心点 |
| set_map_zoom | 设置地图缩放级别 |
| add_map_marker | 添加地图标记 |
| get_map_state | 获取当前地图状态 |
| generate_report | 生成项目报告 |
| save_business_info | 保存业务信息 |
| query_knowledge | 检索知识库 |
| explore | 读取当前会话上传文件 |
| sandbox | 执行代码（Docker 隔离） |
| ask_user_question | 询问用户澄清问题 |

## 可用 Skill
| Skill 名 | 用途 |
|----------|------|
| data-skill | 数据查询与分析工作流 |

## Skill 使用指南
### data-skill：数据查询与分析
**何时使用**：用户要求查询地图相关数据或生成报告时。
**如何使用**：调用 `load_skill("data-skill")` 加载 skill 正文，按 skill 工作流执行。
**注意事项**：报告生成需先完成数据查询。

## 行为规范
- 响应使用中文。
- 地图操作需先确认坐标有效性。
- 报告生成需包含数据来源。
```

---

## 8. 统一 Agent Router

**位置**：`app/routers/agent_router.py`（新增）

```python
router = APIRouter(prefix="/api/agent", tags=["Agent"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    agent_name: str = "map_agent"
    attachments: list = []
    resume: Optional[dict] = None
    context_overrides: dict = {}


@router.post("/chat")
async def chat(request: Request, chat_request: ChatRequest):
    """统一智能体聊天接口。"""
    config = await agent_config_service.get_agent_config(chat_request.agent_name)

    context = build_context(
        agent_name=chat_request.agent_name,
        context_schema=config.context_schema,
        request=chat_request,
    )

    state_class = config.state_class
    if chat_request.resume:
        from langgraph.types import Command
        input_state = Command(resume=chat_request.resume)
    else:
        input_state = state_class(messages=[HumanMessage(content=chat_request.message)])

    agent = Agent(config)
    await agent.__ainit__()

    return StreamingResponse(
        generate_stream_response(agent, input_state, context, chat_request),
        media_type="text/event-stream",
    )


@router.get("/list")
async def list_agents():
    """列出所有启用的智能体。"""
    return await agent_config_service.list_agents()


@router.get("/{agent_name}/agents-md")
async def get_agents_md(agent_name: str):
    """获取指定 agent 的 AGENTS.md 内容。"""
    config = await agent_config_service.get_agent_config(agent_name)
    return {"content": config.system_prompt}
```

`generate_stream_response` 复用 `app/features/map_agent/router/map_router.py` 中已有的 SSE 生成逻辑（提取到 `app/routers/_stream_helper.py`）。

`Agent.__init__` 改造：保持现有签名，仅在构造 `StateGraph` 时使用 `config.state_class` 和 `config.context_class`，已支持基类 + 动态子类。

---

## 9. /agent 命令

**位置**：`web/Agent/src/utils/commandRegistry.js`

```javascript
export const COMMAND_REGISTRY = [
  {
    name: 'agent',
    description: '切换智能体',
    usage: '/agent <name>',
    requiresBackend: true,
  },
]


export async function handleCommand(command, args) {
  if (command === 'agent' && args.length === 1) {
    const targetAgent = args[0]
    const agents = await fetchAgentList()
    const found = agents.find(a => a.name === targetAgent)
    if (!found) {
      return {
        text: `智能体 '${targetAgent}' 不存在。\n\n可用：${agents.map(a => `${a.name}（${a.display_name}）`).join('\n')}`,
      }
    }
    return {
      text: `已切换到智能体：${found.display_name}`,
      switchAgent: targetAgent,
    }
  }
  return { text: `未知命令：/${command}` }
}
```

`InputBox.vue` 检测到 `/` 开头时调用 `handleCommand`，切换后 emit `agent-switched` 事件，由 `App.vue` 维护当前激活的 `agent_name`（存入 Vue 响应式状态即可，无需 localStorage）。后续 `chatStream` 通过 props / store 读取当前 agent_name。

---

## 10. MCP 注册界面

### 10.1 后端 Router `app/routers/mcp_admin_router.py`

```python
router = APIRouter(prefix="/api/admin/mcp", tags=["MCP Admin"])


@router.get("/servers")
async def list_servers(): ...


@router.post("/servers")
async def create_server(config: McpServerConfig):
    """新增 MCP server。

    流程：
    1. 写入数据库。
    2. 调用 MCPToolsRegistry.add_server(config)。
    3. 首次拉取 method 列表写入 mcp_server_methods。
    4. 返回 server 详情。
    """


@router.put("/servers/{name}")
async def update_server(name: str, config: McpServerConfig): ...


@router.delete("/servers/{name}")
async def delete_server(name: str): ...


@router.post("/servers/{name}/toggle")
async def toggle_server(name: str, enabled: bool): ...


@router.get("/servers/{name}/methods")
async def list_methods(name: str):
    """列出 server 下所有 method（含 enabled 状态）。"""
    # 直接从数据库 mcp_server_methods 读取
    # 如果 methods_synced_at 为空，提示前端需要刷新


@router.post("/servers/{name}/refresh-methods")
async def refresh_methods(name: str):
    """重新从 MCP server 拉取 method 列表，更新数据库。

    流程：
    1. 调用 MCPToolsRegistry 拉取最新 method。
    2. 与数据库 mcp_server_methods 对比。
    3. 新增 method 默认 enabled=true。
    4. 已存在的 method 保留当前 enabled 状态。
    5. 删除消失的 method。
    6. 更新 methods_synced_at。
    """


@router.post("/servers/{name}/methods/{method}/toggle")
async def toggle_method(name: str, method: str, enabled: bool): ...
```

### 10.2 MCPToolsRegistry 增强

新增方法：
- `add_server(config)` / `update_server(name, config)` / `remove_server(name)`
- `toggle_server(name, enabled)` / `toggle_method(name, method, enabled)`
- `get_tools_with_server(tags=None, names=None, server=None)` 内部按 enabled 过滤 server 和 method

启动流程：
1. 从数据库 `mcp_server_configs` 加载所有 server 配置（数据库优先）。
2. 如果数据库为空，从 YAML 导入种子数据。
3. 对每个 server 启动时尝试拉取 method 列表（首次同步），失败不阻塞，记录 warning。

### 10.3 前端 `McpServerManager.vue`

布局：

```
┌─────────────────────────────────────────────────────┐
│ MCP 服务器管理                                       │
├─────────────────────────────────────────────────────┤
│ [+ 新增服务器]                                       │
│                                                     │
│ ┌──────────┐ ┌──────────────────────────────────┐  │
│ │ 服务器列表 │ │ 服务器详情                        │  │
│ │           │ │                                   │  │
│ │ ● 质检分析 │ │ 名称: 质检分析                   │  │
│ │   [ON]    │ │ 类型: SSE                        │  │
│ │           │ │ URL: http://10.20.8.178:1024...  │  │
│ │ ● 高德地图 │ │ Tags: [map, geo, navigation]    │  │
│ │   [OFF]   │ │ [保存] [删除]                    │  │
│ │           │ │                                   │  │
│ │ ● 计数工具 │ │ 方法列表（最后同步: 2026-06-23） │  │
│ │   [ON]    │ │ [刷新方法列表]                   │  │
│ │           │ │                                   │  │
│ │ [+ 新增]  │ │ ☑ method_a   描述...             │  │
│ └──────────┘ │ ☐ method_b   描述...             │  │
│              └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

新增/编辑表单字段：
- name（唯一标识）
- display_name（显示名）
- type（sse / stdio / websocket）
- url（sse / websocket）
- command（stdio，数组输入）
- timeout、read_timeout
- tags（多 tag 输入）
- enabled（server 开关）

---

## 11. 前端改动

### 11.1 `web/Agent/src/utils/api.js`

```javascript
// 改 chatStream 调用 /api/agent/chat
export async function chatStream(sessionId, message, attachments = [], resume = null) {
  const response = await fetchWithAuth('/api/agent/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-ID': sessionId,
    },
    body: JSON.stringify({
      message: resume ? '' : message,
      session_id: sessionId,
      agent_name: 'map_agent',
      attachments,
      resume,
    }),
  })
  return response
}

// 新增 MCP 管理 API
export async function listMcpServers() { ... }
export async function createMcpServer(config) { ... }
export async function updateMcpServer(name, config) { ... }
export async function deleteMcpServer(name) { ... }
export async function toggleMcpServer(name, enabled) { ... }
export async function listMcpMethods(name) { ... }
export async function refreshMcpMethods(name) { ... }
export async function toggleMcpMethod(name, method, enabled) { ... }

// 新增 agent 列表 API
export async function fetchAgentList() {
  return fetchWithAuth('/api/agent/list').then(r => r.json())
}
```

### 11.2 `web/Agent/src/utils/commandRegistry.js`

只保留 `/agent` 命令（详见 §9）。

### 11.3 `UserSettingsDialog.vue` admin 面板

新增 "MCP 服务器" Tab，引用 `McpServerManager.vue`。

---

## 12. 实施步骤

### 阶段 1：数据库与基础设施（无破坏）

1. 新增 `app/migrations/2026_06_23_agent_unified.sql`：创建 5 张表。
2. 新增 `app/shared/utils/agent/dynamic_schema.py`。
3. 新增 `app/shared/tools/registry.py`。
4. 新增 `app/shared/utils/agent/agents_md_loader.py`。
5. 新增 `app/shared/utils/agent/mcp_service.py`。
6. YAML → 数据库迁移脚本（启动时检测空表则导入）。

### 阶段 2：MCP 管理界面

1. 新增 `app/routers/mcp_admin_router.py`。
2. `MCPToolsRegistry` 增加运行时方法。
3. 前端 `McpServerManager.vue` + `UserSettingsDialog.vue` 添加 Tab。
4. 前端 `api.js` 添加 MCP 管理 API。

### 阶段 3：统一 Agent 架构（map_agent 验证）

1. 新增 `agents/map_agent/AGENTS.md`（纯 markdown）。
2. 新增 `app/shared/utils/agent/agent_config_service.py`。
3. 新增 `app/routers/agent_router.py`（统一 `/api/agent/chat`）。
4. 改造 `Agent.__init__` 支持动态 `state_class` / `context_class`。
5. 改造 `AgentConfig.get_tools()` 优先从 `ToolRegistry` 加载。
6. 数据库 seed：`map_agent` 配置（state_schema 含 map_center / map_markers 等；context_schema 含 knowledge_root）。
7. 迁移工具到 `app/shared/tools/skills/map_agent/MapTools.py`，用 `@register_tool` 装饰。
8. 迁移基础工具到 `app/shared/tools/base/`。
9. `app/main.py`：删除 `/api/map/chat` 注册，新增 `/api/agent/chat` + `/api/admin/mcp/*` 注册。
10. 前端 `api.js` 改用 `/api/agent/chat`。
11. 前端 `commandRegistry.js` 只保留 `/agent`。

### 阶段 4：测试

后端：
- `app/tests/shared/utils/agent/test_dynamic_schema.py`（动态构建 state/context）
- `app/tests/shared/utils/agent/test_agent_config_service.py`（加载 AGENTS.md + 数据库）
- `app/tests/shared/tools/test_registry.py`（装饰器 + 过滤）
- `app/tests/routers/test_agent_router.py`（统一聊天接口）
- `app/tests/routers/test_mcp_admin_router.py`（MCP CRUD + toggle）

前端：
- `web/Agent/src/components/__tests__/McpServerManager.spec.js`
- 更新 `web/Agent/src/utils/__tests__/api.test.js`
- 更新 `web/Agent/src/utils/__tests__/commandRegistry.test.js`

### 阶段 5：手动验证 + 清理

1. 启动后端，迁移数据库。
2. 验证 `GET /api/agent/list` 返回 map_agent。
3. 前端发送 `/agents` 查看智能体列表。
4. 前端发送 `/agent map_agent` 切换。
5. 前端发送聊天消息，验证走 `/api/agent/chat`。
6. Admin 登录，验证 MCP 管理界面可增删改 MCP server，可刷新方法列表，可开关 method。
7. 验证 map_agent 工具正常调用。
8. 验证 skill 加载正常。

验证通过后：
- 删除 `app/features/map_agent/`（保留其他 agent）。
- 删除 `app/main.py` 中的 `/api/map/chat` 注册。

---

## 13. 文件清单

### 新增文件

| 文件 | 用途 |
|------|------|
| `app/migrations/2026_06_23_agent_unified.sql` | 5 张表迁移 |
| `app/shared/utils/agent/__init__.py` | 包初始化 |
| `app/shared/utils/agent/dynamic_schema.py` | 动态 state/context 构建 |
| `app/shared/utils/agent/agent_config_service.py` | Agent 配置加载 |
| `app/shared/utils/agent/agents_md_loader.py` | AGENTS.md 加载器 |
| `app/shared/utils/agent/mcp_service.py` | MCP 配置 CRUD |
| `app/shared/tools/registry.py` | ToolRegistry |
| `app/routers/__init__.py` | 路由包初始化 |
| `app/routers/agent_router.py` | 统一聊天接口 |
| `app/routers/mcp_admin_router.py` | MCP 管理接口 |
| `app/routers/_stream_helper.py` | SSE 生成器（从 map_router 提取） |
| `app/shared/tools/base/__init__.py` | 基础工具初始化 |
| `app/shared/tools/base/BaseTools.py` | 基础工具 |
| `app/shared/tools/base/FilesystemReadTools.py` | explore |
| `app/shared/tools/base/SandboxTools.py` | sandbox |
| `app/shared/tools/base/HumanInTheLoopTools.py` | ask_user_question |
| `app/shared/tools/skills/map_agent/__init__.py` | map_agent 工具初始化 |
| `app/shared/tools/skills/map_agent/MapTools.py` | map_agent 工具 |
| `agents/map_agent/AGENTS.md` | map_agent 提示词 |
| `skills/map_agent/data-skill/SKILL.md` | map_agent skill |
| `web/Agent/src/components/McpServerManager.vue` | MCP 管理组件 |
| `web/Agent/src/components/__tests__/McpServerManager.spec.js` | 测试 |
| 测试文件若干 | |

### 修改文件

| 文件 | 改动 |
|------|------|
| `app/core/agent/agent.py` | 支持动态 state_class/context_class |
| `app/core/agent/AgentConfig.py` | get_tools() 优先从 ToolRegistry 加载 |
| `app/core/tools/mcp_registry.py` | 运行时 add/update/remove/toggle |
| `app/main.py` | 注册新路由，删除 map_router |
| `app/core/server.py` | lifespan 中初始化 AgentConfigService + MCP 数据库加载 |
| `web/Agent/src/utils/api.js` | chatStream 改用 /api/agent/chat；新增 MCP API |
| `web/Agent/src/utils/commandRegistry.js` | 只保留 /agent |
| `web/Agent/src/components/InputBox.vue` | 调用 handleCommand |
| `web/Agent/src/components/UserSettingsDialog.vue` | 增加 MCP 管理 Tab |
| `project_memory.md` | 同步架构变更 |

### 删除文件（验证通过后）

- `app/features/map_agent/`（整目录）
- `app/features/map_agent/config/MapAgentConfig.py` / `MapAgentContext.py` / `prompts.py`
- `app/features/map_agent/tools/MapTools.py`
- `app/features/map_agent/router/map_router.py`
- `app/features/map_agent/skills/data-skill/SKILL.md`（已迁移到 `skills/`）
- `app/main.py` 中的 map_router 注册

---

## 14. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 动态 TypedDict 类型检查弱 | 保留基类 Python 代码做兜底；运行时打印 schema 便于调试 |
| MCP server 启动时连接失败 | 启动不阻塞，记录 warning，admin 可在管理界面手动重试 |
| 数据库迁移影响现有数据 | 新增 5 张表，不修改现有表；迁移脚本幂等（CREATE IF NOT EXISTS） |
| 旧前端硬编码 `/api/map/chat` | 同次提交修改 `chatStream`，避免前后端不一致 |
| 工具 import 路径变更导致遗漏 | 迁移完成后 grep 全量验证 `app.features` / `map_router` 无残留引用 |
| map_agent 验证失败回退成本高 | 保留 `app/features/map_agent/` 直到阶段 5 验证通过，验证失败可快速回滚 |

---

## 15. 验证步骤

1. `pytest app/tests/shared/utils/agent/ -v` — 动态 schema + 配置服务
2. `pytest app/tests/shared/tools/test_registry.py -v` — ToolRegistry
3. `pytest app/tests/routers/test_agent_router.py -v` — 统一聊天接口
4. `pytest app/tests/routers/test_mcp_admin_router.py -v` — MCP 管理
5. `pytest app/tests/ -v` — 全量回归
6. `cd web/Agent && npm test` — 前端测试
7. 启动后端，迁移数据库
8. 手动验证流程（详见阶段 5）

---

## 16. 与 LangChain 1.x / LangGraph 1.x 规范的对照

| 设计点 | LangChain 1.x 推荐 | 本方案做法 | 是否符合 |
|--------|--------------------|------------|---------|
| 工具定义 | `@tool` 装饰器 | 保留 `@tool`，外层加 `@register_tool` | ✓ 装饰器可叠加 |
| 工具上下文访问 | `runtime: ToolRuntime[Context]` | `runtime: ToolRuntime` + `runtime.context.get(...)` | ✓ 兼容 |
| State 定义 | `class AgentState(MessagesState)` TypedDict | 基类保留 TypedDict，子类通过 `type(name, (base,), ns)` 动态生成 | ✓ 运行时类型可创建 |
| Context 注入 | `agent.invoke(state, context=ctx)` | `agent.stream(state, context=ctx)` | ✓ LangGraph 原生支持 |
| StateGraph 构造 | `StateGraph(state_schema=S, context_schema=C)` | `StateGraph(config.state_class, config.context_class)` | ✓ 动态 schema 支持 |
| MCP 工具加载 | `langchain-mcp-adapters` `load_mcp_tools` / `convert_mcp_tool_to_langchain_tool` | 沿用现有 `MCPToolToLangChainAdapter`，在 registry 增强 | ✓ 项目已使用 `langchain-mcp-adapters` |

**重写父类机制**：

Python 的 `type(name, bases, dict)` 动态类创建遵循 MRO 规则。如果动态 dict 中包含与基类同名的属性（如 `map_center`），子类会通过属性查找链覆盖基类。但基类的 `__annotations__` 包含的 TypedDict 字段不会自动被子类继承——TypedDict 的字段定义在类的 `__annotations__` 中，子类需要显式包含才能保留。因此动态构造时务必保证子类 namespace 包含所有需要的字段，否则 LangGraph 会报错 `Missing field`。

**Context 字段重写**：

`TypedDict` 在 Python 3.11+ 支持 `total=False`（所有字段可选）。本方案基类字段保留，子类通过 `type()` 动态追加，子类同名属性覆盖基类。MRO 链：动态子类 → `AgentContext`（基类）→ `dict`。运行时实例化时按子类 annotations 校验。
