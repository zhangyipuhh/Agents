Current is conda environment

```bash
conda activate E:\laboratory\AI\Agents
```

Current project path is

```bash
cd E:\laboratory\AI\Agents\agent-user-mangerment\
```

Use as many skills and agents as possible to implement features

All code should follow clean code principles and maintain existing functionality

Comments need to be added after file generation. The comments should be in Chinese and need to include information about function parameters, return values, exceptions, etc.

## CSS Debugging Principles

1. **Prioritize Anomalous Data** — When any computed/live value clearly violates expectations (e.g., a button is 1528px inside a 60px container), immediately stop the current direction and explain this contradiction first.
2. **Don't Just Check Dimensions, Check Position** — `getBoundingClientRect()` is better than `offsetWidth` for discovering "element exists but is moved out of viewport" issues. Always output width + x/y together.
3. **`overflow: hidden` + Centering = Common Hidden Root Cause** — `justify-content: center` pushes narrow icons to the center of wide containers, and `overflow: hidden` clips them. Prioritize checking this combination when investigating invisible elements.
4. **Trace the `width: 100%` Reference Chain** — `100%` is relative to the containing block, not the parent flex container. Check whether every ancestor in the chain has width constraints.
5. **Chase One Hypothesis at Most 3 Steps** — If the phenomenon remains unchanged after 3 modifications, change direction. If multiple consecutive modifications to the same property are ineffective, the root cause is not in that property.

## ⚠️ HARD RULE：project_memory.md 同步协议

**READ 阶段**：在执行任何 `Edit`/`Write` 工具之前，必须先调用 `Read('project_memory.md')` 读取项目记忆。

**WRITE 阶段**：每次 `Edit`/`Write` 工具调用后，必须评估"这次修改是否影响 `project_memory.md` 中的某个章节"：

- 是 → 立即调用 `Edit('project_memory.md', ...)` 同步
- 否 → 在回复结尾明确说明"无同步需要"

**触发清单**（以下任一情况都触发同步）：

- 新增 / 删除 / 重命名模块
- 修改数据库 schema（表结构、字段、索引）
- 改动 API 路由、请求/响应格式
- 改动前端组件、UI 架构、设计 token
- 改动部署配置、环境变量、Docker 配置
- 改动测试用例、测试覆盖率
- 其他架构层面变化（认证体系、提示词分层、Session/缓存策略等）

**强制约束**：

- **禁止使用 `Glob` 探测 `project_memory.md`**（本环境 Glob 工具索引不完整，对根目录文件返回 0 命中，会让 AI 误判文件不存在）
- 必须用 `Read` 工具直接读取
- 项目记忆同步必须在主任务回复中完成，**禁止在主任务之外另开新对话处理**
- 回复结尾必须输出 checklist：`[✓ project_memory.md 已同步]` 或 `[✗ 本次修改无 project_memory.md 同步需要：<理由>]`

# Project Memory

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
