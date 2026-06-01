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
        description="上下文配置，控制前端展示为选项按钮还是输入框。对于'是否'类确认，传 {interaction_type: 'options', options: [{value:'yes',label:'正确'},{value:'no',label:'不正确'}]}；对于需要用户输入的场景，传 {interaction_type: 'input'} 或不传。默认自动携带 other_input: true，即 options 类型会额外显示'其他'输入框，input 类型会标识为'其他'输入"
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

    调用时机：
    - 执行高风险操作前需要用户确认时
    - 需要用户从多个选项中做出选择时
    - 需要用户提供额外信息或修改建议时
    - 用户意图不明确、请求过于模糊，需要澄清具体需求时（如"我要学习一部法律"）
    - 用户请求与所有可用工具的能力范围都不匹配，需要用户进一步明确需求时
    - 业务规则要求人工审批的关键步骤

    交互类型规范：
    - 对于"是否"类确认问题（如"请确认以上信息是否正确"），必须使用 context={"interaction_type": "options", "options": [{"value": "yes", "label": "正确"}, {"value": "no", "label": "不正确"}]}
    - 对于需要用户输入内容的场景（如"请输入修改后的内容"、"我要学习一部法律"），使用 context={"interaction_type": "input"} 或不传
    - 默认自动携带 other_input: true，options 类型会额外显示"其他"输入框，input 类型会标识为"其他"输入

    示例：
    - 用户说"我要学习一部法律"（意图模糊，没有可用工具匹配）→ 调用 request_human_approval(title="请明确法律名称", content="您想学习哪部法律？请提供具体的法律名称。", context={"interaction_type": "input"})
    - 用户说"请确认以上信息是否正确"（需要确认）→ 调用 request_human_approval(title="信息确认", content="请确认以上信息是否正确", context={"interaction_type": "options", "options": [{"value": "yes", "label": "正确"}, {"value": "no", "label": "不正确"}]})

    Args:
        title: 确认请求标题，简短描述需要确认的事项
        content: 确认请求详细内容，说明需要用户决策的具体原因和影响
        context: 上下文配置，控制前端交互方式
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
