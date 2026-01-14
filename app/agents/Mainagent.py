#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
主智能体模块

本模块实现了主智能体的核心功能，包括状态图构建、工具调用、流式输出等。
主智能体使用LangGraph构建工作流，通过LLM决策是否调用工具，支持流式输出和事件监听。
主要功能包括合同条款审计、数据库查询等工具的调用和管理。

Date: 2026-01-13
Author: 张镒谱
"""
from typing import Literal
import json
from langgraph.graph import StateGraph, START, END
from app.agents.llmcalls.model_factory import ModelFactory
from app.agents.config.config import LLM_CONFIG, PROMPT_TEMPLATE
from app.agents.states.mainstates import MessagesState
from app.agents.tools.maintools import MainTools
from app.agents.continues.maincontinues import should_continue
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from app.agents.subgraphs.search_database.agent import Agent as SearchDatabaseAgent
from app.agents.subgraphs.audit_contract_clause.agent import Agent as AuditContractClauseAgent
from app.agents.tools.mcpservers import MCPServersTools


class MainAgent:
    """
    主智能体类

    负责构建和管理智能体工作流，包括模型初始化、工具绑定、状态图构建和执行。
    支持流式输出和工具调用，通过条件边实现智能体的自主决策。

    Attributes:
        model: LLM模型实例，用于生成响应和工具调用决策
        tools: 工具列表，用于绑定到模型
        tool_dict: 工具字典，键为工具名，值为工具对象
        model_with_tools: 绑定了工具的模型实例
        _config_cache: 类级别的配置缓存（共享配置）
    """

    _config_cache: dict | None = None
    _tools_cache: dict | None = None
    """
    主智能体类

    负责构建和管理智能体工作流，包括模型初始化、工具绑定、状态图构建和执行。
    支持流式输出和工具调用，通过条件边实现智能体的自主决策。

    Attributes:
        model_factory: 模型工厂实例，用于创建LLM模型
        messages_state: 消息状态对象，定义工作流中的状态结构
        model: LLM模型实例，用于生成响应和工具调用决策
        main_tools: 主工具集实例，提供可用的工具方法
        tools: 工具列表，用于绑定到模型
        tool_dict: 工具字典，键为工具名，值为工具对象
        model_with_tools: 绑定了工具的模型实例
    """

    def __init__(self):
        """
        初始化主智能体

        创建模型工厂、初始化消息状态、创建LLM模型、绑定工具集。
        """
        # 创建模型工厂实例
        self.model_factory = ModelFactory()
        # 初始化消息状态对象
        self.messages_state = MessagesState()
        # 创建mcp服务器工具集实例
        self.mcpservers_tools = MCPServersTools()
        
        # 步骤1：初始化LLM模型
        # 从配置中读取模型类型、名称、API密钥、温度和基础URL
        self.model = self.model_factory.create_model(
            model_type=LLM_CONFIG["model_type"],
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            temperature=0,
            base_url=LLM_CONFIG["base_url"]
        )

        # 步骤2：绑定工具到模型
        # 创建主工具集实例
        self.main_tools = MainTools()
        # 获取工具列表（用于绑定到模型）
        self.tools = self.main_tools.get_static_method_list()+self.mcpservers_tools.get_mcp_method_list()
        # 获取工具字典（用于工具节点调用）
        self.tool_dict = self.main_tools.get_static_methods().update(self.mcpservers_tools.get_mcp_methods())
        # 将工具绑定到模型，使模型能够调用这些工具
        self.model_with_tools = self.model.bind_tools(self.tools)

    def CreateAgent(self, prompt: str = None):
        """
        创建智能体工作流

        构建LangGraph状态图，定义节点、边和条件边，编译并返回可执行的工作流。
        工作流包含LLM调用节点和工具执行节点，通过条件边实现循环调用。

        Args:
            prompt: 可选的系统提示词，当前未使用

        Returns:
            编译后的状态图对象，可执行工作流
        """
        # 步骤3：定义状态图结构
        # 创建状态图，使用MessagesState作为状态类型

        
        
        
        # 步骤4：连接状态图节点和边
        graph = (
            StateGraph(MessagesState)
            # 添加LLM调用节点，处理消息生成和工具调用决策
            .add_node("llm_call", self.llm_call)
            # 添加工具执行节点，执行LLM决策的工具调用
            .add_node("tool_node", self.tool_node)
            # 添加子图B节点：使用包装函数调用子图
            .add_node("subgraph_b", self.create_subgraph_b)
            .add_node("subgraph_a", self.create_subgraph_a)
            # 添加起始边：从START节点到LLM调用节点
            .add_edge(START, "llm_call")
            # 添加条件边：根据should_continue函数决定下一步
            # 如果需要调用工具则转到tool_node，否则结束
            .add_conditional_edges(
                "llm_call",
                should_continue,
                ["tool_node", END]
            )
            # 添加条件边：根据子图类型决定下一步
            .add_conditional_edges(
                "tool_node",
                self.route_after_tool,
                ["subgraph_a", "subgraph_b", "llm_call"]
            )
            # 添加回环边：工具执行完成后返回LLM调用节点
            .add_edge("subgraph_a", "llm_call")
            .add_edge("subgraph_b", "llm_call")
        )

        # 编译并返回状态图
        return graph.compile()

    def tool_node(self, state: MessagesState):
        """
        工具执行节点

        执行LLM决策的工具调用，收集工具执行结果并返回更新后的状态。
        支持多个工具的批量执行和错误处理。

        Args:
            state: 当前工作流状态，包含消息列表

        Returns:
            dict: 更新后的状态，包含工具执行结果消息
        """
        # 从状态中获取LLM的最后一条响应消息
        llm_response = state["messages"][-1]

        # 检查响应是否包含工具调用
        if not hasattr(llm_response, 'tool_calls') or not llm_response.tool_calls:
            # 没有工具调用，直接返回原状态
            return state

        # 初始化工具消息列表，用于存储执行结果
        tool_messages = []

        # 遍历所有工具调用
        for tool_call in llm_response.tool_calls:
            # 提取工具名称、参数和调用ID
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id")

            try:
                # 调用工具并获取结果
                result = self.tool_dict[tool_name].invoke(tool_args)
                # 创建工具消息对象
                tool_msg = ToolMessage(
                    content=result,
                    tool_call_id=tool_id
                )
                # 将工具消息添加到结果列表
                tool_messages.append(tool_msg)

            except Exception as e:
                # 工具执行失败，创建错误消息
                error_msg = ToolMessage(
                    content=f"工具执行失败: {str(e)}",
                    tool_call_id=tool_id
                )
                # 将错误消息添加到结果列表
                tool_messages.append(error_msg)

        # 返回更新后的状态，包含工具执行结果
        return {
            "messages": tool_messages
        }

    def llm_call(self, state: dict):
        """
        LLM调用节点

        使用绑定了工具的LLM模型处理消息，支持流式输出。
        根据输入生成响应或工具调用决策，自动添加系统提示词。

        Args:
            state: 当前工作流状态，包含消息列表和规则检查计数

        Returns:
            dict: 更新后的状态，包含LLM响应消息和递增的规则检查计数
        """
        print(f"当前消息列表: 进入模型调用函数")
        # 获取当前的消息列表
        existing_messages = state["messages"]

        # 检查消息列表中是否已包含系统消息
        has_system_message = any(msg.type == "system" for msg in existing_messages)
        # 如果没有系统消息，添加系统提示词到消息列表开头
        if not has_system_message:
            system_msg = SystemMessage(content=PROMPT_TEMPLATE["main"])
            # 将系统消息插入到最前面
            existing_messages = [system_msg] + existing_messages

        # 初始化流式输出变量
        full_content = ""  # 存储完整的文本内容
        tool_calls_list = []  # 存储工具调用列表
        args_list = ""  # 存储工具参数，流式输出时参数需要特殊处理

        try:
            # 流式调用模型，逐块处理响应
            for chunk in self.model_with_tools.stream(existing_messages):
                # 分支1：处理文本内容块
                if hasattr(chunk, 'content') and chunk.content:
                    # 累加文本内容
                    full_content += chunk.content
                # 分支2：处理工具调用块
                elif hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                    # 遍历工具调用
                    for tc in chunk.tool_calls:
                        # 跳过无效的工具调用（没有名称）
                        if "name" not in tc or not tc["name"]:
                            continue
                        # 添加有效的工具调用
                        tool_calls_list.append(tc)
                # 分支3：处理内容块（包含工具参数）
                elif hasattr(chunk, 'content_blocks') and chunk.content_blocks:
                    # 遍历内容块
                    for block in chunk.content_blocks:
                        # 检查是否为工具参数块
                        if "type" in block and block["type"] == "tool_call_chunk" and "args" in block and block["args"]:
                            # 累加工具参数
                            args_list += block["args"]

        except Exception as e:
            # 流式输出失败，回退到非流式调用
            # 调用模型获取完整响应
            response = self.model_with_tools.invoke(existing_messages)
            # 处理文本内容
            if hasattr(response, 'content') and response.content:
                full_content = response.content
            # 处理工具调用
            if hasattr(response, 'tool_calls') and response.tool_calls:
                tool_calls_list = response.tool_calls

        # 处理工具参数：将流式收集的参数字符串解析为JSON并替换到工具调用中
        for tc in tool_calls_list:
            # 将参数字符串转换为JSON对象
            tc["args"] = json.loads('{"' + args_list.replace(" ", ""))

        # 过滤无效的工具调用
        valid_tool_calls = []
        for tc in tool_calls_list:
            # 检查工具调用是否有效：名称非空、ID非空、名称不含空格
            if tc.get("name") and tc.get("id") and " " not in tc.get("name"):
                # 添加到有效工具调用列表
                valid_tool_calls.append(tc)

        # 构造AI消息对象
        if valid_tool_calls:
            # 分支1：有有效的工具调用，创建包含工具调用的消息
            response = AIMessage(
                content=full_content,
                tool_calls=valid_tool_calls
            )
        else:
            # 分支2：没有工具调用，创建普通文本消息
            response = AIMessage(content=full_content)

        # 返回更新后的状态
        return {
            "messages": [response],
            # 递增规则检查计数器
            "checked_rules_count": state.get("checked_rules_count", 0) + 1
        }
    def route_after_tool(self, state: MessagesState) -> Literal["subgraph_a", "subgraph_b", "llm_call"]:
        """
        工具节点执行后的路由函数
        
        根据最后一条消息的类型和内容，决定下一步跳转到哪个节点：
        - 如果是合同审计工具且发现违规，跳转到子图A（违规处理流程）
        - 如果是合同审计工具且未发现违规，跳转到子图B（正常流程）
        - 其他情况返回LLM调用节点继续处理
        
        Args:
            state: 当前工作流状态，包含消息列表
            
        Returns:
            str: 下一步执行的目标节点名称
                - "subgraph_a": 违规处理子图
                - "subgraph_b": 正常流程子图  
                - "llm_call": 返回LLM继续处理
        """
        # 获取消息列表
        messages = state["messages"]
        
        # 获取最后一条消息
        last_message = messages[-1]
        
        # 情况1：最后一条消息是工具执行结果
        if isinstance(last_message, ToolMessage):
            content = last_message.content
            
            # 分支1：合同审计发现违规
            if "subgraph_a" in content:
                return "subgraph_a"
            
            # 分支2：合同审计未发现违规
            elif "subgraph_b" in content:
                return "subgraph_b"
            
            # 分支3：其他工具执行结果，返回LLM继续处理
            else:
                return "llm_call"
        
        # 情况2：最后一条消息是AI消息（包含工具调用信息）
        elif isinstance(last_message, AIMessage):
            # 检查是否包含工具调用
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                # 获取第一个工具调用的名称
                tool_name = last_message.tool_calls[0].get("name", "")
                
                # 分支1：合同审计工具
                if tool_name == "audit_contract_clause":
                    # 需要等待工具执行结果，返回llm_call继续
                    return "llm_call"
                
                # 分支2：数据库搜索工具
                elif tool_name == "search_database":
                    # 直接返回llm_call继续处理
                    return "llm_call"
                
                # 分支3：其他工具
                else:
                    return "llm_call"
            
            # 没有工具调用，返回llm_call
            else:
                return "llm_call"
        
        # 情况3：其他类型的消息，返回llm_call
        else:
            return "llm_call"
# e:\laboratory\AI\Agents\app\agents\Mainagent.py
# 子图调用函数（修复版本）

    #子图测试
    async def create_subgraph_a(self, state: MessagesState):
        """
        创建违规处理子图
        
        使用 ainvoke 执行子图，子图的流式输出通过主图的 astream_events 监听实现。
        
        Args:
            state: 当前工作流状态，包含消息列表
            
        Returns:
            dict: 子图执行后的状态
        """
        audit_agent = AuditContractClauseAgent()
        agent = audit_agent.CreateAgent()
        result = await agent.ainvoke(state)
        return result
    
    async def create_subgraph_b(self, state: MessagesState):
        """
        创建正常流程子图
        
        使用 ainvoke 执行子图，子图的流式输出通过主图的 astream_events 监听实现。
        
        Args:
            state: 当前工作流状态，包含消息列表
            
        Returns:
            dict: 子图执行后的状态
        """
        search_agent = SearchDatabaseAgent()
        agent = search_agent.CreateAgent()
        result = await agent.ainvoke(state)
        return result
    
    
    
    
import asyncio


async def main():
    """
    主函数：演示智能体的执行流程

    创建智能体实例，执行工作流，监听并输出流式事件。
    展示智能体如何处理合同条款审计任务。
    """
    print("DEBUG: 开始执行代码")
    print("=" * 50)
    print(" 主图执行流程测试")
    print("=" * 50)
    
    # 创建主图实例
    from app.agents.Mainagent import MainAgent
    from app.agents.states.mainstates import MessagesState
    
    # 创建主智能体实例并编译图
    main_agent = MainAgent()
    graph = main_agent.CreateAgent()
    
    # 定义测试输入：模拟触发子图B的场景
    # 当LLM决定调用search_database工具时，应该跳转到subgraph_b
    inputs = {
        "messages": [HumanMessage(content="查询数据库中的合同记录")]
    }
    
    print("\n🚀 启动主图测试...")
    print("-" * 50)
    
    # 异步监听主图事件
    async for event in graph.astream_events(inputs, version="v1", subgraphs=True):
        event_type = event["event"]
        data = event.get("data", {})
        
        # 处理智能体步骤事件
        if event_type == "on_chain_stream":
            step_output = data.get("chunk", {})
            if step_output and isinstance(step_output, dict) and 'messages' in step_output:
                messages = step_output["messages"]
                for msg in messages:
                    if isinstance(msg, AIMessage) and msg.content:
                        print(f"🔄 处理步骤: {msg.content}")
        
        # 处理节点开始事件
        elif event_type == "on_chain_start":
            node_name = data.get("name", "Unknown")
            print(f"📍 进入节点: {node_name}")
        
        # 处理工具调用事件
        elif event_type == "on_tool_start":
            tool_name = data.get("name", "Unknown")
            print(f"🔧 开始执行工具: {tool_name}")
        
        elif event_type == "on_tool_end":
            tool_name = data.get("name", "Unknown")
            print(f"✅ 工具执行完成: {tool_name}")
        
        # 处理子图相关事件
        elif "subgraph" in event_type:
            if event_type == "on_subgraph_start":
                node_name = data.get("name", "Unknown")
                print(f"📦 进入子图: {node_name}")
            elif event_type == "on_subgraph_end":
                node_name = data.get("name", "Unknown")
                print(f"📦 子图完成: {node_name}")
        
        # 处理链结束事件
        elif event_type == "on_chain_end":
            print("\n✅ 主图测试完成")
    
    # 输出完成信息
    print("\n" + "=" * 50)
    print("✅ 所有测试执行完成")
    print("=" * 50)


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
