# 双重输出策略总结

## 🎯 问题背景

用户提出的问题：
> "ToolMessage也要用，这个样例中没有告诉大模型"

**核心问题**：之前的示例只使用了 `get_stream_writer()` 发送详细数据，但没有使用 `ToolMessage` 告诉大模型工具执行了什么。

## ✅ 解决方案：双重输出策略

### 核心思想

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

### 代码示例

```python
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command
from langgraph.config import get_stream_writer
from langchain_core.messages import ToolMessage

@tool(description="获取系统日志")
def get_system_logs(
    log_type: str = "syslog",
    lines: int = 100,
    runtime: ToolRuntime = None
) -> Command:
    """获取服务器系统日志"""
    writer = get_stream_writer()
    
    # ... 执行逻辑 ...
    
    # 1. 流式发送详细数据（不占用上下文）
    writer({
        "header": {
            "tool_name": "get_system_logs",
            "tool_call_id": tool_call_id,
            "timestamp": datetime.now().isoformat(),
            "status": "progress",
            "version": "1.0"
        },
        "body": {
            "data": log_lines,  # 详细日志数据（可能几千行）
            "metadata": {
                "total_lines": total_lines,
                "current_line": current_line,
                "percentage": percentage
            }
        },
        "footer": None
    })
    
    # 2. 返回简短 ToolMessage（告诉大模型发生了什么）
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"成功获取 {total_lines} 行 {log_type} 日志",  # 简短摘要
                    tool_call_id=tool_call_id
                )
            ],
            "tool_results": {
                tool_call_id: {
                    "tool": "get_system_logs",
                    "status": "success",
                    "total_lines": total_lines
                }
            }
        }
    )
```

## 📊 对比分析

### ❌ 传统方式（占用大量 token）

```python
# 返回所有日志到 messages
return Command(
    update={
        "messages": [
            ToolMessage(
                content="日志内容：\n" + "\n".join(log_lines),  # 可能几千行
                tool_call_id=tool_call_id
            )
        ]
    }
)
```

**问题**：
- ❌ messages 状态包含几千行日志
- ❌ 占用大量 token
- ❌ 大模型上下文被污染

### ❌ 只使用 get_stream_writer（大模型不知道发生了什么）

```python
# 只发送详细数据
writer({
    "body": {"data": log_lines}
})

# 不返回 ToolMessage
return Command(update={"tool_results": {...}})
```

**问题**：
- ❌ 大模型不知道工具执行了什么
- ❌ 无法进行后续推理
- ❌ 对话流程中断

### ✅ 双重输出策略（最佳实践）

```python
# 1. 流式发送详细数据
writer({
    "body": {"data": log_lines}  # 详细数据
})

# 2. 返回简短 ToolMessage
return Command(
    update={
        "messages": [
            ToolMessage(
                content="成功获取 100 行日志",  # 简短摘要
                tool_call_id=tool_call_id
            )
        ]
    }
)
```

**优势**：
- ✅ 大模型知道工具执行了什么
- ✅ 详细数据不占用 token
- ✅ 前端实时显示进度
- ✅ 对话流程正常

## 🔑 关键要点

### 1. ToolMessage 内容要简短

```python
# ✅ 正确：简短摘要
ToolMessage(content="成功获取 100 行日志")

# ❌ 错误：详细数据
ToolMessage(content=str(log_lines))  # 可能几千行
```

### 2. 详细数据通过 get_stream_writer 发送

```python
# ✅ 正确：流式发送
writer({
    "body": {"data": detailed_data}
})

# ❌ 错误：返回到 messages
return Command(update={
    "messages": [ToolMessage(content=str(detailed_data))]
})
```

### 3. 错误处理也要使用 ToolMessage

```python
# ✅ 正确：错误也返回 ToolMessage
return Command(
    update={
        "messages": [
            ToolMessage(
                content="错误：SSH 连接失败",
                tool_call_id=tool_call_id
            )
        ]
    }
)

# ❌ 错误：不返回 ToolMessage
return Command(update={"tool_results": {...}})
```

## 📁 修改的文件

1. **SSHTools.py** - 添加了 `get_system_logs` 示例函数
   - 所有返回都包含 `ToolMessage`
   - 同时使用 `get_stream_writer` 发送详细数据

2. **TOOL_OUTPUT_FORMAT.md** - 更新文档
   - 添加了双重输出策略说明
   - 添加了对比示例

3. **QUICK_REFERENCE.md** - 更新快速参考
   - 添加了双重输出策略图示
   - 更新了关键要点

## 🎓 学习要点

1. **ToolMessage 是必需的** - 大模型需要知道工具执行了什么
2. **内容要简短** - 只包含摘要，不包含详细数据
3. **详细数据用 get_stream_writer** - 流式发送，不占用上下文
4. **错误也要 ToolMessage** - 让大模型知道发生了什么错误

## 🚀 下一步

1. 运行测试验证功能：`python test_tool_output_format.py`
2. 使用模板创建新工具
3. 在前端实现统一的解析逻辑

## 📚 参考资料

- [LangGraph 官方文档 - Command](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [LangGraph 官方文档 - Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [项目文档 - TOOL_OUTPUT_FORMAT.md](./TOOL_OUTPUT_FORMAT.md)
