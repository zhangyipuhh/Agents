# Agent 与 Skill 体系

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

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

### `BASE_SYSTEM_PROMPT` 可选跳过（2026-08-19 新增）

`AgentConfig` 新增 `base_system_prompt: Optional[str] = field(default=None)` 字段，让上层可控制 base 段：
- `None`（默认，向后兼容）→ 使用常量 `BASE_SYSTEM_PROMPT`
- `""`（显式空串）→ 跳过 base 段；`SkillsAwarePrompt.build()` 的 `"\n\n".join(p for p in parts if p)` 自动过滤空串，整段 `BASE_SYSTEM_PROMPT` 不参与拼接
- 非空字符串 → 完全覆盖常量内容（按 Agent 维度定制通用规则）

`Agent._llm_call` 通过 `getattr(self._config, "base_system_prompt", None)` 读取，None 时回退到常量；显式空串/非空时直接透传给 `SkillsAwarePrompt(base=...)`。

**用法**：子智能体已有完整 `system_prompt`（如 HtAgent/DocAgent/ApprovalAgent）又不需要通用基类规则时，在 `AgentConfig(..., base_system_prompt="")` 即可关闭。

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
| DevOpsAgent        | （已下线 2026-07-15）                                                | —                                                                            |
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

### 2026-07-13 定位扩展:文档 + 运维双职责

`project` 智能体由「软件工程项目文档智能体」扩展为「**项目文档与运维智能体**」,运维侧覆盖运维记录汇总、飞书同步、需求/修改单插入、主动/定时巡检。

**最终状态**:

- `agents` 表 `display_name` = `项目文档与运维智能体`
- `agents` 表 `description` = `负责软件工程项目文档的查询、生成、更新与管理,以及项目运维记录汇总、飞书同步、需求/修改单插入、主动/定时巡检等运维管理工作`
- `agents` 表 `agents_md_path` = `agents/project/AGENTS.md`(路径未变)
- 入口文档 [agents/project/AGENTS.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/agents/project/AGENTS.md) 已重写,新增「运维类工具(占位)」与「占位运维工具说明」章节
- `seed_project_agent.py` 的 `PROJECT_AGENT_TOOLS` / `PROJECT_AGENT_SKILLS` 列表**未改动**,因此 `agents.tool_bindings` / `agents.skill_bindings` JSONB 字段内容保持不变
- `state_schema` / `context_schema` / `config_schema` 仍为空对象兜底

**5 个新增占位 SKILL.md**(仅作为定位扩展占位,未实现 `@tool`):

- [app/skills/ops-log-aggregate/SKILL.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/skills/ops-log-aggregate/SKILL.md) — 运维记录汇总(对应未来 `ops_log_aggregate` / `ops_log_query` 工具)
- [app/skills/feishu-sync/SKILL.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/skills/feishu-sync/SKILL.md) — 飞书 Open API 同步(对应未来 `feishu_notify` 工具,**被依赖基础能力**)
- [app/skills/requirement-ticket/SKILL.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/skills/requirement-ticket/SKILL.md) — 需求单插入(对应未来 `requirement_ticket_create` 工具)
- [app/skills/change-ticket/SKILL.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/skills/change-ticket/SKILL.md) — 修改单插入(对应未来 `change_ticket_create` 工具)
- [app/skills/ops-inspection/SKILL.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/skills/ops-inspection/SKILL.md) — 主动/定时巡检(对应未来 `inspection_run` 工具,定时模式对接 `TaskSchedulerService` 5 段 crontab)

**后续 PR 计划**(本轮**未做**):

1. 在 `app/shared/tools/skills/project/OpsTools.py` 中实现 5 个 `@tool`(`ops_log_aggregate` / `ops_log_query` / `feishu_notify` / `requirement_ticket_create` / `change_ticket_create` / `inspection_run`)
2. 接入飞书 SDK(`lark-oapi` 优先)并在 `app/requirements.txt` 中加依赖
3. 把 5 个占位 skill 加入 `seed_project_agent.py` 的 `PROJECT_AGENT_SKILLS`,把 5 个 `@tool` 加入 `PROJECT_AGENT_TOOLS`
4. 引入新数据库表(预计 `requirement_tickets` / `change_tickets` / `inspection_runs` / `inspection_items`)与对应 schema,同步追加到 `app/migrations/init_all_tables.sql`
5. 新增单测 `app/tests/shared/tools/skills/project/test_ops_tools.py`
6. 在 `app/core/config/settings.py` 中新增 `feishu_app_id` / `feishu_app_secret` / `feishu_default_chat_id` 等敏感配置,通过环境变量注入

**关键约束**(防止后续 PR 误改):

- 飞书 sync 是 `requirement-ticket` / `change-ticket` / `ops-inspection` 的**被依赖基础能力**,**必须先实现**
- 定时巡检模式必须复用现有 `TaskSchedulerService`,**不要**新建独立的定时任务服务
- 所有运维工具的输入数据(飞书账号/群组/工单编号/巡检结果)必须来自用户确认或系统实际产生,严禁虚构

**AGENTS.md 文档契约边界**(2026-07-13 反馈后修正):AGENTS.md 只写智能体**最终行为契约**(职责 / 工具 / 能力 / 触发词),**不**写变更过程/未做清单/后续 PR 计划。本轮起,本章节是这些"过程记录"的唯一存放处;`agents/project/AGENTS.md` 不再出现 "本轮调整/未做/留给后续 PR" 之类的描述。

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


