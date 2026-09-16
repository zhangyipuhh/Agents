# 智能体对话

智能体对话是系统最核心的功能模块。本章节介绍对话的高级使用技巧、工具调用、流式响应与中止、反馈机制。

![智能体对话](/help/screenshots/features-chat/01-chat.png)

## 前置条件

- 已登录系统
- 拥有至少 1 个智能体的访问权限（admin 全开；普通用户需在「权限管理 → 智能体访问」被授权）
- 已启用 MFA（admin 强制；普通用户可选）

## 切换智能体

不同智能体配置了不同的提示词、工具集与领域知识。点击顶部智能体名称右侧的下拉箭头即可切换。

每个智能体的能力边界不同：

| 智能体类型 | 适用场景 | 典型工具 |
|-----------|---------|---------|
| 通用对话（project） | 日常问答、文档总结 | 联网搜索、文件读取 |
| 运维专家 | 服务器巡检、日志分析 | SSH 执行、巡检脚本 |
| 代码助手 | 代码审查、重构建议 | 文件编辑、Git 操作 |
| 地图查询（map_agent） | POI 检索、路线规划 | 高德地图 MCP |
| 知识库专家（knowledge_ydt） | 知识库深度检索 | 知识库检索 + 文件读取 |
| 合同审批（contract_host_agent 等三件套） | 合同文档解析 + 审批 | 文档读取 + 审批规则引擎 |
| 沙箱代码执行（sandbox_agent） | 隔离环境运行 Python/Shell | Docker 容器化执行 |

#### 切换后效果
- 新消息使用新智能体的 system_prompt + tool_bindings
- 历史消息归属原智能体（按 `messages.agent_name` 字段）
- 会话标题不受智能体切换影响

## 高级特性

### 上下文管理

系统自动维护会话上下文（`messages` 列表）。如需重置上下文，开启新会话即可（左侧栏「新建对话」按钮）。

#### 上下文长度管理
- LLM 上下文窗口由各智能体的 `LLM_CONFIG.max_tokens` 决定
- 超出上下文窗口时，由 `app/core/messages/trim.py` 自动截断最早的对话
- 截断策略：保留 system prompt + 最近 N 轮对话 + 当前用户消息

### 多模态输入

支持上传图片、文档等附件：

- **图片**（`upload_validation.validate_upload_extension` + 魔数嗅探）：智能体可识别图像内容（截图识别、OCR）
- **PDF / Word**（`.pdf` / `.doc` / `.docx`）：智能体可阅读文档内容并回答相关问题
- **表格**：Excel 文件可被智能体分析
- **白名单**（来自 `memory/security-compliance.md` §入侵防范）：`.pdf / .doc / .docx / .txt / .md / .markdown / .csv / .json`

> ⚠️ **白名单不可扩展**——`.exe` / `.bat` / `.sh` 等可执行扩展名一律拒绝，防止上传漏洞。

### 工具调用

智能体在回答过程中会自动调用相应工具（如 SSH 执行、文件搜索、API 调用）。用户可在消息下方展开「工具调用详情」查看调用记录与返回值。

![工具调用详情](/help/screenshots/features-chat/01-chat.png)

#### 工具调用展示规则
- **OpenAI 风格**：`msg.tool_calls` 字段直接提取
- **Anthropic 风格**：`msg.content_blocks` 中 `type=='tool_use'` 的块归一化为 `type=='non_standard'`
- 二者统一为 `[{name, args, id}]` 列表展示

### 智能体消息提取

`subagent_message_extractor` 负责从 LLM 决策中提取工具调用并推送给前端。详细实现见 `app/core/tools/subagent_message_extractor.py`。

## 流式响应

默认开启流式响应（Server-Sent Events），智能体会逐字输出回答。如需完整结果后再展示，可在「基本设置 → 安全认证 → 流式开关」中关闭。

#### 流式响应链路
1. 前端 `fetch('/api/agent/chat', { method: 'POST', body: ... })`
2. 后端 `agent.astream(...)` 流式生成 token
3. SSE 事件类型：`message` / `tool_call` / `tool_result` / `subagent` / `done`
4. 前端 `MessageBubble.vue` 按 `streamParser` 解析并渲染

### 中止生成

在智能体生成过程中，点击输入区右上角的「停止」按钮即可中止。当前已生成的内容会保留。

#### 中止链路
1. 前端调用 `POST /api/agent/{session_id}/abort`
2. 后端通过 `idle_timeout_middleware` 注册的 `abort_event.set()` 触发
3. 子智能体（如 sandbox）每 5 个 chunk 检查 `abort_event.is_set()` → 主动 break
4. 推送 `tool_stop` 事件 `status='stopped_by_user'`，前端可识别
5. 清理 Docker 容器资源（`middleware.cleanup()`）

> **避免 orphan tool_calls**：中止后会构造 `ToolMessage(tool_call_id)` 返回，避免下次会话恢复时触发 2013 "tool call result does not follow tool call" 错误。

## HITL 人机协同

部分智能体支持 Human-in-the-Loop（人机协同）。当 LLM 决策需要人工确认时，会暂停执行并展示「[HumanApprovalBox](/help/features/chat#人机协同)」按钮。

### 触发场景
- 智能体调用高风险工具（删除文件 / SSH 执行 / 发送通知）
- LLM 输出置信度低于阈值
- 配置了「强制 HITL」的策略

### 恢复方式
1. 前端展示「批准」/「拒绝」按钮 + 可选说明文本
2. 用户点击「批准」→ `POST /api/agent/{session_id}/resume` 携带批准内容
3. 后端 LangGraph `Command(resume=...)` 恢复执行

## 反馈机制

对智能体的回答不满意时，可点击回答下方的「👎」按钮提交反馈，反馈会用于智能体的持续优化。

#### 反馈接口
- `POST /api/agent/message-feedback`
- 请求体：`{ message_id: str, feedback_type: 'dislike' | 'like', reason?: str }`
- 落库到 `message_feedback` 表（admin 可在「日志管理」查询）

## 会话切换与会话管理

### 界面导览

对话区由消息流 + 底部输入框组成。智能体回答卡片支持展开「思考过程」、复制、重新生成、👍 / 👎 反馈；输入框支持 `/` 唤起智能体列表、`#` 引用服务器、附件上传与会话文件夹归属。

### 新建会话
- 左侧栏「+」按钮
- 独立上下文（不继承历史消息）
- `agent_name` 默认沿用上一个会话

### 切换会话
- 左侧栏点击目标会话
- 自动加载历史消息
- `InputBox.vue` 清理本地态（防止上一会话的草稿污染）

### 删除会话
- 会话列表项右侧「⋮」→「删除」
- **不可逆操作**，删除前请确认
- 重要会话被误删请联系管理员查审计日志（仅记录操作，不保留内容）

## 常见问题

### 智能体切换后回答异常？
- 检查是否切换到了合适的智能体
- 部分智能体（如 contract_*）有特定 prompt 约束，跨场景使用可能输出「请上传合同文件」

### 工具调用失败？
- 检查智能体是否绑定了对应工具（admin 在「智能体管理 → 工具绑定」）
- 检查工具的 ACL（如 SSH 工具需要 devops_server 授权）

### 流式响应中断？
- 检查浏览器开发者工具 Network 面板是否正常
- 检查 nginx 配置的 SSE 超时（`proxy_read_timeout 300s;` 推荐）

## 相关章节

- [智能体管理](/help/features/agent-management) — admin 配置智能体
- [权限管理](/help/features/permission-management) — 普通用户授权
- [MCP 服务器管理](/help/features/mcp-servers) — 第三方 MCP 工具接入
- [常见问题](/help/faq) — 高频问题解答
