# 流式 vs 非流式输出对比

## 🎯 核心问题

**用户提问**：非流式输出是否有影响？

**答案**：**有影响，但不会丢失关键信息**

---

## 📊 对比分析

### 1. 流式输出（推荐）

```python
# 使用 astream 接收流式数据
async for chunk in graph.astream(
    inputs, 
    stream_mode=["updates", "custom"],
    version="v2"
):
    chunk_type, chunk_data = chunk
    
    if chunk_type == "updates":
        # 接收节点状态更新（包含 ToolMessage）
        print(f"节点更新: {chunk_data}")
    
    elif chunk_type == "custom":
        # 接收自定义流式数据（详细数据）
        print(f"详细数据: {chunk_data}")
```

**结果**：
- ✅ 实时接收 `ToolMessage`（简短摘要）
- ✅ 实时接收 `get_stream_writer` 发送的详细数据
- ✅ 前端可以实时显示进度
- ✅ 用户体验最佳

---

### 2. 非流式输出

```python
# 使用 invoke 一次性获取结果
result = await graph.ainvoke(inputs)

# 查看结果
print(result["messages"])  # 包含 ToolMessage
print(result["tool_results"])  # 包含工具结果摘要
```

**结果**：
- ✅ 接收 `ToolMessage`（简短摘要）
- ❌ **丢失** `get_stream_writer` 发送的详细数据
- ❌ 无法实时显示进度
- ⚠️ 用户体验较差

---

## 🔍 详细对比

### 工具代码（双重输出）

```python
@tool(description="获取系统日志")
def get_system_logs(log_type: str, lines: int, runtime: ToolRuntime = None) -> Command:
    writer = get_stream_writer()
    
    # 执行任务
    log_lines = fetch_logs(log_type, lines)
    
    # 1. 流式发送详细数据
    writer({
        "header": {..., "status": "progress"},
        "body": {"data": log_lines},  # 详细数据（几千行）
        "footer": None
    })
    
    # 2. 返回简短 ToolMessage
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"成功获取 {len(log_lines)} 行日志",  # 简短摘要
                    tool_call_id=tool_call_id
                )
            ],
            "tool_results": {
                tool_call_id: {
                    "tool": "get_system_logs",
                    "total_lines": len(log_lines)
                }
            }
        }
    )
```

### 流式输出接收

```python
# ✅ 流式模式
async for chunk in graph.astream(inputs, stream_mode=["updates", "custom"]):
    if chunk[0] == "updates":
        # 接收到 ToolMessage
        # content: "成功获取 100 行日志"
        pass
    
    elif chunk[0] == "custom":
        # 接收到详细数据
        # data: ["日志行1", "日志行2", ...] (几千行)
        pass

# 结果：
# ✅ 大模型看到简短摘要
# ✅ 前端看到详细数据
# ✅ 两者都收到
```

### 非流式输出接收

```python
# ⚠️ 非流式模式
result = await graph.ainvoke(inputs)

# 查看结果
print(result["messages"])
# [HumanMessage(...), AIMessage(...), ToolMessage(content="成功获取 100 行日志")]

print(result["tool_results"])
# {"call_123": {"tool": "get_system_logs", "total_lines": 100}}

# 结果：
# ✅ 大模型看到简短摘要
# ❌ 详细数据丢失（get_stream_writer 的数据未接收）
# ⚠️ 只有摘要，没有详细内容
```

---

## 📋 影响总结

| 方面 | 流式输出 | 非流式输出 |
|------|---------|-----------|
| **ToolMessage** | ✅ 接收 | ✅ 接收 |
| **详细数据** | ✅ 接收 | ❌ 丢失 |
| **实时进度** | ✅ 显示 | ❌ 无 |
| **大模型推理** | ✅ 正常 | ✅ 正常 |
| **前端体验** | ✅ 最佳 | ⚠️ 较差 |

---

## 🎯 推荐方案

### 方案 1：优先使用流式输出（推荐）

```python
# ✅ 推荐：流式输出
async for chunk in graph.astream(
    inputs, 
    stream_mode=["updates", "custom"],
    version="v2"
):
    # 实时处理数据
    handle_stream_chunk(chunk)
```

**优势**：
- ✅ 实时显示进度
- ✅ 接收所有数据
- ✅ 用户体验最佳

---

### 方案 2：非流式 + 状态存储（备选）

如果必须使用非流式输出，可以将详细数据存储到状态中：

```python
@tool(description="获取系统日志")
def get_system_logs(log_type: str, lines: int, runtime: ToolRuntime = None) -> Command:
    writer = get_stream_writer()
    
    # 执行任务
    log_lines = fetch_logs(log_type, lines)
    
    # 1. 流式发送详细数据（流式模式可用）
    writer({
        "header": {..., "status": "progress"},
        "body": {"data": log_lines},
        "footer": None
    })
    
    # 2. 存储详细数据到状态（非流式模式可用）
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"成功获取 {len(log_lines)} 行日志",
                    tool_call_id=tool_call_id
                )
            ],
            "tool_results": {
                tool_call_id: {
                    "tool": "get_system_logs",
                    "total_lines": len(log_lines),
                    "log_lines": log_lines  # ⚠️ 存储详细数据
                }
            }
        }
    )
```

**注意**：
- ⚠️ 详细数据会存储在状态中
- ⚠️ 如果数据量很大，会占用内存
- ⚠️ 需要定期清理状态

---

### 方案 3：混合策略（最佳实践）

```python
@tool(description="获取系统日志")
def get_system_logs(log_type: str, lines: int, runtime: ToolRuntime = None) -> Command:
    writer = get_stream_writer()
    
    # 执行任务
    log_lines = fetch_logs(log_type, lines)
    
    # 1. 流式发送详细数据
    writer({
        "header": {..., "status": "progress"},
        "body": {"data": log_lines},
        "footer": None
    })
    
    # 2. 返回简短摘要 + 数据引用
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"成功获取 {len(log_lines)} 行日志",
                    tool_call_id=tool_call_id
                )
            ],
            "tool_results": {
                tool_call_id: {
                    "tool": "get_system_logs",
                    "total_lines": len(log_lines),
                    "data_reference": f"logs/{log_type}/{tool_call_id}"  # 数据引用
                }
            }
        }
    )

# 前端可以根据 data_reference 从其他地方获取详细数据
# 例如：数据库、文件系统、缓存等
```

**优势**：
- ✅ 流式模式：实时接收详细数据
- ✅ 非流式模式：通过引用获取详细数据
- ✅ 不占用大量状态空间
- ✅ 灵活性高

---

## 💡 最佳实践建议

### 1. 优先使用流式输出

```python
# ✅ 推荐
async for chunk in graph.astream(inputs, stream_mode=["updates", "custom"]):
    handle_chunk(chunk)
```

### 2. 非流式场景的应对

如果必须使用非流式输出（例如某些 API 限制）：

```python
# 方案 A：存储详细数据到状态（小数据量）
return Command(update={
    "tool_results": {
        tool_call_id: {
            "data": detailed_data  # ⚠️ 仅适用于小数据量
        }
    }
})

# 方案 B：存储数据引用（大数据量）
return Command(update={
    "tool_results": {
        tool_call_id: {
            "data_reference": "path/to/data"  # ✅ 推荐
        }
    }
})
```

### 3. 前端兼容性处理

```typescript
// 前端代码：兼容流式和非流式
async function executeTool(toolName: string, params: any) {
    try {
        // 尝试流式输出
        for await (const chunk of graph.astream(inputs, { 
            stream_mode: ["updates", "custom"] 
        })) {
            if (chunk[0] === "custom") {
                // 实时显示详细数据
                displayDetailedData(chunk[1].body.data);
            }
        }
    } catch (error) {
        // 降级到非流式输出
        const result = await graph.invoke(inputs);
        
        // 从状态中获取详细数据
        const toolResult = result.tool_results[toolCallId];
        if (toolResult.data) {
            displayDetailedData(toolResult.data);
        } else if (toolResult.data_reference) {
            // 从引用位置获取数据
            const data = await fetchDataByReference(toolResult.data_reference);
            displayDetailedData(data);
        }
    }
}
```

---

## 📊 总结

| 场景 | 推荐方案 | 原因 |
|------|---------|------|
| **正常使用** | 流式输出 | 体验最佳，数据完整 |
| **API 限制** | 非流式 + 数据引用 | 兼容性好，不占用状态 |
| **小数据量** | 非流式 + 状态存储 | 简单直接 |
| **大数据量** | 流式输出 + 数据引用 | 性能最优 |

---

## 🎓 关键要点

1. **流式输出优先** - 体验最佳，数据完整
2. **非流式不丢失关键信息** - ToolMessage 仍然可用
3. **详细数据可降级处理** - 通过状态或引用获取
4. **前端需要兼容处理** - 支持两种模式

---

## 📚 相关文档

- [TOOL_OUTPUT_FORMAT.md](./TOOL_OUTPUT_FORMAT.md) - 统一输出格式
- [DUAL_OUTPUT_STRATEGY.md](./DUAL_OUTPUT_STRATEGY.md) - 双重输出策略
- [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - 快速参考
