#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HumanInTheLoopTools - 人机交互工具模块

提供通用的人工确认和审批工具，支持在 Agent 执行过程中暂停并等待人类输入。
基于 LangGraph 的 interrupt() 机制实现。

Date: 2026-05-28
Author: AI Assistant
"""

import json
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext


@tool
def request_human_approval(
    title: str,
    content: str,
    context: dict = None,
    runtime: ToolRuntime[AgentContext] = None,
) -> Command:
    """
    【请求人工确认】在需要人工决策的关键节点暂停执行，等待用户反馈。

    调用时机：
    - 执行高风险操作前需要用户确认时
    - 需要用户从多个选项中做出选择时
    - 需要用户提供额外信息或修改建议时
    - 业务规则要求人工审批的关键步骤

    Args:
        title: 确认请求标题，简短描述需要确认的事项
        content: 确认请求详细内容，说明需要用户决策的具体原因和影响
        context: 附加上下文信息（可选），可包含选项列表、决策类型等
            示例: {"options": [{"id": 0, "text": "选项A"}], "allow_multiple": False}
        runtime: 工具运行时上下文，包含会话信息和工具调用ID

    Returns:
        Command: 包含 pending_approval 状态和 ToolMessage 的命令对象
            - pending_approval: 待确认信息，包含 title、content、context、tool_call_id
            - messages: ToolMessage，记录确认请求已发起
    """
    tool_name = "request_human_approval"
    tool_call_id = runtime.tool_call_id

    try:
        pending_approval = {
            "status": "pending",
            "title": title,
            "content": content,
            "context": context or {},
            "tool_call_id": tool_call_id,
        }

        summary = {
            "status": "pending",
            "tool": tool_name,
            "message": f"已发起人工确认请求: {title}",
            "pending_approval": pending_approval,
        }

        return Command(
            update={
                "pending_approval": pending_approval,
                "messages": [
                    ToolMessage(
                        content=json.dumps(summary, ensure_ascii=False),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        error_summary = {
            "status": "error",
            "tool": tool_name,
            "error": str(e),
            "message": f"发起人工确认请求失败: {str(e)}"
        }

        return Command(
            update={
                "pending_approval": None,
                "messages": [
                    ToolMessage(
                        content=json.dumps(error_summary, ensure_ascii=False),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
