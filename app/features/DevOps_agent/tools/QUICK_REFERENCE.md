# 工具输出模板快速参考

## 🎯 核心目标

**双重输出策略：返回大量文本数据，但不占用主模型 token**

## 💡 双重输出策略

```
┌─────────────────────────────────────────────────────────┐
│  工具执行                                                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. ToolMessage (简短摘要)                               │
│     └─> 添加到 messages 状态                             │
│     └─> 大模型可以看到                                   │
│     └─> 告诉大模型工具执行了什么                         │
│                                                          │
│  2. get_stream_writer (详细数据)                         │
│     └─> 流式发送到前端                                   │
│     └─> 不添加到 messages 状态                           │
│     └─> 大模型看不到详细内容                             │
│     └─> 前端实时显示                                     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 📋 统一输出格式

```python
{
    "header": {
        "tool_name": "工具名称",
        "tool_call_id": "调用ID",
        "timestamp": "ISO时间戳",
        "status": "start|progress|complete|error",
        "version": "1.0"
    },
    "body": {
        "data": "实际数据",
        "metadata": {"元数据": "信息"}
    },
    "footer": {
        "success": true/false,
        "message": "完成消息",
        "stats": {"total": 0, "processed": 0, "failed": 0}
    }
}
```

## 🔧 工具实现模板

```python
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command
from langgraph.config import get_stream_writer
from datetime import datetime

@tool(description="工具描述")
def my_tool(param: str, runtime: ToolRuntime = None) -> Command:
    """工具函数"""
    writer = get_stream_writer()
    
    # 1. 错误检查
    if runtime is None:
        writer({
            "header": {..., "status": "error"},
            "body": {...},
            "footer": {...}
        })
        return Command(update={"tool_results": {...}})
    
    # 2. 发送开始标记
    writer({
        "header": {..., "status": "start"},
        "body": {...},
        "footer": None
    })
    
    try:
        # 3. 执行任务并发送进度
        for i in range(total):
            # 处理数据
            result = process(i)
            
            # 发送进度（每批次）
            if (i + 1) % batch_size == 0:
                writer({
                    "header": {..., "status": "progress"},
                    "body": {"data": batch, "metadata": {...}},
                    "footer": None
                })
        
        # 4. 发送完成标记
        writer({
            "header": {..., "status": "complete"},
            "body": {...},
            "footer": {...}
        })
        
        # 5. 返回 Command（不包含 messages）
        return Command(update={"tool_results": {...}})
    
    except Exception as e:
        # 6. 发送错误标记
        writer({
            "header": {..., "status": "error"},
            "body": {...},
            "footer": {...}
        })
        return Command(update={"tool_results": {...}})
```

## 📊 状态流转

```
start → progress → complete
                  ↓
                error
```

## ✅ 关键要点

### 1. 双重输出策略

```python
# ✅ 正确：双重输出
# 1. 流式发送详细数据
writer({
    "header": {..., "status": "progress"},
    "body": {"data": detailed_data, "metadata": {...}},
    "footer": None
})

# 2. 返回简短 ToolMessage
return Command(
    update={
        "messages": [
            ToolMessage(
                content="成功处理 100 个项目",  # 简短摘要
                tool_call_id=tool_call_id
            )
        ],
        "tool_results": {...}
    }
)

# ❌ 错误：只返回详细数据，大模型不知道发生了什么
return Command(update={"tool_results": {...}})

# ❌ 错误：返回大量数据到 messages
return Command(
    update={
        "messages": [
            ToolMessage(
                content=str(detailed_data),  # 可能几千行
                tool_call_id=tool_call_id
            )
        ]
    }
)
```

### 2. 简短摘要 vs 详细数据

```python
# ✅ 正确：简短摘要 + 详细数据分离
# ToolMessage 只包含简短摘要
ToolMessage(content="成功获取 100 行日志")

# 详细数据通过 get_stream_writer 发送
writer({"body": {"data": log_lines}})  # 详细数据

# ❌ 错误：ToolMessage 包含详细数据
ToolMessage(content=str(log_lines))  # 可能几千行
```

### 2. 流式发送数据

```python
# ✅ 正确：分批发送
for i in range(0, total, batch_size):
    batch = data[i:i + batch_size]
    writer({...})

# ❌ 错误：一次性发送
writer({"body": {"data": all_data}})  # 可能非常大
```

### 3. 统一元数据

```python
# ✅ 正确：一致的元数据
"metadata": {
    "total": 100,
    "current": 50,
    "percentage": 50
}

# ❌ 错误：不一致的字段
"metadata": {
    "total_count": 100,
    "current_item": 50
}
```

## 🎨 前端解析示例

```typescript
// 解析流式输出
for await (const chunk of graph.astream(inputs, { 
    stream_mode: 'custom', 
    version: 'v2' 
})) {
    const { header, body, footer } = chunk.data;
    
    switch (header.status) {
        case 'start':
            console.log('开始执行:', header.tool_name);
            break;
        
        case 'progress':
            console.log(`进度: ${body.metadata.percentage}%`);
            break;
        
        case 'complete':
            console.log('完成:', footer.message);
            break;
        
        case 'error':
            console.error('失败:', footer.message);
            break;
    }
}
```

## 📁 文件结构

```
app/features/DevOps_agent/tools/
├── SSHTools.py                    # 工具实现
│   └── get_system_logs()          # ✅ 示例模板
├── TOOL_OUTPUT_FORMAT.md          # 📖 完整文档
├── test_tool_output_format.py     # 🧪 测试脚本
└── QUICK_REFERENCE.md             # 📋 本文档
```

## 🚀 快速开始

1. **查看示例**: 阅读 `SSHTools.py` 中的 `get_system_logs` 函数
2. **运行测试**: 执行 `python test_tool_output_format.py`
3. **阅读文档**: 查看 `TOOL_OUTPUT_FORMAT.md` 了解详情
4. **创建工具**: 复制模板并修改业务逻辑

## 💡 常见问题

**Q: 为什么不使用 ToolMessage？**\
A: ToolMessage 会添加到 messages 状态，占用主模型 token。使用自定义流式输出可以避免这个问题。

**Q: 数据存储在哪里？**\
A: 数据通过 `get_stream_writer()` 实时发送到前端，同时简要摘要存储在 `tool_results` 状态字段中。

**Q: 前端如何接收数据？**\
A: 使用 `stream_mode="custom"` 接收自定义流式数据，前端可以实时显示进度和结果。

**Q: 如何处理错误？**\
A: 发送 `status="error"` 的消息，包含详细的错误信息，同时返回 Command 更新 `tool_results`。

## 📚 相关资源

- [LangGraph 官方文档 - Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph 官方文档 - Command](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [项目文档 - TOOL\_OUTPUT\_FORMAT.md](./TOOL_OUTPUT_FORMAT.md)

