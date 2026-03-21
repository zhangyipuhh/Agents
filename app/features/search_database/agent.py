# e:\laboratory\AI\Agents\app\agents\subgraphs\search_database\agent.py
#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
数据库搜索子图智能体模块

本模块实现了数据库搜索子图的核心功能，包括状态图构建、流式输出等。
子图使用LangGraph构建工作流，支持流式输出和事件监听。

Date: 2026-01-13
Author: 张镒谱
"""
import asyncio
from app.agents.states.mainstates import MessagesState
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END


class Agent:
    """
    数据库搜索子图智能体类

    负责构建和管理数据库搜索子图的工作流，包括状态图构建和执行。
    支持流式输出和事件监听。

    Attributes:
        messages_state: 消息状态对象，定义工作流中的状态结构
    """

    def __init__(self):
        pass

    async def normal_process(self, state: MessagesState):
        """
        正常流程处理节点

        使用yield输出中间状态和最终结果，实现流式响应。

        Args:
            state: 当前工作流状态，包含消息列表

        Yields:
            dict: 更新后的状态，包含处理结果消息
        """
        #last_message = state["messages"][-1]
        intermediate_messages = []
        # 模拟长时间处理过程
        # 使用yield输出中间状态
        process_steps = []
        for i in range(5):
            await asyncio.sleep(0.5)  # 引入标准库 time，实现阻塞式延时，模拟数据库查询耗时（张镒谱，2026-01-13）
            step_content = f"处理步骤 {i+1}/5: 正在查询数据库..."
            yield {"messages": [AIMessage(content=step_content)]}
            process_steps.append(step_content)
            #print(step_content)
            # 使用yield输出中间状态
            yield {"messages": intermediate_messages}
        
        # 构建完整的结果消息
        final_message = AIMessage(content="✅ 数据库查询完成，我是子图B的返回信息")
        intermediate_messages.append(final_message)
        print(f"✅✅✅ [Subgraph B] 节点运行完毕，准备返回状态。消息数量: {len(intermediate_messages)}")
        # 使用yield返回最终状态
        yield {"messages": intermediate_messages}

    def CreateAgent(self, prompt: str = None):
        """
        创建智能体工作流

        构建LangGraph状态图，定义节点、边和条件边，编译并返回可执行的工作流。
        工作流包含正常流程处理节点。

        Args:
            prompt: 可选的系统提示词，当前未使用

        Returns:
            编译后的状态图对象，可执行工作流
        """
        # 创建状态图，使用MessagesState作为状态类型
        subgraph = StateGraph(MessagesState)
        subgraph.add_node("normal_process", self.normal_process)    
        subgraph.add_edge(START, "normal_process")
        # 移除连接到END的边，让子图直接返回状态更新给主图
        subgraph.add_edge("normal_process", END)
        
        return subgraph.compile()