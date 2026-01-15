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
                result = self.tool_dict[tool_name].invoke(tool_args)
                tool_messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_id)
                )
            except Exception as e:
                error_msg = f"工具调用失败: {tool_name}, 错误: {str(e)}"
                tool_messages.append(
                    ToolMessage(content=error_msg, tool_call_id=tool_id)
                )

        return {"messages": tool_messages}

    async def llm_call(self, state: MessagesState):
        """
        LLM调用节点

        使用绑定了工具的模型生成响应，支持工具调用决策。
        消息历史会累积，形成对话上下文。

        Args:
            state: 当前工作流状态，包含消息列表

        Returns:
            dict: 更新后的状态，包含AI响应消息
        """
        messages = state["messages"]
        response = await self.model_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def route_after_tool(self, state: MessagesState):
        """
        工具执行后路由决策

        根据最后一条工具消息的内容，决定下一个处理节点。
        支持合同条款审计和数据库搜索两种子图类型。

        Args:
            state: 当前工作流状态，包含消息列表

        Returns:
            str: 下一个节点的名称
        """
        last_message = state["messages"][-1]
        if not isinstance(last_message, ToolMessage):
            return "llm_call"

        content = last_message.content
        if "subgraph_b" in content:
            return "subgraph_b"
        elif "subgraph_a" in content:
            return "subgraph_a"
        else:
            return "llm_call"

    def create_subgraph_a(self, state: MessagesState):
        """
        子图A：合同条款审计

        使用专门的合同审计智能体处理合同条款相关任务。
        将当前状态传递给子图，获取审计结果后返回。

        Args:
            state: 当前工作流状态，包含消息列表

        Returns:
            dict: 更新后的状态，包含审计结果消息
        """
        audit_agent = AuditContractClauseAgent()
        result = audit_agent.invoke(state)
        return result

    def create_subgraph_b(self, state: MessagesState):
        """
        子图B：数据库搜索

        使用专门的数据库搜索智能体处理数据库查询任务。
        将当前状态传递给子图，获取搜索结果后返回。

        Args:
            state: 当前工作流状态，包含消息列表

        Returns:
            dict: 更新后的状态，包含搜索结果消息
        """
        search_agent = SearchDatabaseAgent()
        result = search_agent.invoke(state)
        return result
