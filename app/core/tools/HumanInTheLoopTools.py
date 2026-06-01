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
from typing import Literal, List, Optional
from pydantic import BaseModel, Field
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext


class ApprovalOption(BaseModel):
    """确认选项"""
    value: str = Field(description="选项的值，用于标识用户选择了哪个选项，如 'yes'/'no'")
    label: str = Field(description="选项的显示文本，展示给用户看的文字，如 '正确'/'不正确'")


class ApprovalContext(BaseModel):
    """人工确认的上下文配置，控制前端交互方式"""
    interaction_type: Literal["options", "input"] = Field(
        default="input",
        description="交互类型：'options' 表示选项型（显示按钮供用户选择，适合'是否正确'类确认），'input' 表示输入型（显示文本框供用户输入，适合需要填写内容的场景）"
    )
    options: Optional[List[ApprovalOption]] = Field(
        default=None,
        description="选项列表，当 interaction_type='options' 时必须提供，每个选项包含 value 和 label"
    )
    other_input: bool = Field(
        default=True,
        description="是否显示'其他'输入框。默认为 True，options 类型时会额外显示一个文本输入框供用户填写自定义内容，input 类型时标识当前输入为'其他'输入"
    )


class RequestHumanApprovalInput(BaseModel):
    """请求人工确认的输入参数"""
    title: str = Field(description="确认请求标题，简短描述需要确认的事项，如'确认用户信息'")
    content: str = Field(description="确认请求详细内容，说明需要用户决策的具体原因和影响")
    context: Optional[ApprovalContext] = Field(
        default=None,
        description="交互配置，决定前端展示为选项按钮还是输入框，详见 ApprovalContext 定义"
    )


@tool(args_schema=RequestHumanApprovalInput)
def request_human_approval(
    title: str,
    content: str,
    context: ApprovalContext = None,
    runtime: ToolRuntime[AgentContext] = None,
) -> Command:
    """
    【请求人工确认/澄清】在需要人工决策、需求澄清或信息补充的关键节点暂停执行，等待用户反馈。

    使用步骤：
    1. 生成 title：用一句话概括需要用户确认的事项，如"请明确审批信息"。
    2. 生成 content：详细说明需要用户决策的原因，如"您的审批请求不够明确，请告诉我需要进行哪些分析？"
    3. 根据用户意图生成 ApprovalContext 格式的数据：
       - 若用户需要从多个预设选项中选择（如"合规性审查"、"项目预审"、"补充耕地"），必须生成：
         context={
           "interaction_type": "options",
           "options": [
             {"value": "合规性审查", "label": "合规性审查"},
             {"value": "项目预审", "label": "项目预审"},
             {"value": "补充耕地", "label": "补充耕地"}
           ]
         }
       - 若用户需要自由输入内容（如"请输入项目名称"），生成：
         context={"interaction_type": "input"}
       - 若未传 context，默认按 input 处理

    重要约束：
    - 当需要用户从多个预设选项中选择时，必须把选项封装到 context.options 中，不能只写在 content 文本里
    - options 中的每个选项必须同时包含 value（提交值）和 label（显示文本）
    - 默认 other_input: true，options 模式下会额外显示"其他"输入框

    Args:
        title: 确认请求标题，简短描述需要确认的事项
        content: 确认请求详细内容，说明需要用户决策的具体原因和影响
        context: 交互配置，决定前端展示为选项按钮还是输入框，格式遵循 ApprovalContext
        runtime: 工具运行时上下文，包含会话信息和工具调用ID（LangChain内部注入，无需在args_schema中定义）

    Returns:
        Command: 包含 pending_approval 状态和 ToolMessage 的命令对象
            - pending_approval: 待确认信息，包含 title、content、context、tool_call_id
            - messages: ToolMessage，记录确认请求已发起
    """
    tool_name = "request_human_approval"
    tool_call_id = runtime.tool_call_id

    try:
        # 将 Pydantic 模型转换为 dict 以便序列化
        context_dict = context.model_dump() if context else {"other_input": True}
        pending_approval = {
            "status": "pending",
            "title": title,
            "content": content,
            "context": context_dict,
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
                        tool_call_id=tool_call_id,
                        id=tool_call_id
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
                        tool_call_id=tool_call_id,
                        id=tool_call_id
                    )
                ]
            }
        )
