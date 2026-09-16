# 合同审批

合同审批模块由 3 个智能体组成（`HtAgent` / `DocAgent` / `ApprovalAgent`），负责合同 `.docx` 文档的解析、结构化抽取与自动审批。

> 使用方式：在会话中上传合同 `.docx` 文件，切换到合同审批智能体（如 `contract_host_agent`）后发起审批指令，智能体将自动完成「验证 → 审批中 → 完成 → 确认」四段工作流。

## 前置条件

- 合同 `.docx` 文件**必须先上传到会话**（白名单内类型，详见「[快速入门 → 文件类型白名单](/help/getting-started#文件类型白名单来自安全策略)」）
- `.env` 配置 `CONTRACT_LLM_*` 4 字段（**重启后生效**）
- admin 角色或被授权合同三智能体

## 三个智能体

### 1. HtAgent（合同主机智能体）

- **工作流**（2026-08-20 收敛）：验证 → 审批中 → 完成 → 确认（4 段）
- **核心工具**：`validate_prerequisites`（合并原 `check_approval` 副作用）+ 文件读取
- **提示词**：`app/features/contract_host_agent/prompts.py`
- **入参**：`prompt: str`（任务说明）

#### 设置后效果
- `agents` 表新增 `contract_host_agent`（lifespan 自动 seed）
- 路由 `/api/contract/chat` 可调用

### 2. DocAgent（合同文档智能体）

- **职责**：按 `answer_template` 结构化抽取合同内容
- **核心工具**：
  - `open_file_by_id`
  - `read_cached_chunk`
  - `split_file`
  - `get_extraction_rule_id`
  - `get_extraction_rule_detail`
  - `save_extraction_result`
- **约束**：禁止空 `clause_numbers` 与凭空猜测

#### 三个场景

| 场景 | 触发条件 | 输出 |
|---|---|---|
| A | 简单合同，无多层嵌套 | 直接抽取条款 |
| B | 标准合同，含附件 | 分块抽取 |
| C | 复杂合同，含表格 | 表格 + 文本混合抽取 |

### 3. ApprovalAgent（合同审批智能体）

- **职责**：根据审批规则引擎对抽取结果做决策
- **核心工具**：审批规则查询 + 决策写入
- **入参**：`structured_result` + `approval_rules`

## 配置 CONTRACT_LLM_*

`.env` 必须设置（合同三智能体专属 LLM，与全局 `LLM_*` 隔离）：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `CONTRACT_LLM_MODEL_TYPE` | `openai` | 强制 OpenAI 兼容协议 |
| `CONTRACT_LLM_MODEL_NAME` | （空 → 整组回退 LLM_CONFIG） | 模型名 |
| `CONTRACT_LLM_MODEL_API_BASE` | （空 → 字段级回退） | API base URL |
| `CONTRACT_LLM_MODEL_API_KEY` | （空 → 字段级回退） | API key |
| `CONTRACT_LLM_PARALLEL_TOOL_CALLS` | `false` | **必须 false**（Ollama 默认 true 会触发 `InvalidUpdateError`） |
| `CONTRACT_LLM_TEMPERATURE` | （空 → 字段级回退） | 温度 |
| `CONTRACT_LLM_MAX_TOKENS` | `64000` | 假设模型最大上下文 64k |

### 双层回退策略

`ContractLLMSettings.get_config()`：

1. `model_name` 空 → 整组回退 `LLM_CONFIG`
2. `model_name` 非空 → 凭据类 4 项（`api_base` / `api_key` / `temperature` / `max_tokens`）字段级回退
3. 行为类 5 项（`model_type` / `parallel_tool_calls` / `timeout` 等）不参与回退

### Ollama 接入示例

```env
CONTRACT_LLM_MODEL_TYPE=openai
CONTRACT_LLM_MODEL_API_BASE=http://your-ollama:11434/v1
CONTRACT_LLM_MODEL_API_KEY=ollama
CONTRACT_LLM_MODEL_NAME=qwen2.5:32b
CONTRACT_LLM_PARALLEL_TOOL_CALLS=false
```

> ⚠️ **Ollama 必须用 OpenAI 兼容端点 `/v1/chat/completions`**（不是原生 `/api/chat`）。原生端点 `application/x-ndjson` 流式响应，httpx.aiter_lines() 空帧会触发 `ResponseError(-1)` 500。

## max_tokens 硬编码上限

合同三 chat 端点显式注入（不走 `.env` / `ContractLLMSettings` / DB）：

| 端点 | 常量 | 值 |
|---|---|---|
| `/api/contract/chat` | `HT_AGENT_MAX_TOKENS` | `64000` |
| `/api/contract/doc_chat` | `DOC_AGENT_MAX_TOKENS` | `64000` |
| `/api/contract/approval_chat` | `APPROVAL_AGENT_MAX_TOKENS` | `64000` |

| 端点 | max_tokens_before_summary | max_summary_tokens |
|---|---|---|
| HT | `50000` | `4000` |
| DOC | `50000` | `4000` |
| APPROVAL | `50000` | `4000` |

> ⚠️ 这些常量定义在 `contract_router.py` 文件顶部，**不走** `.env` / `ContractLLMSettings` / DB。改默认值需修改源码。

## base_system_prompt 单空格覆盖

contract_router.py 三个工厂函数显式传 `base_system_prompt=" "` 单空格：

- 修复 ApprovalAgent 此前 `"##"` 笔误
- 补齐 HtAgent / DocAgent 缺失形参
- 单空格触发三元语义「非空字符串覆盖」分支，等同跳过 BASE_SYSTEM_PROMPT
- 避免通用基类规则污染合同审批场景

## 使用流程

### 1. 上传合同文件
- 主会话上传 `.docx`
- 自动触发 DocAgent 解析

### 2. 切换到合同主机智能体
- 顶部下拉选 `contract_host_agent`

### 3. 发起审批
- 输入「请审批这份合同」
- HtAgent 自动调 DocAgent 抽取条款
- 调 ApprovalAgent 决策
- 输出审批结果

## 常见问题

### LLM 调用失败？
**错误文案**：`httpx.ConnectError` 或 `401 Unauthorized`

**排查**：
1. 检查 `CONTRACT_LLM_MODEL_API_BASE` 是否正确
2. 检查 `CONTRACT_LLM_MODEL_API_KEY`
3. 检查模型是否已下载（Ollama: `ollama list`）

### InvalidUpdateError？
**错误文案**：`InvalidUpdateError: ... file_chunk_read_progress ...`

**原因**：Ollama 默认并行工具调用 → 多个 tool_call 并发写同一 channel

**修复**：
1. `.env` 设 `CONTRACT_LLM_PARALLEL_TOOL_CALLS=false`
2. 重启服务

### 合同条款抽取为空？
**排查**：
1. 确认 DocAgent 提示词已加载（`app/features/contract_document_agent/config/prompts.py`）
2. 检查合同文件是否可读（`.docx` 完整性）
3. 检查 `extraction_rules` 表

### 三 chat 端点 max_tokens 太低？
**修改位置**：`app/features/contract_host_agent/router/contract_router.py` 文件顶部 9 个常量
**重启生效**：常量定义在源码，需重启服务

## 相关章节

- [智能体对话](/help/features/chat) — 切换智能体
- [智能体管理](/help/features/agent-management) — 合同三智能体配置
- [基本设置 → LLM 模型](/help/features/basic-settings#llm-模型) — LLM 配置