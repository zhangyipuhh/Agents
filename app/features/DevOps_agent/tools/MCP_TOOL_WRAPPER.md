# MCP 工具包装方案（不修改 tool_node）

## 🎯 核心问题

**用户需求**：
- ✅ 不修改 `tool_node` 节点代码
- ✅ 让 MCP 工具返回的数据应用双重输出策略
- ✅ 保持 LangGraph 工作流结构不变

**解决方案**：**在工具层面包装 MCP 工具**

---

## 💡 核心思路

```
┌─────────────────────────────────────────────────────────┐
│  工作流程                                                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. LLM 决策调用工具                                     │
│     └─> AIMessage(tool_calls=[...])                     │
│                                                          │
│  2. tool_node 执行工具                                   │
│     └─> result = await tool.ainvoke(args)               │
│                                                          │
│  3. 包装后的 MCP 工具自动处理                            │
│     ├─> 调用原始 MCP 工具                                │
│     ├─> get_stream_writer 发送详细数据                   │
│     └─> 返回简短摘要字符串                               │
│                                                          │
│  4. tool_node 创建 ToolMessage                          │
│     └─> ToolMessage(content=简短摘要)                    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**关键点**：
- `tool_node` 不需要任何修改
- MCP 工具在添加到 `tool_dict` 之前被包装
- 包装后的工具返回简短字符串，而不是大量数据

---

## ✅ 解决方案：MCP 工具包装类

### 完整实现代码

```python
from langchain_core.tools import BaseTool, ToolException
from langgraph.config import get_stream_writer
from pydantic import BaseModel
from typing import Any, Optional, Type
from datetime import datetime
import json


class MCPToolWrapper(BaseTool):
    """
    MCP 工具包装类
    
    包装 MCP 工具，自动应用双重输出策略：
    1. 调用原始 MCP 工具
    2. 通过 get_stream_writer 发送详细数据
    3. 返回简短摘要字符串
    """
    
    original_tool: BaseTool
    max_content_length: int = 500
    
    class Config:
        arbitrary_types_allowed = True
    
    @property
    def name(self) -> str:
        """工具名称"""
        return self.original_tool.name
    
    @property
    def description(self) -> str:
        """工具描述"""
        return self.original_tool.description
    
    @property
    def args_schema(self) -> Optional[Type[BaseModel]]:
        """参数 schema"""
        return self.original_tool.args_schema
    
    def _run(self, *args, **kwargs) -> str:
        """同步运行（不支持）"""
        raise NotImplementedError("MCP 工具只支持异步调用")
    
    async def _arun(self, *args, **kwargs) -> str:
        """
        异步运行 - 应用双重输出策略
        
        Returns:
            str: 简短摘要字符串（不是详细数据）
        """
        writer = get_stream_writer()
        tool_name = self.original_tool.name
        
        # 生成唯一的 tool_call_id（如果没有传入）
        tool_call_id = kwargs.pop("tool_call_id", f"{tool_name}_{datetime.now().timestamp()}")
        
        try:
            # 1. 发送开始标记
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
                        "args": kwargs
                    }
                },
                "footer": None
            })
            
            # 2. 调用原始 MCP 工具
            result = await self.original_tool.ainvoke(kwargs)
            
            # 3. 分析结果数据
            result_str = str(result)
            result_length = len(result_str)
            
            # 4. 判断数据大小
            if result_length <= self.max_content_length:
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
                
                # 返回完整数据（小数据）
                return result_str
            
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
                
                # 4.3 返回简短摘要
                summary = f"执行成功，返回 {result_length} 字符数据"
                if isinstance(result, (dict, list)):
                    summary = f"执行成功，返回 {type(result).__name__}，大小: {result_length} 字符"
                
                return summary  # 关键：返回简短摘要，不是详细数据
        
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
            
            # 返回错误信息
            return f"错误：{error_msg}"


def wrap_mcp_tools(mcp_tools: list[BaseTool], max_content_length: int = 500) -> list[BaseTool]:
    """
    包装 MCP 工具列表
    
    Args:
        mcp_tools: MCP 工具列表
        max_content_length: 最大内容长度（字符）
    
    Returns:
        list[BaseTool]: 包装后的工具列表
    """
    wrapped_tools = []
    
    for tool in mcp_tools:
        wrapped_tool = MCPToolWrapper(
            original_tool=tool,
            max_content_length=max_content_length
        )
        wrapped_tools.append(wrapped_tool)
    
    return wrapped_tools
```

---

## 🚀 使用方法

### 修改 MainAgent 的初始化代码

```python
class MainAgent:
    async def init_async(self):
        """异步初始化"""
        # ... 其他初始化代码 ...
        
        # 获取静态工具
        static_tools = self.main_tools.get_static_methods()
        
        # 获取 MCP 工具
        self.mcp_tools = await self.mcpservers_tools.get_mcp_method_list()
        
        # ✅ 关键：包装 MCP 工具
        wrapped_mcp_tools = wrap_mcp_tools(
            self.mcp_tools, 
            max_content_length=500
        )
        
        # 合并工具列表
        self.tools = static_tools + wrapped_mcp_tools
        
        # 获取工具字典
        self.tool_dict = self.main_tools.get_static_methods()
        self.tool_dict.update({tool.name: tool for tool in wrapped_mcp_tools})
        
        # 绑定工具到模型
        self.model_with_tools = self.model.bind_tools(self.tools)
```

### tool_node 完全不需要修改

```python
async def tool_node(self, state: MessagesState):
    """工具执行节点 - 完全不需要修改"""
    llm_response = state["messages"][-1]
    
    if not hasattr(llm_response, 'tool_calls') or not llm_response.tool_calls:
        return state
    
    tool_messages = []
    
    for tool_call in llm_response.tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")
        
        try:
            # ✅ 包装后的工具自动应用双重输出策略
            # 返回的是简短摘要字符串，不是大量数据
            result = await self.tool_dict[tool_name].ainvoke(tool_args)
            
            tool_messages.append(
                ToolMessage(content=result, tool_call_id=tool_id)
            )
        except Exception as e:
            error_msg = f"工具调用失败: {tool_name}, 错误: {str(e)}"
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id)
            )
    
    return {"messages": tool_messages}
```

---

## 📊 工作流程对比

### ❌ 传统方式（占用大量 token）

```
1. LLM 决策调用 MCP 工具
2. tool_node 调用 MCP 工具
   └─> result = await mcp_tool.ainvoke(args)
   └─> result 包含几千行数据
3. tool_node 创建 ToolMessage
   └─> ToolMessage(content=str(result))  # 大量数据
4. ToolMessage 添加到 messages 状态
   └─> 占用大量 token
```

### ✅ 包装器方式（不占用 token）

```
1. LLM 决策调用 MCP 工具
2. tool_node 调用包装后的 MCP 工具
   └─> 包装器内部：
       ├─> 调用原始 MCP 工具
       ├─> get_stream_writer 发送详细数据
       └─> 返回简短摘要字符串
3. tool_node 创建 ToolMessage
   └─> ToolMessage(content="执行成功，返回 5000 字符数据")
4. ToolMessage 添加到 messages 状态
   └─> 只占用少量 token
```

---

## 💡 优势总结

| 方面 | 传统方式 | 包装器方式 |
|------|---------|-----------|
| **tool_node 修改** | ✅ 不需要 | ✅ 不需要 |
| **Token 占用** | ❌ 大量占用 | ✅ 最小占用 |
| **数据完整性** | ✅ 完整 | ✅ 完整 |
| **实时性** | ❌ 执行完成后返回 | ✅ 实时流式输出 |
| **前端体验** | ⚠️ 较差 | ✅ 最佳 |
| **代码侵入性** | ✅ 无 | ✅ 无 |

---

## 🎯 关键要点

1. **不修改 tool_node** - 完全保持原有结构
2. **在工具层面包装** - 在添加到 `tool_dict` 之前包装 MCP 工具
3. **自动应用双重输出** - 包装器自动处理数据分离
4. **返回简短字符串** - 包装后的工具返回简短摘要，不是详细数据

---

## 📁 文件结构

```
app/core/tools/
├── mcp_wrapper.py              # MCP 工具包装类
│   └── MCPToolWrapper
│   └── wrap_mcp_tools()
└── ...

app/features/stream_Agent/
├── Mainagent.py                # 修改初始化代码
└── tools/
    └── mcpservers.py           # MCP 工具获取（不需要修改）
```

---

## 🚀 实施步骤

1. **创建包装类** - 实现 `MCPToolWrapper` 和 `wrap_mcp_tools`
2. **修改初始化** - 在 `MainAgent.init_async` 中包装 MCP 工具
3. **测试验证** - 确保流式和非流式模式都能正常工作
4. **无需修改 tool_node** - 保持原有结构不变

---

## 📚 相关文档

- [TOOL_OUTPUT_FORMAT.md](./TOOL_OUTPUT_FORMAT.md) - 统一输出格式
- [DUAL_OUTPUT_STRATEGY.md](./DUAL_OUTPUT_STRATEGY.md) - 双重输出策略
- [MCP_DATA_SEPARATION.md](./MCP_DATA_SEPARATION.md) - MCP 数据分离方案
