#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocAgent - 文档处理Agent类

提供可复用的文档处理Agent类，支持多轮对话、工具调用和会话状态管理。

Date: 2026-03-19
Author: 张镒谱
"""

from typing import Optional
from app.agents.agent.agent import get_agent
from app.agents.subgraphs.Doc_Agent.config.DocAgentConfig import (
    DocAgentConfig,
    DocAgentState,
    DocAgentContext,
    DocExecuteConfig,
    DocConfigurableConfig,
)
from app.agents.subgraphs.Doc_Agent.config.config import DEFAULT_SYSTEM_PROMPT
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


class DocAgent:
    """
    文档处理Agent类
    
    提供可复用的文档处理对话功能，支持多轮对话、工具调用和会话状态管理。
    
    Attributes:
        checkpointer: LangGraph 检查点保存器
        store: LangGraph 内存存储器
        config: Agent 配置
        _agent: 底层 agent 实例
    """

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        store: BaseStore,
        system_prompt: Optional[str] = None,
        max_tokens: int = 20000,
        max_tokens_before_summary: int = 16000,
        max_summary_tokens: int = 4000,
    ):
        """
        初始化 DocAgent 实例
        
        Args:
            checkpointer: LangGraph 检查点保存器，用于持久化会话状态
            store: LangGraph 内存存储器，用于存储上下文信息
            system_prompt: 自定义系统提示词，默认使用文档处理专用提示词
            max_tokens: 最大 token 数，默认 20000
            max_tokens_before_summary: 触发摘要的 token 阈值，默认 16000
            max_summary_tokens: 摘要最大 token 数，默认 4000
        """
        self.checkpointer = checkpointer
        self.store = store
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_tokens = max_tokens
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        self._agent = None

    async def _ensure_agent(self):
        """确保 agent 已初始化"""
        if self._agent is None:
            config = DocAgentConfig(
                max_tokens=self.max_tokens,
                max_tokens_before_summary=self.max_tokens_before_summary,
                max_summary_tokens=self.max_summary_tokens,
                system_prompt=self.system_prompt,
                checkpointer=self.checkpointer,
                store=self.store,
            )
            self._agent = await get_agent(config)
        return self._agent

    async def invoke(
        self,
        user_input: str,
        session_id: str,
        host_session_id: Optional[str] = None,
        error_limit: int = 2,
        limit: int = 10,
        **kwargs,
    ) -> str:
        """
        执行对话并返回结果
        
        Args:
            user_input: 用户输入内容
            session_id: 会话ID，用于标识和恢复会话状态
            host_session_id: 发起对话的会话ID，用于跨会话数据访问
            error_limit: 错误限制次数，默认 2
            limit: 最大迭代次数，默认 10
            **kwargs: 其他可选参数
            
        Returns:
            str: Agent 的处理结果
        """
        agent = await self._ensure_agent()

        config = DocExecuteConfig(
            configurable=DocConfigurableConfig(thread_id=session_id)
        )

        state = DocAgentState(
            messages=[user_input],
            error_limit=error_limit,
            limit=limit,
        )

        context = DocAgentContext(
            session_id=session_id,
            host_session_id=host_session_id or session_id,
        )

        result = await agent.invoke(
            config=config,
            input_state=state,
            context=context,
        )

        return result

    async def get_agent(self):
        """
        获取底层 agent 实例
        
        Returns:
            底层 agent 实例
        """
        return await self._ensure_agent()
