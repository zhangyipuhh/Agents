# Agents 智能体模块说明

## 项目概述
本模块基于 **LangGraph** 和 **LangChain** 框架开发的智能体系统，采用图结构的方式组织和管理智能体的各个组件。系统通过模块化设计，将工具定义、模型调用、状态管理、子图定义和条件判断等功能分离，最终在主智能体中完成组装。

## 技术栈
- **LangGraph**：用于构建智能体的图结构和工作流
- **LangChain**：提供大语言模型调用、工具管理和链式调用等基础功能
- **Python 3.x**：开发语言

## 目录结构

```
agents/
├── Mainagent.py          # 主智能体文件，负责所有组件的组装
├── tools/                # 工具定义文件夹
├── llmcalls/             # 模型调用相关代码
├── states/               # 短期记忆管理模块
├── subgraphs/            # 子图定义文件夹
└── continues/            # 执行条件判断逻辑
```

## 文件夹详细说明

### Mainagent.py
**职责**：主智能体入口文件，负责组装所有组件并启动智能体系统

**核心功能**：
- 初始化各个子模块（tools、llmcalls、states、subgraphs、continues）
- 创建 LangGraph 图结构
- 注册所有工具、子图和条件判断逻辑
- 配置智能体的状态管理
- 提供智能体的对外接口

**使用方法**：
```python
from agents.Mainagent import MainAgent

# 创建智能体实例
agent = MainAgent()

# 执行智能体任务
result = agent.run(user_input)
```

### tools/
**职责**：定义和管理智能体可使用的所有工具

**核心功能**：
- 定义工具函数
- 配置工具的输入输出格式
- 实现工具的执行逻辑
- 管理工具的元数据（名称、描述、参数等）

**文件组织**：
```
tools/
├── __init__.py           # 工具模块初始化，导出所有工具
├── base_tools.py         # 基础工具定义
├── search_tools.py       # 搜索相关工具
├── calculation_tools.py  # 计算相关工具
└── custom_tools.py       # 自定义工具
```

**配置说明**：
- 从 `config/` 文件夹读取工具配置
- 支持动态加载和注册工具

**示例**：
```python
from langchain.tools import tool

@tool
def search_web(query: str) -> str:
    """搜索网络信息"""
    # 实现搜索逻辑
    return result
```

### llmcalls/
**职责**：管理所有与大语言模型（LLM）相关的调用逻辑

**核心功能**：
- 初始化 LLM 客户端
- 配置模型参数（温度、最大token等）
- 实现模型调用接口
- 处理模型响应
- 管理多模型切换

**文件组织**：
```
llmcalls/
├── __init__.py           # LLM调用模块初始化
├── model_config.py       # 模型配置文件
├── llm_client.py         # LLM客户端实现
├── prompt_templates.py    # 提示词模板
└── response_handler.py   # 响应处理器
```

**配置说明**：
- 从 `config/` 文件夹读取模型配置
- 支持多种 LLM 提供商（OpenAI、Anthropic、本地模型等）

**示例**：
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4",
    temperature=0.7,
    max_tokens=2000
)
```

### states/
**职责**：管理智能体的短期记忆和状态信息

**核心功能**：
- 定义状态数据结构
- 实现状态的读写操作
- 管理状态的生命周期
- 提供状态查询和更新接口
- 支持状态持久化

**文件组织**：
```
states/
├── __init__.py           # 状态模块初始化
├── state_schema.py       # 状态数据结构定义
├── state_manager.py      # 状态管理器
├── memory_store.py       # 记忆存储实现
└── state_utils.py        # 状态工具函数
```

**配置说明**：
- 从 `config/` 文件夹读取状态配置
- 支持内存、文件、数据库等多种存储方式

**示例**：
```python
from typing import TypedDict, Annotated
from operator import add

class AgentState(TypedDict):
    messages: Annotated[list, add]
    current_step: str
    context: dict
```

### subgraphs/
**职责**：定义和管理智能体的子图结构

**核心功能**：
- 定义子图的节点和边
- 实现子图的执行逻辑
- 管理子图之间的依赖关系
- 支持子图的嵌套和组合

**文件组织**：
```
subgraphs/
├── __init__.py           # 子图模块初始化
├── planning_graph.py     # 规划子图
├── execution_graph.py    # 执行子图
├── reflection_graph.py   # 反思子图
└── custom_graphs.py      # 自定义子图
```

**配置说明**：
- **注意**：此文件夹不使用 `config/` 文件夹的配置
- 子图使用独立的配置文件或硬编码配置

**示例**：
```python
from langgraph.graph import StateGraph

def create_planning_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", planning_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_edge("plan", "evaluate")
    return graph.compile()
```

### continues/
**职责**：实现智能体的条件判断逻辑，决定执行流程的走向

**核心功能**：
- 定义条件判断函数
- 实现分支逻辑
- 支持多条件组合
- 提供条件评估接口

**文件组织**：
```
continues/
├── __init__.py           # 条件判断模块初始化
├── routing_logic.py      # 路由逻辑
├── condition_checkers.py # 条件检查器
└── decision_makers.py    # 决策函数
```

**配置说明**：
- 从 `config/` 文件夹读取条件配置
- 支持动态条件规则

**示例**：
```python
def should_continue(state: AgentState) -> str:
    """判断是否继续执行"""
    if len(state["messages"]) > 10:
        return "end"
    return "continue"
```

## 组件交互流程

### 1. 初始化流程
```
Mainagent.py
    ├── 加载 config/ 配置
    ├── 初始化 tools/ 工具
    ├── 初始化 llmcalls/ 模型客户端
    ├── 初始化 states/ 状态管理器
    ├── 加载 subgraphs/ 子图定义
    └── 加载 continues/ 条件判断逻辑
```

### 2. 执行流程
```
用户输入
    ↓
Mainagent 接收输入
    ↓
更新 states/ 状态
    ↓
continues/ 条件判断 → 决定执行路径
    ↓
llmcalls/ 调用模型 或 tools/ 执行工具
    ↓
更新 states/ 状态
    ↓
continues/ 条件判断 → 循环或结束
    ↓
返回结果
```

### 3. 子图调用流程
```
Mainagent 主图
    ↓
触发子图调用
    ↓
进入 subgraphs/ 子图
    ↓
子图内部执行（可能调用 tools/、llmcalls/）
    ↓
子图返回结果
    ↓
Mainagent 主图继续执行
```

## 配置管理

### config/ 文件夹
- **适用范围**：tools/、llmcalls/、states/、continues/
- **不适用**：subgraphs/

**配置文件示例**：
```yaml
# config/agent_config.yaml
model:
  provider: "openai"
  model_name: "gpt-4"
  temperature: 0.7
  max_tokens: 2000

tools:
  enabled:
    - search_web
    - calculator
    - file_reader

state:
  storage_type: "memory"
  max_history: 50
```

## 开发指南

### 添加新工具
1. 在 `tools/` 文件夹中创建工具函数
2. 使用 `@tool` 装饰器定义工具
3. 在 `tools/__init__.py` 中导出工具
4. 在 `config/` 中添加工具配置

### 添加新子图
1. 在 `subgraphs/` 文件夹中创建子图文件
2. 定义子图的节点和边
3. 实现节点的执行函数
4. 在 `Mainagent.py` 中注册子图

### 添加新条件判断
1. 在 `continues/` 文件夹中创建条件函数
2. 实现条件判断逻辑
3. 返回下一步的节点名称
4. 在 `Mainagent.py` 中注册条件

## 最佳实践

1. **模块化设计**：每个组件应独立、可复用
2. **类型提示**：使用 Type Hints 提高代码可读性
3. **错误处理**：所有外部调用都应有错误处理
4. **日志记录**：记录关键操作和错误信息
5. **配置分离**：配置与代码分离，便于维护
6. **单元测试**：为每个组件编写测试用例
7. **文档注释**：使用 docstring 说明函数和类的用途

## 扩展说明

### 支持的功能
- 多轮对话
- 工具调用
- 复杂任务分解
- 自我反思和修正
- 多智能体协作

### 性能优化
- 使用异步调用提高并发性能
- 缓存模型响应减少重复计算
- 批量处理提高效率
- 状态压缩减少内存占用

## 常见问题

**Q: 如何切换不同的 LLM 模型？**
A: 修改 `config/` 中的模型配置，或直接在 `llmcalls/` 中修改模型初始化代码。

**Q: 如何添加新的存储方式？**
A: 在 `states/` 中实现新的存储类，继承自基础存储接口，然后在配置中指定。

**Q: 子图之间如何共享数据？**
A: 通过全局状态 `states/` 进行数据共享，或通过子图的输入输出传递数据。

**Q: 如何调试智能体的执行过程？**
A: 启用 LangGraph 的调试模式，查看每一步的执行状态和中间结果。

## 参考资料
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 示例](https://github.com/langchain-ai/langgraph/tree/main/examples)

## 版本历史
- v1.0.0 - 初始版本，实现基础智能体框架
