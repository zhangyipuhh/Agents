# LangGraph Store Schema 重构任务清单

## 任务概述

将三个智能体（contract_host_agent、contract_document_agent、contract_approval_agent）之间的共享数据存储方式从混乱的 Key 命名统一为规范的 Schema 设计。

**设计文档**: `docs/store_schema.md`

**执行策略**: 一次性切换（不兼容旧 key）

---

## 前置条件

- [x] 确认 `docs/store_schema.md` 文档内容无误
- [ ] 备份现有代码（建议）

---

## 任务清单

### Phase 1: 基础工具函数定义

- [ ] **T1.1**: 创建 `app/shared/utils/store_schema.py`
  - 定义 `FileRegistry` Pydantic 模型
  - 定义 `ImageRegistry` Pydantic 模型
  - 定义 `DocumentChunk` / `ClauseChunk` Pydantic 模型
  - 定义 `QAItem` / `ExtractionItem` / `ExtractionReference` Pydantic 模型
  - 定义 `ApprovalPrerequisites` / `ApprovalResult` Pydantic 模型
  - 定义 `get_data_session_id()` 统一取值函数

---

### Phase 2: 修改 file_upload_handler.py

**文件**: `app/shared/utils/files/file_upload_handler.py`

| 任务 | 旧代码 | 新代码 | 说明 |
|-----|-------|-------|-----|
| T2.1 | `store.put(namespace, "file_id", data)` | `store.put(namespace, "file/registry", data)` | file_id 注册表 |
| T2.2 | `store.put(namespace, "image_paths", image_data)` | `store.put(namespace, "file/images", image_data)` | 图片注册表 |

**修改位置**:
- Line 180: `store.put(namespace, "file_id", data)` → `store.put(namespace, "file/registry", data)`
- Line 202: `store.put(namespace, "image_paths", image_data)` → `store.put(namespace, "file/images", image_data)`

---

### Phase 3: 修改 contract_document_agent

#### DocTools.py

**文件**: `app/features/contract_document_agent/tools/DocTools.py`

| 任务 | 旧代码 | 新代码 | 说明 |
|-----|-------|-------|-----|
| T3.1 | `runtime.store.get(namespace, cache_id)` | `runtime.store.get(namespace, f"file/cache/{cache_id}")` | 读取文档缓存 |
| T3.2 | `runtime.store.put(namespace, file_id, chunk_data)` | `runtime.store.put(namespace, f"file/chunks/{file_id}", chunk_data)` | 写入条款块 |
| T3.3 | `"ht_file_path"` key | `f"contract/path/{data_session_id}"` | 合同路径（按会话隔离） |
| T3.4 | `"ht_paragraph_data"` key | `f"contract/paragraph/{data_session_id}"` | 段落数据（按会话隔离） |
| T3.5 | `"reference"` key | `f"extraction/ref/{data_session_id}"` | 提取结果（按会话隔离） |

**新增**:
- 导入 `get_data_session_id` 函数
- 在 `split_file` 和 `save_extraction_result` 工具中使用 `get_data_session_id()` 获取会话 ID

**修改位置**:
- Line 97: `result = runtime.store.get(namespace, cache_id)` → `result = runtime.store.get(namespace, f"file/cache/{cache_id}")`
- Line 235: `runtime.store.put(namespace, file_id, chunk_data)` → `runtime.store.put(namespace, f"file/chunks/{file_id}", chunk_data)`
- Line 131-134: `ht_file_path` 相关逻辑 → `f"contract/path/{data_session_id}"`
- Line 140: `runtime.store.put(namespace, "ht_paragraph_data", paragraph_data)` → `runtime.store.put(namespace, f"contract/paragraph/{data_session_id}", paragraph_data)`
- Line 494: `existing_data = runtime.store.get(namespace, "reference")` → `runtime.store.get(namespace, f"extraction/ref/{data_session_id}")`
- Line 505: `runtime.store.put(namespace, "reference", reference_data)` → `runtime.store.put(namespace, f"extraction/ref/{data_session_id}", reference_data)`

---

### Phase 4: 修改 contract_host_agent

#### HtTools.py

**文件**: `app/features/contract_host_agent/tools/HtTools.py`

| 任务 | 旧代码 | 新代码 | 说明 |
|-----|-------|-------|-----|
| T4.1 | `namespace = (f"{session_id}_ht",)` | `namespace = (store_id,)` | 统一 namespace |
| T4.2 | `store.get(namespace, "ht")` | `store.get(namespace, f"approval/prereq/{data_session_id}")` | 读取前置要件 |

**新增**:
- 导入 `get_data_session_id` 函数
- 获取 `store_id` 从 `runtime.context.get('store_id', 'default')`

**修改位置**:
- Line 107: `namespace = (f"{session_id}_ht",)` → `store_id = runtime.context.get('store_id', 'default')` + `namespace = (store_id,)`
- Line 108: `store_result = runtime.store.get(namespace, "ht")` → `data_session_id = get_data_session_id(runtime)` + `store_result = runtime.store.get(namespace, f"approval/prereq/{data_session_id}")`

---

### Phase 5: 修改 contract_approval_agent

#### ApprovalAgentTools.py

**文件**: `app/features/contract_approval_agent/tools/ApprovalAgentTools.py`

| 任务 | 旧代码 | 新代码 | 说明 |
|-----|-------|-------|-----|
| T5.1 | `namespace = (f"{session_id}_ht",)` | `namespace = (store_id,)` | 统一 namespace |
| T5.2 | `get_reference_files`: key 直接使用参数 | `f"extraction/ref/{data_session_id}"` | 提取结果读取 |
| T5.3 | `get_contract_content`: `namespace = (f"{session_id}_ht",)` + key `"ht"` | `namespace = (store_id,)` + `f"contract/path/{data_session_id}"` | 合同路径读取 |
| T5.4 | `write_approval_result`: `namespace = (f"{host_session_id}_result",)` | `namespace = (store_id,)` + `key = f"approval/result/{data_session_id}"` | 审批结果写入 |

**新增**:
- 导入 `get_data_session_id` 函数
- 在所有工具中使用 `get_data_session_id()` 获取会话 ID

**修改位置**:
- `get_reference_files`:
  - Line 35: `namespace = (f"{session_id}_ht",)` → `store_id = runtime.context.get('store_id', 'default')` + `namespace = (store_id,)`
  - Line 36: 直接使用 `key` 参数 → 构建 `f"extraction/ref/{data_session_id}"`
- `get_contract_content`:
  - Line 114: `namespace = (f"{session_id}_ht",)` → `store_id = runtime.context.get('store_id', 'default')` + `namespace = (store_id,)`
  - Line 115: `result = runtime.store.get(namespace, "ht")` → `result = runtime.store.get(namespace, f"contract/path/{data_session_id}")`
- `write_approval_result`:
  - Line 194: `namespace = (f"{host_session_id}_result",)` → `store_id = runtime.context.get('store_id', 'default')` + `namespace = (store_id,)`
  - Line 196: `runtime.store.put(namespace, "result", result_content)` → `runtime.store.put(namespace, f"approval/result/{data_session_id}", result_content)`

---

### Phase 6: 修改 router

#### contract_router.py

**文件**: `app/features/contract_host_agent/router/contract_router.py`

| 任务 | 旧代码 | 新代码 | 说明 |
|-----|-------|-------|-----|
| T6.1 | `/download_contract`: `store.get(namespace, "ht_file_path")` | `store.get(namespace, f"contract/path/{host_session_id}")` | 下载合同时读取路径 |

**修改位置**:
- Line ~360: `result = store.get(namespace, "ht_file_path")` → `result = store.get(namespace, f"contract/path/{host_session_id}")`

---

### Phase 7: 统一 Context 定义（如需要）

**检查文件**: `app/core/agent/AgentContext.py`

确认 `AgentContext` 包含:
```python
class AgentContext(BaseAgentContext):
    session_id: str = "default"
    store_id: str = "default"
    image_ids: List[str] = []
    host_session_id: Optional[str] = None  # 新增
```

---

### Phase 8: 验证与测试

- [ ] **T8.1**: 启动应用
- [ ] **T8.2**: 测试文件上传流程
  - 验证 `file/registry` 正确写入
  - 验证 `file/images` 正确写入
- [ ] **T8.3**: 测试 HtAgent 调用 DocAgent 流程
  - 验证 `file/cache/{cache_id}` 正确
  - 验证 `file/chunks/{file_id}` 正确
  - 验证 `contract/path/{hsid}` 正确
  - 验证 `extraction/ref/{hsid}` 正确
- [ ] **T8.4**: 测试审批流程
  - HtAgent 调用 ApprovalAgent
  - 验证 `approval/result/{hsid}` 正确
- [ ] **T8.5**: 测试子智能体单独使用
  - 单独调用 DocAgent（无 host_session_id）
  - 单独调用 ApprovalAgent（无 host_session_id）
  - 验证数据按 `session_id` 隔离

---

## 风险与注意事项

1. **数据丢失风险**: 一次性切换后，旧数据将无法访问
2. **Key 命名一致性**: 修改过程中可能出现拼写错误，建议使用复制粘贴
3. **Context 传递**: 需要确认所有调用路径都正确传递 `host_session_id`
4. **向后兼容**: 不保留旧 key 的读取支持

---

## 回滚计划

如遇严重问题无法快速修复：

1. 恢复旧代码（使用 git）
2. 暂时回退到旧的 Key 命名
3. 分析问题后重新制定迁移计划

---

## 修改文件清单

| 文件路径 | 修改类型 |
|---------|---------|
| `app/shared/utils/files/file_upload_handler.py` | Key 命名 |
| `app/features/contract_document_agent/tools/DocTools.py` | Key 命名 + 会话隔离 |
| `app/features/contract_host_agent/tools/HtTools.py` | Key 命名 + 会话隔离 |
| `app/features/contract_approval_agent/tools/ApprovalAgentTools.py` | Key 命名 + 会话隔离 |
| `app/features/contract_host_agent/router/contract_router.py` | Key 命名 |
| `app/core/agent/AgentContext.py` | 可能需要添加字段 |
| `app/shared/utils/store_schema.py` | 新建文件 |
