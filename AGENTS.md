## Design Rules
- High cohesion and low coupling; unified entry/exit points, unified configuration entry, unified preloading—make everything configurable whenever possible.
- Database-intensive loading operations are completed during service startup, with configurations loaded into memory simultaneously; modifications and insertions must synchronize both memory and database.
- Design must prioritize asynchronous programming and performance optimization.
- All code should follow clean code principles and maintain existing functionality
- Comments need to be added after file generation. The comments should be in Chinese and need to include information about function parameters, return values, exceptions, etc.
- 基础设施降级（checkpointer / 缓存 / 存储回退内存模式等）必须 fail-loud：初始化失败要重试 + 告警日志 + 健康检查暴露降级状态；禁止静默降级。

## ⚠️ HARD RULE：agents/AGENTS.md 与 app/skills/SKILL.md 文档契约边界

**适用范围**:

- `agents/<agent>/AGENTS.md` —— 各智能体的入口契约文档(project / map_agent / knowledge_ydt / ...)
- `app/skills/<skill-name>/SKILL.md` —— 各 skill 的元数据与工作流文档(project-doc-* / ops-* / feishu-sync / ...)

**编写原则——只写最终结果**:

- ✅ **允许**写:智能体职责、工具清单与语义、skill 触发条件与工作流、参数契约、能力清单、最终生效的触发关键词
- ❌ **禁止**写:
  - "本轮调整/本次新增/本次扩展"等变更过程标记
  - "未做/未实现/留待后续 PR/请勿删除"等未做清单
  - 日期后缀(如「(2026-07-13 新增)」「(已实现)」)除非该日期属于工具/SKILL 本身的契约字段
  - 工具描述里的 `【占位】` 标记(在最终契约中,要么实现并删除占位标记,要么把占位工具从契约中删除,**不要让占位标记污染最终契约**——占位状态由 `seed_*_agent.py` / `ProjectTools.py` 真实代码反映,而不是 SKILL.md 文字)
  - 决策历史、迭代步骤、变更前后的对比

**过程记录的归属**:

- 变更过程、未做清单、PR 计划、决策历史**只**记录在 `project_memory.md`
- `git log` 负责保留完整的"何时/由谁/为什么"信息,不需要在 AGENTS.md / SKILL.md 重复

**反模式示例**(禁止):

```markdown
## 占位运维工具说明(2026-07-13 重要提示)
本轮调整**仅完成以下三件事**...
- ❌ 未在 ProjectTools.py 中新增任何 @tool
- ❌ 未真实接入飞书 Open API
```

**正例**(只写契约):

```markdown
## TOOL DESCRIPTION
### ops_log_aggregate
汇总项目运维记录(巡检结果、告警条目、人工处理记录)...
```

**审计清单**(每次新增/修改 `agents/**/*.md` 或 `app/skills/**/SKILL.md` 后必查):

- [ ] 是否包含日期后缀 / 变更过程标记 / 未做清单?如有 → 删除,迁到 `project_memory.md`
- [ ] 工具描述里是否有 `【占位】` 字样?如有 → 要么真正实现并删除,要么把工具从契约中删掉
- [ ] 标题里是否有 `(xxx 新增)` / `(已实现)` / `(本轮)`?如有 → 删除

## Path Management Rules

- **所有路径相关常量**（项目根、数据目录、知识库、临时文件、上传目录等）必须集中写在 `app/core/config/paths.py`。

## Frontend Vue Rules
- When developing frontend interfaces, prioritize using standalone template syntax first. This approach enhances maintainability and prevents syntax conflicts or rendering issues.
- When using `<style scoped>` in Vue 3 SFC, scoped CSS only applies to elements rendered by template syntax; elements created via `defineComponent` + `h()` render function within the `<script>` block will not automatically receive the `data-v-xxx` scopeId, causing all scoped CSS selectors to silently fail to match, resulting in completely ineffective layouts/styles with no error messages. Prioritize using standalone .vue files with `<template>` syntax.
- SPA 路由守卫中的重定向目标必须存在于路由表内；独立 HTML 入口（如 `/login`，刻意不进路由表）禁止用 `return { path }` 应用内跳转，只能用 `window.location.href` 整页跳转并 `return false` 终止导航（应用内跳转会被 catch-all 兜底弹回守卫，形成无限重定向循环：微任务链饿死 fetch 回调，页面白屏且主线程占满）。守卫逻辑应抽为具名导出函数（如 `requiresAuthGuard`）供测试直接调用真实实现。

## Nginx 静态资源与缓存规则

- 后端端口配置散布在多处且必须协调一致：`nginx/conf/nginx.conf` 的 `proxy_pass`、`web/Agent/vite.config.js` 的 `VITE_API_TARGET` 默认值、后端 `uvicorn --port` 启动参数；修改任一处必须同步核对其余点位，并确认对应进程真实重启（以 PID 为准）

- hash 指纹资产（`expires 1y` + `immutable` 长缓存）必须与 HTML 入口禁缓存（`location ~* \.html$`，`no-cache, no-store, must-revalidate`）成对配置；HTML 被浏览器缓存会引用已删除的旧 hash 资产导致白屏
- nginx location 优先级：精确匹配 `=` > 正则 `~*` > 前缀；新增正则缓存块后必须检查是否存在冲突的精确匹配块（如 `location = /index.html`）将其架空
- location 内一旦出现任何 `add_header`，server 级 `add_header`（CSP / HSTS / X-Frame-Options / X-Content-Type-Options / Referrer-Policy 等）全部不再继承，必须在该 location 内整块显式重复

## use subagents
- 派 explore/coder subagent 前，必须先查 `project_memory.md` 索引与相关分片；索引/分片已收录的事实（路由位置、组件结构、权限装饰器、表结构）直接引用，禁止重复探索
- 仅当探索目标未收录于项目记忆、且预估需要 >3 次搜索时才派 subagent；已知路径的读取与小范围搜索由主 agent 直接完成
- subagent 的 prompt 必须携带已知线索（文件路径、行号区间），禁止从零泛搜
## use skills rule
- Use as many skills and agents as possible to implement features


## Use PostgreSQL MCP

When querying the database, use this MCP to inspect table schemas and row data.


## Database rules

1. After any `Edit`/`Write` operation, check whether it is necessary to append content to `app\migrations\init_all_tables.sql`, including statements for adding new fields and statements for adding new tables

## Debug rules 
1. When troubleshooting any issues, first use PostgreSQL MCP to verify whether the error originates from database problems before investigating other causes.

## ⚠️ HARD RULE: 调试元认知规则(方法论级)

> 这些规则**不绑定任何具体领域**(网络 / 数据库 / 前端 / 业务逻辑 / 基础设施均适用),
> 约束的是排查故障时的**思考方式**,而不是某个具体技术点。
> 核心目标:避免「方向错了越改越糟」——用最少的修改、最快的验证定位真正的根因。

### 核心原则

**R1. 不要过早锁定单一假设**
- 面对任何异常,先列出多个(至少 3 个)可能根因,再决定调查顺序
- 对每个假设追问:「如果根因不是它,我应该能观察到什么反例?」
- 反例未排除前,不要急于修改代码

**R2. 追溯源头,不在症状点打补丁**
- 异常暴露的位置往往只是症状,真正的根因可能在上游若干层之外
- 沿数据流 / 调用链逐级回溯:`最终失败点 → 上游调用 → … → 输入源头`
- 修复应落在根因处,而不是在报错处掩盖它

**R3. 用反向证据检验假设**
- 提出假设后,主动设计「假设错误时必然出现的可观测信号」并去验证
- 一旦反向证据成立,立即放弃该假设,而不是「再加一个开关试试」

**R4. 区分信号与噪音**
- 故障现场常有多种信息并存(错误文本、耗时、退出码、日志等)
- 不要挑最显眼的线索归因,要挑**最具区分性**、最能排除其他假设的那条

**R5. 真实环境验证优先于理论推理**
- 涉及平台 / 版本 / 环境差异的问题,纯推理得出的「修复」往往是空中楼阁
- 优先在真实(或最小化复现)环境中观察实际行为,再动手修改

**R6. 先广度、后深度,失败即转向**
- 不熟悉的领域先广泛列出假设,不要一头扎进「最像的」那一个
- 同一方向连续多次(约 3 次)修改仍无效果 → 立即停止,回到 R1 重新列假设
- 方向错误时,修改得越多偏差越大;方向正确时,往往只需很小的改动

**R7. 否定证据比肯定证据更可靠**
- 「加了 A 之后问题消失」不能证明 A 是根因(可能是共同作用或巧合)
- 设计「撤销 A 后问题是否复现」的反向实验,才能确认因果关系

**R8. 反复失败时,真实环境复现是继续修改的前置条件**
- 当累计多次修改未果,或问题与环境差异强相关时:
  - 必须先在与故障一致的真实环境中**复现问题**,才允许继续修改
  - 复现失败 → 说明假设方向可能根本不对,回到 R1
  - 复现成功 → 修复也必须在同一真实环境中验证,不能只靠单元测试或 mock

**R9. 调试工具挂起本身是高区分度信号**
- evaluate / CDP / 截图等调试调用在目标页面上挂起,通常等价于「页面主线程被占满」(死循环 / 同步长任务),不要只当工具故障反复重试
- 主线程占满的页面典型伴随特征:白屏但标题正常、网络请求发一半断流(如 refresh 已发出、后续 validate 永不发出)、外部调试器全部无响应
- SPA 场景优先怀疑路由守卫无限重定向循环(守卫 redirect 目标不在路由表 → catch-all 兜底弹回 → 死循环)

**R10. 多入口行为不一致时,先核对进程/端口映射再查代码**
- 同一应用存在多个入口(如 nginx HTTPS / vite dev / IDE 调试实例)且行为不一致时,第一动作是确认各入口实际命中的后端进程:`netstat -ano | grep LISTENING` 查端口归属 PID,再用各进程日志中的请求记录验证请求落点
- 「重启了服务」不等于「重启了目标进程」:端口被旧进程占用时新进程无法接管,必须以 PID 为准核实
- 两个后端进程各自持有独立的内存态(如 MemorySaver checkpoint 单例),表现为「同一代码、一边有数据一边没有」,极易误判为配置或代码 bug

**R11. 浏览器侧前端加载/渲染异常,第一步是 DevTools 取证,不是改服务器配置**
- 前端异常(白屏 / 转圈 / 资源未加载)的根因大多在**浏览器安全策略**(CORS / CSP / Mixed Content / 模块加载 / HSTS / 证书链),curl / headless 模拟不还原这些策略
- **标准取证动作(30 秒内完成,优先于任何改配置)**:
  1. DevTools → **Console**:截图/拷贝所有红色错误。CORS 拒绝文案固定为 `Access to script at '…' from origin '…' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present.`,看到这条即可 100% 锁定 CORS 根因
  2. DevTools → **Network**:列出缺失或红色状态码的请求(main bundle / chunk / 资源)。模块加载失败时,请求可能**根本不发起**(network 面板无对应行)而非 4xx/5xx
  3. DevTools → **Application → Cookies**:确认关键 Cookie 是否被设置、Domain / Path / Secure / SameSite 是否匹配当前 origin
- 拿到上述截图/错误文案后再行动;**禁止在没看过 Console 的情况下连续改服务器配置 3 次以上**(违反 R6「失败即转向」)
- HTTP 与 HTTPS 的浏览器安全约束不同:同源 CORS 严格度、HSTS preload、Mixed Content、crossorigin module 加载要求 ACAO 等只对 HTTPS(或 HTTP→HTTPS 切换后)生效。Docker HTTP 下能跑不代表 HTTPS 下能跑(违反 R5「真实环境优先于理论推理」)

**R12. 浏览器对失败的请求有 network-level negative cache,服务侧修复后必须让用户硬刷新**
- CORS / CSP / Mixed Content / 证书错误 / 模块加载失败会被浏览器在 network 层记忆,后续 reload **不会重试**该资源;DevTools Network 也不显示新请求,表现为「我改了配置但用户还说没生效」
- **标准动作(改完服务端配置后)**:
  1. 服务端验证新响应头确实已下发(curl -I 看新 header,不要只看状态码)
  2. 让用户在浏览器端做**硬刷新**(`Ctrl+Shift+R` / `Cmd+Shift+R`)
  3. 若仍异常,DevTools → Network 勾选 **"Disable cache"** 后再刷新
  4. 极端情况:让用户清站点数据(DevTools → Application → Clear storage),或用无痕窗口打开
- **禁止在没让用户硬刷新的情况下,就判断「我的修改没生效」**(违反 R5 + R8「修复必须在同一真实环境验证」)

### 通用审计清单

排查或修复任何问题时,自检:

- [ ] 是否列出了多个候选根因,而非只盯着第一个想法?(R1)
- [ ] 修复是落在根因处,还是在症状点打补丁?(R2)
- [ ] 对当前假设,是否验证过「假设错误时应出现的信号」?(R3)
- [ ] 归因依据的是最具区分性的线索,还是最显眼的线索?(R4)
- [ ] 涉及环境差异的问题,是否做了真实环境验证?(R5)
- [ ] 同一方向是否已连续多次修改无果?该转向了吗?(R6)
- [ ] 验证用的是「撤销后是否复现」的强证据,还是「加上后刚好好了」的弱证据?(R7)
- [ ] 多次失败之后,是否先在真实环境复现再继续修改?(R8)
- [ ] 调试工具在目标页面挂起时,是否把它当作「主线程被占满」的信号而不是工具故障?(R9)
- [ ] 多入口行为不一致时,是否先 netstat 核对端口→PID→进程日志的映射,而非直接改代码?(R10)
- [ ] 浏览器侧加载/渲染类异常,是否在第一次改配置前就让用户提供了 DevTools Console + Network 截图?(R11)
- [ ] 修改涉及浏览器安全策略的配置后,是否要求用户硬刷新或在 DevTools 勾选 Disable cache?(R12)

## CSS Debugging Principles

1. **Prioritize Anomalous Data** — When any computed/live value clearly violates expectations (e.g., a button is 1528px inside a 60px container), immediately stop the current direction and explain this contradiction first.
2. **Don't Just Check Dimensions, Check Position** — `getBoundingClientRect()` is better than `offsetWidth` for discovering "element exists but is moved out of viewport" issues. Always output width + x/y together.
3. **`overflow: hidden` + Centering = Common Hidden Root Cause** — `justify-content: center` pushes narrow icons to the center of wide containers, and `overflow: hidden` clips them. Prioritize checking this combination when investigating invisible elements.
4. **Trace the `width: 100%` Reference Chain** — `100%` is relative to the containing block, not the parent flex container. Check whether every ancestor in the chain has width constraints.
5. **Chase One Hypothesis at Most 3 Steps** — If the phenomenon remains unchanged after 3 modifications, change direction. If multiple consecutive modifications to the same property are ineffective, the root cause is not in that property.

## ⚠️ HARD RULE: 项目记忆分级读取与同步协议

**记忆结构**: `project_memory.md` 是**索引**（≤ 200 行），正文拆分为 `memory/` 目录下的主题分片（architecture / database / api-routes / auth / agents-skills / mcp / frontend / menu-acl / devops-sandbox / misc）。历史全文归档在 `memory/_archive/project_memory_full.md`，仅兜底使用，正常禁止读取。

**READ Phase（分级读取，禁止全量复读）**:

- L0：会话内首次涉及修改 → 只读 `project_memory.md`（索引）
- L1：按任务关键词在索引中定位 1~2 个相关分片 → 只读相关分片
- L2：分片内查找 → 优先 Grep 分片文件，再按行号区间 Read，禁止顺序翻页读取整个分片
- 会话内已读过的分片不重复读；会话内自己写入的内容视为已知最新，不复读

**WRITE Phase**: After each `Edit`/`Write` operation, evaluate whether the change affects any chapter:

- Yes → 只 Edit 对应分片（`memory/<shard>.md`），并更新索引 `project_memory.md` 中对应行的「更新时间」列；新增章节时若无合适分片，在 `memory/` 新建分片并在索引登记一行
- No → Explicitly state at the end of the response: "No sync needed."

**What to Record**: Only record the **final/current state**. Do **not** record the change process, decision history, or iterative steps. For example, if an API endpoint changes, document only its final signature and behavior. Retrieve historical process via `git log` if needed.

**Trigger List** (synchronization is required if any of the following occurs):

- Adding / deleting / renaming modules
- Modifying database schema (tables, fields, indexes)
- Changing API routes, request/response formats
- Changing frontend components, UI architecture, design tokens
- Changing deployment config, environment variables, Docker configuration
- Changing test cases, test coverage
- Other architectural changes (authentication, prompt layering, session/cache strategy, etc.)

**Mandatory Constraints**:

- **Do not use `Glob` to probe `project_memory.md` or `memory/` shards** (the Glob tool index is incomplete in this environment and may return 0 hits, which may mislead the AI into thinking files do not exist).
- You must use the `Read` tool to read the index and shards directly.
- Project memory synchronization must be completed within the main task response. **Do not start a separate conversation to handle it.**
- At the end of the response, output the checklist: `[✓ project_memory.md synchronized]` or `[✗ No project_memory.md sync needed: <reason>]`.

## Project Memory

- 修改前通过 `project_memory.md` 索引定位并读取相关 `memory/` 分片，获取项目架构、功能模块、数据库设计等关键信息（分级读取规则见上方 HARD RULE）
- When modifying code, make changes based on the information in project memory to ensure modifications do not affect the normal operation of the project.
- After modifying code, update the corresponding memory shard to ensure it remains consistent with the actual project status.
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

**重要约束**：执行 `Edit`/`Write` 操作后，若功能发生变更，必须同步检查对应测试文件是否需要更新。测试文件必须与源码变更保持一致，禁止出现「源码已改、测试未动」的不一致状态。

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
- 禁止在测试中重新实现被测逻辑再断言（假测试）：测试必须调用真实实现；被测对象不便导入时，应将被测逻辑抽为具名导出函数/模块供测试直接调用
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
- [ ] 测试失败时是否先问「这是生产 bug 还是测试 bug？」而不是「怎么 Mock 掉这个错？」？
- [ ] 历史兼容 fixture 是否在 docstring 标注「仅历史兼容」+ 在 `project_memory.md` 写入待办？

## ⚠️ HARD RULE：测试 fake 必须模拟依赖的完整语义

**核心原则**：fake（手工构造的 `asyncpg.Connection` / `requests.Session` / 任何第三方客户端替身）**只模仿协议形状**（方法签名 + 返回值结构）是不够的——它还必须模仿**该依赖在真实运行时的约束与失败模式**。否则生产里"参数编码层 / TLS 校验 / 大小限制"等会抛错的环节，会被 fake 完全旁路，导致「**生产崩溃、测试全绿**」。

**典型反模式（2026-08-08 MFA 绑定 401 案例）**：

- 生产 `mfa_service.py::confirm_login_enrollment` 把 `datetime.now(timezone.utc)`（**aware**）直接写入 PG `user_mfa_totp.enabled_at`（**TIMESTAMP 朴素列**）
- 测试 `_FakeConnection.execute()` 只调 `_dispatch_execute(sql, args)`，把 `args[1]` 原样塞进 `totp_row["enabled_at"]` 字典，**完全绕过** asyncpg 的 `_encode_bind_msg` 参数编码层
- 后果：测试 100% 通过，但生产 asyncpg 抛 `DataError: invalid input for query argument $2: ... (can't subtract offset-naive and offset-aware datetimes)` → 被 `auth_middleware` 的 `try/except Exception` 吞掉 → 用户看到 `401 Unauthorized`
- 根因：fake 模拟的是"**调用通过 + 数据落库**"这一**结果**，但没模拟"**编码/校验/约束**"这一**过程**

**硬约束**：

1. **fake 必须明确分类**：在 docstring / 类型注解里标注它模拟的是「形状层」还是「完整语义层」。形状层 fake 仅用于路由断言 / 数据结构校验；涉及**参数编码、类型校验、安全约束、协议版本**等场景，必须用「完整语义层」fake 或真依赖。

2. **强制 hook 扩展点**：所有 fake 基类（如 `_FakeConnection` / `_FakeHttpClient`）必须预留 `_check_<依赖语义>` 类的方法（如 `_check_bind_args`），由子类按需 override。基类默认实现为 `pass`（保持向后兼容），但**涉及真实约束的 fake 子类必须 override**。禁止把所有约束都堆在 `_dispatch_execute` 里——那本质是「**只断言成功路径**」。

3. **测试必须包含反向用例**：对每个受 fake 影响的"真实约束"（如 aware datetime → naive 列），必须有 `pytest.raises(...)` 反向测试证明 fake 能捕获该 bug。**仅正向断言 happy path = 100% 漏检真生产 bug**。

4. **禁用"`happy path only`" fake 应付 SQL/调用顺序测试**：常见借口是"我只测 SQL 文本 + 字段名匹配"。这是上一条"测试全绿、生产崩溃"案例的精确根因。**只要生产代码把数据写入某列，fake 必须能识别"列类型 ↔ 参数类型"约束**。

5. **发现"测试过、生产崩"反模式时**：先怀疑 fake 缺约束校验，再考虑"要不要补集成测试"。补 fake 的 hook 成本远低于"补集成测试 + 找真 PG 跑"。

**反例 → 正例对照**：

| 反例（fake 不模拟约束） | 正例（fake 模拟完整语义） |
|---|---|
| `_FakeConnection.execute(sql, args)` 直接调 `_dispatch_execute`，把 `args` 原样塞字典 | `_FakeConnection.execute` 先调 `_check_bind_args(sql, args)`，子类 override 检测 aware datetime 写入 naive 列时抛 `DataError` |
| `_FakeHttpClient.get(url)` 返回固定 JSON，不校验 URL scheme / Host 头 | `_FakeHttpClient` override `_check_request`，对 `file://` 或恶意 host 抛异常 |
| `_FakeRedis.set(key, value)` 直接塞 dict，不校验 value 序列化格式 | `_FakeRedis.set` 调 `_check_serialize`，对不可 pickle 的对象抛 `TypeError` |
| 测试仅断言"传 naive datetime 能正常落库" | 测试同时断言"传 aware datetime 必抛 DataError"，证明 fake 真能捕获类型冲突 |

**审计清单**（每次新增 fake / 修改 fake 子类后必查）：

- [ ] fake 的 docstring 是否明确标注「形状层 / 完整语义层」？
- [ ] 涉及真实约束的 fake 子类是否 override 了对应的 `_check_*` hook？
- [ ] 该 fake 影响的关键生产 bug 是否有反向测试（`pytest.raises`）证明 fake 能捕获？
- [ ] `args` / `params` / `headers` / `body` 等敏感输入是否在进入 fake 主路径前已经过类型 / 编码校验？
- [ ] fake 的"成功路径"测试通过 ≠ fake 的"失败路径"也覆盖了吗？（happy path only = 反模式）

## Skill 系统使用规范（2026-06-21 落地，v2）

> **详情**：路径约定、frontmatter 格式、模块位置、与 opencode 差异、API 列表等完整信息见 `memory/agents-skills.md` 的 "Skill 系统" 章节。本节只列**操作硬约束**。

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

## 菜单管理规则（2026-07-23 新增）

本节给出菜单的"操作规则"。具体设计（字段定义、注册表位置、API 契约、ACL 表结构等）
见 `memory/menu-acl.md` 的 "用户菜单权限管理" 章节。

### 新增菜单
1. 在 `app/core/menu_registry.py::MENU_CATALOG` 追加一条 `MenuItem` 注册项
2. 在 `web/Agent/src/components/UserSettingsDialog.vue` 的 `NAV_MENU_METADATA` 加对应元数据（label + icon）
3. 如需独立 tab 渲染区，在 `UserSettingsDialog.vue` 模板加 `<div v-show="activeTab === '<id>'">` 块
4. 完成——菜单管理 UI 自动出现该项，admin 可在「权限管理 → 菜单管理」勾选授权

### 修改菜单（重命名 / 移动层级 / 改图标 / 改排序）
- 可改：`label` / `icon_key` / `sort_order` / `level` / `parent_id` / `required_role` / `enabled`
- **id 永不改**（id 是身份，改 id = 删菜单 + 建菜单，老 ACL 全部失效）
- 授权数据全自动保留，无需任何迁移脚本

### 下架菜单
将 `MenuItem.enabled` 置为 `False`——菜单管理 UI 隐藏，老授权记录保留不删

### 禁止事项
- ❌ 在 `UserSettingsDialog.vue` 硬编码菜单列表（必须从 `visibleMenus` prop 派生）
- ❌ 私自改动 `MENU_CATALOG` 中现有条目的 `id`
- ❌ 绕过 `MenuPermissionService` 直接读写 `user_menu_acl` 表
- ❌ 在前端维护菜单 icon/svg path 副本（统一用 `icon_key`，在前端图标组件里映射）

## 等保三级安全编码规范

> 本章节依据 GB/T 22239-2019 应用层面要求制定，是项目编码的**强制性安全约束**。所有后续代码变更、Agent 工具实现、路由/菜单/数据访问逻辑必须无条件遵守；任何与下述条款冲突的实现必须被拒绝并要求修正。具体技术实现细节见 `memory/auth.md`、`memory/menu-acl.md`、`memory/architecture.md`；完整合规检查清单见 `memory/security-compliance.md`。

### 身份鉴别

- 口令复杂度：后端必须校验长度≥8、大小写+数字+特殊字符，禁止仅靠前端正则。
- 登录失败处理：连续失败≥5 次锁定账户≥30 分钟，后端实现防暴力破解与防枚举。
- 会话超时：Access Token 有效期≤30 分钟；Refresh Token 通过 HttpOnly Cookie 传递。
- 双因素认证：管理员/运维账号必须支持双因素（短信/令牌/指纹等）。
- 传输加密：所有身份鉴别信息（口令、Token）必须走 HTTPS，禁止明文传输。
- 用户唯一标识：一人一账号，禁止共享账号；JWT payload 必须包含稳定 user_id。

### 访问控制

- 最小权限原则：所有路由、菜单、工具、Agent 可见性按最小权限设计。
- 权限分离：区分系统管理员、审计管理员、业务操作员，禁止超级管理员一权独大。
- 默认拒绝：未显式授权的路径/菜单/数据默认拒绝访问（白名单机制）。
- 敏感操作二次授权：权限变更、关键配置修改、强制下线等操作需复核或二次确认。
- 数据层隔离：普通用户访问配置/数据时必须通过 `OwnershipScope` 过滤；越权按 404 处理，不泄露记录存在性。
- 端点与菜单 ACL 对齐：路由守卫使用的 `require_admin_or_menu_acl(menu_id)` 必须与所服务的 tab 粒度一致。

### 安全审计

- 统一审计入口：所有重要操作（登录、退出、增删改、权限变更、SSH 执行）必须通过 `LogService.emit` 写入。
- 审计字段完整：每条记录必须包含用户 ID、用户名、时间、IP、操作类型、操作对象、结果。
- 留存时间：审计日志留存≥6 个月，生产环境禁止物理删除或覆盖。
- 防篡改：审计记录独立存储，仅审计管理员可读；日志内容禁止回显口令、Token、私钥等敏感字段。
- 脱敏规范：命令、URL userinfo、Authorization、Cookie、各类 password/secret/key 必须脱敏后落库。

### 入侵防范

- 输入校验：所有用户输入在后端做白名单校验，前端校验仅作为 UX 辅助。
- XSS 防护：渲染用户可控内容必须使用 DOMPurify/安全 marked；CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy 必须在网关层配置。
- SQL 注入防护：必须使用参数化查询/预编译语句，禁止字符串拼接 SQL。
- 命令注入防护：禁止直接把用户输入拼入系统命令；SSH 工具必须通过 `CommandInterceptor` 黑白名单过滤。
- 文件上传安全：限制文件类型、大小、路径；禁止上传可执行文件；上传目录不可执行；使用路径规范化防止 `../` 遍历。
- 漏洞管理：新增依赖必须审查版本与 CVE；高危漏洞修复周期≤7 天。
- 异常响应：统一错误处理，禁止向客户端暴露堆栈、SQL、服务器路径、密钥名等内部信息。

### 恶意代码防范

- 用户提交内容过滤：富文本/用户输入中的危险标签与事件处理器必须过滤。
- 前端资源完整性：CDN 引入的 JS/CSS 必须使用 SRI（Subresource Integrity）。
- 依赖审查：第三方组件/开源库纳入版本管理和安全审计；定期执行 `npm audit` / `pip audit` 等扫描。

### 数据保密性

- 全站 HTTPS：禁止 HTTP 入口；配置 301 跳转、HSTS（max-age≥31536000）、禁用 TLS 1.0/1.1 与弱加密套件。
- 敏感数据存储加密：口令使用 bcrypt/Argon2；身份证、银行卡、密钥等使用 AES 加密存储。
- 密钥管理：加密密钥必须存储在 KMS/HSM 或独立环境变量，禁止硬编码在源码或日志中。
- Token 安全：Access Token 仅存内存；Refresh Token 哈希入库；Cookie 设置 HttpOnly、Secure、SameSite=Strict。

### 剩余信息保护

- 会话失效：用户退出/密码修改/被强制下线时，服务端必须立即使 Refresh Token 失效并清除相关 Cookie。
- 客户端清理：登出后前端必须清理 localStorage/sessionStorage 中的会话标识与敏感缓存。
- 内存清理：临时解密数据、密码输入等敏感值使用完毕后应立即置空或缩短生命周期，避免长时间驻留内存。

### 个人信息保护

- 最小必要原则：仅采集业务必需的个人信息，禁止过度收集。
- 授权同意：采集个人信息前必须获得用户明确授权，禁止默认勾选。
- 禁止对外提供：未经授权不得向第三方接口、日志、测试环境输出个人信息。
- 用户权利：必须支持用户查询、更正、删除其个人信息。
- 日志脱敏：审计日志与系统日志中不得出现明文手机号、身份证、邮箱等个人敏感信息。