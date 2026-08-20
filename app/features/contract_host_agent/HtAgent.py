#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HtAgent - 合同审批Agent类

提供可复用的合同审批Agent类，支持多轮对话、工具调用和会话状态管理。

Date: 2026-03-17
Author: 张镒谱
"""

from typing import Optional, Any, List
from app.core.agent.agent import get_agent
from app.features.contract_host_agent.config.HtAgentConfig import (
    HtAgentConfig,
    HtAgentState,
    HtAgentContext,
    HtExecuteConfig,
    HtConfigurableConfig,
)
from app.core.messages import extract_text
from app.features.contract_host_agent.config.prompts import DEFAULT_SYSTEM_PROMPT
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


class HtAgent:
    """
    合同审批Agent类
    
    提供可复用的合同审批对话功能，支持多轮对话、工具调用和会话状态管理。
    
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
        store_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        base_system_prompt: Optional[str] = None,
        enabled_skill_names: Optional[List[str]] = None,
        max_tokens: int = 20000,
        max_tokens_before_summary: int = 16000,
        max_summary_tokens: int = 4000,
        model_type: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0,
        parallel_tool_calls: Optional[bool] = None,
    ):
        """
        初始化 HtAgent 实例

        Args:
            checkpointer: LangGraph 检查点保存器，用于持久化会话状态
            store: LangGraph 内存存储器，用于存储上下文信息
            system_prompt: 自定义系统提示词，默认使用合同审批专用提示词
            base_system_prompt:
                可选基类系统提示词，覆盖 app.core.prompts.BASE_SYSTEM_PROMPT。
                详见 AgentConfig.base_system_prompt。三元语义：
                - None（默认）：使用常量 BASE_SYSTEM_PROMPT（向后兼容）
                - ""：跳过 base 段，整段 BASE_SYSTEM_PROMPT 不参与拼接
                - 非空字符串：按 Agent 维度完全覆盖常量内容
            enabled_skill_names:
                该 Agent 启用的 skill 白名单；透传给 HtAgentConfig.enabled_skill_names，
                供 SkillsAwarePrompt 在构造 system prompt 时过滤可用 skill。
                - None（默认）：按"未绑定 = 不绑定"契约，SkillsAwarePrompt 不加载任何 skill
                  （2026-08-19 改语义：原"加载全部 skill"已废弃，避免特性专属路由绕过
                  AgentConfigService 后 LLM 误加载 skills 表全部条目）
                - []：显式空列表，过滤后 available_skills 段为空
                - 非空列表：仅展示这些 skill（前提是它们在 DB skills 表已注册且 enabled=True）
            max_tokens: 最大 token 数，默认 20000
            max_tokens_before_summary: 触发摘要的 token 阈值，默认 16000
            max_summary_tokens: 摘要最大 token 数，默认 4000
            model_type: 模型类型（2026-08-19 新增），如 "ollama"/"deepseek"/"openai" 等；默认 None（由 HtAgentConfig 取全局 LLM_CONFIG）
            model_name: 模型名称（2026-08-19 新增），如 "deepseek-chat"/"qwen3:32b" 等；默认 None
            api_key: API 密钥（2026-08-19 新增），用于访问远程模型服务；默认 None
            base_url: API 基础 URL（2026-08-19 新增），指定模型服务的地址；默认 None
            temperature: 模型温度参数（2026-08-19 新增），控制生成多样性；默认 0
            parallel_tool_calls: 是否启用并行工具调用（2026-08-20 新增），透传给 AgentConfig.parallel_tool_calls；
                三元语义 None/True/False 详见 AgentConfig.parallel_tool_calls 字段 docstring。
                合同场景下通常从 ContractLLMSettings.get_config()['parallel_tool_calls'] 传入，
                关闭 Ollama 默认并行避免 LangGraph 多 tool 并行写 file_chunk_read_progress 触发 InvalidUpdateError。
        """
        self.checkpointer = checkpointer
        self.store = store
        self.store_id = store_id
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.base_system_prompt = base_system_prompt
        self.enabled_skill_names = enabled_skill_names
        self.max_tokens = max_tokens
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        self.model_type = model_type
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.parallel_tool_calls = parallel_tool_calls
        self._agent = None

    async def _ensure_agent(self):
        """确保 agent 已初始化"""
        if self._agent is None:
            config = HtAgentConfig(
                max_tokens=self.max_tokens,
                max_tokens_before_summary=self.max_tokens_before_summary,
                max_summary_tokens=self.max_summary_tokens,
                system_prompt=self.system_prompt,
                base_system_prompt=self.base_system_prompt,
                enabled_skill_names=self.enabled_skill_names,
                checkpointer=self.checkpointer,
                store=self.store,
                model_type=self.model_type,
                model_name=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=self.temperature,
                parallel_tool_calls=self.parallel_tool_calls,
            )
            self._agent = await get_agent(config)
        return self._agent

    async def invoke(
        self,
        user_input: str,
        session_id: str,
        error_limit: int = 2,
        limit: int = 10,
        **kwargs,
    ) -> str:
        """
        执行对话并返回结果
        
        Args:
            user_input: 用户输入内容
            session_id: 会话ID，用于标识和恢复会话状态
            error_limit: 错误限制次数，默认 2
            limit: 最大迭代次数，默认 10
            **kwargs: 其他可选参数
            
        Returns:
            str: Agent 的处理结果
        """
        agent = await self._ensure_agent()

        config = HtExecuteConfig(
            configurable=HtConfigurableConfig(thread_id=session_id),
            recursion_limit=100  # 增加递归限制，支持更多轮次的工具调用
        )

        state = HtAgentState(
            messages=[user_input],
            error_limit=error_limit,
            limit=limit,
        )

        context = HtAgentContext(
            session_id=session_id, 
            store_id=self.store_id or session_id
        )

        result = await agent.invoke(
            config=config,
            input_state=state,
            context=context,
        )

        return extract_text(result["messages"][-1])

    async def get_agent(self):
        """
        获取底层 agent 实例
        
        Returns:
            底层 agent 实例
        """
        return await self._ensure_agent()
