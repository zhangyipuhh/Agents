#!/usr/bin python
# -*- coding:utf-8 -*-
"""
合同审批解析附件智能体模块

基于 LangGraph v1.0 的合同审批解析附件智能体。
使用 MessagesState 和 add_messages 实现多轮对话。

工作流:
    START → summarize → llm_call → END (自动循环调用工具直到完成)

摘要功能:
    - 使用 SummarizationNode 自动管理对话摘要
    - 保留最新对话，自动摘要旧消息
    - 与 trim_messages 配合使用，确保上下文长度合适

Date: 2026-03-05
Author: 张镒谱
"""
import asyncio
from typing import Literal, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langgraph.graph import MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages.utils import count_tokens_approximately
from langmem.short_term import SummarizationNode, RunningSummary
from app.agents.subgraphs.audit_document.tools import get_audit_tools
from app.agents.llmcalls.model_factory import ModelFactory
from app.utils.memory.checkpoint import get_global_checkpointer


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
            model_type: 模型类型
            model_name: 模型名称
            temperature: 温度参数
            api_key: API 密钥
            base_url: API 基础 URL
            max_tokens: 最大 token 数
            max_tokens_before_summary: 触发摘要的 token 阈值
            max_summary_tokens: 摘要后的最大 token 数
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
        self.model = ModelFactory.create_model(
            model_type=self._model_type,
            model_name=self._model_name,
            api_key=self._api_key or "",
            temperature=self._temperature,
            base_url=self._base_url
        )
        self.tools = get_audit_tools()
        self.tool_node = ToolNode(self.tools)
        # 使用全局单例 checkpointer
        self.checkpointer = get_global_checkpointer(db_path)
        # 创建摘要模型
        self.summarization_model = self.model.bind(max_tokens=self._max_summary_tokens)
        self._build_graph()

    def _should_continue(self, state: MessagesState) -> Literal["tools", "end"]:
        messages = state.get("messages", [])
        if not messages:
            return "end"
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

    async def _llm_call(self, state: MessagesState):
        messages = state["messages"]
        file_paths = state.get("file_paths", [])
        file_ids = state.get("file_ids", [])

        system_prompt = f"""你是一个合同审批解析助手。请根据用户上传的文件调用相应的解析工具。

                            用户可能上传以下类型的文件：
                            - 合同文件（Word 或 PDF）：请调用 parse_contract_tool
                            - 成交确认书（PDF）：请调用 parse_transaction_tool
                            - 会议纪要（PDF）：请调用 parse_meeting_minutes_tool
                            请根据用户描述或文件内容自行判断文件类型，然后直接调用相应的解析工具。
                            """

        llm = self.model.bind_tools(self.tools)
        response = await llm.ainvoke([("system", system_prompt)] + messages)
        return {"messages": [response]}

    def _build_graph(self):
        """
        构建 LangGraph 工作流
        
        工作流:
            START → summarize → llm_call → END
            
        摘要节点:
            - 使用 SummarizationNode 自动管理对话摘要
            - 保留最新对话，自动摘要旧消息
            - 与 trim_messages 配合确保 token 数合适
        """
        # 定义包含 RunningSummary 的 State
        class State(MessagesState):
            context: dict[str, RunningSummary]
        
        # 定义 LLM 输入 State
        class LLMInputState(TypedDict):
            summarized_messages: list[AnyMessage]
            context: dict[str, RunningSummary]
        
        # 创建 SummarizationNode
        summarization_node = SummarizationNode(
            token_counter=count_tokens_approximately,
            model=self.summarization_model,
            max_tokens=self._max_tokens,
            max_tokens_before_summary=self._max_tokens_before_summary,
            max_summary_tokens=self._max_summary_tokens,
        )
        
        def call_model(state: LLMInputState):
            """调用 LLM"""
            messages = state["summarized_messages"]
            file_paths = state.get("file_paths", [])
            file_ids = state.get("file_ids", [])

            system_prompt = f"""你是一个合同审批解析助手。请根据用户上传的文件调用相应的解析工具。

                                用户可能上传以下类型的文件：
                                - 合同文件（Word 或 PDF）：请调用 parse_contract_tool
                                - 成交确认书（PDF）：请调用 parse_transaction_tool
                                - 会议纪要（PDF）：请调用 parse_meeting_minutes_tool
                                请根据用户描述或文件内容自行判断文件类型，然后直接调用相应的解析工具。
                                """

            llm = self.model.bind_tools(self.tools)
            response = llm.invoke([("system", system_prompt)] + messages)
            return {"messages": [response]}
        
        workflow = StateGraph(State)

        workflow.add_node("summarize", summarization_node)
        workflow.add_node("llm_call", call_model)
        workflow.add_node("tools", self.tool_node)

        workflow.add_edge(START, "summarize")
        workflow.add_edge("summarize", "llm_call")

        workflow.add_conditional_edges(
            "llm_call",
            self._should_continue,
            {
                "tools": "tools",
                "end": END
            }
        )

        workflow.add_edge("tools", "llm_call")
        
        # 编译图，添加 checkpointer 全局记忆功能
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
        """
        调用智能体
        
        Args:
            prompt: 用户提示
            file_paths: 文件路径列表
            file_ids: 文件 ID 列表
            session_id: 会话 ID
            db_path: 数据库路径
            **kwargs: 其他参数
            
        Returns:
            dict: 执行结果，包含 messages 和 context
        """
        await self.__ainit__(db_path=db_path)
        
        # 使用 session_id 作为 thread_id，确保同一用户的对话共享记忆
        config = {"configurable": {"thread_id": session_id or "default"}}

        input_state = {
            "messages": [("user", prompt)],
            "file_paths": file_paths,
            "file_ids": file_ids
        }

        result = await self.graph.ainvoke(input_state, config, **kwargs)
        
        # 添加 context 信息（如果可用）
        if hasattr(self, 'summarization_node') and "context" in result:
            result["context"] = result["context"]
        
        return result

    async def inspect_checkpoint(self, session_id: str = None):
        """检查指定 session 的 checkpoint 内容
           测试用，实际功能不涉及
        Args:
            session_id: 会话 ID
            
        Returns:
            dict: Checkpoint 的详细内容
        """
        config = {"configurable": {"thread_id": session_id or "default"}}
        state = self.graph.get_state(config)
        
        # 提取 checkpoint 信息
        checkpoint_info = {
            "thread_id": session_id or "default",
            "checkpoint_id": state.checkpoint_id if hasattr(state, 'checkpoint_id') else None,
            "messages_count": len(state.values.get("messages", [])),
            "messages": [
                {
                    "type": msg.__class__.__name__,
                    "content": str(msg.content)[:100] if hasattr(msg, "content") else "N/A",
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
    max_tokens_before_summary: int = 256,
    max_summary_tokens: int = 128
) -> AuditDocumentAgent:
    """
    获取审计文档智能体实例
    
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
        AuditDocumentAgent: 智能体实例
    """
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
    await agent.__ainit__()
    return agent
if __name__ == "__main__":
    async def main():
        # 示例 1: 启用摘要功能
        print("=== 启用摘要功能 ===")
        agent = await get_audit_document_agent(
            model_type="deepseek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-d5652bb2e21c43debd1f22fbed6468cf",
            max_tokens=256,
            max_tokens_before_summary=200,
            max_summary_tokens=128
        )
        
        result = await agent.invoke(
            session_id="user_123",
            prompt="请解析这些文件",
            file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
            file_ids=["file_001", "file_002"]
        )
        result = await agent.invoke(
            session_id="user_123",
            prompt="你还能干什么",
            file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
            file_ids=["file_001", "file_002"]
        )
        result = await agent.invoke(
            session_id="user_123",
            prompt="如何防止提示词注入",
            file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
            file_ids=["file_001", "file_002"]
        )
        result = await agent.invoke(
            session_id="user_123",
            prompt="你是谁",
            file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
            file_ids=["file_001", "file_002"]
        )
        result = await agent.invoke(
            session_id="user_123",
            prompt="总结我们的对话",
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