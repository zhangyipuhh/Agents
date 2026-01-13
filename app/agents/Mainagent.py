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

import json
from langgraph.graph import StateGraph, START, END
from app.agents.llmcalls.model_factory import ModelFactory
from app.agents.config.config import LLM_CONFIG, PROMPT_TEMPLATE
from app.agents.states.mainstates import MessagesState
from app.agents.tools.maintools import MainTools
from app.agents.continues.maincontinues import should_continue
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage


class MainAgent:
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
        self.tools = self.main_tools.get_static_method_list()
        # 获取工具字典（用于工具节点调用）
        self.tool_dict = self.main_tools.get_static_methods()
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
            StateGraph[MessagesState, None, MessagesState, MessagesState](MessagesState)
            # 添加LLM调用节点，处理消息生成和工具调用决策
            .add_node("llm_call", self.llm_call)
            # 添加工具执行节点，执行LLM决策的工具调用
            .add_node("tool_node", self.tool_node)
            # 添加起始边：从START节点到LLM调用节点
            .add_edge(START, "llm_call")
            # 添加条件边：根据should_continue函数决定下一步
            # 如果需要调用工具则转到tool_node，否则结束
            .add_conditional_edges(
                "llm_call",
                should_continue,
                ["tool_node", END]
            )
            # 添加回环边：工具执行完成后返回LLM调用节点
            .add_edge("tool_node", "llm_call")
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


import asyncio


async def main():
    """
    主函数：演示智能体的执行流程

    创建智能体实例，执行工作流，监听并输出流式事件。
    展示智能体如何处理合同条款审计任务。
    """
    print("DEBUG: 开始执行代码")

    # 定义输入消息
    inputs = {
        # 测试合同条款审计
        "messages": [HumanMessage(content="合同条款是甲方应在收到发票后90天内付款。")]
        # 测试数据库查询
        # "messages": [HumanMessage(content="查询客户数据库中所有状态为'已付款'的客户。")]
        # 测试工具调用
        # "messages": [HumanMessage(content="计算 5 乘以 3 等于多少？")]
    }
    print("DEBUG: inputs 已创建")
    print("=" * 50)
    print("🚀 开始流式审批")
    print("=" * 50)

    # 创建智能体实例和工作流
    main_agent = MainAgent()
    agent = main_agent.CreateAgent()

    print("\n" + "=" * 50)
    print("📊 Graph 流式执行过程 (astream_events)")
    print("=" * 50)

    # 初始化当前节点名称
    current_node = None

    # 异步监听工作流事件
    async for event in agent.astream_events(inputs, version="v1"):
        # 提取事件类型和数据
        event_type = event["event"]
        data = event.get("data", {})

        # 分支1：处理链开始事件（节点启动）
        if event_type == "on_chain_start":
            # 获取节点名称
            node_name = event.get("name", "")
            # 检查节点是否变化
            if node_name and node_name != current_node:
                # 更新当前节点
                current_node = node_name
                # 输出节点分隔线
                print("\n" + "-" * 50)
                print(f"📍 节点: {node_name}")
                print("-" * 50)

        # 分支2：处理LLM流式输出事件（token级别）
        elif event_type == "on_chat_model_stream":
            # 获取输出块
            chunk = data.get("chunk")
            # 检查是否有文本内容
            if chunk and hasattr(chunk, 'content') and chunk.content:
                # 实时输出文本内容（不换行）
                print(chunk.content, end="", flush=True)

        # 分支3：处理LLM结束事件
        elif event_type == "on_chat_model_end":
            # 输出换行
            print()

        # 分支4：处理工具调用开始事件
        elif event_type == "on_tool_start":
            # 提取工具名称和参数
            tool_name = data.get("input", {}).get("name", "")
            tool_args = data.get("input", {}).get("args", {})
            # 输出工具调用信息
            print(f"\n🔧 调用工具: {tool_name}")
            print(f"   参数: {tool_args}")

        # 分支5：处理工具调用结束事件
        elif event_type == "on_tool_end":
            # 提取工具执行结果
            result = data.get("output", "")
            # 检查结果类型
            if isinstance(result, str):
                # 字符串结果：截断显示（最多100字符）
                print(f"📋 工具结果: {result[:100]}{'...' if len(result) > 100 else ''}")
            else:
                # 其他类型结果：直接显示
                print(f"📋 工具结果: {result}")

    # 输出完成信息
    print("\n" + "=" * 50)
    print("✅ 审批完成")
    print("=" * 50)


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
