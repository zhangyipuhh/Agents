#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
通用agent模块

基于 LangGraph v1.0 。
实现多轮对话。
通过传入 state_class 和 context_class 来定义状态类和上下文类。
通过传入checkpointer来设置检查点。
使用 AgentConfig 来配置模型、Token 及存储等相关参数。

工作流:
    START → summarize → llm_call → END (自动循环调用工具直到完成)

摘要功能:
    - 使用 SummarizationNode 自动管理对话摘要，里面包含trim_messages的逻辑
    - 保留最新对话，自动摘要旧消息


Date: 2026-03-10
Author: 张镒谱
"""
import logging

import asyncio
from email import message
from typing import Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph import MessagesState
from langchain_core.messages import AnyMessage
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode, RunningSummary
from app.agents.llmcalls.model_factory import ModelFactory
from app.utils.memory.checkpoint import get_global_checkpointer
from app.agents.agent.AgentConfig import AgentConfig, AgentContext, AgentState, ExecuteConfig
from app.agents.config.config import LLM_VISION_CONFIG,LLM_CONFIG

class LLMInputState(TypedDict):
    """LLM 输入状态的类型定义
    
    定义了传递给 LLM 节点的输入格式：
        - summarized_messages: 经过摘要处理后的消息列表
        - context: 上下文摘要信息字典
    """
    summarized_messages: list[AnyMessage]
    context: dict[str, RunningSummary]


class Agent:
    """
    通用智能体
    
    使用 LangGraph MessagesState 实现多轮对话，
    工具在内部解析并保存到长期记忆，返回摘要信息。
    
    摘要功能:
        - 使用 SummarizationNode 自动管理对话摘要
        - 保留最新对话，自动摘要旧消息
        - 与 trim_messages 配合使用，确保上下文长度合适
        
    工作流:
        START → summarize → llm_call → END
    """

    def __init__(
        self,
        config: AgentConfig
    ):
        """
        初始化智能体
        
        Args:
            config: 配置实例，必填。需传入 AgentConfig 或其子类的实例，
                   内部包含模型、Token 及存储等相关配置。
        """
        self._config = config
        self._config.IS_MULTIMODAL = self._config.IS_MULTIMODAL
        self._model_type = config.model_type or LLM_CONFIG["model_type"]
        self._model_name = config.model_name or LLM_CONFIG["model_name"]
        self._temperature = config.temperature
        self._api_key = config.api_key or LLM_CONFIG["api_key"]
        self._base_url = config.base_url or LLM_CONFIG["base_url"]
        self._max_tokens = config.max_tokens
        self._max_tokens_before_summary = config.max_tokens_before_summary
        self._max_summary_tokens = config.max_summary_tokens
        self.checkpointer = config.checkpointer
        self.store = config.store
        self.system_prompt = config.system_prompt

  


    async def __ainit__(self):
        """异步初始化方法
        
        创建模型实例、工具节点和检查点器，构建工作流图。
        
        为什么使用异步初始化：
        - 模型加载、工具初始化等操作涉及 I/O 或异步调用
        - db_path 是运行时参数，创建时才能确定
        - 采用延迟加载模式，节省内存和启动时间
        
        Args:
            db_path: 数据库路径，用于持久化对话记忆，默认使用内存数据库
        """
        # 创建模型实例
        self.model = ModelFactory.create_model(
            model_type=self._model_type,
            model_name=self._model_name,
            api_key=self._api_key or "",
            temperature=self._temperature,
            base_url=self._base_url
        )
        # 获取审计工具列表,创建工具节点，用于执行工具调用
        self.tools,self.tool_node = self._config.get_tools()
        
        # 创建摘要模型，绑定最大生成 token 数
        self.summarization_model = self.model.bind(max_tokens=self._max_summary_tokens)
        # 构建工作流图
        self._build_graph()

    def _should_continue(self, state: MessagesState) -> Literal["tools", "end"]:
        """判断是否需要继续执行工具调用
        
        检查最后一条消息是否包含工具调用，如果有则继续执行工具节点，
        否则结束当前轮次。
        
        Args:
            state: 当前消息状态
            
        Returns:
            "tools": 如果最后一条消息包含工具调用，需要执行工具
            "end": 如果最后一条消息是模型回复，结束当前轮次
        """
        messages = state.get("messages", [])
        if not messages:
            return "end"
        last_message = messages[-1]
        # 检查最后一条消息是否有工具调用
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

    async def _llm_call(self, state: LLMInputState):
        """LLM 调用节点
        
        根据系统提示词和用户消息，调用模型进行推理。
        系统提示词指导模型根据上传的文件类型调用相应的解析工具。
        
        Args:
            state: 包含 summarized_messages 的输入状态
            config: 包含 configurable 配置的字典，用于获取 thread_id 作为 namespace
            
        Returns:
            包含模型响应消息的字典
        """
        messages = state["summarized_messages"]
        logging.info(f"对话历史: {messages[-1]['content']}")
        #messages = state["messages"]
        # 系统提示词，指导模型如何根据文件类型调用相应的解析工具
        system_prompt = self.system_prompt or ""
        # 从状态中获取图片路径列表,如果传入了需要处理图片,则从状态中获取图片路径列表
        image_paths = state.get("image_paths_id", [])   
        # 如果是多模态模型,则需要处理图片
        if self._config.IS_MULTIMODAL and image_paths and self.store:
            # 从存储中获取图片内容
            # 注意：图片只添加到本地 messages，不更新 state
            # 这样下次 invoke 时图片不会保留在对话历史中
            # 使用 session_id\store_id 作为 namespace
            session_id = state.get("session_id", "default")
            store_id = state.get("store_id", "default")
            namespace = (store_id, session_id)
            logging.info(f"namespace: {namespace}")
            image_contents = []
            for image_id in image_paths:
                #这里存放的是一个dict id 和 base64的映射关系,每次会话传入
                #例image_path返回  {"image_id_1": "base64_1", "image_id_2": "base64_2"}
                result = self.store.get(namespace, "image_paths", default=None)
                content = result.value.get(image_id, "")
                logging.info(f"image_id: {image_id}, content: {content}")
                if content:
                    image_contents.append(content)
                    # 将图片内容添加到消息中，使用OpenAI风格的多模态格式
                    messages.append({
                    "type": "image_url",
                    "image_url": {"url": content}
                })
        # 绑定工具到模型，使模型能够调用工具
        llm = self.model.bind_tools(self.tools)
        # 调用模型，传入系统提示词和历史消息
        response = await llm.ainvoke([("system", system_prompt)] + messages)
        return {"messages": [response]}

    def _build_graph(self):
        """构建 LangGraph 工作流
        
        工作流结构:
            START → summarize → llm_call → END
            
        摘要节点功能:
            - 使用 SummarizationNode 自动管理对话摘要
            - 保留最新对话，自动摘要旧消息
            - 与 trim_messages 配合确保 token 数合适
            
        边连接逻辑:
            - 从 START 到 summarize 节点
            - 从 summarize 到 llm_call 节点
            - 从 llm_call 根据条件分支到 tools 或 END
            - 从 tools 回到 llm_call 继续调用
        """
        # 创建 SummarizationNode，用于自动管理对话摘要
        summarization_node = SummarizationNode(
            token_counter=count_tokens_approximately,
            model=self.summarization_model,
            max_tokens=self._max_tokens,
            max_tokens_before_summary=self._max_tokens_before_summary,
            max_summary_tokens=self._max_summary_tokens,
        )
        # state传入的使会话中可能被操作的变量，就是变化的量，这里只是格式，实际运行时会有具体的值
        # context传入的是会话中可能被操作的静态变量，就是不变的量，这里只是格式，实际运行时会有具体的值
        workflow = StateGraph(AgentState, AgentContext)

        # 添加节点
        workflow.add_node("summarize", summarization_node)
        workflow.add_node("llm_call", self._llm_call)
        workflow.add_node("tools", self.tool_node)

        # 添加边
        workflow.add_edge(START, "summarize")
        workflow.add_edge("summarize", "llm_call")

        # 添加条件边，根据 _should_continue 的返回值决定分支
        workflow.add_conditional_edges(
            "llm_call",
            self._should_continue,
            {
                "tools": "tools",
                "end": END
            }
        )

        # 工具执行完成后回到 llm_call 继续调用
        # workflow.add_edge("tools", "llm_call")
         # 这样 ToolMessage 会被 summarize 节点处理（trim、摘要等）
        workflow.add_edge("tools", "summarize")
        # 编译图，添加 checkpointer 实现全局记忆功能
        self.graph = workflow.compile(checkpointer=self.checkpointer, store=self.store)

    async def invoke(
        self,
        input_state: AgentState,
        context: AgentContext,
        config: ExecuteConfig,
    ):
        """调用智能体执行任务
        
        将用户输入状态、上下文和配置传入工作流，执行对话并返回结果。
        
        Args:
            input_state: 输入状态，包含 summarized_messages 和 context
            context: 上下文实例，用于传递静态变量
            config: 运行配置，包含 thread_id 等信息
            
        Returns:
            dict: 执行结果，包含 messages（消息列表）和 context（上下文摘要信息）
        """
        # 延迟初始化：如果 graph 尚未创建，则先初始化
        if not hasattr(self, 'graph') or self.graph is None:
            await self.__ainit__()
        
  
        ''' 
        执行图，传入上下文
        与StateGraph(State=state_class, context_schema=context_class)
        中的context_schema与context对应,state_schema与input_state对应,在每次调用时传入具体值
        '''
        result = await self.graph.ainvoke(input_state, config, context=context)
        
        # 添加 context 信息（如果可用）
        if hasattr(self, 'summarization_node') and "context" in result:
            result["context"] = result["context"]
        res_content=result["messages"][-1].content
        logging.info(f"AI回复: {res_content}")
        return res_content

    async def inspect_checkpoint(self, session_id: str = None):
        """检查指定 session 的 checkpoint 内容
        
        用于调试和监控，查看对话历史和摘要信息。
        
        Args:
            session_id: 会话 ID
            
        Returns:
            dict: Checkpoint 的详细内容，包括消息数量、消息内容、文件信息和摘要信息
        """
         # 构建配置
        config = {"configurable": {"thread_id": session_id or "default"}}
        # 获取当前状态
        state = self.graph.get_state(config)
        
        # 提取 checkpoint 信息
        checkpoint_info = {
            "thread_id": session_id or "default",
            "checkpoint_id": state.checkpoint_id if hasattr(state, 'checkpoint_id') else None,
            "messages_count": len(state.values.get("messages", [])),
            "messages": [
                {
                    "type": msg.__class__.__name__,
                    "content": str(msg.content) if hasattr(msg, "content") else "N/A",
                    "tool_calls": [tc["name"] for tc in getattr(msg, "tool_calls", [])] if hasattr(msg, "tool_calls") else None
                }
                for msg in state.values.get("messages", [])
            ],
            "file_paths": state.values.get("file_paths", []),
            "file_ids": state.values.get("file_ids", [])
        }
        
        # 添加 context 信息（如果可用）
        if "context" in state.values:
            checkpoint_info["context"] = {}
            for key, value in state.values["context"].items():
                if hasattr(value, 'summary'):
                    checkpoint_info["context"][key] = {
                        "summary": value.summary,
                        "summary_length": len(value.summary)
                    }
        
        return checkpoint_info


async def get_agent(
    config: AgentConfig
) -> Agent:
    """获取通用智能体实例的工厂函数
    
    创建并初始化 Agent 实例，简化智能体的创建过程。
    
    Args:
        config: AgentConfig 配置实例，包含模型、Token、检查点器、存储库、系统提示词等所有配置
        
    Returns:
        Agent: 初始化完成的智能体实例
    """
    agent = Agent(config=config)
    await agent.__ainit__()
    return agent



