#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MapAgent - 地图控制Agent类

提供可复用的地图控制Agent类，支持多轮对话、工具调用和会话状态管理。
实现流式输出，实时反馈地图操作结果。

Date: 2026-04-14
Author: AI Assistant
"""

from typing import Optional, AsyncGenerator, Union
from app.core.agent.agent import get_agent
from app.features.map_agent.config.MapAgentConfig import (
    MapAgentConfig,
    MapAgentState,
    MapAgentContext,
    MapExecuteConfig,
    MapConfigurableConfig,
)
from app.features.map_agent.config.prompts import DEFAULT_SYSTEM_PROMPT
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


class MapAgent:
    """
    地图控制Agent类

    提供可复用的地图控制对话功能，支持多轮对话、工具调用和会话状态管理。
    通过流式输出实时反馈地图操作结果，适用于需要实时交互的场景。

    Attributes:
        checkpointer: LangGraph 检查点保存器
        store: LangGraph 内存存储器
        store_id: 存储 ID，用于区分不同用户的存储空间
        system_prompt: 系统提示词
        max_tokens: 最大 token 数
        max_tokens_before_summary: 触发摘要的 token 阈值
        max_summary_tokens: 摘要最大 token 数
        _agent: 底层 agent 实例
    """

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        store: BaseStore,
        store_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 20000,
        max_tokens_before_summary: int = 16000,
        max_summary_tokens: int = 4000,
    ):
        """
        初始化 MapAgent 实例

        Args:
            checkpointer: LangGraph 检查点保存器，用于持久化会话状态
            store: LangGraph 内存存储器，用于存储上下文信息
            store_id: 存储 ID，用于区分不同用户的存储空间，默认使用 session_id
            system_prompt: 自定义系统提示词，默认使用地图控制专用提示词
            max_tokens: 最大 token 数，默认 20000
            max_tokens_before_summary: 触发摘要的 token 阈值，默认 16000
            max_summary_tokens: 摘要最大 token 数，默认 4000
        """
        self.checkpointer = checkpointer
        self.store = store
        self.store_id = store_id
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_tokens = max_tokens
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        self._agent = None

    async def _ensure_agent(self):
        """
        确保 agent 已初始化

        采用延迟初始化模式，在第一次调用时创建 agent 实例。
        创建 MapAgentConfig 配置实例，并调用 get_agent() 获取 agent 实例。

        Returns:
            Agent: 初始化完成的智能体实例
        """
        if self._agent is None:
            config = MapAgentConfig(
                max_tokens=self.max_tokens,
                max_tokens_before_summary=self.max_tokens_before_summary,
                max_summary_tokens=self.max_summary_tokens,
                system_prompt=self.system_prompt,
                checkpointer=self.checkpointer,
                store=self.store,
                state_class=MapAgentState,
                context_class=MapAgentContext,
            )
            self._agent = await get_agent(config)
        return self._agent

    async def stream(
        self,
        user_input: str,
        session_id: str,
        error_limit: int = 2,
        limit: int = 10,
        stream_mode: Union[str, list[str]] = None,
        context: any = None,
        geometry_data: dict = {},
        **kwargs,
    ) -> AsyncGenerator[dict, None]:
        """
        流式调用智能体

        通过流式输出，实时获取每个节点的执行结果，包括每次 LLM 调用的输出。
        适用于需要实时反馈的场景，如用户对话、实时监控等。

        Args:
            user_input: 用户输入内容
            session_id: 会话ID，用于标识和恢复会话状态
            error_limit: 错误限制次数，默认 2
            limit: 最大迭代次数，默认 10
            stream_mode: 流式输出模式，默认为 ["updates", "custom", "messages"] 组合模式
                支持以下选项：
                - "updates": 每个节点执行后返回状态更新（推荐）
                - "values": 每个节点执行后返回完整状态
                - "messages": 流式输出 LLM token
                - "custom": 流式输出自定义数据
                - ["updates", "messages"]: 组合模式，同时获取多种输出
            geometry_data: 地理数据类型，格式为 {"point": [...], "line": [...], "polygon": [...]}
            **kwargs: 其他可选参数

        Yields:
            dict: 流式输出的数据块，格式取决于 stream_mode：
                - stream_mode="updates": {node_name: {state_updates}}
                - stream_mode="messages": (message_chunk, metadata)
                - stream_mode=["updates", "messages"]: (mode, data)

        Examples:
            基本使用（获取每次 llm_call 的输出）：
            ```python
            async for chunk in map_agent.stream("定位到北京", "session_123"):
                if "llm_call" in chunk:
                    print(f"LLM 输出: {chunk['llm_call']['messages'][-1].content}")
            ```

            流式输出 LLM token：
            ```python
            async for chunk in map_agent.stream(
                "定位到北京", "session_123",
                stream_mode="messages"
            ):
                message_chunk, metadata = chunk
                print(message_chunk.content, end="", flush=True)
            ```

            组合模式：
            ```python
            async for mode, data in map_agent.stream(
                "定位到北京", "session_123",
                stream_mode=["updates", "messages"]
            ):
                if mode == "updates":
                    print(f"节点更新: {data}")
                elif mode == "messages":
                    print(data[0].content, end="", flush=True)
            ```
        """
        agent = await self._ensure_agent()

        # 默认使用组合模式，支持多种输出
        if stream_mode is None:
            stream_mode = ["updates", "custom", "messages"]

        # 构建执行配置
        config = MapExecuteConfig(
            configurable=MapConfigurableConfig(thread_id=session_id),
            recursion_limit=100  # 增加递归限制，支持更多轮次的工具调用

        )

        # 构建输入状态
        state = MapAgentState(
            messages=[user_input],
            error_limit=error_limit,
            limit=limit,
        )

        # 构建上下文
        context = MapAgentContext(
            session_id=session_id,
            store_id=self.store_id or session_id,
            knowledge_root= context.get("knowledge_root") ,
            system_prompt=context.get("system_prompt"),
            geometry_data=geometry_data
        )

        # 流式调用 agent
        async for chunk in agent.stream(
            input_state=state,
            context=context,
            config=config,
            stream_mode=stream_mode
        ):
            yield chunk

    async def get_agent(self):
        """
        获取底层 agent 实例

        Returns:
            Agent: 底层 agent 实例
        """
        return await self._ensure_agent()
