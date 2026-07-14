<div align="center">

# Agent Core

**面向 LLM · RAG · Agent 场景的企业级智能体运行框架**

<table align="center">
  <thead>
    <tr>
      <th align="center">🧠 核心框架</th>
      <th align="center">🤖 LLM Provider</th>
      <th align="center">🛠️ 基础设施</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td align="center">
        <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"><br>
        <img src="https://img.shields.io/badge/LangGraph-1.1.10-FF4D6D?style=flat-square" alt="LangGraph"><br>
        <img src="https://img.shields.io/badge/LangChain-1.2.16-1C3C3C?style=flat-square" alt="LangChain"><br>
        <img src="https://img.shields.io/badge/Pydantic-2.12.5-E92063?style=flat-square" alt="Pydantic"><br>
        <img src="https://img.shields.io/badge/FastAPI-0.128.0-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
      </td>
      <td align="center">
        <img src="https://img.shields.io/badge/OpenAI-2.14.0-412991?style=flat-square" alt="OpenAI"><br>
        <img src="https://img.shields.io/badge/Anthropic-0.97.0-D4A574?style=flat-square" alt="Anthropic"><br>
        <img src="https://img.shields.io/badge/DeepSeek-1.0.1-0066CC?style=flat-square" alt="DeepSeek"><br>
        <img src="https://img.shields.io/badge/Ollama-0.6.1-000000?style=flat-square" alt="Ollama">
      </td>
      <td align="center">
        <img src="https://img.shields.io/badge/asyncpg-0.31.0-FF6B6B?style=flat-square" alt="asyncpg"><br>
        <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL"><br>
        <img src="https://img.shields.io/badge/MCP-1.27.1-000000?style=flat-square" alt="MCP"><br>
        <img src="https://img.shields.io/badge/Docker-7.1.0-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
      </td>
    </tr>
  </tbody>
</table>

<p align="center">
  🚀 基于 <b>LangGraph v1.0</b> + <b>LangChain</b> · 多 Provider LLM 工厂 · 三层提示词协议 · SSE 流式策略 · MCP 工具生态
</p>

</div>

---

<details>
<summary>📚 一句话能力摘要</summary>

通用智能体运行框架 · **典型业务场景：`project` 智能体**（项目文档 + 项目运维双职责）· 多 LLM Provider 适配 · 三层提示词协议 · 消息裁剪与多模态提取 · SSE 流式策略 · 异步并发队列 · 文件分片上传 · 异步连接池 · FastAPI 应用工厂 · MCP / 子智能体 / HITL 工具生态 · 双 Token 认证 · 图形验证码 · 用户 / 角色管理 · 强制下线 · 审计日志

**🔌 接入方式**

- AI 编程工具：MCP 协议 — 任意 LangChain / LlamaIndex / 自研 Agent 框架
- 业务子图：`Agent` 基类 + `AgentConfig` + `AgentContext` 三件套继承即用（已落地 `project` / `contract_*` / `audit_document` / `DevOps` / `AI_Coding_Check` / `Tagent` / `map_agent` 等实例）
- 开发集成：Python SDK · FastAPI · Docker Compose

</details>

---

## 📋 更新记录

- **2026.07 — 项目-会话解耦与文档缓存镜像大重构**  ⭐ 本月主线

  本次版本是一次 **端到端的大重构**：项目文件夹与会话完全解耦，配套完成 `relative_path` 数据模型、文档缓存镜像、文件下载链路与前端项目-会话分离交互；其余 Abort / AI 反馈 / 项目文档智能体 / Docker 沙箱部署等作为本次重构的支撑性进展。

  - **🏗️ 项目-会话解耦 + 文档缓存镜像（大重构主线）**（`91674de` → `a78a16b` → `5a9ae8f` → `ae6c5e9` → `f30efd1` → `6c398fd` → `ad5d393` → `658d5a7` → `f3792f9` → `3430532`）

    - **数据库 schema 改造**：`projects` 表新增 `relative_path VARCHAR(500)` 字段（`init_all_tables.sql`），后端按 `created_at` 自动生成 `data/project/yyyy/mm/dd/{uuid}/` 路径，`project_uuid` 不再由前端传入；旧记录启动时由 `_backfill_missing_relative_paths()` 一次性补齐
    - **路径常量集中化**：`app/core/config/paths.py` 新增 `resolve_project_dir(relative_path)` / `resolve_project_tmp_dir(relative_path)` / `resolve_tmp_mirror_path(original_path)` 三大解析器，作为项目根 / 项目缓存 / 文档镜像的唯一真相源
    - **后端 service / router 全链路改造**：`project_db` / `project_router` / `fileTransfer.delete_session` / `file_upload_router` 全部从「按 `project_uuid` 拼接路径」改为「读 `project['relative_path']` → 委托 `get_project_upload_dir(relative_path, create=False)`」，入参语义对齐
    - **沙箱写入与文档缓存镜像**：`DockerSandboxBackend.write/awrite` 改为在宿主机 Python 进程直接写入 workspace 并同步生成 `<项目根>/data/tmp/.../.md` 镜像，避免 `BaseSandbox.write` 在 Docker 容器内执行 preflight 路径检查时无法识别宿主机路径的问题；`filesystem_encoding_fix` 新增 `_patched_write` 并注册到 `apply_fix()`，写入 `pdf/docx/xlsx/md/txt` 时自动落 `.md` 镜像（其他扩展名直接读原文件）
    - **文件下载链路**：`SessionFileDrawer` + `FolderTree` 改造为按 `relative_path` 解析文件树，支持下载 `.md` 镜像（沙箱读）与原文件（前端直读），`merge-chunks` 与 `uploadfile` 的 project 分支同步更新为日期化目录格式
    - **前端项目-会话分离交互**：`ProjectDialog` 移除「新建项目立即建空文件夹」副作用，`Sidebar` 折叠/展开与会话完全分离；新增「项目删除 / 重命名」接口与侧边栏交互，`App.vue` 新建会话时自动重置 `currentProjectId = null` 避免串台
    - **项目选择器上传锁定**：`InputBox` 上传文件 → 自动锁定项目选择器（`658d5a7`），覆盖 `App.project-lock.spec.js` / `InputBox.upload-lock.spec.js`；`ad5d393` 修复 `App.vue` 新建会话时未重置当前项目的 bug
    - **重构影响面**：横跨 DB migration、路径常量层、5 个 service / router / 中间件、3 个前端组件 + 5 个单测；是 7 月最大的一次体系性改动
  - **Docker 沙箱部署与本地开发链路**（`099ce74` → `d34a651` → `d110b4e` → `8172f02` → `46ec043`）

    - `docker-compose.yml` 新增 `preview-app` 服务，挂载宿主机 docker socket 复用宿主机 daemon，web 服务加上 `8g` 内存 limit
    - `app/Dockerfile` + `dockers/sandbox/Dockerfile` 双镜像构建，`agents/` 目录支持开发模式热挂载
    - `.gitignore` 增补 sandbox / tmp_test_workspace 等条目，删除临时测试文件 `app/tmp_test_workspace/test.txt`（`d849c20`）
  - **用户主动 Abort 通道 + 停止待生效 UI**（`6ac9093` → `949b254` → `e5561de` → `f30efd1` → `3fc82c8` → `7c7a98e`）

    - `app/core/tools/_stop_signal.py` 新增模块级 `_abort_signals: dict[str, asyncio.Event]`，按 `session_id` 索引，`register_abort_signal` / `unregister_abort_signal` / `trigger_abort` 配套 API
    - 新增 `POST /api/agent/{session_id}/abort` 与 `POST /api/knowledge/{session_id}/abort` 端点（idempotent，未注册 session 返回 `not_found` 不报错）
    - `BaseFilesystemTool` / `SandboxTools` 检测顺序统一为「abort_event 优先 + is_disconnected 兜底」，每 N chunk 检查一次，触发后主动构造 `ToolMessage(stopped_by_user)` 返回，避免 orphan tool_calls 引发的 2013 错误
    - `agent_router` 新增 `/api/agent/list` 会话白名单，按需创建 session（修复未登录态下 sandbox 启动失败）
    - 前端 `App.vue` / `KnowledgeApp.vue` / `InputBox.vue` / `KnowledgeChat.vue` / `ProfileInputBox.vue` 新增「停止待生效」灰色占位状态，对应 `App.stop-pending.spec.js` / `InputBox.stop-pending.spec.js` / `KnowledgeChat.stop.spec.js`
  - **AI 反馈 like/dislike 与历史弹窗子智能体抽屉**（`dadbdf9` → `817e5a1` → `d9af6fe` → `358a0a1`）

    - 新增 `message_feedback` 表（`user_id` / `session_id` / `message_id` / `feedback_type` / `problem_type` / `problem_description` / `expected_answer` + `CHECK (feedback_type IN ('like','dislike'))` + `(user_id, session_id, message_id)` 唯一索引）
    - `POST /api/agent/message-feedback` 端点（201），使用 `INSERT ... ON CONFLICT ... DO UPDATE` 保证同一用户同条消息只有一种反馈
    - 前端 `DislikeDialog.vue` 弹窗收集踩的具体问题（problem_type / description / expected_answer），`UserSettingsDialog` 互斥：点过赞的点不了踩，反之亦然
    - 历史弹窗新增 `SubAgentDrawer` 内嵌入口（`historySubAgentDrawerVisible`），通过 Teleport 挂到 `.history-dialog-main` 与内容左右并排，复用主区 `SubAgentDrawer` 组件
  - **项目文档生成智能体套件**（`e2254b3`）

    - `agents/project/AGENTS.md` + `app/shared/tools/skills/project/ProjectTools.py` 注册为系统智能体
    - `app/migrations/seed_project_agent.py` / `seed_project_skills.sql` 自动注册 7 个 skill：`project-doc-overview` / `project-doc-hub` / `project-doc-outline` / `project-doc-query` / `project-doc-workflow` / `project-doc-write` + `intent-clarification`
    - 每个 skill 配套完整 references（项目管理五大过程组 × 输出模板 + 数据完整性规则 + Word 落盘工作流）
  - **权限 / 管理 / 附件 MCP 等收口**（`49c489f` → `f69b76d` → `cdcc80f` → `72f2ed3` → `31dc4cd` → `0e92532` → `7f5d75b`）

    - `app/shared/routers/session_router.py` 新增 admin session 管理（按用户查询、停用、迁移）
    - `app/core/database.py` + `auth_router` + `user_router` + `Safety.py` 引入「用户智能体白名单 + 会话文件粒度管控」，DB 新增 `user_agent_permissions` 表
    - `DELETE /api/core/attachments` 端点，按 `stored_path` 批量删除 `.md` 缓存 + 原文件 + `attachments` 记录，并校验 `session_id` / `project_id` 归属
    - `McpServerManager.vue` + `attachment_db.py` 优化 MCP 服务器配置加载与附件删除流程
    - `AgentConfig` 工具消息 `trim` 默认值改为 `false`（避免误删 tool_call 上下文）
    - `ChatArea.vue` 修复 sticky header 抖动、滚动按钮组嵌套 div 冗余、会话头部居中样式
  - **测试 / 文档 / Mock 同步**（`8c2dac5` → `96703c1`）

    - 统一 `App.agent-switch.spec.js` / `App.project-lock.spec.js` 会话创建接口 mock（`createSession` vs `create-session`）
    - `agents/map_agent/AGENTS.md` + `app/skills/hgsc/skill.md` 更新合规审查与项目预审相关文档

---

<!-- 项目介绍 + 作品截图占位 ② -->

<p align="center">
  <img src="img/cover.png" width="100%" alt="系统演示截图" />
</p>

# 项目定位

**Feature Agent Core** 是一套**以业务场景为锚点的企业级智能体运行框架**。

它既不是空泛的通用框架宣传，也不是单一业务的封闭产品 —— 而是**沉淀一套"框架底座 + 业务场景实例"双向驱动的工程化方法论**：

- **底座层** (`app/core/`)：LLM 多 Provider 适配、Agent 运行框架、提示词协议、消息治理、流式输出、并发调度、文件 I/O、数据持久化等横切关注点的可复用基础设施。
- **业务层** (`app/features/`)：在底座之上构建的领域智能体，目前已落地 **`project`**（项目文档与运维）、`contract_*`（合同 4 个）、`audit_document`（审计）、`DevOps`（运维）、`AI_Coding_Check`（AI 编程审查）、`Tagent`、`map_agent`（地图）等实例。
- **场景实例**：每个业务智能体都是一个具体的、可演示的场景切片 —— 其中 **`project` 智能体是业务价值最完整、双职责最典型的实例**（详见下一章节）。

业务开发者只需继承 `Agent` 基类、配置 `AgentConfig`、实现专属工具与提示词，即可基于同一底座快速搭建新的生产级智能体服务。

> **为什么做这个项目**：项目诞生于自然资源业务智能化的预研过程，目标是沉淀一套"既能落地真实业务、又能横向复用"的智能体工程化方法论。

## 🎯 典型业务场景：`project` 智能体

`project` 智能体是本框架**首个完整落地**的业务实例，承接 [agents/project/AGENTS.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/agents/project/AGENTS.md) 中定义的双职责——**项目文档工作流**与**项目运维管理**。它的存在完整地回答了"框架底座如何在具体业务场景中落地"这一问题。

### 1. 业务定位

`project` 智能体面向软件工程团队的两类核心痛点：

| 业务线 | 解决什么问题 | 典型产物 |
|---|---|---|
| **项目文档工作流** | 策划表/需求规格/概要设计/详细设计/测试计划/测试报告/验收报告/实施部署/培训计划 等 10 类软件工程文档的查询、生成与更新；多项目管理框架（PMP / PRINCE2 / 信息系统项目管理师）支持 | 实施方案、需求规格书、概要/详细设计文档、测试报告、验收报告等 `.docx` 交付物 |
| **项目运维管理** | 运维记录汇总（巡检结果/告警/人工处理）、飞书消息同步、需求/修改单插入、主动巡检 + 定时巡检（对接 `TaskSchedulerService` 5 段 crontab） | 运维日报/周报、飞书卡片、需求工单、修改单、巡检报告 |

### 2. 已落地的能力 — 项目文档线

- **入口契约**：[agents/project/AGENTS.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/agents/project/AGENTS.md) 明确智能体职责、工具清单与 skill 触发条件
- **已实现的 7 个 skill**：
  - `project-doc-overview` — 套件总览与分流入口（模型自读入口文档）
  - `project-doc-hub` — 文档生成/查询/更新的统一调度入口
  - `project-doc-query` — 回答"项目里有什么 / 何时评审 / 谁负责"等事实性问题
  - `project-doc-outline` — 为 10 类文档生成符合软件工程规范的章节大纲
  - `project-doc-write` — 基于真实项目材料填充正文 + 生成决策与意见（严禁虚构）
  - `project-doc-workflow` — 端到端 4 步流水线编排（query → outline → write → save-to-disk + 变更记录）
  - `intent-clarification` — 统一澄清协议（所有"问用户"的步骤必须经过它）
- **已注册的 8 个 `@tool`**：[ProjectTools.py](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/app/shared/tools/skills/project/ProjectTools.py) 实现 `intent_clarification` / `project_doc_query` / `project_doc_outline` / `project_doc_write` / `project_doc_workflow` / `manage_project_log` / `append_change_log` / `generate_project_docx`
- **典型调用契约示例**：

  ```python
  # 事实问答（项目里有什么）
  result = project_doc_query(scope="project", query="评审计划")

  # 端到端编排 query → outline → write → save-to-disk
  result = project_doc_workflow(
      project_root="<项目根>",
      doc_type="implementation_plan",
      creation_mode="E1_based_on_materials",  # E1/E2/E3/E4 四选一
  )

  # 输出 Word 交付物
  generate_project_docx(content=doc_body, output_path="<项目根>/03_技术文档及评审/...")
  ```

- **核心约束**（来自 AGENTS.md 硬规则）：
  - **统一澄清协议**：所有追问必须先调 `intent_clarification`，禁止 SKILL.md 内联提问
  - **严禁虚构**：人名/日期/数字/工具名/角色签字表/文档状态/框架标签必须来自项目材料或用户确认
  - **4 步流水线**：`query → outline → write → save-to-disk` + 变更记录追加

### 3. 规划中的能力 — 项目运维线

已在 `agents/project/AGENTS.md` 中规划、SKILL.md 已起草、待补 `@tool` 与外部对接：

- **5 个 skill**：
  - `ops-log-aggregate` — 汇总运维记录（巡检/告警/人工处理），按时间/类型/责任人聚合生成日报/周报底稿
  - `feishu-sync` — 封装飞书 Open API 推送消息/文档/卡片（**被依赖基础能力**：其他 3 个运维 skill 都会调用它）
  - `requirement-ticket` — 向需求管理系统插入需求单 + 飞书通知
  - `change-ticket` — 向变更管理系统插入修改单 + 飞书通知审批人
  - `ops-inspection` — 主动/定时触发项目巡检（定时模式对接 `TaskSchedulerService` 5 段 crontab），异常时飞书告警
- **巡检两种触发模式**：
  - **主动触发**：用户在对话中发起"巡检一下"
  - **定时触发**：对接 `app/shared/utils/agent/task_scheduler_service.py` 的 5 段 crontab 调度器

### 4. `project` 智能体如何复用框架底座

`project` 智能体并不是孤立功能，而是**深度复用**了通用框架的每一层基础设施：

| 框架底座能力 | `project` 智能体的复用点 |
|---|---|
| `Agent` 基类 + `AgentConfig` + `AgentContext` | 智能体的运行骨架与配置三件套 |
| `ModelFactory` 多 LLM Provider | 文档生成时调用不同模型厂商 |
| 三层提示词协议（基类 + 专有 + 上下文） | `project` 智能体注入专属业务角色提示词 |
| `ToolNode` + `explore(...)` 子智能体 | 读取项目材料（策划表、需求、设计稿、邮件等） |
| `SkillTools` 加载 skill | 调用 7 个 project-doc-* skill + intent-clarification |
| 消息治理（trim / 多模态提取） | 长会话上下文裁剪与多模态附件处理 |
| 文件分片上传 + 文档缓存镜像 | 项目根目录 `.md` 镜像 + 文档缓存读取 |
| MCP 工具生态 | 可横向挂载文档解析/翻译/审稿等 MCP 工具 |

> 这正是"框架是基础、场景是落地"的具象体现 —— `project` 智能体**没有重新发明轮子**，而是在通用底座上组合出完整的业务价值。

---

# 🧠 核心能力

本节按通用方法视角介绍 `app/core/` 中沉淀的六大基础设施能力。它们是上层 **`project`** 等业务智能体的运行底座——理解这些底座能力，有助于判断"某个业务场景在底座上是否能落地"以及"如何组合底座能力"。

## 🏭 多 Provider LLM 工厂

> 子模块：`app/core/llmcalls/`

采用 **工厂模式 + 注册表模式** 统一管理多厂商大语言模型。

| 特性              | 说明                                                            |
| ----------------- | --------------------------------------------------------------- |
| 内置 Provider     | `openai` · `deepseek` · `ollama` · `anthropic`       |
| 注册表机制        | `ModelFactory._model_creators` 字典维护类型→构造器映射       |
| 动态扩展          | `ModelFactory.register_model_creator()` 运行时注册新 Provider |
| 不区分大小写      | `model_type.lower()` 归一化                                   |
| Provider 特定参数 | `Ollama` 额外支持 `reasoning` / `timeout`                 |

```python
from app.core.llmcalls.model_factory import ModelFactory

# 创建内置模型
model = ModelFactory.create_model(
    model_type="openai",
    model_name="gpt-4",
    api_key="sk-xxx",
    temperature=0.2,
    base_url="https://api.openai.com/v1",
)

# 动态注册自定义 Provider
ModelFactory.register_model_creator("custom", create_custom_model)
```

## 🧬 通用智能体运行框架

> 子模块：`app/core/agent/`

基于 **LangGraph v1.0** 的 `MessagesState` 实现的 `Agent` 基类，是整个体系的运行核心。

**工作流**：

<!-- 📌 插图占位：通用智能体运行框架工作流示意图 -->

<!-- 建议尺寸：landscape_16_9（横版宽屏，适合横向流程图） -->

<!-- 主题：基于 LangGraph MessagesState 的 Agent 循环执行流程 -->

<!-- 应包含节点：START → hitl_check → summarize → llm_call（条件分支）→ tools / END -->

<!-- 循环回路：tools → hitl_check → summarize → llm_call -->

<p align="center">
  <img
    src="img\langgraph_workflow.png"
    alt="通用智能体运行框架工作流示意图"
    width="100%"
  />
</p>

> **插图说明占位**：
>
> - 上方插图用于直观展示 `Agent` 基类的工作流，对应下方节点跳转说明
> - 待插图生成后，请删除以上 `<!-- 📌 插图占位 -->` 注释行
> - 如需更换插图源，可替换 `<img>` 的 `src` 即可

> 节点跳转说明：
>
> - `llm_call` 是**条件分支节点**：通过 `_should_continue` 判断最后一条消息是否含 `tool_calls`
> - 有 `tool_calls` → `ToolNode` 执行工具 → 结果写回 `messages` → **回到 `hitl_check` 重新进入主流程**（hitl → summarize → llm_call 再次判断）
> - 无 `tool_calls` → 直接流向 `END`，本轮对话结束
> - 也就是说 `llm_call` 的下游在每轮迭代中可能是 `tools`（循环）/ `hitl_check`（经 tools 回到主流程）/ `END`（终止）

| 节点           | 职责                                                                    |
| -------------- | ----------------------------------------------------------------------- |
| `hitl_check` | 检查 `pending_question`，调用 `interrupt()` 暂停图执行等待用户回答  |
| `summarize`  | `SummarizationNode` 自动摘要旧消息，配合 `trim_messages` 控制 token |
| `llm_call`   | 拼接三层提示词（基类 + 专有 + 上下文），调用预绑定的 `llm` 实例       |
| `tools`      | `ToolNode` 执行工具调用，结束后回到 `hitl_check` 继续处理           |

**双调用入口**：

```python
# 非流式：等待图执行完成，返回最终状态
result = await agent.invoke(input_state, context, config)

# 流式：实时 yield 每个节点输出，支持 updates / values / messages / custom / 组合
async for chunk in agent.stream(input_state, context, config, stream_mode="updates"):
    print(chunk)

# 中断恢复
async for chunk in agent.stream(Command(resume={"decision": "approve"}), context, config):
    print(chunk)
```

**配置三件套**：

- `AgentConfig` — 数据类封装模型、token、检查点器、存储库、系统提示词等
- `AgentContext` — 运行时上下文（`store_id` / `system_prompt` / `image_ids`）
- `AgentState` — 状态类，继承 `MessagesState` + `pending_question` / `question_answers` / `tool_progress` 等扩展字段

## 📜 提示词与消息协议

> 子模块：`app/core/prompts.py`、`app/core/messages/`

**三层提示词架构**：

```
system_prompt = BASE_SYSTEM_PROMPT   # ① 全局基类（核心原则、知识优先级、子智能体策略）
                + "\n\n" + self.system_prompt   # ② Agent 专有提示词
                + "\n\n" + context.system_prompt  # ③ 运行时上下文动态提示词
```

| 层            | 来源                                 | 职责                                                           |
| ------------- | ------------------------------------ | -------------------------------------------------------------- |
| ① 全局基类   | `prompts.BASE_SYSTEM_PROMPT`       | 核心原则 · 知识优先级 · 工具使用 · 输出规则 · 子智能体策略 |
| ② Agent 专有 | `AgentConfig.system_prompt`        | 业务角色 · 行为准则 · 工具选择引导                           |
| ③ 上下文动态 | `runtime.context["system_prompt"]` | 任务级临时约束 · 风格定制                                     |

**消息治理**：

| 能力             | 入口                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------ |
| 按 token 裁剪    | `messages.trim.trim_messages_with_tool_limit()`                                          |
| 按工具调用数裁剪 | `messages.trim.trim_old_tool_messages()`                                                 |
| 多模态内容提取   | `messages.converter.extract_message_content()` / `extract_text()` / `extract_full()` |

## 📡 流式输出与并发调度

> 子模块：`app/core/format/stream/`、`app/core/concurrency/`

**SSE 流式策略模式**：

```python
# 抽象基类
class StreamFormatStrategy(ABC):
    @abstractmethod
    def format_content(self, message_chunk, metadata) -> Optional[Any]: ...
  
    @property
    @abstractmethod
    def provider_name(self) -> str: ...
```

| 策略实现                | Provider                            |
| ----------------------- | ----------------------------------- |
| `DefaultStreamFormat` | OpenAI 兼容 / DeepSeek              |
| `OllamaStreamFormat`  | Ollama（含 reasoning 字段特殊处理） |

新 Provider 只需实现 `format_content` 与 `provider_name`，无需修改 `tool_node`。

**异步并发队列**：

| 能力                  | 说明                                                                   |
| --------------------- | ---------------------------------------------------------------------- |
| 单例模式              | 全局共享同一 `AgentConcurrencyQueue` 实例                            |
| `asyncio.Semaphore` | 限制同时处理的 Agent 请求数                                            |
| FIFO 等待             | 超限请求进入有序队列                                                   |
| 位置查询              | `position()` 返回当前调用方在队列中的位置（1-based）                 |
| 队列快照              | `snapshot()` 返回 `{active_count, waiting_count, max_concurrency}` |

## 🔌 工具与 MCP 生态

> 子模块：`app/core/tools/`

| 组件                           | 能力                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `BaseTools`                  | 通用基础工具 — 当前时间、文件加载、分块缓存（`RecursiveCharacterTextSplitter`）、`open_file_by_id` 按 ID 读取 |
| `HumanInTheLoopTools`        | `ask_user_question` — 触发 LangGraph `interrupt()` 暂停图执行                                                 |
| `SandboxTools`               | 沙箱化执行环境，隔离工具副作用                                                                                     |
| `FilesystemReadTools`        | 文件系统只读工具集                                                                                                 |
| `mcp_wrapper`                | MCP 工具包装器 — 自动应用「双重输出策略」（大数据返回摘要，详细数据走 `get_stream_writer`）                     |
| `mcp_registry`               | MCP Servers 注册中心，启动时统一初始化                                                                             |
| `subagent_registry`          | 子智能体注册表（基于 `BaseStore` 的命名空间隔离）                                                                |
| `mcp_tool_adapter`           | MCP 工具 → LangChain `BaseTool` 适配器                                                                          |
| `subagent_message_extractor` | 子智能体消息流提取器                                                                                               |
| `_stop_signal`               | 工具执行中断信号                                                                                                   |

**MCP 双重输出策略**：

```python
# 小数据 → 完整返回
# 大数据 → 摘要 + stream writer 详细数据
class MCPToolWrapper(BaseTool):
    def _run(self, *args, **kwargs):
        result = self.original_tool._run(*args, **kwargs)
        if len(result) > self.max_content_length:
            summary = result[:self.max_content_length] + "..."
            writer = get_stream_writer()
            writer({"full_result": result})
            return summary
        return result
```

**典型场景实例 — `project` 智能体**：以 `project` 智能体为例，它通过 `project_doc_*` 工具直接复用 `explore(...)` 子智能体读取项目材料（策划表、需求文档、设计稿、邮件等），并通过 `SkillTools` 调用 7 个项目文档类 skill；不重新发明文件系统读取、消息治理、SSE 流式，而是**组合底座能力形成完整业务闭环**。

---

## 🚀 子智能体工具（可触发 Sub-Agent）

<!-- 📌 插图占位：子智能体时序图（父 LLM ↔ Sub-Agent 交互流程） -->

<!-- 建议尺寸：landscape_16_9（横版宽屏，适合横向时序图） -->

<!-- 主题：父 LLM 调用 explore / sandbox 子智能体的时序交互 -->

<!-- 应包含泳道：父 LLM、Sub-Agent、中间件、工具层、回流（Command + ToolMessage） -->

<!-- 关键节点：tool_call → 中间件初始化 → 内部工具执行 → 结果回流 → 父图继续 -->

<p align="center">
  <img
    src="img\subagent_diagram.png"
    alt="子智能体时序图（父 LLM ↔ Sub-Agent 交互流程）"
    width="100%"
  />
</p>
<sub align="center">子智能体时序图：父 LLM → Sub-Agent → 中间件 → 内部工具 → Command + ToolMessage 回流</sub>

> 子模块：`app/core/tools/FilesystemReadTools.py`、`app/core/tools/SandboxTools.py`

`explore` 与 `sandbox` 是 `app/core/tools/` 中**两个可触发子智能体**的特殊工具。父 LLM 调用后，**当前工作流会等待子智能体自主完成任务**，子智能体可使用专属中间件、复用 LangGraph Checkpoint，最后将结构化结果以 `Command` + `ToolMessage` 回流至父图。

### 🗂️ explore — 文件探索子智能体

| 项              | 说明                                                                                                               |
| --------------- | ------------------------------------------------------------------------------------------------------------------ |
| 触发场景        | 复杂文件搜索 + 内容分析（多目录 / 多关键词 / 需读全文 / 跨文件交叉引用）                                           |
| 子智能体能力    | `glob_search` · `grep_search` · `read_file` · `ls` · `write_todos`（任务规划）                       |
| 挂载中间件      | `TodoListMiddleware` · `EncodingSafeFileSearchMiddleware`（编码安全）· `FilesystemMiddleware`              |
| 工作空间        | `data/upload/{session_id}/`，**只读**，子智能体不可修改宿主文件                                            |
| 并发模型        | 支持**单消息内并发启动多个** `explore` 实例，由父 LLM 触发后并行搜索不同子主题                             |
| 会话恢复        | 每次调用返回 `task_id`，传入可恢复历史上下文（LangGraph Checkpoint 持久化）                                      |
| 父 LLM 触发条件 | 任务匹配 `explore` 描述（文件搜索 / 内容提取 / 多文档分析）时**优先**调用，避免父 LLM 直接堆 `read_file` |

<p align="center">
  <img src="img/explore.png" width="100%" alt="explore 子智能体执行流程" />
</p>
<sub align="center">explore工作流时序图（待补充）</sub>

**典型调用契约**：

```python
@tool(description="Launch a new agent to handle complex, multistep file search ...")
async def explore(
    prompt: str,                     # 高度详细的任务描述（含搜索目标 / 预期返回 / 约束）
    task_id: Optional[str] = None,    # 传入历史 task_id 恢复会话
) -> Command: ...
```

> **Prompt 编写铁律**：`prompt` 不能直接传用户原话，必须由父 LLM **改写为结构化任务描述**，包含搜索目标、文件路径范围、预期输出格式、子智能体应返回的具体信息。

### 🐳 sandbox — 沙箱执行子智能体

| 项           | 说明                                                                                                                                     |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 触发场景     | 安全执行代码 / 数据处理 / 动态生成文件 / 跑临时脚本                                                                                      |
| 隔离级别     | 独立**Docker 容器**，默认 `network_enabled=False` · `max_memory_mb=512` · `max_cpu_percent=100` · `default_timeout=60s` |
| 子智能体能力 | `ls` · `read_file` · `write_file` · `edit_file` · `glob` · `grep` · `execute`（Shell / Python）                      |
| 挂载中间件   | `DockerSandboxMiddleware`（继承自 `FilesystemMiddleware`）                                                                           |
| 工作空间     | `data/upload/{session_id}/sandbox/`，挂载到容器内的工作目录                                                                            |
| 用户停止感知 | 每 5 个 chunk 检测 `request.is_disconnected()`，按下停止按钮后**立即**中断子智能体 + 清理容器                                    |
| 流式事件     | 推 `tool_start` / `tool_progress` / `tool_stop` / `tool_error`，前端可实时展示 5 步进度条                                        |
| 安全规则     | 容器默认无网络 · 禁止 `rm -rf /` / `mkfs` / `dd` 等破坏性命令 · 资源受限 · 60s 超时                                             |

<p align="center">
  <img src="img/sandbox.png" width="100%" alt="sandbox 子智能体沙箱执行流程" />
</p>
<sub align="center">sandbox工作流时序图（待补充）</sub>

**5 步进度模板**（`SANDBOX_STEPS`）：

```
① code_generation (📝 生成代码)
   ↓
② file_write        (💾 写入文件)
   ↓
③ command_execute   (▶️  执行代码)
   ↓
④ command_output    (📤 获取输出)
   ↓
⑤ result_analysis   (✅ 分析结果)
```

**典型调用契约**：

```python
@tool(description="Launch a sandbox subagent to safely execute code ... in an isolated Docker container.")
async def sandbox(
    prompt: str,    # 高度详细的任务描述（要执行的代码 / 文件操作 / 预期返回）
) -> Command: ...
```

### 🛠️ 工具调用机制

工具与 LLM 的协作遵循统一的**调用契约**，可被所有 `app/core/tools/` 下的工具复用：

```
┌──────────────────────────────────────────────────────────────────────┐
│                       单次工具调用生命周期                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 父 LLM 决策 → 解析 tool_call（name + args）                       │
│            │                                                         │
│            ▼                                                         │
│  2. ToolNode 执行工具 → 注入 ToolRuntime（含 context / store / request）│
│            │                                                         │
│            ▼                                                         │
│  3. 工具执行中 → get_stream_writer() 推 tool_progress（SSE 实时）       │
│            │                                                         │
│            ▼                                                         │
│  4. 工具完成 → 返回 Command(update={messages: [ToolMessage]})         │
│            │                                                         │
│            ▼                                                         │
│  5. 父图回到 hitl_check → summarize → llm_call 继续推理               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

| 关键能力         | 入口                                                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 工具运行时上下文 | `ToolRuntime[AgentContext]` — 自动注入 `context` / `store` / `tool_call_id`                                     |
| 流式事件推送     | `get_stream_writer()` + `create_tool_event()` 推 `tool_start` / `tool_progress` / `tool_stop` / `tool_error` |
| 中断恢复         | 父 LLM 收到 `ToolMessage` 后继续；子智能体本身可被 `Command(resume=...)` 恢复                                        |
| 用户停止信号     | 通过 ContextVar 注入 FastAPI `Request`，工具内部 `is_disconnected()` 检测                                            |
| 大数据返回       | `MCPToolWrapper` 自动应用双重输出策略（完整结果 → SSE 流 / 摘要 → 父 LLM）                                           |
| 结构化输出       | 父 LLM 收到 `<task_result>{json}</task_result>` 格式，统一解析                                                         |

**子智能体与父图的关系**：

```
父 Agent (MessagesState)
   │
   │  ToolNode
   ▼
explore / sandbox 工具
   │
   │  create_agent / create_deep_agent
   ▼
子智能体 (独立 Checkpoint · 独立中间件)
   │
   │  ToolMessage({"subagent": "..."}, tool_call_id=parent_tcid)
   ▼
回流到父 messages → 父 LLM 继续推理
```

---

## 💾 数据与基础设施

> 子模块：`app/core/database.py`、`app/core/router/`、`app/core/server.py`、`app/core/dependencies.py`

**异步数据库连接池**：

| 能力                        | 说明                                       |
| --------------------------- | ------------------------------------------ |
| `asyncpg.Pool` 单例       | 进程级复用                                 |
| `@register_schema` 装饰器 | 业务模块声明式注册表结构，启动时统一初始化 |
| 环境变量控制                | `AUTH_STORAGE_MODE` 切换启用 / 关闭      |

**文件 I/O 路由**（`/api/core/*`）：

| 接口                | 方法 | 能力                          |
| ------------------- | ---- | ----------------------------- |
| `/uploadfile`     | POST | 单 / 多文件上传，自动解析文档 |
| `/upload-chunk`   | POST | 大文件分片上传                |
| `/merge-chunks`   | POST | 合并已上传分片                |
| `/download`       | GET  | 单文件下载                    |
| `/batch-download` | POST | 批量下载 / 断点续传           |

**FastAPI 应用工厂**（`server.py`）：

| 能力         | 说明                                                              |
| ------------ | ----------------------------------------------------------------- |
| 生命周期管理 | `lifespan` 初始化 DB → Session → Checkpointer → MCP Registry |
| 中间件链     | CORS +`auth_middleware` + `session_auth_middleware`           |
| 静态文件     | `StaticFiles` 挂载前端 SPA                                      |
| 依赖注入     | `dependencies.py` 暴露 FastAPI Depends                          |

---

# 🚀 快速开始

### 环境要求

- Python 3.10+
- pip 或 uv 包管理器
- 可选：PostgreSQL（启用 DB 持久化时需要）

### 安装

```bash
git clone <repository-url>
cd feature-agent-core

python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
```

`.env` 关键配置：

```env
# 大模型配置（示例：OpenAI 兼容）
MODEL_TYPE=openai
MODEL_NAME=gpt-4
MODEL_API_KEY=your-api-key
MODEL_API_BASE=https://api.openai.com/v1
MODEL_TEMPERATURE=0.2
```

### 启动

```bash
python -m app.main
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

服务启动后访问：

- API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)
- 健康检查：[http://localhost:8000/health](http://localhost:8000/health)

### Docker 部署

```bash
docker-compose up -d
docker-compose logs -f agents
```

---

# 🛠️ 部署启动

> 本节只讲**怎么把服务跑起来**，不涉及业务接口调用。如需了解接口怎么调，参见 [📘 如何使用](#-如何使用) 上半节的代码示例。

## 1️⃣ 部署方式总览

`feature-agent-core` 提供三种部署形态，按场景选择：

| 形态                            | 适用场景                 | 启动速度 | 隔离性 | 推荐度              |
| ------------------------------- | ------------------------ | -------- | ------ | ------------------- |
| **本地源码启动**          | 开发 / 调试 / 改代码热跑 | 快       | 无     | ⭐⭐⭐ 日常开发     |
| **Docker Compose 启动**   | 测试 / Demo / 内部署     | 中       | 容器级 | ⭐⭐⭐ 验证环境     |
| **镜像构建 + 容器化部署** | 生产 / 多节点 / 集群     | 中       | 容器级 | ⭐⭐⭐⭐⭐ 生产环境 |

下面逐个展开。

## 2️⃣ 本地源码启动

### 2.1 环境要求

| 项         | 最低 | 推荐                         |
| ---------- | ---- | ---------------------------- |
| Python     | 3.10 | 3.11（与 Dockerfile 一致）   |
| 内存       | 4 GB | 8 GB（含 Sandbox 子容器）    |
| 磁盘       | 5 GB | 20 GB（含模型缓存）          |
| Docker     | 可选 | 启用 `sandbox` 工具时必装  |
| PostgreSQL | 可选 | 启用 DB 持久化时必装（16.x） |

> 💡 纯开发联调可只装 Python；不启用 DB 时框架自动降级到内存模式（`AUTH_STORAGE_MODE=memory`）。

### 2.2 克隆 & 安装

```bash
git clone <repository-url>
cd feature-agent-core

python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

pip install -r app/requirements.txt
```

> mcpClient 是独立子项目（如需使用统一 MCP 客户端）：
>
> ```bash
> pip install -e mcpClient/
> ```

### 2.3 配置环境变量

```bash
cp .env.example .env
```

按需修改关键项（详见 [§ 5️⃣ 环境变量](#5️⃣-环境变量)）：

```env
# === 大模型（必填）===
MODEL_TYPE=openai
MODEL_NAME=gpt-4
MODEL_API_KEY=sk-xxx
MODEL_API_BASE=https://api.openai.com/v1
MODEL_TEMPERATURE=0.2

# === 存储模式（可选）===
AUTH_STORAGE_MODE=memory        # memory = 内存模式（无 DB 即可跑）
# AUTH_STORAGE_MODE=postgres    # postgres = 需要 DATABASE_URL
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/feature_agent
```

### 2.4 启动服务

```bash
# 方式 A：默认参数（0.0.0.0:8001）
python -m app.main

# 方式 B：自定义参数
python -m app.main --host 127.0.0.1 --port 8003

# 方式 C：直接用 uvicorn（支持热重载，开发用）
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

启动成功后会看到：

```text
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 2.5 验证启动

```bash
# 健康检查
curl http://localhost:8001/health
# 预期返回：{"status":"ok"}

# 交互式 API 文档
open http://localhost:8001/docs   # Swagger UI
open http://localhost:8001/redoc  # ReDoc
```

## 3️⃣ Docker Compose 一键启动

> 适合不想装 Python / DB 的快速验证场景。

### 3.1 准备镜像

后端镜像 `Dockerfile` 位于 `app/Dockerfile`（多阶段构建）。可推到任一镜像仓库或使用本地构建。

修改 `docker-compose.yml` 顶部的镜像地址，或改用本地构建：

```yaml
# 方式 A：拉远端镜像（默认）
services:
  backend:
    image: ${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/backend:latest
    # ...

# 方式 B：本地构建（取消 image 行，启用 build）
services:
  backend:
    build: ./app
    container_name: preview-backend
    ports:
      - "8001:8001"
```

### 3.2 准备环境变量

```bash
# .env（与 compose 同目录，docker-compose 自动加载）
ALIYUN_REGISTRY=registry.cn-hangzhou.aliyuncs.com
ALIYUN_NAMESPACE=your-namespace
```

如要注入到后端容器，追加 `environment` 块（参考 .env.example）：

```yaml
services:
  backend:
    environment:
      - MODEL_TYPE=openai
      - MODEL_NAME=gpt-4
      - MODEL_API_KEY=sk-xxx
      - MODEL_API_BASE=https://api.openai.com/v1
      - AUTH_STORAGE_MODE=memory
```

### 3.3 拉起服务

```bash
# 后台启动
docker-compose up -d

# 实时查看日志
docker-compose logs -f backend

# 停止
docker-compose down
```

### 3.4 带数据库的完整栈

如需启用 PostgreSQL，可扩 `docker-compose.yml`：

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: feature-agent-db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: feature_agent
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    # ... 原有配置
    environment:
      - AUTH_STORAGE_MODE=postgres
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/feature_agent
    depends_on:
      - db

volumes:
  pgdata:
```

## 4️⃣ 镜像构建与发布（生产环境）

### 4.1 后端镜像

```bash
# 构建
docker build -f app/Dockerfile -t feature-agent-core-backend:1.0.0 .

# 推送到镜像仓库
docker tag feature-agent-core-backend:1.0.0 registry.example.com/feature-agent-core:1.0.0
docker push registry.example.com/feature-agent-core:1.0.0
```

### 4.2 前端镜像（如使用自带 web/）

`web/Agent/Dockerfile` 是多阶段构建（node:20-alpine → nginx:alpine）：

```bash
cd web/Agent
docker build -t feature-agent-core-frontend:1.0.0 .
docker push registry.example.com/feature-agent-core-frontend:1.0.0
```

### 4.3 沙箱模式选择（生产重点）

> 沙箱子智能体需要 Docker daemon。容器化部署时**默认 `local` 模式不可用**，必须显式配置。

| 部署模式   | 适用场景                                    | 配置项                                                                                                                             |
| ---------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `local`  | 应用直接跑在宿主机（无容器）                | 默认值                                                                                                                             |
| `socket` | 应用容器挂载宿主机 `/var/run/docker.sock` | `SANDBOX_DOCKER_MODE=socket` + `SANDBOX_DOCKER_HOST=unix:///var/run/docker.sock` + `SANDBOX_HOST_WORKSPACE_PREFIX=/app/data` |
| `dind`   | Docker-in-Docker（需 `--privileged`）     | `SANDBOX_DOCKER_MODE=dind`                                                                                                       |
| `k8s`    | K8s API 创建 Pod（占位，未实现）            | —                                                                                                                                 |

**socket 模式启动示例**（生产推荐）：

```bash
docker run -d \
  -p 8001:8001 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /data/feature-agent:/app/data \
  -e SANDBOX_DOCKER_MODE=socket \
  -e SANDBOX_DOCKER_HOST=unix:///var/run/docker.sock \
  -e SANDBOX_HOST_WORKSPACE_PREFIX=/app/data \
  -e AUTH_STORAGE_MODE=postgres \
  -e DATABASE_URL=postgresql://postgres:pwd@db:5432/feature_agent \
  --name feature-agent-core \
  feature-agent-core-backend:1.0.0
```

## 5️⃣ 环境变量

### 5.1 必填项

| 变量               | 说明                                                             |
| ------------------ | ---------------------------------------------------------------- |
| `MODEL_TYPE`     | 模型类型：`openai` / `deepseek` / `ollama` / `anthropic` |
| `MODEL_NAME`     | 模型名称（如 `gpt-4`、`deepseek-chat`）                      |
| `MODEL_API_KEY`  | 模型 API 密钥                                                    |
| `MODEL_API_BASE` | 模型 API 地址                                                    |

### 5.2 存储与数据库

| 变量                  | 默认       | 说明                                          |
| --------------------- | ---------- | --------------------------------------------- |
| `AUTH_STORAGE_MODE` | `memory` | `memory` = 内存模式；`postgres` = 启用 DB |
| `DATABASE_URL`      | —         | PostgreSQL 连接串（启用 postgres 模式时必填） |

### 5.3 Agent 并发与流式

| 变量                           | 默认  | 说明                     |
| ------------------------------ | ----- | ------------------------ |
| `AGENT_CHAT_MAX_CONCURRENCY` | `3` | Agent 聊天接口最大并发数 |

### 5.4 沙箱（SANDBOX_*）

| 变量                              | 默认                   | 说明                                      |
| --------------------------------- | ---------------------- | ----------------------------------------- |
| `SANDBOX_DOCKER_MODE`           | `local`              | 沙箱部署模式                              |
| `SANDBOX_DOCKER_HOST`           | —                     | Docker daemon URL（socket 模式必填）      |
| `SANDBOX_IMAGE`                 | `python:3.12-alpine` | 沙箱镜像                                  |
| `SANDBOX_MAX_MEMORY_MB`         | `512`                | 容器内存限制                              |
| `SANDBOX_MAX_CPU_PERCENT`       | `100`                | 容器 CPU 限制                             |
| `SANDBOX_NETWORK_ENABLED`       | `false`              | 是否启用容器网络                          |
| `SANDBOX_DEFAULT_TIMEOUT`       | `60`                 | 命令默认超时（秒）                        |
| `SANDBOX_CONTAINER_WORKSPACE`   | `/workspace`         | 容器内工作目录                            |
| `SANDBOX_HOST_WORKSPACE_PREFIX` | —                     | 宿主机视角工作目录前缀（socket 模式必填） |

完整配置见项目根目录 [`.env.example`](file:///e:/laboratory/AI/Agents/feature-agent-core/.env.example)。

## 6️⃣ 数据目录

运行时数据落在**项目根**（非 `app/` 内），便于与代码解耦、避免被打入 Docker 镜像：

```
data/                          # 项目根运行时数据目录
├── Knowledge/                 # 知识库数据
├── upload/                    # 用户上传文件（按 session_id 分目录）
├── download/                  # 用户下载文件
├── upload_chunks/             # 分片上传临时目录
└── demonstration/download/    # 演示模式下载目录
```

> **容器化部署**：把宿主机目录挂载到容器 `/app/data`：
>
> ```bash
> -v /data/feature-agent:/app/data
> ```

## 7️⃣ 启动参数

`app/main.py` 启动入口支持 CLI 参数：

| 参数       | 默认        | 说明     |
| ---------- | ----------- | -------- |
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `8001`    | 监听端口 |

完整启动选项也可直接用 `uvicorn`：

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8001 \
  --workers 4 \
  --log-level info
```

## 8️⃣ 健康检查

服务启动后可访问：

| 端点            | 用途                 |
| --------------- | -------------------- |
| `GET /health` | 存活探针（Liveness） |
| `GET /docs`   | Swagger UI           |
| `GET /redoc`  | ReDoc 文档           |

在 Kubernetes / Docker Compose 中推荐配置：

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## 9️⃣ 常见部署问题

| 症状                                          | 原因                                        | 解决                                                                                 |
| --------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------ |
| 启动报 `ModuleNotFoundError: app`           | 未在项目根目录执行                          | `cd feature-agent-core && python -m app.main`                                      |
| 启动报 `RuntimeError: event loop is closed` | 多进程下 asyncpg 句柄泄漏                   | 改用 `--workers 1` 或前置 nginx 负载均衡                                           |
| 报 `connection refused` PostgreSQL          | `AUTH_STORAGE_MODE=postgres` 但 DB 未启动 | 切换为 `memory` 或启动 DB                                                          |
| `sandbox` 工具调用失败                      | 容器内无 Docker daemon                      | 见[§ 4.3 沙箱模式选择](#43-沙箱模式选择生产重点)                                       |
| 前端 `502 Bad Gateway`                      | `VITE_API_TARGET` 配置错位                | 容器化时改为 `http://backend:8001`                                                 |
| 端口 `8001` 已被占用                        | 旧进程未清理                                | `lsof -i:8001` → `kill -9 <pid>`（Windows 用 `netstat -ano \| findstr :8001`） |
| 启动时 OOM Killed                             | 子智能体 + Sandbox 同时跑                   | 内存升到 8 GB+，或调小 `AGENT_CHAT_MAX_CONCURRENCY=1`                              |

## 🔟 反向代理（Nginx 模板）

如要前置 Nginx 处理 HTTPS / SSE 长连接：

```nginx
upstream backend {
    server 127.0.0.1:8001;
}

server {
    listen 443 ssl;
    server_name agent.example.com;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    # SSE 长连接必须关掉缓冲
    proxy_buffering off;
    proxy_read_timeout  3600s;
    proxy_send_timeout  3600s;

    location /api/ {
        proxy_pass         http://backend;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # SSE 路由额外保护
    location /api/map/chat {
        proxy_pass http://backend;
        proxy_buffering     off;
        proxy_cache         off;
        proxy_set_header    Connection '';
        proxy_http_version  1.1;
    }
}
```

---

<!-- 架构总览 — 文本图 -->

# 🏗️ 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       feature-agent-core · 整体架构                              │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
    │   Web Frontend   │  HTTP  │   FastAPI App    │  WS    │  SSE Stream      │
    │   (Vue / HTML)   │◀──────▶│  (server.py)     │◀──────▶│  (format/stream) │
    └──────────────────┘        └────────┬─────────┘        └──────────────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                  │  Auth /      │ │   Core       │ │   File       │
                  │  Session     │ │   Agent      │ │   Router     │
                  │  Middleware  │ │   (core/agent)│ │   (core/rtr) │
                  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
                         │                │                │
                         ▼                ▼                ▼
                  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                  │  PostgreSQL  │ │  LLM Factory │ │  Local FS /  │
                  │  (asyncpg)   │ │ (core/llm    │ │  Doc Parser  │
                  │              │ │   calls)     │ │              │
                  └──────────────┘ └──────┬───────┘ └──────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                  │   OpenAI     │ │   DeepSeek   │ │   Ollama     │
                  │  / 兼容 API  │ │     API      │ │   / Local    │
                  └──────────────┘ └──────────────┘ └──────────────┘
                                          ▲
                                          │
                                  ┌───────┴───────┐
                                  │   Anthropic   │
                                  │      API      │
                                  └───────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       core/ 通用方法层 · 内部依赖关系                              │
└─────────────────────────────────────────────────────────────────────────────────┘

                       ┌─────────────────────┐
                       │   config/           │
                       │  (settings / cfg)   │
                       └──────────┬──────────┘
                                  │ 配置注入
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
   │   llmcalls/     │   │   prompts.py    │   │  database.py    │
   │  ModelFactory   │   │ BASE_SYSTEM_*   │   │  DatabasePool   │
   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
            │                     │                     │
            └──────────┬──────────┴──────────┬──────────┘
                       ▼                     ▼
              ┌─────────────────┐   ┌─────────────────┐
              │   agent/        │   │   messages/     │
              │ Agent 基类       │   │ trim / extract  │
              │ Config / Ctx    │   │                 │
              └────────┬────────┘   └─────────────────┘
                       │ 使用
            ┌──────────┼──────────────┬─────────────┐
            ▼          ▼              ▼             ▼
   ┌─────────────┐ ┌────────┐  ┌─────────────┐ ┌──────────────┐
   │  tools/     │ │ format/│  │ concurrency/│ │  router/     │
   │ BaseTools   │ │ stream/│  │ AsyncQueue  │ │ file upload/ │
   │ HITL / MCP  │ │ SSE    │  │             │ │ download     │
   │ subagent    │ │        │  │             │ │              │
   └──────┬──────┘ └────────┘  └─────────────┘ └──────────────┘
          │ 触发
          ▼
   ┌─────────────────┐         ┌──────────────────┐
   │  子智能体        │         │  Docker 沙箱     │
   │ explore (只读)  │         │  sandbox (隔离)  │
   │ + checkpoint    │         │  + 中间件         │
   └─────────────────┘         └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│  业务层 (features/) — 在 core/ Agent 基类上构建的领域智能体                       │
└─────────────────────────────────────────────────────────────────────────────────┘

         ┌─────────────────────────────────────────────┐
         │  MainAgent (LangGraph 状态图)                 │
         │  hitl_check → summarize → llm_call → tools  │
         └────────────────────┬────────────────────────┘
                              │ 路由
         ┌─────────────┬──────┴──────┬─────────────┐
         ▼             ▼             ▼             ▼
      子智能体 A    子智能体 B    子智能体 C    子智能体 D
      (继承 Agent) (继承 Agent) (继承 Agent) (继承 Agent)
```

**核心设计原则**：

- **业务与基座解耦** — 业务智能体只继承 `Agent` 基类，不直接耦合 core 内部实现
- **协议可替换** — LLM、流式策略、文件存储、提示词均通过注册表 / 策略模式解耦
- **状态可观测** — `AgentState` 内置 `tool_progress` / `intermediate_results`，支持审计与调试
- **中断可恢复** — 统一的 `interrupt()` / `Command(resume=...)` 协议，HITL 与子智能体共用

**业务层（features/）已落地的领域智能体**：

`app/features/` 在 core/ Agent 基座上已经构建了多个**具体业务场景**实例：

| 智能体 | 业务场景 | 入口 |
|---|---|---|
| **`project`**（**典型**） | 项目文档与运维双职责（文档生成 + 运维管理） | [agents/project/AGENTS.md](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/agents/project/AGENTS.md) |
| `contract_*`（4 个） | 合同相关场景（审批 / 文档 / 主持） | `app/features/contract_*/` |
| `audit_document` | 审计文档智能体 | `app/features/audit_document_agent/` |
| `DevOps` | 运维执行智能体（含 SSH / 命令拦截） | `app/features/DevOps_agent/` |
| `AI_Coding_Check` | AI 编程审查智能体 | `app/features/AI_Coding_Check_agent/` |
| `Tagent` | 测试类智能体 | `app/features/Tagent/` |
| `map_agent` | 地图相关业务 | `agents/map_agent/AGENTS.md` |

其中 **`project` 是业务价值最完整、双职责最典型的实例**——它完整回答了"框架底座如何在具体业务场景中落地"这一问题（详见 [🎯 典型业务场景：`project` 智能体](#-典型业务场景project-智能体) 章节）。

---

# 🧩 扩展指南

新增 Provider / 工具 / 业务智能体的扩展点：

| 扩展目标        | 扩展点                         | 操作                                                                       |
| --------------- | ------------------------------ | -------------------------------------------------------------------------- |
| 新 LLM Provider | `app/core/llmcalls/`         | 实现 `create_model` → `ModelFactory.register_model_creator()`         |
| 新流式策略      | `app/core/format/stream/`    | 继承 `StreamFormatStrategy` 实现 `format_content` 与 `provider_name` |
| 新工具          | `app/core/tools/`            | 继承 `BaseTools` 或使用 `@tool` 装饰器                                 |
| 新 MCP Server   | `mcp_registry`               | 在 `settings.mcp` 中追加配置                                             |
| 新业务智能体    | `app/features/<your_agent>/` | 继承 `Agent` 基类 + 自定义 `AgentConfig` + `AgentContext`（参考 [`project` 智能体](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/agents/project/AGENTS.md) 的入口契约与 `ProjectTools.py` 实现） |
| 新 Schema       | `database.py`                | `@register_schema` 装饰器声明初始化函数                                  |

---

# ❓ FAQ

**Q1：如何注册自定义 LLM Provider？**

调用 `ModelFactory.register_model_creator("custom_name", create_custom_model)` 即可，工厂支持热注册，无需修改源码。

**Q2：HITL 中断如何恢复？**

`hitl_check` 节点检测到 `pending_question` 时调用 `interrupt()` 暂停图执行，前端收到中断事件后将用户答案通过 `Command(resume={"answers": [...]})` 传入 `stream()` 恢复执行。

**Q3：如何控制对话上下文长度？**

通过 `AgentConfig` 中的 `max_tokens` / `max_tokens_before_summary` / `max_summary_tokens` 三参数控制 `SummarizationNode` 行为；亦可启用 `trim_tool_messages` 按工具调用次数裁剪旧消息。

**Q4：MCP 工具返回大数据如何处理？**

`MCPToolWrapper` 自动应用双重输出策略：超过 `max_content_length` 时返回摘要，详细数据通过 `get_stream_writer` 流式下发至 SSE。

---

# 👤 关于作者

| 项目   | 内容                                                                           |
| ------ | ------------------------------------------------------------------------------ |
| 姓名   | 张镒谱                                                                         |
| Email  | [zhangyipu@foxmail.com.cn](mailto:zhangyipu@foxmail.com.cn)                       |
| 方向   | 大语言模型工程化 · Agent 框架 · 智能体基础设施                               |
| 技术栈 | Python · FastAPI · LangGraph · LangChain · PostgreSQL · asyncpg · Docker |

---

# 🙏 致谢

本项目构建于以下优秀开源项目之上：

- [LangGraph](https://github.com/langchain-ai/langgraph) — Agent 状态图运行时
- [LangChain](https://github.com/langchain-ai/langchain) — LLM 应用开发框架
- [FastAPI](https://github.com/tiangolo/fastapi) — 高性能 Web 框架
- [asyncpg](https://github.com/MagicStack/asyncpg) — 异步 PostgreSQL 驱动
- [langmem](https://github.com/langchain-ai/langmem) — 短期 / 长期记忆管理
- [Model Context Protocol](https://modelcontextprotocol.io) — MCP 工具协议
- [MinerU](https://github.com/opendatalab/MinerU) — 高精度 PDF / 文档智能解析（布局、公式、表格提取）
