# MCP 工具包装器使用示例

## 🎯 目标

**不修改 tool_node，让 MCP 工具自动应用双重输出策略**

---

## 📁 文件清单

1. ✅ **包装类代码** - `app/core/tools/mcp_wrapper.py`
2. ✅ **使用文档** - 本文档

---

## 🚀 使用步骤

### 步骤 1：导入包装器

在 `Mainagent.py` 中导入包装器：

```python
from app.core.tools.mcp_wrapper import wrap_mcp_tools
```

### 步骤 2：修改初始化代码

在 `MainAgent.init_async` 方法中包装 MCP 工具：

```python
async def init_async(self):
    """
    异步初始化方法
    """
    try:
        print("开始初始化 MainAgent...")
        
        # 创建模型
        print("创建模型...")
        self.model = ModelFactory.create_model(
            model_type=self.model_type,
            model_name=self.model_name,
            api_key=self.api_key,
            temperature=self.temperature,
            base_url=self.base_url
        )
        
        # 获取静态工具
        print("获取静态工具...")
        static_tools = self.main_tools.get_static_method_list()
        print(f"静态工具列表获取完成，共 {len(static_tools)} 个工具")
        
        # 获取 MCP 工具
        print("获取 MCP 工具...")
        self.mcp_tools = await self.mcpservers_tools.get_mcp_method_list()
        print(f"MCP 工具列表获取完成，共 {len(self.mcp_tools)} 个工具")
        
        # ✅ 关键步骤：包装 MCP 工具
        print("包装 MCP 工具...")
        wrapped_mcp_tools = wrap_mcp_tools(
            self.mcp_tools,
            max_content_length=500  # 可根据需要调整
        )
        print(f"MCP 工具包装完成，共 {len(wrapped_mcp_tools)} 个工具")
        
        # 合并工具列表
        print("合并工具列表...")
        self.tools = static_tools + wrapped_mcp_tools
        print(f"合并后工具列表，共 {len(self.tools)} 个工具")
        
        # 获取工具字典
        print("获取工具字典...")
        self.tool_dict = self.main_tools.get_static_methods()
        
        # ✅ 关键：添加包装后的 MCP 工具到字典
        self.tool_dict.update({tool.name: tool for tool in wrapped_mcp_tools})
        print(f"工具字典共 {len(self.tool_dict)} 个工具")
        
        # 绑定工具到模型
        print("绑定工具到模型...")
        self.model_with_tools = self.model.bind_tools(self.tools)
        print("初始化完成！")
        
    except Exception as e:
        print(f"MainAgent.init_async 错误: {e}")
        import traceback
        traceback.print_exc()
        raise
```

### 步骤 3：tool_node 无需修改

```python
async def tool_node(self, state: MessagesState):
    """
    工具执行节点 - 完全不需要修改
    """
    llm_response = state["messages"][-1]
    
    if not hasattr(llm_response, 'tool_calls') or not llm_response.tool_calls:
        return {}
    
    tool_messages = []
    
    for tool_call in llm_response.tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_id = tool_call.get("id")
        
        try:
            # ✅ 调用包装后的工具
            # 如果是 MCP 工具，会自动应用双重输出策略
            result = await self.tool_dict[tool_name].ainvoke(tool_args)
            
            # ✅ result 已经是简短摘要（对于大数据）
            # 或者完整数据（对于小数据）
            tool_messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_id)
            )
        except Exception as e:
            error_msg = f"工具调用失败: {tool_name}, 错误: {str(e)}"
            tool_messages.append(
                ToolMessage(content=error_msg, tool_call_id=tool_id)
            )
    
    return {"messages": tool_messages}
```

---

## 📊 工作流程

### 传统方式（占用大量 token）

```
LLM 决策 → tool_node 调用 MCP 工具 → 返回大量数据 → ToolMessage 包含所有数据 → 占用大量 token
```

### 包装器方式（不占用 token）

```
LLM 决策 → tool_node 调用包装后的 MCP 工具
         ↓
    包装器内部：
    1. 调用原始 MCP 工具
    2. get_stream_writer 发送详细数据
    3. 返回简短摘要字符串
         ↓
    tool_node 创建 ToolMessage（简短摘要）
         ↓
    只占用少量 token
```

---

## 🎯 效果对比

### 示例：高德地图搜索工具

#### ❌ 传统方式

```python
# MCP 工具返回大量数据
result = await amap_search.ainvoke({"query": "北京餐厅"})

# result 包含：
# {
#   "pois": [
#     {"name": "餐厅1", "address": "...", "phone": "...", ...},
#     {"name": "餐厅2", "address": "...", "phone": "...", ...},
#     ...  # 可能有几十个结果
#   ],
#   "total": 50,
#   ...
# }

# ToolMessage 包含所有数据
ToolMessage(content=str(result))  # 可能几千字符
```

**结果**：占用大量 token

#### ✅ 包装器方式

```python
# 调用包装后的工具
result = await wrapped_amap_search.ainvoke({"query": "北京餐厅"})

# 包装器内部：
# 1. 调用原始工具获取数据
# 2. get_stream_writer 发送详细数据
# 3. 返回简短摘要

# result 是简短摘要
result = "执行成功，返回 dict，大小: 3500 字符"

# ToolMessage 只包含摘要
ToolMessage(content=result)  # 只有几十字符
```

**结果**：只占用少量 token，详细数据已流式发送

---

## 💡 关键要点

### 1. 自动判断数据大小

```python
# 包装器自动判断
if len(result) <= 500:
    # 小数据：直接返回
    return result
else:
    # 大数据：分离处理
    writer({"body": {"data": result}})  # 发送详细数据
    return "执行成功，返回 3500 字符数据"  # 返回摘要
```

### 2. 流式输出详细数据

```python
# 前端接收流式数据
async for chunk in graph.astream(inputs, stream_mode="custom"):
    if chunk["header"]["status"] == "progress":
        # 接收详细数据
        detailed_data = chunk["body"]["data"]
        display(detailed_data)
```

### 3. tool_node 完全透明

```python
# tool_node 不需要知道工具是否被包装
result = await self.tool_dict[tool_name].ainvoke(tool_args)
# 包装器自动处理，返回简短摘要或完整数据
```

---

## 🔧 配置选项

### 调整最大内容长度

```python
# 默认 500 字符
wrapped_tools = wrap_mcp_tools(mcp_tools, max_content_length=500)

# 调整为 1000 字符
wrapped_tools = wrap_mcp_tools(mcp_tools, max_content_length=1000)

# 调整为 200 字符（更激进的分离）
wrapped_tools = wrap_mcp_tools(mcp_tools, max_content_length=200)
```

### 查看包装后的工具

```python
# 查看工具名称
print([tool.name for tool in wrapped_tools])

# 查看工具类型
print([type(tool).__name__ for tool in wrapped_tools])
# 输出: ['MCPToolWrapper', 'MCPToolWrapper', ...]
```

---

## 📚 相关文档

- [MCP_TOOL_WRAPPER.md](./MCP_TOOL_WRAPPER.md) - 包装器设计文档
- [MCP_DATA_SEPARATION.md](./MCP_DATA_SEPARATION.md) - 数据分离方案
- [TOOL_OUTPUT_FORMAT.md](./TOOL_OUTPUT_FORMAT.md) - 统一输出格式

---

## 🎉 总结

✅ **不修改 tool_node** - 完全保持原有结构  
✅ **自动应用双重输出** - 包装器自动处理  
✅ **减少 token 占用** - 大数据只返回摘要  
✅ **保持数据完整** - 详细数据流式发送  
✅ **代码侵入性最小** - 只修改初始化代码
