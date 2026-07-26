# 前端架构

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

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

> 全部组件的「组件 → 文件 → 数据来源 API」速查见根目录索引 `project_memory.md` 的「前端组件速查表」；本节记录组件级行为契约与迭代细节。

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
  - `UserSettingsDialog.vue`：admin 角色可访问的「用户设置与管理」对话框；左侧主导航固定宽度为 200px，导航项采用图标与文字左对齐、浅蓝圆角面高亮当前项，不使用彩色侧边强调条；hover、focus-visible、active 分别使用全局中性背景、inset 焦点环和强调色 token。左侧主导航包含 8 个 Tab —— `profile`（个人设置）/ `user-management`（用户管理）/ `agent-management`（智能体管理，调用 `AgentManager.vue`）/ `mcp-management`（MCP 管理，调用 `McpServerManager.vue`）/ `tool-management`（工具管理，调用 `ToolManager.vue`）/ `skill-management`（Skill 管理，调用 `SkillManager.vue`）/ `task-scheduler`（运维任务，调用 `TaskSchedulerManager.vue`）/ `email-settings`（邮件设置，调用 `EmailSettingsManager.vue`）。其中 `user-management` Tab 内部以水平子 tab（`.sub-tabs` / `.sub-tab`）形式展示三个子页面：用户列表 / 在线监控 / 会话查询，由 `activeUserMgmtTab` 状态控制，`switchUserMgmtTab` 切换并触发对应数据加载；`session-query` 子 tab 为两级视图：人员列表 → 点击人员进入该用户的会话列表；会话表格支持复选框批量选择、批量删除、单条导出 Markdown，点击会话标题弹出历史消息对话框，使用 `MessageBubble` 渲染完整消息（含 `ToolCallCard` 工具卡片与 `SubAgentCard` 子智能体卡片）。`initialTab` 仍兼容传入 `online-monitor` / `session-query` 旧值，会自动映射到 `user-management` 主 tab + 对应子 tab
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
- **与飞书侧流式的边界**：本节 SSE 流式仅服务前端 Web 入口，由 `app/routers/_stream_helper.py` 统一包装（**飞书流式卡片输出改造一行未改此文件**）。飞书 WebSocket 入口的流式输出走独立路径：`FeishuWebSocketService._call_agent` → `StreamEventSource` → `ChannelConsumer` → CardKit patch（详见「飞书流式卡片输出（多渠道架构）」章节）。两条路径互不影响，abort 信号共用 `register_abort_signal` / `trigger_abort` 全局 dict

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

## 前端 UserSettingsDialog 普通用户显示左侧导航栏

`UserSettingsDialog` 不再根据 `role` 条件渲染 `.dialog-nav`，所有角色都使用水平布局（`dialog-body-horizontal`），左侧导航栏始终可见；普通用户仅展示「个人设置」一项，admin 维持原有 8 项不变。标题文案统一为「用户设置与管理」。

### 修改要点

- **template（dialog-title）**：去掉 `isAdmin` 三元表达式，统一为静态文本 `用户设置与管理`
- **template（dialog-body）**：`:class="{ 'dialog-body-horizontal': isAdmin }"` → 静态 `class="dialog-body dialog-body-horizontal"`，所有角色均使用水平布局
- **template（dialog-nav）**：`v-if="isAdmin"` 移除，左侧导航栏对所有用户可见
- **navItems 计算属性**：保持原状——普通用户天然只返回 `[{ id: 'profile', label: '个人设置', ... }]`，admin 在此基础上追加 7 项
- **isAdmin 计算属性**：保留（组件内部仍依赖其判断 admin 专属 tab 的 `v-show` 与数据加载）

### 视觉与行为契约

- 普通用户打开「设置」后：左侧出现 200px 宽导航栏，仅显示「个人设置」一项且默认 active；右侧内容区域为个人资料表单
- 单项导航栏下方空白由 `.dialog-nav` 的 `flex-direction: column` 自然处理，菜单项贴顶部对齐
- 原有 admin 多 Tab 工作流（用户管理 / 智能体管理 / MCP / 工具 / Skill / 运维 / 邮件）不受影响

### 测试

- 路径：`web/Agent/src/components/__tests__/UserSettingsDialog.user-sidebar.spec.js`（6 用例）
- 测试策略：与 mcp.spec.js 一致，依赖 `document.body.querySelectorAll` 穿透 `<Teleport to="body">`
- 覆盖：普通用户能看到 `.dialog-nav` / 普通用户只显示「个人设置」一项 / 普通用户 dialog-body 含 `dialog-body-horizontal` 类 / 普通用户标题统一为「用户设置与管理」 / 普通用户进入 dialog 时「个人设置」默认 active / admin 回归 8 项导航 + 标题不变

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

## TaskSchedulerManager 普通用户数据源分流（2026-07-26 新增）

「普通用户的定时任务时，需要选择已授权的智能体和所有的脚本」诉求触发本次前端改造。

**改动点**：

1. **`loadInitialData` 智能体数据源按 `props.isAdmin` 分流**（`TaskSchedulerManager.vue:1079-1082`）：
   - admin → `fetchAdminAgentList`（`GET /api/admin/agents`，全量含禁用项）
   - 普通用户 → `fetchAgentList`（`GET /api/agent/list`，后端按 `user_agent_acl` 过滤、仅启用项）
2. **`loadScripts` 移除 `if (!props.isAdmin) return` 拦截**：后端已把 `GET /api/admin/scripts` 改为 JWT-only，所有登录用户都能拉脚本列表
3. **`fetchAgentList` 已存在于 `web/Agent/src/utils/api.js:1721-1733`**，无需新增

**与 ACL 双重门的协同**：

- 「定时任务」菜单（`task-scheduler.scheduled`）受 `require_admin_or_menu_acl` + OwnershipScope 双重保护
- 普通用户被授权该菜单后，进入「编辑任务」面板时：
  - 「目标智能体」下拉只列其已授权智能体（来自 `user_agent_acl`）
  - 「目标脚本」下拉列全部已注册脚本（白名单字段，不暴露源码）
- 「脚本扫描入库」子 tab（`task-scheduler.script-inventory`）仍需独立授权，普通用户点了扫描按钮会被后端 `Depends(require_admin)` 拦下

**失效授权处理**：

- admin 收回某智能体授权后，普通用户编辑老任务时 `form.agent_name` 下拉不含该 option
- Vue `v-model` 自然归零（select 值为空），用户必须重选才能保存（`schedule-agent` select 已带 `required` 校验）
- 不在前端做"当前值兜底"显示（按用户选择："仅显示授权项，编辑时显示空值"）

**测试**（`web/Agent/src/components/__tests__/TaskSchedulerManager.spec.js`）：

- `setupFetchMock` 改造支持 `agentListResponse` 参数与 `/api/agent/list` mock 分发
- 新增 describe 块「TaskSchedulerManager 普通用户数据源分流（2026-07-26 新增）」4 用例：
  - `test_non_admin_uses_agent_list_endpoint`：普通用户拉智能体走 `/api/agent/list` 而非 `/api/admin/agents`，不再显示「权限不足」占位
  - `test_non_admin_loads_scripts`：普通用户也能拉脚本列表（不再被 isAdmin 短路）
  - `test_admin_still_uses_admin_agents_endpoint`：admin 仍走 `/api/admin/agents`（向后兼容）
  - `test_non_admin_agent_dropdown_renders_filtered_options`：智能体下拉来自已授权列表（`mockAgents` 启用项），不含 `disabled_agent`

**关联改动**：后端 `app/routers/script_admin_router.py` 移除 router 级 `require_admin`（GET 登录态、POST /scan admin-only），详见 [api-routes.md § 脚本管理接口权限拆分（2026-07-26 新增）](api-routes.md)。

