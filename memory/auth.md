# 认证与会话控制

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

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
| DevOps Agent      | 已下线（2026-07-15）。SSH 工具迁移至 `app/shared/tools/skills/devops/SSHTools.py`，配置服务迁移至 `app/shared/utils/devops_server_service.py`                                                                                                       |
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

## 动态上下文注入（attachments / 动态节点，2026-07-24 落地，2026-07-26 注册表化重构）

在提示词三层架构之外，系统提示词**末尾**还会追加一段"动态上下文后缀"，把会话的运行时状态（用户上传附件列表、用户通过前端 trigger 引用的引用项）以 XML 节点形式注入，抑制模型对附件的幻觉。

### 核心模块

- **文件位置**：`app/shared/utils/prompt/dynamic_context.py`
- **关键函数 / 数据结构**：
  - `DynamicNodeSpec`（frozen dataclass）：单节点契约（`overrides_key` / `xml_parent_tag` / `xml_item_tag` / `allowed_fields` / `max_items=50` / `max_field_len=128`）
  - `DYNAMIC_NODE_REGISTRY`：动态节点注册表元组；本期内置 `referenced_servers` 一条（对应前端 `#` trigger）
  - `sanitize_dynamic_nodes(overrides)`：按 registry 从 `context_overrides` 提取并清洗（白名单字段 / 长度/条数上限 / 非法项静默丢弃）；未注册键自动忽略
  - `build_dynamic_system_suffix(session_id, dynamic_nodes=None)`：以 attachments 表为唯一事实源，按 session_id 实时查询并组装后缀（静态规则文本 + XML 节点）；查询异常 / Memory 模式降级为空附件列表，仍输出显式空节点；`dynamic_nodes` 由 router 传入
  - `build_dynamic_context_xml(attachments, dynamic_nodes=None)`：遍历 registry 渲染 `<attachments>` + 每个注册节点；空状态显式化（注册表中所有节点即便为空也输出空成对节点）
  - `normalize_attachment_path(stored_path)`：路径规范化为 POSIX 风格并剥离 Windows 盘符
  - `resolve_prompt_path(prompt_path)`：与 normalize 互逆，Windows 下为无盘符 `/` 开头路径补项目根所在盘符
- **静态规则文本** `DYNAMIC_CONTEXT_RULES`：随动态节点一起注入，含 `<attachments>` 与 `<servers>` 使用说明

### 注入链路

```
chat 路由（每轮）                AgentContext              agent.py::_llm_call
sanitize_dynamic_nodes      →    dynamic_context_suffix  →  SkillsAwarePrompt(...).build()
build_dynamic_system_suffix  →   (context_overrides 注入)    + "\n\n" + 动态后缀（末尾）
(session_id 查 attachments 表)   (并保留原键供工具读取)
```

- **两个 chat 入口均已接入**：`/api/agent/chat`（agent_router.py）+ `/api/knowledge-chat`（knowledge_router.py，未注入 referenced_servers，行为不变）
- **保留键**：router **不 pop** `referenced_servers`，让该键继续随 `merged_overrides` 注入 `AgentContext`（作为一等 context 字段），工具可经 `runtime.context.get("referenced_servers")` 读取结构化数据；XML 渲染与一等 context 字段同源，均来自同一份 sanitize 结果
- `AgentContext` 基类声明 `dynamic_context_suffix: str = ""` + `referenced_servers: list = []`（2026-07-26 新增）；`dynamic_schema._BASE_CONTEXT_DEFAULTS` 同步兜底
- 累积语义由 attachments 表 INSERT 天然保证（多次上传累加，不覆盖）；上传/删除后下一轮对话自动同步
- `ChatRequest.attachments` 字段仅用于前端消息展示与历史记录渲染，**不参与**提示词拼接
- 前端历史会话附件列表链路本已完整（`GET /api/session/{id}/detail` 返回 attachments，App.vue 切换会话时恢复 `currentAttachments`），无需改动

### 可扩展性设计

- 前端 `triggerRegistry.TRIGGER_REGISTRY` ↔ 后端 `DYNAMIC_NODE_REGISTRY` 镜像对称
- 未来新增触发类型（如 `@` 知识库）：前端注册 1 条 trigger + 后端注册 1 条 `DynamicNodeSpec`，`chatStream` 签名 / `build_dynamic_system_suffix` 签名 / router 全部零改动
- `sanitize_dynamic_nodes` 是「通用清洗器」，不针对任何具体字段硬编码（仅依赖 registry）

### 工具侧兜底

`app/shared/tools/middleware/filesystem_encoding_fix.py::_patched_read`：

- 优先识别 `<attachments>` 节点中的规范化绝对路径：经 `resolve_prompt_path` 解析命中真实文件时直接读取；未命中回退原虚拟路径逻辑
- 文件不存在时返回明确错误并指引模型使用 `<attachments>` 节点中的 path，支持自我纠正

### 测试

- `app/tests/shared/utils/prompt/test_dynamic_context.py`：路径规范化（Win/Linux 三态）、反向解析、`sanitize_dynamic_nodes` 7 用例（白名单/缺 name/条数截断/长度截断/非 dict 丢弃/未注册键/空与缺失）、`build_dynamic_context_xml`（attachments + dynamic_nodes + server_type 属性 + 空态显式化 + 属性转义）、`build_dynamic_system_suffix`（dynamic_nodes 端到端 + 无 dynamic_nodes 时显式空节点 + 异常降级）、`AgentContext` 契约一致性（`dynamic_context_suffix` + `referenced_servers` 双字段）
- 运行命令：`pytest app/tests/shared/utils/prompt/ -v`

### 「#」服务器引用触发链路（2026-07-26 端到端）

```
InputBox 输入 # 词边界 → TriggerPanel 显示 fetchUserServerTree 拍平数据
  → 选中服务器 → selectedTriggers['server']
  → handleSend 经 buildOverridesFor → emit('send', text, files, {referenced_servers:[...]} )
  → App.vue::handleSendMessage 透传 extras → chatStream(..., extras)
  → context_overrides.referenced_servers 写入 body
  → agent_router 调 sanitize_dynamic_nodes(...) 提取 + 清洗
  → build_dynamic_system_suffix(session_id, dynamic_nodes={referenced_servers:[...]})
  → XML <server name="..." server_type="..." /> 渲染进 dynamic_context_suffix
  → 注入 AgentContext.dynamic_context_suffix（与 referenced_servers 并存）
  → agent.py::_llm_call 拼到 system_prompt 末尾
```

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

