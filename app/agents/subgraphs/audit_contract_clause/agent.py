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
from app.agents.states.mainstates import MessagesState
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END


class Agent:
    """
    合同条款审计子图智能体类

    负责构建和管理合同条款审计子图的工作流，包括模型初始化、工具绑定、状态图构建和执行。
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
        self.messages_state = messages_state
        pass
    def violation_analysis(self,state: MessagesState):
            last_message = state["messages"][-1]
            analysis = f"违规分析：建议修改条款。"
            return {"messages": [AIMessage(content=analysis)]}
        
    def violation_report(self,state: MessagesState):
            last_message = state["messages"][-1]
            report = f"违规报告："
            return {"messages": [AIMessage(content=report)]}
    def CreateAgent(self):
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
        subgraph = StateGraph(MessagesState)
        subgraph.add_node("violation_analysis", self.violation_analysis)
        subgraph.add_node("violation_report", self.violation_report)
        subgraph.add_edge(START, "violation_analysis")
        subgraph.add_edge("violation_analysis", "violation_report")
        subgraph.add_edge("violation_report", END)
        
        return subgraph.compile()

    