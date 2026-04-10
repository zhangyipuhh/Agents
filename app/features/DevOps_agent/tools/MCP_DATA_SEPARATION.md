# MCP 工具数据分离方案

## 🎯 核心问题

**用户提问**：MCP 返回的数据能分开吗？

**答案**：**可以，但需要包装处理**

---

## 📊 问题分析

### 当前 MCP 工具调用方式

```python
# 当前代码：直接调用 MCP 工具
result = await self.tool_dict[tool_name].ainvoke(tool_args)
tool_messages.append(
    ToolMessage(content=str(result), tool_call_id=tool_id)
)
```

**问题**：
- ❌ MCP 工具返回的所有数据都放入 `ToolMessage`
- ❌ 如果返回大量数据，会占用大量 token
- ❌ 无法应用双重输出策略

### MCP 工具的限制

1. **无法修改 MCP 工具本身** - MCP 工具是从外部服务器获取的
2. **无法在 MCP 工具内部使用 `get_stream_writer`** - MCP 工具运行在外部服务器
3. **只能控制调用后的数据处理** - 可以在调用层进行包装

---

## ✅ 解决方案：MCP 工具包装器

### 方案 1：智能数据分离（推荐）

```python
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
import json

async def invoke_mcp_tool_with_dual_output(
    tool,
    tool_name: str,
    tool_args: dict,
    tool_call_id: str,
    max_content_length: int = 500
) -> Command:
    """
    调用 MCP 工具并应用双重输出策略
    
    Args:
        tool: MCP 工具对象
        tool_name: 工具名称
        tool_args: 工具参数
        tool_call_id: 工具调用 ID
        max_content_length: ToolMessage 最大内容长度（字符）
    
    Returns:
        Command: 包含简短 ToolMessage 和详细数据的 Command
    """
    writer = get_stream_writer()
    
    try:
        # 1. 调用 MCP 工具
        result = await tool.ainvoke(tool_args)
        
        # 2. 分析结果数据
        result_str = str(result)
        result_length = len(result_str)
        
        # 3. 发送开始标记
        writer({
            "header": {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "start",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "tool_type": "mcp",
                    "result_length": result_length
                }
            },
            "footer": None
        })
        
        # 4. 判断数据大小，决定处理方式
        if result_length <= max_content_length:
            # 小数据：直接返回
            writer({
                "header": {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "complete",
                    "version": "1.0"
                },
                "body": {
                    "data": result,
                    "metadata": {
                        "tool_type": "mcp",
                        "data_size": "small"
                    }
                },
                "footer": {
                    "success": True,
                    "message": "执行成功",
                    "stats": {
                        "total": 1,
                        "processed": 1,
                        "failed": 0
                    }
                }
            })
            
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=result_str,  # 小数据直接返回
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        else:
            # 大数据：分离处理
            # 4.1 流式发送详细数据
            writer({
                "header": {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "progress",
                    "version": "1.0"
                },
                "body": {
                    "data": result,  # 详细数据
                    "metadata": {
                        "tool_type": "mcp",
                        "data_size": "large",
                        "result_length": result_length
                    }
                },
                "footer": None
            })
            
            # 4.2 发送完成标记
            writer({
                "header": {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "complete",
                    "version": "1.0"
                },
                "body": {
                    "data": None,
                    "metadata": {
                        "tool_type": "mcp",
                        "data_size": "large"
                    }
                },
                "footer": {
                    "success": True,
                    "message": f"执行成功，返回 {result_length} 字符数据",
                    "stats": {
                        "total": 1,
                        "processed": 1,
                        "failed": 0
                    }
                }
            })
            
            # 4.3 返回简短 ToolMessage
            summary = f"执行成功，返回 {result_length} 字符数据"
            if isinstance(result, (dict, list)):
                summary = f"执行成功，返回 {type(result).__name__}，大小: {result_length} 字符"
            
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=summary,  # 简短摘要
                            tool_call_id=tool_call_id
                        )
                    ],
                    "tool_results": {
                        tool_call_id: {
                            "tool": tool_name,
                            "tool_type": "mcp",
                            "status": "success",
                            "result_length": result_length,
                            "summary": summary
                        }
                    }
                }
            )
    
    except Exception as e:
        error_msg = f"工具调用失败: {tool_name}, 错误: {str(e)}"
        
        # 发送错误标记
        writer({
            "header": {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "version": "1.0"
            },
            "body": {
                "data": None,
                "metadata": {
                    "tool_type": "mcp",
                    "error": error_msg
                }
            },
            "footer": {
                "success": False,
                "message": error_msg,
                "stats": {
                    "total": 1,
                    "processed": 0,
                    "failed": 1
                }
            }
        })
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"错误：{error_msg}",
                        tool_call_id=tool_call_id
                    )
                ],
                "tool_results": {
                    tool_call_id: {
                        "tool": tool_name,
                        "tool_type": "mcp",
                        "status": "error",
                        "error": error_msg
                    }
                }
            }
        )
```

---

### 方案 2：修改 tool_node 使用包装器

```python
async def tool_node(self, state: MessagesState):
    """
    工具执行节点 - 支持 MCP 工具双重输出
    """
    llm_response = state["messages"][-1]
    
    if not hasattr(llm_response, 'tool_calls') or not llm_response.tool_calls:
        return {}
    
    writer = get_stream_writer()
    tool_messages = []
    tool_results = {}
    
    for tool_call in llm_response.tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")
        
        try:
            tool = self.tool_dict[tool_name]
            
            # 判断是否为 MCP 工具
            is_mcp_tool = tool_name in self.mcp_tool_names  # 需要维护 MCP 工具名称列表
            
            if is_mcp_tool:
                # 使用双重输出包装器
                command = await invoke_mcp_tool_with_dual_output(
                    tool=tool,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_call_id=tool_id,
                    max_content_length=500
                )
                
                # 提取 Command 中的更新
                if "messages" in command.update:
                    tool_messages.extend(command.update["messages"])
                if "tool_results" in command.update:
                    tool_results.update(command.update["tool_results"])
            
            else:
                # 普通工具：直接调用
                result = await tool.ainvoke(tool_args)
                tool_messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_id)
                )
        
        except Exception as e:
            error_msg = f"工具调用失败: {tool_name}, 错误: {str(e)}"
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id)
            )
    
    return {
        "messages": tool_messages,
        "tool_results": tool_results
    }
```

---

## 📊 对比分析

### ❌ 当前方式（占用大量 token）

```python
# MCP 工具返回大量数据
result = await mcp_tool.ainvoke(args)
# result 可能包含几千行数据

# 直接放入 ToolMessage
ToolMessage(content=str(result))  # 占用大量 token
```

### ✅ 包装器方式（双重输出）

```python
# 使用包装器
command = await invoke_mcp_tool_with_dual_output(
    tool=mcp_tool,
    tool_name="mcp_tool",
    tool_args=args,
    tool_call_id="call_123"
)

# 结果：
# 1. ToolMessage 只包含简短摘要："执行成功，返回 5000 字符数据"
# 2. 详细数据通过 get_stream_writer 发送
# 3. 不占用大量 token
```

---

## 🎯 实施步骤

### 1. 创建包装器函数

将 `invoke_mcp_tool_with_dual_output` 函数添加到项目中：

```python
# app/core/tools/mcp_wrapper.py
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
from datetime import datetime

async def invoke_mcp_tool_with_dual_output(...):
    # 实现代码见上文
    pass
```

### 2. 修改 tool_node

在 `Mainagent.py` 中修改 `tool_node` 方法，使用包装器处理 MCP 工具。

### 3. 维护 MCP 工具列表

```python
class MainAgent:
    def __init__(self):
        self.mcp_tool_names = set()  # 存储 MCP 工具名称
    
    async def init_async(self):
        # 获取 MCP 工具
        self.mcp_tools = await self.mcpservers_tools.get_mcp_method_list()
        
        # 记录 MCP 工具名称
        self.mcp_tool_names = {tool.name for tool in self.mcp_tools}
```

---

## 💡 优势总结

| 方面 | 当前方式 | 包装器方式 |
|------|---------|-----------|
| **Token 占用** | ❌ 大量占用 | ✅ 最小占用 |
| **数据完整性** | ✅ 完整 | ✅ 完整 |
| **实时性** | ❌ 执行完成后返回 | ✅ 实时流式输出 |
| **前端体验** | ⚠️ 较差 | ✅ 最佳 |
| **兼容性** | ✅ 简单 | ⚠️ 需要包装 |

---

## 🚀 下一步

1. **创建包装器函数** - 实现 `invoke_mcp_tool_with_dual_output`
2. **修改 tool_node** - 使用包装器处理 MCP 工具
3. **测试验证** - 确保流式和非流式模式都能正常工作
4. **更新文档** - 记录 MCP 工具的双重输出策略

---

## 📚 相关文档

- [TOOL_OUTPUT_FORMAT.md](./TOOL_OUTPUT_FORMAT.md) - 统一输出格式
- [DUAL_OUTPUT_STRATEGY.md](./DUAL_OUTPUT_STRATEGY.md) - 双重输出策略
- [STREAMING_VS_NON_STREAMING.md](./STREAMING_VS_NON_STREAMING.md) - 流式 vs 非流式
