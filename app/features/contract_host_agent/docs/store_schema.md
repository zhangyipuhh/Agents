# LangGraph Store 共享数据 Schema 设计文档

## 一、设计原则

1. **Namespace 统一**: `(store_id,)` - 所有智能体共享同一顶级空间
2. **file_id/cache_id 全局**: 同一合同文件协作时只上传一次
3. **其他数据按 host_session_id 隔离**: 多智能体协作时数据分开
4. **子智能体单独使用**: `host_session_id = session_id`

## 二、Namespace 和 Key 规范

### 2.1 Namespace 结构

```
namespace = (store_id,)
```

所有智能体共享同一个 store，通过 `(store_id,)` 作为 namespace。

### 2.2 Key 命名规范

#### 全局数据（不带 session_id）

| Key | 数据类型 | 说明 |
|-----|---------|------|
| `file/registry` | `Dict[str, str]` | file_id → file_path 映射 |
| `file/images` | `Dict[str, str]` | image_id → base64_data 映射 |
| `file/cache/{cache_id}` | `List[DocumentChunk]` | 文档缓存块 |
| `file/chunks/{file_id}` | `List[ClauseChunk]` | 合同条款块 |

#### 会话隔离数据（按 host_session_id 分隔）

| Key Pattern | 数据类型 | 说明 |
|------------|---------|------|
| `contract/path/{host_session_id}` | `str` | 合同文件路径 |
| `contract/paragraph/{host_session_id}` | `Dict` | 段落结构数据 |
| `extraction/ref/{host_session_id}` | `ExtractionReference` | 提取结果 |
| `approval/prereq/{host_session_id}` | `ApprovalPrerequisites` | 前置要件 |
| `approval/result/{host_session_id}` | `ApprovalResult` | 审批结果 |

## 三、数据模型定义 (Pydantic Schema)

```python
# ============================================
# 基类
# ============================================

class BaseSchema(BaseModel):
    pass


# ============================================
# 文件相关模型
# ============================================

class FileRegistry(BaseSchema):
    """文件注册表 - 全局共享"""
    files: Dict[str, str] = Field(default_factory=dict, description="file_id → file_path")


class ImageRegistry(BaseSchema):
    """图片注册表 - 全局共享"""
    images: Dict[str, str] = Field(default_factory=dict, description="image_id → base64_data")


class DocumentChunk(BaseSchema):
    """文档块"""
    index: int = Field(..., description="块索引")
    name: str = Field(..., description="块名称/类型")
    content: str = Field(..., description="块内容")


class ClauseChunk(BaseSchema):
    """条款块"""
    index: int = Field(..., description="块索引")
    name: str = Field(..., description="条款名称")
    content: str = Field(..., description="条款内容")


# ============================================
# 提取相关模型
# ============================================

class QAItem(BaseSchema):
    """问答对"""
    question: str = Field(..., description="问题内容")
    answer: str = Field(..., description="答案内容")


class ExtractionItem(BaseSchema):
    """提取项"""
    index: str = Field(..., description="索引标识，如'基础信息'、'第一条'等")
    content: List[QAItem] = Field(default_factory=list, description="问答列表")


class ExtractionReference(BaseSchema):
    """提取参考 - 按 host_session_id 隔离"""
    host_session_id: str = Field(..., description="会话ID")
    documents: Dict[str, List[ExtractionItem]] = Field(
        default_factory=dict,
        description="文档类型 → 提取项列表"
    )


# ============================================
# 审批相关模型
# ============================================

class ApprovalPrerequisites(BaseSchema):
    """审批前置要件 - 按 host_session_id 隔离"""
    host_session_id: str = Field(..., description="会话ID")
    requirements: Dict[str, List[ExtractionItem]] = Field(
        default_factory=dict,
        description="要件类型 → 要件列表"
    )


class ApprovalResult(BaseSchema):
    """审批结果 - 按 host_session_id 隔离"""
    host_session_id: str = Field(..., description="会话ID")
    status: str = Field(..., description="approved/rejected")
    result: str = Field(..., description="审批结论")
    timestamp: str = Field(..., description="时间戳")
    details: Optional[Dict] = Field(default=None, description="详情")
```

## 四、Context 参数规范与取值函数

### 4.1 Context 定义

```python
class AgentContext(BaseAgentContext):
    """统一的 Agent Context"""
    session_id: str = "default"          # 用于 checkpointer thread_id
    store_id: str = "default"           # 存储 ID（顶级隔离）
    image_ids: List[str] = []            # 图片 ID 列表
    host_session_id: Optional[str] = None  # 数据隔离 ID（多智能体协作时）
```

### 4.2 统一取值函数

```python
def get_data_session_id(runtime: ToolRuntime) -> str:
    """
    获取用于数据隔离的 session_id
    
    优先级：
    1. host_session_id（多智能体协作时由主智能体传递）
    2. session_id（子智能体单独使用时）
    
    这样设计确保：
    - 子智能体单独使用时，数据按自己的 session_id 隔离
    - 被主智能体调用时，数据按主智能体的 session_id 隔离
    """
    host_session_id = runtime.context.get('host_session_id')
    if host_session_id:
        return host_session_id
    return runtime.context.get('session_id', 'default')
```

### 4.3 各智能体工具中的使用示例

#### DocTools.py (split_file)

```python
@tool
def split_file(type: str, cache_id: str, file_id: str, runtime: ToolRuntime) -> Command:
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    
    # file_id, cache_id 是全局的，直接使用
    cache_result = runtime.store.get(namespace, f"file/cache/{cache_id}")
    # ...
    
    # 但 ht_file_path 需要按会话隔离
    data_session_id = get_data_session_id(runtime)  # 关键！
    runtime.store.put(namespace, f"contract/path/{data_session_id}", file_path)
```

#### DocTools.py (save_extraction_result)

```python
@tool
def save_extraction_result(doc_type: str, extracted_data: list, runtime: ToolRuntime) -> Command:
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    
    # 按 host_session_id 隔离
    data_session_id = get_data_session_id(runtime)
    key = f"extraction/ref/{data_session_id}"
    
    existing = runtime.store.get(namespace, key)
    ref = existing.value if existing and existing.value else {}
    # ... 更新 ref[data_session_id][doc_type]
    runtime.store.put(namespace, key, ref)
```

#### HtTools.py (validate_prerequisites)

```python
@tool
def validate_prerequisites(runtime: ToolRuntime) -> Command:
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    
    # 按 host_session_id 获取
    data_session_id = get_data_session_id(runtime)
    key = f"approval/prereq/{data_session_id}"
    
    result = runtime.store.get(namespace, key)
    # ...
```

#### ApprovalAgentTools.py

```python
@tool
def get_reference_files(key: str, runtime: ToolRuntime) -> Command:
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    
    # 按 host_session_id 获取
    data_session_id = get_data_session_id(runtime)
    result = runtime.store.get(namespace, f"extraction/ref/{data_session_id}")
    # ...

@tool
def write_approval_result(result_content: str, runtime: ToolRuntime) -> Command:
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    
    data_session_id = get_data_session_id(runtime)
    key = f"approval/result/{data_session_id}"
    
    approval_result = ApprovalResult(
        host_session_id=data_session_id,
        status="approved" if some_condition else "rejected",
        result=result_content,
        timestamp=datetime.now().isoformat()
    )
    runtime.store.put(namespace, key, approval_result.model_dump())
```

## 五、数据流图

```
┌─────────────────────────────────────────────────────────────────┐
│                   LangGraph Store                               │
│              namespace = (store_id,)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────── 全局共享 ──────────────────┐                │
│  │                                                 │                │
│  │  file/registry      ──► {file_id: path}        │                │
│  │  file/images       ──► {image_id: base64}     │                │
│  │  file/cache/{cid}  ──► [DocumentChunk]        │                │
│  │  file/chunks/{fid} ──► [ClauseChunk]         │                │
│  │                                                 │                │
│  └─────────────────────────────────────────────────┘                │
│                                                                  │
│  ┌───────────── 按 host_session_id 隔离 ────────────┐            │
│  │                                                     │            │
│  │  contract/path/{hsid}      ──► "/path/..."        │            │
│  │  contract/paragraph/{hsid} ──► {...}              │            │
│  │                                                     │            │
│  │  extraction/ref/{hsid}     ──► {                  │            │
│  │                                "供地合同": [...],   │            │
│  │                                "成交确认书": [...]   │            │
│  │                              }                      │            │
│  │                                                     │            │
│  │  approval/prereq/{hsid}    ──► {req_type: [...]}  │            │
│  │  approval/result/{hsid}    ──► {status, result}   │            │
│  │                                                     │            │
│  └─────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                                    ▲
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ contract_host │          │ contract_doc  │          │ contract_     │
│ _agent        │          │ _agent        │          │ _approval_     │
│ (HtAgent)     │          │ (DocAgent)    │          │ agent         │
│               │          │               │          │               │
│ session_id=   │          │ session_id=   │          │ session_id=   │
│ "ht_001"      │          │ "doc_001"     │          │ "appr_001"    │
│               │          │               │          │               │
│ host_session_ │────────► │ host_session_ │────────► │ host_session_ │
│ id=           │ 调用     │ id="ht_001"   │ 调用     │ id="ht_001"   │
│ "ht_001"      │          │               │          │               │
└───────────────┘          └───────────────┘          └───────────────┘
```

## 六、数据格式示例

### 6.1 全局数据示例

#### `file/registry` - 文件注册表

```python
# Key: "file/registry"
# 类型: Dict[str, str]
# 说明: file_id → file_path 映射，全局共享

{
    "file_001": "/app/data/upload/session_abc123/file_001.docx",
    "file_002": "/app/data/upload/session_abc123/file_002.pdf",
    "file_003": "/app/data/upload/session_xyz789/file_003.docx"
}
```

#### `file/images` - 图片注册表

```python
# Key: "file/images"
# 类型: Dict[str, str]
# 说明: image_id → base64_data 映射，全局共享

{
    "img_001": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMC...（base64数据）",
    "img_002": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMC...（base64数据）"
}
```

#### `file/cache/{cache_id}` - 文档缓存块

```python
# Key: "file/cache/cache_abc123"
# 类型: List[DocumentChunk]
# 说明: 文档切分前的原始缓存块，全局共享

[
    {
        "index": 1,
        "name": "供地合同",
        "content": "电子监管号：GT-2024-001\n合同编号：HT2024001\n甲方：XX市人民政府..."
    },
    {
        "index": 2,
        "name": "供地合同",
        "content": "第二条 地块位置：该地块位于XX区XX路以东..."
    }
]
```

#### `file/chunks/{file_id}` - 合同条款块

```python
# Key: "file/chunks/file_001"
# 类型: List[ClauseChunk]
# 说明: 合同条款切分后的块，全局共享

[
    {
        "index": 1,
        "name": "供地合同",
        "content": "电子监管号：GT-2024-001\n合同编号：HT2024001\n甲方：XX市人民政府\n乙方：XX房地产开发有限公司\n签订日期：2024年1月15日"
    },
    {
        "index": 2,
        "name": "供地合同",
        "content": "第一条条款 地块面积：宗地面积共计150,000平方米...\n第二条条款 土地用途：商住综合用地...\n第三条条款 土地使用权出让年限：70年"
    },
    {
        "index": 3,
        "name": "供地合同",
        "content": "第四条条款 出让价款：人民币大写叁亿元整（小写¥300,000,000）...\n第五条条款 付款方式：分期付款..."
    }
]
```

---

### 6.2 会话隔离数据示例

假设 `host_session_id = "hsid_001"` 或 `session_id = "hsid_001"`

#### `contract/path/{host_session_id}` - 合同文件路径

```python
# Key: "contract/path/hsid_001"
# 类型: str
# 说明: 合同文件的完整路径，按会话隔离

"/app/data/upload/hsid_001/file_001.docx"
```

#### `contract/paragraph/{host_session_id}` - 段落结构数据

```python
# Key: "contract/paragraph/hsid_001"
# 类型: Dict
# 说明: 合同段落结构信息，按会话隔离

{
    "session_id": "hsid_001",
    "paragraphs": [
        {"index": 1, "title": "电子监管号", "content": "GT-2024-001"},
        {"index": 2, "title": "合同编号", "content": "HT2024001"},
        {"index": 3, "title": "第一条条款", "content": "地块面积：..."}
    ]
}
```

#### `extraction/ref/{host_session_id}` - 提取结果

```python
# Key: "extraction/ref/hsid_001"
# 类型: ExtractionReference (Dict)
# 说明: 从合同文档中提取的结构化数据，按会话隔离

{
    "host_session_id": "hsid_001",
    "documents": {
        "供地合同": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "合同编号", "answer": "HT2024001"},
                    {"question": "电子监管号", "answer": "GT-2024-001"},
                    {"question": "签订日期", "answer": "2024年1月15日"}
                ]
            },
            {
                "index": "第一条",
                "content": [
                    {"question": "地块面积", "answer": "150,000平方米"},
                    {"question": "土地用途", "answer": "商住综合用地"}
                ]
            },
            {
                "index": "第四条",
                "content": [
                    {"question": "出让价款", "answer": "人民币叁亿元整（¥300,000,000）"},
                    {"question": "付款方式", "answer": "分期付款"}
                ]
            }
        ],
        "成交确认书": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "成交价格", "answer": "人民币贰亿捌仟万元整（¥280,000,000）"},
                    {"question": "竞得人", "answer": "XX房地产开发有限公司"}
                ]
            }
        ],
        "会议纪要": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "会议时间", "answer": "2024年1月10日"},
                    {"question": "主持人", "answer": "张局长"}
                ]
            }
        ]
    }
}
```

#### `approval/prereq/{host_session_id}` - 审批前置要件

```python
# Key: "approval/prereq/hsid_001"
# 类型: ApprovalPrerequisites (Dict)
# 说明: 审批前置要件清单，按会话隔离

{
    "host_session_id": "hsid_001",
    "requirements": {
        "供地合同": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "合同编号", "answer": "HT2024001"},
                    {"question": "电子监管号", "answer": "GT-2024-001"}
                ]
            },
            {
                "index": "第四条",
                "content": [
                    {"question": "出让价款", "answer": "人民币叁亿元整"}
                ]
            }
        ],
        "成交确认书": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "成交价格", "answer": "人民币贰亿捌仟万元整"}
                ]
            }
        ],
        "会议纪要": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "会议时间", "answer": "2024年1月10日"}
                ]
            }
        ]
    }
}
```

#### `approval/result/{host_session_id}` - 审批结果

```python
# Key: "approval/result/hsid_001"
# 类型: ApprovalResult (Dict)
# 说明: 审批结果，按会话隔离

{
    "host_session_id": "hsid_001",
    "status": "approved",
    "result": "经审核，该供地合同符合审批条件，批准通过。",
    "timestamp": "2026-03-27T15:30:00",
    "details": {
        "approved_items": ["供地合同", "成交确认书", "会议纪要"],
        "total_amount": "叁亿元整",
        "land_area": "150,000平方米",
        "approval_conditions": [
            "土地款已全额支付",
            "审批材料齐全",
            "符合城市规划要求"
        ]
    }
}
```

---

## 七、旧 Key 到新 Key 映射

| 旧 Key | 新 Key | 隔离方式 | 修改文件 |
|-------|-------|---------|---------|
| `file_id` | `file/registry` | 全局 | file_upload_handler.py |
| `image_paths` | `file/images` | 全局 | file_upload_handler.py |
| `cache_id` (动态) | `file/cache/{cache_id}` | 全局 | DocTools.py |
| `{file_id}` (动态) | `file/chunks/{file_id}` | 全局 | DocTools.py |
| `ht_file_path` | `contract/path/{host_session_id}` | 按会话 | DocTools.py |
| `ht_paragraph_data` | `contract/paragraph/{host_session_id}` | 按会话 | DocTools.py |
| `ht` | `approval/prereq/{host_session_id}` | 按会话 | HtTools.py |
| `reference` | `extraction/ref/{host_session_id}` | 按会话 | DocTools.py |
| `result` | `approval/result/{host_session_id}` | 按会话 | ApprovalAgentTools.py |

## 八、智能体数据操作汇总

### 7.1 contract_host_agent (HtAgent)

| 操作 | Key Pattern | 数据结构 |
|-----|------------|---------|
| 读取前置要件 | `approval/prereq/{host_session_id}` | `ApprovalPrerequisites` |
| 写入前置要件 | `approval/prereq/{host_session_id}` | `ApprovalPrerequisites` |

### 7.2 contract_document_agent (DocAgent)

| 操作 | Key Pattern | 数据结构 |
|-----|------------|---------|
| 写入文件信息 | `file/registry` | `FileRegistry` |
| 写入图片信息 | `file/images` | `ImageRegistry` |
| 读取文档缓存 | `file/cache/{cache_id}` | `List[DocumentChunk]` |
| 写入条款块 | `file/chunks/{file_id}` | `List[ClauseChunk]` |
| 写入合同路径 | `contract/path/{host_session_id}` | `str` |
| 写入段落数据 | `contract/paragraph/{host_session_id}` | `Dict` |
| 写入提取结果 | `extraction/ref/{host_session_id}` | `ExtractionReference` |

### 7.3 contract_approval_agent (ApprovalAgent)

| 操作 | Key Pattern | 数据结构 |
|-----|------------|---------|
| 读取提取结果 | `extraction/ref/{host_session_id}` | `ExtractionReference` |
| 读取合同路径 | `contract/path/{host_session_id}` | `str` |
| 读取条款块 | `file/chunks/{file_id}` | `List[ClauseChunk]` |
| 写入审批结果 | `approval/result/{host_session_id}` | `ApprovalResult` |
