#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HumanInTheLoopTools - 人机交互工具模块

提供通用的人工确认和审批工具，支持在 Agent 执行过程中暂停并等待人类输入。
基于 LangGraph 的 interrupt() 机制实现。

本模块定义 ask_user_question 工具，支持多问题、结构化选项、虚拟 Other 项。

Date: 2026-06-01
Author: AI Assistant
"""

import json
from typing import Literal, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext


# =============================================================================
# Pydantic Schema（v2 强制约束）
# =============================================================================


class QuestionOption(BaseModel):
    """问题选项 - 必填 label + description

    label 用于按钮显示文本，description 解释该选项的具体含义。
    约束：label 1-50 字符，description 1-200 字符。
    """
    label: str = Field(
        min_length=1, max_length=50,
        description="选项显示文本（1-5 词，简短），如'React'"
    )
    description: str = Field(
        min_length=1, max_length=200,
        description="选项说明，解释该选项的具体含义"
    )


class Question(BaseModel):
    """单个问题（每个 Question 必须是 1 个明确决策点）

    约束：question 1-500 字符，header 1-30 字符，options 0-4 个。
    - options 为空时，本题降级为纯文本问题（前端显示 textarea）
    - options 非空时，必须 2-4 个，并自动追加虚拟"Other"项
    - text_only 显式标记为纯文本题，跳过 Other 注入
    - multiple 字段控制单选/多选，默认单选
    """
    question: str = Field(
        min_length=1, max_length=500,
        description="完整问题文本，如'你想用哪个前端框架？'"
    )
    header: str = Field(
        min_length=1, max_length=30,
        description="极短标签（用于 Tab 显示），如'框架'"
    )
    options: List[QuestionOption] = Field(
        min_length=0, max_length=4,
        description="可选选项列表（0-4 个）。为空时为纯文本问题；非空时 2-4 个"
    )
    multiple: Optional[bool] = Field(
        default=False,
        description="是否允许多选，默认 false（单选）"
    )
    text_only: Optional[bool] = Field(
        default=False,
        description="显式标记为纯文本问题（不自动追加 Other，前端显示 textarea）"
    )

    @field_validator("options")
    @classmethod
    def _validate_options(cls, v: List[QuestionOption]) -> List[QuestionOption]:
        """options 长度 0-4：为空是合法（纯文本），非空时必须 ≥ 2"""
        if v and len(v) < 2:
            raise ValueError("options 非空时必须至少 2 个；如需纯文本问题请传 options=[]")
        return v


class AskUserQuestionInput(BaseModel):
    """请求用户回答问题的工具入参

    约束：questions 1-4 个。
    自动注入：非 text_only 且非空 options 的问题自动追加虚拟"Other"项，
    保证用户始终有"逃逸通道"输入自定义回答。
    """
    questions: List[Question] = Field(
        min_length=1, max_length=4,
        description="问题列表（1-4 个相关问题）"
    )

    @model_validator(mode="after")
    def _inject_other_option(self) -> "AskUserQuestionInput":
        """为每个非纯文本问题自动追加虚拟'Other'选项

        - text_only=True：纯文本题，跳过注入
        - options=[]：纯文本题，跳过注入
        - AI 已传 label='Other' 的选项：不重复追加
        """
        for q in self.questions:
            if q.text_only or not q.options:
                continue
            if any(opt.label == "Other" for opt in q.options):
                continue
            q.options.append(QuestionOption(
                label="Other",
                description="输入自定义回答",
            ))
        return self


# =============================================================================
# ask_user_question 工具
# =============================================================================


@tool(args_schema=AskUserQuestionInput)
def ask_user_question(
    questions: List[Question],
    runtime: ToolRuntime[AgentContext] = None,
) -> Command:
    """
    【向用户提问】在需要澄清需求或补充信息的节点暂停执行，等待用户回答。

    使用步骤：
    1. 判断用户意图是否清晰（如"用什么框架？" → 不清晰）
    2. 构造 1-4 个明确的问题（每个问题只问 1 件事）
    3. 为每个问题提供 2-4 个选项，**推荐项放第一个并加 (Recommended) 后缀**
       - 如果问题是开放式的（如"请输入项目名称"），传 options=[] + text_only=true
    4. 调用本工具，传入结构化 questions 数组

    重要约束：
    - questions 数组必填，1-4 个
    - 每个 question 的 options 0-4 个：
        * 非空：2-4 个选项，**后端会自动追加虚拟"Other"项**（不必手写）
        * 空：纯文本问题，前端显示 textarea 让用户自由输入
    - text_only=true：显式标记纯文本问题，跳过 Other 注入
    - 推荐项放 options[0]，label 末尾加 "(Recommended)" 后缀
    - 多选用 multiple: true

    Args:
        questions: 问题列表，每个问题包含 question/header/options/multiple/text_only
        runtime: 工具运行时上下文（LangChain 内部注入）

    Returns:
        Command: 包含 pending_question 状态和 ToolMessage 的命令对象
            - pending_question: 待回答问题信息
            - messages: ToolMessage，记录问题已发起
    """
    tool_call_id = runtime.tool_call_id

    # Pydantic 自动校验（args_schema 已做，这里 model_dump 输出 dict）
    pending_question = {
        "status": "pending",
        "questions": [q.model_dump() for q in questions],
        "tool_call_id": tool_call_id,
    }

    summary = {
        "status": "pending",
        "tool": "ask_user_question",
        "questions_count": len(questions),
        "message": f"已发起 {len(questions)} 个问题等待用户回答",
    }

    return Command(
        update={
            "pending_question": pending_question,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
