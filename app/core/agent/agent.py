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
    START → hitl_check → summarize → llm_call → END (自动循环调用工具直到完成)

摘要功能:
    - 使用 SummarizationNode 自动管理对话摘要，里面包含trim_messages的逻辑
    - 保留最新对话，自动摘要旧消息

调用方式:
    - invoke(): 非流式调用，等待整个图执行完成，返回最终状态
    - stream(): 流式调用，实时获取每个节点的执行结果，包括每次 _llm_call 的输出


Date: 2026-03-10
Author: 张镒谱
"""

from imaplib import IMAP4
import logging
from datetime import datetime

from typing import Literal, Union, AsyncGenerator
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy, Command as LGCommand
from langgraph.types import interrupt, Overwrite
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode, RunningSummary
from app.core.llmcalls.model_factory import ModelFactory
from app.core.agent.AgentConfig import (
    AgentConfig,
    AgentContext,
    AgentState,
    ExecuteConfig,
)
from app.core.config.config import LLM_CONFIG
from app.core.messages import trim_old_tool_messages
from app.core.prompts import BASE_SYSTEM_PROMPT


class LLMInputState(TypedDict):
    """LLM 输入状态的类型定义

    定义了传递给 LLM 节点的输入格式：
        - summarized_messages: 经过摘要处理后的消息列表
        - context: 上下文摘要信息字典
        - image_ids: 图片ID列表
        - state: 完整的原始状态，用于访问任意字段
    """

    summarized_messages: list[AnyMessage]
    context: dict[str, RunningSummary]


def _get_mime_type_from_base64(base64_data: str) -> str:
    """从 base64 数据推断图片的 MIME 类型

    通过检查 base64 数据的前缀来推断图片格式

    Args:
        base64_data: base64 编码的图片数据

    Returns:
        MIME 类型字符串，如 "image/jpeg", "image/png" 等
    """
    if base64_data.startswith("/9j/"):
        return "image/jpeg"
    elif base64_data.startswith("iVBORw0KGgo"):
        return "image/png"
    elif base64_data.startswith("R0lGOD"):
        return "image/gif"
    elif base64_data.startswith("UklGR"):
        return "image/webp"
    else:
        return "image/jpeg"  # 默认返回 JPEG


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
        START → hitl_check → summarize → llm_call → END

    调用方式:
        - invoke(): 非流式调用，返回最终结果
        - stream(): 流式调用，实时获取每个节点的输出
    """

    def __init__(self, config: AgentConfig):
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
        self._trim_tool_messages = config.trim_tool_messages
        self._keep_last_n_tools = config.keep_last_n_tools
        self._ollama_reasoning =  LLM_CONFIG["ollama_reasoning"]
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
            base_url=self._base_url,
            reasoning=self._ollama_reasoning,
        )
        # 获取审计工具列表,创建工具节点，用于执行工具调用
        self.tools, self.tool_node = self._config.get_tools()

        # 构建工具绑定参数，根据配置决定是否传入 parallel_tool_calls
        bind_kwargs = {"tools": self.tools}
        parallel_tool_calls = LLM_CONFIG.get("parallel_tool_calls")
        if parallel_tool_calls is not None:
            bind_kwargs["parallel_tool_calls"] = parallel_tool_calls

        # 预绑定工具到模型，避免每次调用时重复绑定
        self.llm = self.model.bind_tools(**bind_kwargs)

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

    async def hitl_check_node(
        self,
        state: AgentState,
        runtime: Runtime[AgentContext],
    ):
        """HITL 检查节点：检查 pending_question 并暂停图执行

        检查当前状态中是否存在待回答的问题。
        如果存在且状态为 pending，则调用 interrupt() 暂停图执行，
        向前端发送中断事件，等待用户回答后恢复。
        恢复后添加 HumanMessage 反馈（保持 HumanMessage 模式避免 tool_call_id 风险）
        并清除 pending_question、记录 question_answers。

        Args:
            state: 当前对话状态，包含 messages 和 pending_question
            runtime: 包含 context 的运行时对象

        Returns:
            dict: 更新后的状态，包含修改后的 messages 和清除后的 pending_question
        """
        pending = state.get("pending_question")

        if not pending or pending.get("status") != "pending":
            return state

        # 构造 interrupt 请求（LangGraph 新版格式：直接传 dict）
        request = {
            "action": "ask_user_question",
            "questions": pending["questions"]
        }

        # 调用 interrupt 暂停执行
        response = interrupt(request)

        # ===== 恢复后处理 =====
        # response 直接是 Command(resume=...) 传入的值
        answers = response.get("answers", []) if isinstance(response, dict) else []
        questions = pending["questions"]

        # 构造结构化的 HumanMessage（保持 HumanMessage 模式，详见设计文档 §6.1）
        formatted_parts = []
        for i, q in enumerate(questions):
            labels = answers[i] if i < len(answers) else []
            if not labels:
                formatted_parts.append(f'问题「{q["question"]}」：未回答')
            else:
                formatted_parts.append(f'问题「{q["question"]}」：用户选择了 {", ".join(labels)}')

        feedback_text = (
            f"【用户对 {len(questions)} 个问题的回答】\n"
            + "\n".join(formatted_parts)
            + "\n\n请基于以上回答继续。"
        )

        # 记录历史问答（用 Overwrite 处理 list 字段）
        new_record = {
            "questions": questions,
            "answers": answers,
            "timestamp": datetime.now().isoformat()
        }
        existing = state.get("question_answers", [])

        return {
            "messages": [HumanMessage(content=feedback_text)],
            "pending_question": None,
            "question_answers": Overwrite(value=existing + [new_record])
        }

    async def _llm_call(
        self,
        state: LLMInputState,
        runtime: Runtime[AgentContext],
    ):
        """LLM 调用节点

        根据系统提示词和用户消息，调用模型进行推理。
        系统提示词指导模型根据上传的文件类型调用相应的解析工具。

        Args:
            state: 包含 summarized_messages 的输入状态
            runtime: 包含 context 的运行时对象，用于获取 thread_id 作为 namespace

        Returns:
            包含模型响应消息的字典
        """
        context = runtime.context
        messages = state["summarized_messages"]
        
        # 根据配置对消息进行工具消息过滤
        if self._trim_tool_messages:
            messages = trim_old_tool_messages(messages, keep_last_n=self._keep_last_n_tools)
        
        # logging.info(f"对话历史: {messages[-1].content}")
        # messages = state["messages"]
        # 系统提示词，指导模型如何根据文件类型调用相应的解析工具
        #运行时可以通过上下文动态添加主提示词
        system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + (self.system_prompt or "")+"\n\n"+(context.get("system_prompt") or "")
        #logging.info(f"system_prompt: {system_prompt}")
        #logging.info(f"system_prompt: {system_prompt}")
        # 从状态中获取图片路径列表,如果传入了需要处理图片,则从状态中获取图片路径列表
        image_ids = context.get("image_ids", [])
        # 如果是多模态模型,则需要处理图片
        if self._config.IS_MULTIMODAL and image_ids and self.store:
            # 从存储中获取图片内容
            # 注意：图片只添加到本地 messages，不更新 state
            # 这样下次 invoke 时图片不会保留在对话历史中
            # 使用store_id 作为 namespace
            store_id = context.get("store_id", "default")
            namespace = (store_id,)
            logging.info(f"namespace: {namespace}")
            image_contents = []
            # 例image_path返回  {"image_id_1": "base64_1", "image_id_2": "base64_2"}
            result = self.store.get(namespace, "file/images")
            content_parts = []
            for image_id in image_ids:
                base64_data = result.value.get(image_id, "") if result else ""
                logging.info(
                    f"image_id: {image_id}, content length: {len(base64_data)}"
                )
                if base64_data:
                    image_contents.append(base64_data)
                    mime_type = _get_mime_type_from_base64(base64_data)
                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}"
                            },
                        }
                    )
            if content_parts:
                last_message = messages[-1]
                user_text = (
                    last_message.content
                    if isinstance(last_message.content, str)
                    else ""
                )
                content_parts.insert(0, {"type": "text", "text": user_text})
                user_message = HumanMessage(content=content_parts)
                messages[-1] = user_message
                context["image_ids"] = []
        # 直接使用预绑定的 self.llm
        response = await self.llm.ainvoke([("system", system_prompt)] + messages)
        return {"messages": [response]}

    def _build_graph(self):
        """构建 LangGraph 工作流

        工作流结构:
            START → hitl_check → summarize → llm_call → END
            (如果配置了工具): llm_call → tools → hitl_check → summarize

        摘要节点功能:
            - 使用 SummarizationNode 自动管理对话摘要
            - 保留最新对话，自动摘要旧消息
            - 与 trim_messages 配合确保 token 数合适

        HITL 检查节点功能:
            - 在 summarize 之前检查是否有 pending_approval
            - 如果有，调用 interrupt() 暂停执行等待用户确认
            - 恢复后添加 HumanMessage 反馈，然后由 summarize 重新生成 summarized_messages
            - 无 pending_approval 时直接透传，不影响原有流程

        为什么 hitl_check 在 summarize 之前:
            - hitl_check 更新 messages 后，summarize 会基于最新 messages 重新生成 summarized_messages
            - 确保 _llm_call 读取的 summarized_messages 始终包含用户反馈
            - 避免手动维护 messages 和 summarized_messages 两份列表的一致性

        边连接逻辑:
            - 从 START 到 hitl_check 节点
            - 从 hitl_check 到 summarize 节点
            - 从 summarize 到 llm_call 节点
            - 从 llm_call 根据条件分支到 tools 或 END（如果没有工具则直接到 END）
            - 从 tools 回到 hitl_check 节点继续处理
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
        workflow = StateGraph(AgentState, AgentContext)

        # 添加节点（带重试策略）
        workflow.add_node(
            "summarize",
            summarization_node,
            retry_policy=self._config.get_summarize_retry_policy(),
        )
        workflow.add_node(
            "hitl_check", self.hitl_check_node, retry_policy=self._config.get_llm_retry_policy()
        )
        workflow.add_node(
            "llm_call", self._llm_call, retry_policy=self._config.get_llm_retry_policy()
        )

        # 添加边
        workflow.add_edge(START, "hitl_check")
        workflow.add_edge("hitl_check", "summarize")
        workflow.add_edge("summarize", "llm_call")

        # 如果配置了工具节点，添加工具和条件边
        if self.tool_node is not None:
            workflow.add_node(
                "tools",
                self.tool_node,
                retry_policy=self._config.get_tool_retry_policy(),
            )
            # 添加条件边，根据 _should_continue 的返回值决定分支
            workflow.add_conditional_edges(
                "llm_call", self._should_continue, {"tools": "tools", "end": END}
            )
            # 工具执行完成后回到 hitl_check 节点处理
            workflow.add_edge("tools", "hitl_check")
        else:
            # 没有工具时，llm_call 直接连接到 END
            workflow.add_edge("llm_call", END)

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
        if not hasattr(self, "graph") or self.graph is None:
            await self.__ainit__()

        """ 
        执行图，传入上下文
        与StateGraph(State=state_class, context_schema=context_class)
        中的context_schema与context对应,state_schema与input_state对应,在每次调用时传入具体值
        """
        result = await self.graph.ainvoke(input_state, config, context=context)

        # 添加 context 信息（如果可用）
        if hasattr(self, "summarization_node") and "context" in result:
            result["context"] = result["context"]
        # res_content=result["messages"][-1].content
        # logging.info(f"AI回复: {res_content}")
        return result

    async def stream(
        self,
        input_state: Union[AgentState, LGCommand],
        context: AgentContext,
        config: ExecuteConfig,
        stream_mode: Union[str, list[str]] = "updates",
    ) -> AsyncGenerator[dict, None]:
        """流式调用智能体

        通过流式输出，实时获取每个节点的执行结果，包括每次 _llm_call 的输出。
        适用于需要实时反馈的场景，如用户对话、实时监控等。
        支持通过 Command(resume=...) 恢复被中断的执行。

        Args:
            input_state: 输入状态或恢复命令。正常调用时传入 AgentState；
                从中断恢复时传入 Command(resume=...) 对象。
            context: 上下文实例，用于传递静态变量
            config: 运行配置，包含 thread_id 等信息
            stream_mode: 流式输出模式，支持以下选项：
                - "updates": 每个节点执行后返回状态更新（推荐）
                - "values": 每个节点执行后返回完整状态
                - "messages": 流式输出 LLM token
                - "custom": 流式输出自定义数据
                - ["updates", "messages"]: 组合模式，同时获取多种输出

        Yields:
            dict: 流式输出的数据块，格式取决于 stream_mode：
                - stream_mode="updates": {node_name: {state_updates}}
                - stream_mode="messages": (message_chunk, metadata)
                - stream_mode=["updates", "messages"]: (mode, data)

        Examples:
            基本使用（获取每次 llm_call 的输出）：
            ```python
            async for chunk in agent.stream(input_state, context, config):
                if "llm_call" in chunk:
                    print(f"LLM 输出: {chunk['llm_call']['messages'][-1].content}")
            ```

            从中断恢复：
            ```python
            async for chunk in agent.stream(
                Command(resume={"decision": "approve"}), context, config
            ):
                print(chunk)
            ```
        """
        if not hasattr(self, "graph") or self.graph is None:
            await self.__ainit__()

        async for chunk in self.graph.astream(
            input_state, config, context=context, stream_mode=stream_mode
        ):
            yield chunk

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
            "checkpoint_id": state.checkpoint_id
            if hasattr(state, "checkpoint_id")
            else None,
            "messages_count": len(state.values.get("messages", [])),
            "messages": [
                {
                    "type": msg.__class__.__name__,
                    "content": str(msg.content) if hasattr(msg, "content") else "N/A",
                    "tool_calls": [tc["name"] for tc in getattr(msg, "tool_calls", [])]
                    if hasattr(msg, "tool_calls")
                    else None,
                }
                for msg in state.values.get("messages", [])
            ],
            "file_paths": state.values.get("file_paths", []),
            "file_ids": state.values.get("file_ids", []),
        }

        # 添加 context 信息（如果可用）
        if "context" in state.values:
            checkpoint_info["context"] = {}
            for key, value in state.values["context"].items():
                if hasattr(value, "summary"):
                    checkpoint_info["context"][key] = {
                        "summary": value.summary,
                        "summary_length": len(value.summary),
                    }

        return checkpoint_info


async def get_agent(config: AgentConfig) -> Agent:
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
