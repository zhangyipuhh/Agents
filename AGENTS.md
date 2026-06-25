## Design Rules
- High cohesion and low coupling; unified entry/exit points, unified configuration entry, unified preloading—make everything configurable whenever possible.
- Database-intensive loading operations are completed during service startup, with configurations loaded into memory simultaneously; modifications and insertions must synchronize both memory and database.

## use subagents
Use as many subagents  as possible to speed up
## use skills rule
Use as many skills and agents as possible to implement features

All code should follow clean code principles and maintain existing functionality

Comments need to be added after file generation. The comments should be in Chinese and need to include information about function parameters, return values, exceptions, etc.
## Use PostgreSQL MCP

When querying the database, use this MCP to inspect table schemas and row data.


## Database rules

1. After any `Edit`/`Write` operation, check whether it is necessary to append content to `app\migrations\init_all_tables.sql`, including statements for adding new fields and statements for adding new tables

## Debug rules 
1. When troubleshooting any issues, first use PostgreSQL MCP to verify whether the error originates from database problems before investigating other causes.

## CSS Debugging Principles

1. **Prioritize Anomalous Data** — When any computed/live value clearly violates expectations (e.g., a button is 1528px inside a 60px container), immediately stop the current direction and explain this contradiction first.
2. **Don't Just Check Dimensions, Check Position** — `getBoundingClientRect()` is better than `offsetWidth` for discovering "element exists but is moved out of viewport" issues. Always output width + x/y together.
3. **`overflow: hidden` + Centering = Common Hidden Root Cause** — `justify-content: center` pushes narrow icons to the center of wide containers, and `overflow: hidden` clips them. Prioritize checking this combination when investigating invisible elements.
4. **Trace the `width: 100%` Reference Chain** — `100%` is relative to the containing block, not the parent flex container. Check whether every ancestor in the chain has width constraints.
5. **Chase One Hypothesis at Most 3 Steps** — If the phenomenon remains unchanged after 3 modifications, change direction. If multiple consecutive modifications to the same property are ineffective, the root cause is not in that property.

## ⚠️ HARD RULE: project_memory.md Synchronization Protocol

**READ Phase**: Before executing any `Edit`/`Write` operation, you must first call `Read('project_memory.md')` to load the project memory.

**WRITE Phase**: After each `Edit`/`Write` operation, evaluate whether the change affects any chapter in `project_memory.md`:

- Yes → Immediately call `Edit('project_memory.md', ...)` to synchronize.
- No → Explicitly state at the end of the response: "No sync needed."

**What to Record**: Only record the **final/current state** in `project_memory.md`. Do **not** record the change process, decision history, or iterative steps. For example, if an API endpoint changes, document only its final signature and behavior. Retrieve historical process via `git log` if needed.

**Trigger List** (synchronization is required if any of the following occurs):

- Adding / deleting / renaming modules
- Modifying database schema (tables, fields, indexes)
- Changing API routes, request/response formats
- Changing frontend components, UI architecture, design tokens
- Changing deployment config, environment variables, Docker configuration
- Changing test cases, test coverage
- Other architectural changes (authentication, prompt layering, session/cache strategy, etc.)

**Mandatory Constraints**:

- **Do not use `Glob` to probe `project_memory.md`** (the Glob tool index is incomplete in this environment and returns 0 hits for root-directory files, which may mislead the AI into thinking the file does not exist).
- You must use the `Read` tool to read it directly.
- Project memory synchronization must be completed within the main task response. **Do not start a separate conversation to handle it.**
- At the end of the response, output the checklist: `[✓ project_memory.md synchronized]` or `[✗ No project_memory.md sync needed: <reason>]`.

## Project Memory

- Read project key information through project_memory.md before modification, including project architecture, functional modules, database design, etc.
- When modifying code, make changes based on the information in project_memory.md to ensure modifications do not affect the normal operation of the project.
- After modifying code, update the information in project_memory.md to ensure it remains consistent with the actual project status.
- After modifying code, test the project functionality to ensure modifications do not affect the normal operation of the project.

---

## 🔧 工具环境说明：Glob 工具索引不完整

**重要**：本环境（Trae sandbox）中的 `Glob` 工具对以下目标**返回 0 命中**，但 `Get-ChildItem`（PowerShell 真实枚举）能正常看到：

| 目标                                                                                        | 状态        |
| ------------------------------------------------------------------------------------------- | ----------- |

**强制约束**：

- 文件操作优先使用 `Write`/`Edit`，禁止用 `echo`/`cat`/`sed` 等 shell 命令
- 搜索文件优先使用 `Glob`/`Grep`，禁止用 `find`/`grep` 等 shell 命令
- 读取文件优先使用 `Read`，禁止用 `cat`/`head`/`tail` 等 shell 命令

## ⚠️ HARD RULE：测试同步协议

**READ 阶段**：在执行 `Edit`/`Write` 修改 `app/` 目录下的 `.py` 文件之前，应先了解对应模块是否已有测试文件及其测试风格。

**WRITE 阶段**：每次 `Edit`/`Write` 工具调用修改 `app/` 目录下的 `.py` 文件后，必须评估"本次修改是否引入了需要测试的新功能"：

- 是 → 立即在 `app/tests/` 对应位置生成或更新测试文件
- 否 → 在任务回复结尾明确说明 `[✗ 本次修改无测试同步需要：<理由>]`

**触发清单**（以下任一情况都视为引入新功能，需要同步测试）：

- 新增函数、方法、类或 Pydantic 模型
- 新增 FastAPI 路由端点（`@router.get/post/put/delete`）
- 新增 Agent 工具函数（被 `@tool` 装饰的函数）
- 新增业务逻辑分支（新的 if/else 路径、新的异常抛出点）
- 新增数据库操作方法（CRUD 函数）
- 新增配置文件项且伴随读取/使用逻辑

**不触发清单**（以下情况无需追加测试）：

- 仅修改注释、文档字符串、日志文本
- 仅重命名变量（无行为变化）
- 仅调整代码格式、换行、空格
- 纯 bug 修复且未改变原有接口契约（仍应验证现有测试通过）

**测试文件路径映射**：

```
app/{module}/foo.py          →  app/tests/{module}/test_foo.py
app/{module}/bar/baz.py      →  app/tests/{module}/bar/test_baz.py
```

- 若对应测试目录不存在，需先创建目录（含 `__init__.py`）
- 测试文件命名：`test_{源文件名小写转换}.py`
- 测试函数命名：`test_{被测对象}_{场景}_{预期结果}`

**最低测试内容要求**：

| 优先级 | 测试类型 | 说明 |
|-------|---------|------|
| P0 | 导入/存在性 | `test_{对象}_importable` / `test_{对象}_exists` |
| P1 | 成功路径 | 正常输入下功能按预期工作 |
| P1 | 失败路径 | 异常输入下抛出预期异常或返回预期错误 |
| P2 | 边界条件 | 空值、极值、越界等（如适用） |

**代码风格要求**（与现有测试保持一致）：

- 文件首行：`# -*- coding:utf-8 -*-`
- 模块级 docstring（中文，说明测试目标）
- 函数级 docstring（中文，说明参数、返回值、异常）
- 使用 `pytest.raises` 验证异常
- 使用 `monkeypatch` / `unittest.mock.patch` 进行 Mock
- 路由测试使用 `client` fixture（来自 conftest）
- 异步测试使用 `asyncio.run()` 包装

**强制约束**：

- 测试同步必须在主任务回复中完成，**禁止在主任务之外另开新对话处理**
- 生成测试后必须执行 `pytest app/tests/对应路径 -v` 验证通过
- 若测试失败，需修复源码或测试直至通过
- 最终回复必须包含 checklist：`[✓ 测试已同步生成并通过]` 或 `[✗ 本次修改无测试同步需要：<理由>]`

## ⚠️ HARD RULE：禁止在测试中虚构生产不存在的依赖

**核心原则**：测试是生产的镜像，不是生产的补丁。**绝不允许**通过 `conftest` / `fixture` 注入生产环境（`lifespan` / 启动钩子）**根本不会初始化**的对象来让测试通过——这是掩盖真实 bug 的反模式，会让「测试全绿、生产崩溃」成为常态。

**典型反模式（2026-06-24 agent_admin_router 401 案例）**：

- 生产 `app/routers/agent_admin_router.py::list_agents` 访问 `request.app.state.db`，但 `app/core/server.py` 的 `lifespan` **从未初始化** `app.state.db`（只初始化了 `agent_config_service` / `mcp_config_service` / `mcp_registry`）
- 测试 `app/tests/routers/conftest.py::_init_db` 用 `app.state.db = MagicMock()` 让路由代码"看似"能跑
- 后果：测试 100% 通过，但生产抛 `AttributeError: 'State' object has no attribute 'db'` → 被 `auth_middleware` 的 `try/except Exception` 吞掉 → 用户看到 `401 Unauthorized`
- 根因：测试用 Mock **虚构**了一个生产中根本不存在的对象，把「lifespan 漏初始化」与「路由错误直接访问 app.state」两层 bug 一起掩盖

**硬约束**：

1. **依赖一致性检查（必做）**：写测试前，先 `Grep` 生产启动路径（`app/core/server.py` lifespan / `app/main.py` `register_routers` / 所有 `app.state.*` 赋值点）确认目标对象在生产**真的会存在**。如不存在 → **先修生产代码**（补 lifespan 或改走 service 层），再写测试。

2. **禁止用 Mock 填补生产空洞**：
   - ❌ `app.state.xxx = MagicMock()` 但生产 lifespan 没初始化 `xxx`
   - ❌ `monkeypatch.setattr("module.yyy", MagicMock())` 但生产代码根本不调 `module.yyy`
   - ✅ 修补生产 `lifespan` 让对象真实存在，再在测试 fixture 注入**真实实例**（即使是 `db=None` 的 stub service）；或重构代码让生产根本不依赖该对象

3. **autouse fixture 必须有生产对等物**：每个 `autouse=True` fixture 都必须在 docstring 明确指向「生产中谁负责初始化这个对象」（lifespan / 启动钩子 / 中间件）。如果只是为了「让测试跑起来」注入 MagicMock → **删除该 fixture** 或改为显式 opt-in（不 autouse）。

4. **测试失败时优先怀疑生产 bug**：测试抛 `AttributeError: 'State' object has no attribute 'xxx'` / `AttributeError: 'NoneType' object has no attribute 'yyy'` 时，**先 `Grep` 生产是否真的会初始化 `xxx` / `yyy`**，不要先想「怎么 Mock 掉这个错」。

5. **历史兼容 fixture 必须标注 + 给出移除时间表**：`@pytest.fixture(autouse=True)` 注入 MagicMock 的兼容 fixture 必须在 docstring 显式标注「仅供历史兼容」「生产未初始化此对象」「如未来路由错误地直接访问此对象，生产仍会 AttributeError」，并写入 `project_memory.md` 待办，给出移除时间表。

**反例 → 正例对照**：

| 反例（掩盖 bug） | 正例（暴露并修复 bug） |
|-----------------|---------------------|
| `_init_db` 注入 `app.state.db = MagicMock()` 让路由通过 | ① 修 `lifespan` 让 `app.state.db` 真实存在；② 或改路由改走 `service._db`，让 `app.state.db` 不再被需要；③ 测试 fixture 注入**真实 service 实例**（如 `AgentConfigService(db=None, agents_md_loader=AgentsMdLoader())`）|
| 测试 `monkeypatch.setattr("xxx", Mock())` 让 import 不报错 | 让生产代码 `try/except ImportError` 优雅降级，或把 import 移到运行时 |
| 测试 fixture 注入生产 lifespan 不创建的对象 | 删除 fixture，改让测试显式 `monkeypatch` 业务方法（按需 opt-in） |

**审计清单**（每次新增/修改 `app/tests/**/conftest.py` 后必查）：

- [ ] 每个 `autouse=True` fixture 是否有生产对等初始化点？（`Grep "app.state.<attr>" app/core/server.py app/main.py` 验证）
- [ ] 是否有 `MagicMock()` 直接挂在 `app.state.*` 上？（如有不属于 stub service 的 → 删除或迁移到 service 层）
- [ ] 测试失败时是否先问「这是生产 bug 还是测试 bug？」而不是「怎么 Mock 掉这个错？」
- [ ] 历史兼容 fixture 是否在 docstring 标注「仅历史兼容」+ 在 `project_memory.md` 写入待办？

## Skill 系统使用规范（2026-06-21 落地，v2）

> **详情**：路径约定、frontmatter 格式、模块位置、与 opencode 差异、API 列表等完整信息见 [`project_memory.md` "Skill 系统" 章节](file:///e:/laboratory/AI/Agents/feature-agent-core/project_memory.md)。本节只列**操作硬约束**。

- **硬约束**：**禁止** 使用 `<system-reminder>` 标签包装 skill 内容（项目 `BASE_SYSTEM_PROMPT:54` 已声明其为 LangChain 运行时系统提醒专用，不能用作业务包装层）。
- **硬约束**：bootstrap 优先级链（从高到低）**禁止** 任意颠倒：
  1. `app/features/<agent>/config/bootstrap.md`（子智能体）
  2. `settings.skills_bootstrap_path`（用户自定义全局）
  3. `app/core/skills/bootstrap.md`（系统默认）
  4. 代码内置 `_FALLBACK_TOOL_MAPPING`（最后兜底）
- **硬约束**：子智能体维度一旦存在 `app/features/<agent>/skills/` 目录，会**完全覆盖**全局默认根扫描（仅扫描该目录，不追加 `app/skills` 与 `.agents/skills`）。添加新全局 skill 时**必须**确认目标子智能体 skills/ 是否已存在，避免被静默覆盖。
- **测试命令**：`pytest app/tests/core/skills/ -v`

# langchain使用说明

- **凡涉及 LangChain / LangChain-Core / LangGraph / LangSmith / LangMem / deepagents 的 API 使用**，必须通过 **context7 MCP** 查找对应官方文档后再调用，禁止凭记忆使用旧版本 API。
- 优先查询顺序：
  1. `usecontext7_mcp` → `get-library-docs` 拉取目标库的最新 docs（如 `/langchain-ai/langchain`、`/langchain-ai/langgraph`）
  2. 命中失败再降级 WebSearch + 官方文档站（`https://python.langchain.com/`、`https://langchain-ai.github.io/langgraph/`）
- 版本兼容注意：项目使用 **LangChain 1.x + LangGraph 1.x**（旧版 0.x 的 `create_react_agent`、`AgentExecutor`、`LLMChain` 等签名已变更，迁移文档参考 context7 `/langchain-ai/langchain` 的 v1 migration guide）
- 更新 `app/requirements.txt` 时，必须同步更新本表版本号，避免文档查错版本