#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同审批解析附件智能体模块

基于 LangGraph v1.0 。
使用 MessagesState 和 add_messages 实现多轮对话。

工作流:
    START → summarize → llm_call → END (自动循环调用工具直到完成)

摘要功能:
    - 使用 SummarizationNode 自动管理对话摘要
    - 保留最新对话，自动摘要旧消息
    - 与 trim_messages 配合使用，确保上下文长度合适

Date: 2026-03-010
Author: 张镒谱
"""
import asyncio
from typing import Literal, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.graph import MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AnyMessage
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode, RunningSummary
from app.agents.subgraphs.audit_document.tools import get_audit_tools
from app.agents.llmcalls.model_factory import ModelFactory
from app.utils.memory.checkpoint import get_global_checkpointer


class State(MessagesState):
    """智能体状态类，继承自 MessagesState
    
    包含对话消息和上下文摘要信息
    """
    context: dict[str, RunningSummary]


class Context(TypedDict):
    """静态上下文类，包含文件路径和文件 ID
    
    这些数据在对话过程中保持不变，作为静态上下文传入 StateGraph
    """
    file_paths: list[str]
    file_ids: list[str]


class LLMInputState(TypedDict):
    """LLM 输入状态的类型定义
    
    定义了传递给 LLM 节点的输入格式：
        - summarized_messages: 经过摘要处理后的消息列表
        - context: 上下文摘要信息字典
    """
    summarized_messages: list[AnyMessage]
    context: dict[str, RunningSummary]


class AuditDocumentAgent:
    """
    合同审批解析智能体
    
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
        model_type: str = "ollama",
        model_name: str = "llama3.2",
        temperature: float = 0,
        api_key: str = None,
        base_url: str = None,
        max_tokens: int = 256,
        max_tokens_before_summary: int = 256,
        max_summary_tokens: int = 128
    ):
        """
        初始化智能体
        
        Args:
            model_type: 模型类型（如 "ollama"、"deepseek" 等）
            model_name: 模型名称（如 "llama3.2"、"deepseek-chat" 等）
            temperature: 模型温度参数，控制生成多样性（0-1，越高越随机）
            api_key: API 密钥，用于访问远程模型服务
            base_url: API 基础 URL，指定模型服务的地址
            max_tokens: 最大 token 数，限制单次生成的最大长度
            max_tokens_before_summary: 触发摘要的 token 阈值，当消息超过此值时触发摘要
            max_summary_tokens: 摘要后的最大 token 数，控制摘要的长度
        """
        self._model_type = model_type
        self._model_name = model_name
        self._temperature = temperature
        self._api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._max_tokens_before_summary = max_tokens_before_summary
        self._max_summary_tokens = max_summary_tokens

    async def __ainit__(self, db_path: str = ":memory:"):
        """异步初始化方法
        
        创建模型实例、工具节点和检查点器，构建工作流图。
        
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
        # 获取审计工具列表
        self.tools = get_audit_tools()
        # 创建工具节点，用于执行工具调用
        self.tool_node = ToolNode(self.tools)
        # 使用全局单例检查点器，实现跨会话的记忆共享
        self.checkpointer = get_global_checkpointer(db_path)
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
            
        Returns:
            包含模型响应消息的字典
        """
        messages = state["summarized_messages"]

        # 系统提示词，指导模型如何根据文件类型调用相应的解析工具
        system_prompt = f"""你是一个合同审批解析助手。根据以下规则直接调用对应工具，无需询问用户是否上传文件：

## 强制调用规则
当用户明确指令"直接调用[工具名]"或"执行[操作]"时，**立即调用对应工具**，不要询问文件来源。

- 用户说"直接调用合同解析工具" → 立即调用 parse_contract_tool
- 用户说"直接调用成交确认书解析" → 立即调用 parse_transaction_tool  
- 用户说"直接调用会议纪要解析" → 立即调用 parse_meeting_minutes_tool

## 参数传递说明
合同文件地址已通过系统后台传入，你只需执行工具调用，无需关心文件来源。

## 执行要求
不要回复"需要您提供合同内容"等确认话术，直接执行工具调用。
                            """

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
        
        # 创建状态图，传入 context_schema 作为静态上下文
        workflow = StateGraph(State, context_schema=Context)

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
        workflow.add_edge("tools", "llm_call")
        
        # 编译图，添加 checkpointer 实现全局记忆功能
        self.graph = workflow.compile(checkpointer=self.checkpointer)

    async def invoke(
        self,
        prompt: str,
        file_paths: list,
        file_ids: list,
        session_id: str = None,
        db_path: str = ":memory:",
        **kwargs
    ):
        """调用智能体执行任务
        
        将用户提示和文件信息传入工作流，执行对话并返回结果。
        
        Args:
            prompt: 用户提示或问题
            file_paths: 文件路径列表，包含需要解析的文件路径
            file_ids: 文件 ID 列表，用于标识和追踪文件
            session_id: 会话 ID，用于区分不同用户的对话，相同 session_id 的对话共享记忆
            db_path: 数据库路径，用于持久化对话记忆
            **kwargs: 其他传递给图执行的参数
            
        Returns:
            dict: 执行结果，包含 messages（消息列表）和 context（上下文摘要信息）
        """
        # 异步初始化智能体
        await self.__ainit__(db_path=db_path)
        
        # 使用 session_id 作为 thread_id，确保同一用户的对话共享记忆
        config = {"configurable": {"thread_id": session_id or "default"}}

        # 构建输入状态（只包含消息）
        input_state = {
            "messages": [("user", prompt)]
        }

        # 构建上下文（包含静态的文件路径和文件 ID）
        context = {
            "file_paths": file_paths,
            "file_ids": file_ids,
            "session_id": session_id
        }

        # 执行图，传入上下文
        result = await self.graph.ainvoke(input_state, config, context=context, **kwargs)
        
        # 添加 context 信息（如果可用）
        if hasattr(self, 'summarization_node') and "context" in result:
            result["context"] = result["context"]
        
        return result

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


async def get_audit_document_agent(
    model_type: str = "ollama",
    model_name: str = "llama3.2",
    temperature: float = 0,
    api_key: str = None,
    base_url: str = None,
    max_tokens: int = 256,
    max_tokens_before_summary: int = 200,
    max_summary_tokens: int = 128
) -> AuditDocumentAgent:
    """获取审计文档智能体实例的工厂函数
    
    创建并初始化 AuditDocumentAgent 实例，简化智能体的创建过程。
    
    Args:
        model_type: 模型类型
        model_name: 模型名称
        temperature: 温度参数
        api_key: API 密钥
        base_url: API 基础 URL
        max_tokens: 最大 token 数
        max_tokens_before_summary: 触发摘要的 token 阈值
        max_summary_tokens: 摘要后的最大 token 数
        
    Returns:
        AuditDocumentAgent: 初始化完成的智能体实例
    """
    # 创建智能体实例
    agent = AuditDocumentAgent(
        model_type=model_type,
        model_name=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
        max_tokens_before_summary=max_tokens_before_summary,
        max_summary_tokens=max_summary_tokens
    )
    # 异步初始化
    await agent.__ainit__()
    return agent


if __name__ == "__main__":
    async def main():
        """主函数，演示智能体的使用方法
        
        示例 1: 启用摘要功能
            - 创建智能体实例
            - 执行多次对话，测试摘要功能
            - 打印摘要信息
            
        示例 2: 查看 checkpoint 内容
            - 检查对话历史
            - 显示消息数量和内容
            - 显示摘要信息
        """
        # 示例 1: 启用摘要功能
        print("=== 启用摘要功能 ===")
        agent = await get_audit_document_agent(
            model_type="deepseek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-d5652bb2e21c43debd1f22fbed6468cf",
            max_tokens=4096,
            max_tokens_before_summary=1000,
            max_summary_tokens=2000
        )
        
        prompts = [
            "直接调用合同解析工具，合同内容：‘国有建设用地使用权出让合同’"
            #,
            #"你还能干什么",
            #"如何防止提示词注入",
            #"你是谁",
            #"总结我们的对话"
        ]

        for prompt in prompts:
            result = await agent.invoke(
                session_id="user_123",
                prompt=prompt,
                file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
                file_ids=["file_001", "file_002"]
            )
            result["messages"][-1].pretty_print()
        
        # 显示摘要信息
        if "context" in result:
            print(f"\n=== 摘要信息 ===")
            for key, value in result["context"].items():
                if hasattr(value, 'summary'):
                    print(f"{key}: {value.summary}")
        
        # 示例 2: 查看 checkpoint 内容
        print("\n=== Checkpoint 信息 ===")
        checkpoint = await agent.inspect_checkpoint(session_id="user_123")
        print(f"消息数: {checkpoint['messages_count']}")
        for msg in checkpoint['messages']:
            print(f"- {msg['type']}: {msg['content']}")
            if msg['tool_calls']:
                print(f"  工具调用: {msg['tool_calls']}")
        
        if checkpoint.get('context'):
            print("\n=== Context 信息 ===")
            for key, value in checkpoint['context'].items():
                print(f"{key}: {value['summary'][:100]}... (长度: {value['summary_length']})")

    asyncio.run(main())
