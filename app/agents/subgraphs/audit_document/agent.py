#!/usr/bin python
# -*- coding:utf-8 -*-
"""
合同审批解析附件智能体模块

基于 LangGraph v1.0 的合同审批解析附件智能体。
使用 MessagesState 和 add_messages 实现多轮对话。

工作流:
    START → agent → END (自动循环调用工具直到完成)

Date: 2026-03-05
Author: 张镒谱
"""
import asyncio
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langgraph.graph import MessagesState
from langgraph.prebuilt import ToolNode
from app.agents.subgraphs.audit_document.tools import get_audit_tools
from app.agents.llmcalls.model_factory import ModelFactory


class AuditDocumentAgent:
    """
    合同审批解析智能体

    使用 LangGraph MessagesState 实现多轮对话，
    工具在内部解析并保存到长期记忆，返回摘要信息。
    """

    def __init__(
        self,
        model_type: str = "ollama",
        model_name: str = "llama3.2",
        temperature: float = 0,
        api_key: str = None,
        base_url: str = None
    ):
        self._model_type = model_type
        self._model_name = model_name
        self._temperature = temperature
        self._api_key = api_key
        self._base_url = base_url

    async def __ainit__(self):
        self.model = ModelFactory.create_model(
            model_type=self._model_type,
            model_name=self._model_name,
            api_key=self._api_key or "",
            temperature=self._temperature,
            base_url=self._base_url
        )
        self.tools = get_audit_tools()
        self.tool_node = ToolNode(self.tools)
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
                            请根据用户描述或文件内容自行判断文件类型，然后直接调用相应的解析工具。"""

        llm = self.model.bind_tools(self.tools)
        response = await llm.ainvoke([("system", system_prompt)] + messages)
        return {"messages": [response]}

    def _build_graph(self):
        

        workflow = StateGraph(MessagesState)

        workflow.add_node("llm_call", self._llm_call)
        workflow.add_node("tools", self.tool_node)

        workflow.add_edge(START, "llm_call")

        workflow.add_conditional_edges(
            "llm_call",
            self._should_continue,
            {
                "tools": "tools",
                "end": END
            }
        )

        workflow.add_edge("tools", "llm_call")

        self.graph = workflow.compile()

    async def invoke(
        self,
        prompt: str,
        file_paths: list,
        file_ids: list,
        session_id: str = None
    ):
        await self.__ainit__()

        input_state = {
            "messages": [("user", prompt)],
            "file_paths": file_paths,
            "file_ids": file_ids
        }

        return await self.graph.ainvoke(input_state)


async def get_audit_document_agent(
    model_type: str = "ollama",
    model_name: str = "llama3.2",
    temperature: float = 0,
    api_key: str = None,
    base_url: str = None
) -> AuditDocumentAgent:
    agent = AuditDocumentAgent(
        model_type=model_type,
        model_name=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url
    )
    await agent.__ainit__()
    return agent
if __name__ == "__main__":
    async def main():
        agent = await get_audit_document_agent(
            model_type="deepseek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-d5652bb2e21c43debd1f22fbed6468cf"
        )
        result = await agent.invoke(
            prompt="请解析这些文件",
            file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
            file_ids=["file_001", "file_002"]
        )
        print(result)

    asyncio.run(main())