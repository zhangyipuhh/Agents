#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent 配置模块

该模块定义了 AgentConfig 数据类，用于封装 Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。
使用 field() 处理默认值，解决了 dataclass 的类属性共享陷阱问题。

Date: 2026-03-10
Author: 张镒谱
"""

from typing import Optional, Any
from typing_extensions import TypedDict
from dataclasses import dataclass, field
from langgraph.graph import MessagesState
from langgraph.store.base import BaseStore
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import RetryPolicy
from app.core.agent.AgentContext import AgentContext
from app.core.tools.BaseTools import get_current_time, open_file, load_web_page, read_cached_chunk,open_file_by_id
from app.core.tools.SandboxTools import sandbox
from app.core.tools.FilesystemReadTools import explore
from app.core.skills.tool import load_skill
from app.core.config.config import LLM_CONFIG

class ConfigurableConfig(TypedDict):
    """可配置参数内部类，用于配置 LangGraph 运行时的各种参数"""

    thread_id: str = "default"
    """线程ID，用于区分不同会话，相同 thread_id 的对话共享记忆"""



class ExecuteConfig(TypedDict):
    """
    LangGraph 可运行配置结构

    用于配置 LangGraph 运行时的各种参数，如线程ID、回调等。
    与 LangGraph 的 invoke 方法的 config 参数兼容。
    """

    configurable: ConfigurableConfig 
    """可配置参数，如 thread_id（线程ID，用于区分不同会话）等"""
    
    recursion_limit: int
    """递归限制，控制图执行的最大步数，防止无限循环，默认 25"""

class AgentState(MessagesState):
    """
    状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    具体实现的agent需要继承该类
    """
    
    
    error_limit: int = 5
    """最大错误次数，控制图执行的最大错误次数，这里的5是类型提示语法的一部分，不是默认值，必须在初始化时指定"""
    limit: int = 25
    """最大递归深度，控制图执行的最大步数，这里的25是类型提示语法的一部分，不是默认值，必须在初始化时指定"""
    file_chunk_read_progress: int = 1
    """文件读取进度，记录当前读取到的文件位置，用于连续读文件,默认从文件开头开始读取"""
    # === 新增：过程变量（借鉴 hermes-agent 的 tool_state）===
    tool_progress: dict[str, dict]  
    """
    工具执行进度，记录每个工具的执行状态和进度。
    格式：{"tool_name": {"stage": "...", "progress": "..."}}
    """
    intermediate_results: dict[str, Any]  # 工具中间计算结果
    """
    工具中间计算结果，记录每个工具的中间结果。
    格式：{"tool_name": {"result": "..."}}
    """
    pending_question: dict = None
    """
    待用户回答的问题（替代旧的 pending_approval）。
    当工具调用 ask_user_question 时，会将问题信息写入此字段。
    格式：{
        "status": "pending",
        "questions": [Question, ...],
        "tool_call_id": "..."
    }
    """

    question_answers: list = []
    """
    历史问答记录（用于审计/调试）。
    hitl_check_node 用 Overwrite 显式追加。
    格式：[{"questions": [...], "answers": [[...]], "timestamp": "..."}, ...]
    """



@dataclass(kw_only=True)
class AgentConfig:
    """
    Agent 配置类
    
    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """

    model_type: str = field(default=LLM_CONFIG["model_type"])
    """模型类型，如 "ollama"、"deepseek"、"openai" 等，指定使用的模型服务商"""
    
    model_name: str = field(default=LLM_CONFIG["model_name"])   
    """模型名称，如 "llama3.2"、"deepseek-chat"、"gpt-4" 等，指定具体的模型"""
    
    state_class: type[AgentState] = field(default=None)
    """
    状态类，需要传入一个继承自 AgentState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值   
    """
    
    context_class: type[AgentContext] = field(default=None)
    """
    上下文类，需要传入一个 AgentContext 类型，定义对话上下文结构，不可变
    上下文类是一个 TypedDict 类型，用于定义对话上下文的结构。
    上下文类的字段会被添加到状态类中，用于在会话中传递上下文信息。
    """ 
    
    temperature: float = field(default=0)
    """模型温度参数，控制生成多样性。取值范围 0-1，越高越随机，默认 0"""
    
    api_key: Optional[str] = field(default=LLM_CONFIG["api_key"])
    """API 密钥，用于访问远程模型服务。如果为 None，则使用环境变量或本地模型"""
    
    base_url: Optional[str] = field(default=LLM_CONFIG["base_url"])
    """API 基础 URL，指定模型服务的地址。如果为 None，则使用默认地址"""
    
    max_tokens: int = field(default=999999999)
    """最大 token 数，限制单次生成的最大长度，防止生成过长响应，默认 999999999"""
    
    max_tokens_before_summary: int = field(default=999999999)
    """触发摘要的 token 阈值，当消息历史超过此值时触发摘要操作，默认 999999999"""
    
    max_summary_tokens: int = field(default=999999999)
    """摘要后的最大 token 数，控制摘要的长度，避免摘要过于冗长，默认 999999999"""
    
    checkpointer: BaseCheckpointSaver = field(default=None)
    """
    检查点器，用于持久化对话状态，支持断点续训和状态恢复，默认 None
    如果每次重新定义checkpointer，需要确保session_id一致，否则会导致状态丢失
    
    重要：每次传入不同的检查点实例，相当于关闭多轮对话。多轮对话的前提是使用同一个检查点实例（通常为全局单例），
    并通过 session_id 来区分不同的会话。
    """
    
    store: Optional[BaseStore] = field(default=None)
    """存储库，用于长期跨会话记忆存储，支持跨会话上下文共享，默认 None
    
    LangGraph Store 存储结构：
        - namespace: 命名空间，用于区分不同类型的数据，类型为 tuple，如 ("audit_documents",)
        - key: 使用 session_id 作为 key，关联同一用户的文档数据
        - value: 存储文档解析结果（合同条款、成交确认书图片、会议纪要文本块等）
    
    示例用法：
        # 1. 创建 Store
        from langgraph.store.memory import InMemoryStore
        store = InMemoryStore()
        
        # 2. 写入数据
        store.put(
            ("audit_documents",),  # namespace
            "session_001",           # key (session_id)
            {
                "file_id": "file_001",
                "type": "contract",
                "clauses": [
                    {"clause_title": "第一条", "clause_content": "..."},
                    {"clatitude_title": "第二条", "clause_content": "..."}
                ]
            }
        )
        
        # 3. 读取数据
        result = store.get(("audit_documents",), "session_001")
        print(result.value)  # {'file_id': 'file_001', 'type': 'contract', ...}
        
        # 4. 查询同一命名空间下的所有数据
        all_docs = store.search(("audit_documents",))
        for doc in all_docs:
            print(doc.key, doc.value)
        
        # 5. 传入 AgentConfig
        config = AgentConfig(
            model_type="deepseek",
            model_name="deepseek-chat",
            store=store
        )
    """
    
    system_prompt: Optional[str] = field(default=None)
    """系统提示词，用于设置 AI 的行为角色、性格和约束条件，默认 None"""

    name: Optional[str] = field(default=None)
    """Agent 注册名（2026-06-21 新增，与 app/features/<dir>/ 目录名一致）。

    用于 skill 系统按子智能体维度隔离（agent_name 维度 SkillsService 实例 +
    子智能体专属 config/bootstrap.md 覆盖）。None 表示该 Agent 不绑定特定子智能体，
    SkillAwarePrompt 会回退到全局 skill 注册表。

    子智能体应在自身的 *AgentConfig 子类中通过 ``field(default="<dir_name>")`` 覆盖。
    """

    max_input_tokens: int = field(default=999999999)
    """最大输入 token 数，限制单次输入的最大长度，防止输入过长导致上下文超限，默认 999999999"""

    trim_tool_messages: bool = field(default=True)
    """是否启用工具消息 trim，启用后会删除旧的工具消息，只保留最近 keep_last_n_tools 条，默认 True"""

    keep_last_n_tools: int = field(default=2)
    """保留最近几条工具消息，用于控制发送给 LLM 的工具消息数量，默认 2"""

    IS_MULTIMODAL: bool = field(default=LLM_CONFIG["is_multimodal"]==True)
    """是否多模态模型，用于判断是否需要处理图片"""
    
    llm_retry_max_attempts: int = field(default=3)
    """LLM 调用最大重试次数，默认 3 次"""
    
    llm_retry_initial_interval: float = field(default=1.0)
    """LLM 调用初始重试间隔（秒），默认 1.0 秒"""
    
    tool_retry_max_attempts: int = field(default=2)
    """工具执行最大重试次数，默认 2 次"""
    
    tool_retry_initial_interval: float = field(default=0.5)
    """工具执行初始重试间隔（秒），默认 0.5 秒"""
    
    summarize_retry_max_attempts: int = field(default=2)
    """摘要操作最大重试次数，默认 2 次"""
    
    summarize_retry_initial_interval: float = field(default=1.0)
    """摘要操作初始重试间隔（秒），默认 1.0 秒"""
    
    def get_tools(self) -> tuple[list[str], ToolNode]:
        """
        获取所有审计文档工具名称列表

        返回:
            tuple[list[str], ToolNode]: 工具名称列表和对应的 ToolNode 对象

        注意:
            此方法需要子类重写，在子类中添加工具到 tools 列表
        """
        tools: list[str] = [get_current_time, open_file, load_web_page, read_cached_chunk,open_file_by_id, sandbox, explore, load_skill]

        return tools, ToolNode(tools, handle_tool_errors=True)
    
    def get_llm_retry_policy(self) -> RetryPolicy:
        """
        获取 LLM 调用重试策略
        
        Returns:
            RetryPolicy: LLM 调用的重试策略实例
        """
        return RetryPolicy(
            max_attempts=self.llm_retry_max_attempts,
            initial_interval=self.llm_retry_initial_interval,
            backoff_factor=2.0,
            jitter=True,
            retry_on=(ConnectionError, TimeoutError)
        )
    
    def get_tool_retry_policy(self) -> RetryPolicy:
        """
        获取工具执行重试策略
        
        Returns:
            RetryPolicy: 工具执行的重试策略实例
        """
        return RetryPolicy(
            max_attempts=self.tool_retry_max_attempts,
            initial_interval=self.tool_retry_initial_interval,
            backoff_factor=1.5,
            jitter=True,
            retry_on=(FileNotFoundError, PermissionError, ConnectionError, TimeoutError)
        )
    
    def get_summarize_retry_policy(self) -> RetryPolicy:
        """
        获取摘要操作重试策略
        
        Returns:
            RetryPolicy: 摘要操作的重试策略实例
        """
        return RetryPolicy(
            max_attempts=self.summarize_retry_max_attempts,
            initial_interval=self.summarize_retry_initial_interval,
            backoff_factor=2.0,
            jitter=True,
            retry_on=(ConnectionError, TimeoutError)
        )
