# 合同智能体系统

## 概述

本合同智能体系统是一个多智能体协作平台，专门用于处理自然资源业务相关的合同审批工作。该系统采用多智能体架构，通过 LangGraph Store 实现智能体之间的数据共享与协作。

## 系统架构

系统包含三个核心智能体，分别承担不同的职责：

| 智能体                       | 目录                        | 职责                          |
| ------------------------- | ------------------------- | --------------------------- |
| **HtAgent** (主智能体)        | `contract_host_agent`     | 负责主要用户聊天，调度其他智能体，管理合同审批完整流程 |
| **DocAgent** (文档智能体)      | `contract_document_agent` | 负责拆解上传后的文件，提取文件内容和信息        |
| **ApprovalAgent** (审批智能体) | `contract_approval_agent` | 负责合同的最后审批环节                 |

### 架构流程图

```
用户
  │
  ▼
┌─────────────────────┐
│   HtAgent (主智能体)  │ ◄──────────────┐
│  - 用户对话入口        │                │
│  - 流程调度           │                │
└─────────┬───────────┘                │
          │                            │
          │ 调用                       │ 读取
          ▼                            │
┌─────────────────────┐     ┌─────────────────────┐
│ DocAgent (文档智能体) │     │  LangGraph Store    │
│ - 文件拆解           │ ──► │  (共享存储空间)       │
│ - 内容提取           │     │  - file_id          │
└─────────────────────┘     │  - image_paths      │
                            │  - ht_file_path     │
                            └─────────┬───────────┘
                                      │
                                      │ 读取
                                      ▼
                            ┌─────────────────────┐
                            │ApprovalAgent (审批)  │
                            │ - 合同审批决策       │
                            └─────────────────────┘
```

## 接口路由

所有接口均以 `/api/contract` 为前缀：

| 接口                          | 方法   | 说明              |
| --------------------------- | ---- | --------------- |
| `/api/contract/uploadfile`  | POST | 上传合同文件，处理并转换为图片 |
| `/api/contract/chat`        | POST | 主智能体对话接口        |
| `/api/contract/doc_chat`    | POST | 文档智能体对话接口       |
| `/api/contract/store/value` | POST | 获取共享存储中的值       |

## 数据共享机制

### 共享存储

系统使用 **LangGraph Store** (`InMemoryStore`) 作为共享存储空间，实现智能体之间的数据共享。

### 共享字段

| 字段名                | 说明                              | 数据结构                           |
| ------------------ | ------------------------------- | ------------------------------ |
| `file_id`          | 上传文档ID与文件路径的映射                  | `{file_id: file_path, ...}`    |
| `image_paths`      | 图片唯一标识符与base64数据的映射             | `{image_id: base64_data, ...}` |
| `ht_file_path`     | 上传合同存放在**服**务器的文件路径，审批标记后的合同的路径 | {session\_id1: path1,......}   |
| `approval_results` | 审批智能体存放的审批结果数组，记录每次审批的详细信息 | [{approval\_id, status, timestamp, details}, ...] |

#### approval_results 字段数据结构

```typescript
interface ApprovalResult {
  approval_id: string;       // 审批记录唯一标识符，格式: approval_{timestamp}_{index}
  session_id: string;         // 会话ID，用于关联主智能体的会话
  status: string;             // 审批状态: "通过" | "未通过" | "待审核"
  timestamp: string;          // ISO格式时间戳，如: "2026-03-24T10:30:00Z"
  details: {
    approver?: string;        // 审批人（可选）
    contract_name?: string;   // 合同名称（可选）
    approval_time?: string;    // 审批时间（可选）
    reasons?: string[];       // 审批理由/问题列表（可选）
    attachments?: string[];   // 附件路径列表（可选）
  };
  metadata?: {
    image_ids?: string[];      // 关联的图片ID列表（可选）
    reviewed_items?: string[]; // 已审查的项目列表（可选）
  };
}
```

**示例数据**：

```json
{
  "approval_results": [
    {
      "approval_id": "approval_1711252200_001",
      "session_id": "session_001",
      "status": "通过",
      "timestamp": "2026-03-24T10:30:00Z",
      "details": {
        "approver": "ApprovalAgent",
        "contract_name": "自然资源合同-2026-001",
        "approval_time": "2026-03-24 10:30:00",
        "reasons": ["合同内容完整", "条款符合规定", "签字齐全"],
        "attachments": []
      },
      "metadata": {
        "image_ids": ["img_001", "img_002"],
        "reviewed_items": ["甲方信息", "乙方信息", "合同金额", "签订日期"]
      }
    }
  ]
}
```

#### approval_results 读取方式

```python
# 获取审批结果数组
result = store.get(namespace=(store_id,), key="approval_results")
approval_results = result.value if result else []

# 获取最新的审批结果
latest_approval = approval_results[-1] if approval_results else None

# 获取特定审批状态的结果
passed_approvals = [r for r in approval_results if r.get("status") == "通过"]
```

### 数据读取方式

```python
# 获取文件ID映射
result = store.get(namespace=(store_id,), key="file_id")
file_id_map = result.value if result else {}

# 获取图片映射
result = store.get(namespace=(store_id,), key="image_paths")
image_map = result.value if result else {}

# 获取合同文件路径
result = store.get(namespace=(store_id,), key="ht_file_path")
file_path = result.value if result else None
```

### 设计原则

1. **上下文节省**：子智能体（DocAgent、ApprovalAgent）每次执行完任务后会清空上下文空间
2. **数据持久化**：通过 LangGraph Store 存储处理结果，实现跨会话数据访问
3. **文字读取**：子智能体读取数据时，直接从 Store 中获取文字信息，而非通过上下文传递

## 各智能体详细说明

### HtAgent (主智能体)

**位置**: `app/features/contract_host_agent/HtAgent.py`

**职责**:

- 作为用户对话的主要入口
- 验证合同审批前置条件（文件是否上传完整）
- 调度 DocAgent 进行文件处理
- 基于共享空间中的处理结果进行综合判断
- 设置审批状态（就绪/进行中/通过/未通过）

**主要工具**:

- `validate_prerequisites`: 验证前置条件
- `warn_issue`: 记录审批问题
- `check_approval`: 设置审批状态
- `ht_result`: 获取比对信息

### DocAgent (文档智能体)

**位置**: `app/features/contract_document_agent/DocAgent.py`

**职责**:

- 接收主智能体调度
- 拆解上传的合同文件
- 提取文件内容和关键信息
- 将处理结果写入共享空间

**调用方式**:

```python
result = await doc_agent.invoke(
    user_input="处理合同文件",
    session_id="doc_session_001",
    host_session_id="host_session_001",  # 主会话ID，用于访问共享数据
    image_ids=["image_id_1", "image_id_2"]  # 要处理的图片ID列表
)
```

### ApprovalAgent (审批智能体)

**位置**: `app/features/contract_approval_agent/ApprovalAgent.py`

**职责**:

- 从共享空间读取处理后的文件信息
- 执行合同审批决策
- 输出审批结果

**调用方式**:

```python
result = await approval_agent.invoke(
    user_input="开始审批",
    session_id="approval_session_001",
    host_session_id="host_session_001"  # 主会话ID，用于访问共享数据
)
```

## 使用示例

### 1. 上传合同文件

```bash
curl -X POST "http://localhost:8000/api/contract/uploadfile" \
  -F "files=@contract.pdf"
```

响应:

```json
{
  "fileids": [
    {"id": "file_123", "file_type": "doc"}
  ],
  "count": 1,
  "image_groups": [["img_001", "img_002"]]
}
```

### 2. 主智能体对话

```bash
curl -X POST "http://localhost:8000/api/contract/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我已上传合同文件，请开始审批",
    "session_id": "session_001"
  }'
```

### 3. 文档智能体处理

```bash
curl -X POST "http://localhost:8000/api/contract/doc_chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "提取合同关键信息",
    "session_id": "doc_session_001",
    "host_session_id": "session_001",
    "image_ids": ["img_001", "img_002"]
  }'
```

### 4. 获取共享存储数据

```bash
curl -X POST "http://localhost:8000/api/contract/store/value" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "file_id",
    "session_id": "session_001"
  }'
```

## 目录结构

```
app/features/
├── contract_host_agent/           # 主智能体
│   ├── HtAgent.py                 # 主智能体实现
│   ├── client.py                  # 客户端
│   ├── router/
│   │   └── contract_router.py     # API路由
│   ├── config/
│   │   ├── HtAgentConfig.py        # 配置类
│   │   └── HtAgentContext.py      # 上下文
│   └── tools/
│       └── HtTools.py              # 工具定义
│
├── contract_document_agent/       # 文档智能体
│   ├── DocAgent.py                 # 文档智能体实现
│   ├── client.py                   # 客户端
│   ├── config/
│   │   ├── DocAgentConfig.py      # 配置类
│   │   ├── DocAgentContext.py     # 上下文
│   │   ├── config.py              # 配置
│   │   └── prompts.py             # 提示词
│   └── tools/
│       └── DocTools.py            # 工具定义
│
└── contract_approval_agent/       # 审批智能体
    ├── ApprovalAgent.py           # 审批智能体实现
    ├── config/
    │   ├── ApprovalAgentConfig.py # 配置类
    │   ├── ApprovalAgentContext.py# 上下文
    │   ├── config.py              # 配置
    │   └── prompts.py             # 提示词
    └── tools/
        └── ApprovalAgentTools.py  # 工具定义
```

## 技术栈

- **框架**: FastAPI
- **智能体框架**: LangGraph
- **存储**: LangGraph InMemoryStore
- **会话管理**: LangGraph MemorySaver
- **LLM**: 支持多种大语言模型（通过配置切换）

## 更新日志

- **2026-03-24**: 初始版本， 实现三智能体协作架构

