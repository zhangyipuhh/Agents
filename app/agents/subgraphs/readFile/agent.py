#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件阅读智能体模块

本模块实现了文件阅读智能体的核心功能，包括状态图构建、文件解析、信息提取等。
文件阅读智能体使用LangGraph构建工作流，支持读取图片并提取目标信息。
目前主要支持图片文件的读取和内容提取，后续可扩展支持其他文件格式。

Date: 2026-01-13
Author: 张镒谱
"""
from app.agents.states.mainstates import MessagesState
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END


class Agent:
    """
    文件阅读智能体类

    负责构建和管理文件阅读子图的工作流，包括模型初始化、工具绑定、状态图构建和执行。
    支持图片读取和信息提取，通过条件边实现智能体的自主决策。

    Attributes:
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
    def extract_image_content(self,state: MessagesState):
            last_message = state["messages"][-1]
            analysis = f"图片内容提取：正在分析图片信息。"
            return {"messages": [AIMessage(content=analysis)]}
        
    def organize_extracted_info(self,state: MessagesState):
            last_message = state["messages"][-1]
            report = f"信息整理："
            return {"messages": [AIMessage(content=report)]}
    def CreateAgent(self):
        """
        创建文件阅读智能体工作流

        构建LangGraph状态图，定义节点、边和条件边，编译并返回可执行的工作流。
        工作流包含图片内容提取节点和信息整理节点，通过条件边实现循环调用。

        Args:
            prompt: 可选的系统提示词，当前未使用

        Returns:
            编译后的状态图对象，可执行工作流
        """
        # 步骤3：定义状态图结构
        # 创建状态图，使用MessagesState作为状态类型

        # 步骤4：连接状态图节点和边
        subgraph = StateGraph(MessagesState)
        subgraph.add_node("extract_image_content", self.extract_image_content)
        subgraph.add_node("organize_extracted_info", self.organize_extracted_info)
        subgraph.add_edge(START, "extract_image_content")
        subgraph.add_edge("extract_image_content", "organize_extracted_info")
        subgraph.add_edge("organize_extracted_info", END)
        
        return subgraph.compile()

    