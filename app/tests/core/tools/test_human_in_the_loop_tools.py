# -*- coding:utf-8 -*-
"""
测试 app.core.tools.HumanInTheLoopTools 人机交互工具模块

覆盖 Pydantic Schema 约束校验与 ask_user_question 工具逻辑。
"""

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock

from app.core.tools.HumanInTheLoopTools import (
    QuestionOption,
    Question,
    AskUserQuestionInput,
    ask_user_question,
)
from langgraph.types import Command


# =============================================================================
# QuestionOption Schema 测试
# =============================================================================


def test_question_option_normal():
    """
    测试 QuestionOption 正常创建。

    参数:
        label: 合法长度（1-50）的选项标签
        description: 合法长度（1-200）的选项描述

    返回值:
        None

    异常:
        AssertionError: 创建失败时抛出
    """
    opt = QuestionOption(label="React", description="前端框架")
    assert opt.label == "React"
    assert opt.description == "前端框架"


def test_question_option_label_too_long():
    """
    测试 QuestionOption label 超过 50 字符时触发 ValidationError。

    参数:
        label: 51 个字符的超长字符串

    返回值:
        None

    异常:
        ValidationError: label 长度超过 50 时触发
    """
    with pytest.raises(ValidationError):
        QuestionOption(label="A" * 51, description="正常描述")


def test_question_option_description_too_long():
    """
    测试 QuestionOption description 超过 200 字符时触发 ValidationError。

    参数:
        description: 201 个字符的超长字符串

    返回值:
        None

    异常:
        ValidationError: description 长度超过 200 时触发
    """
    with pytest.raises(ValidationError):
        QuestionOption(label="正常标签", description="D" * 201)


# =============================================================================
# Question Schema 测试
# =============================================================================


def test_question_options_empty():
    """
    测试 Question options 为空列表时合法（纯文本问题）。

    参数:
        question: 问题文本
        header: 短标签
        options: 空列表

    返回值:
        None

    异常:
        AssertionError: 创建失败时抛出
    """
    q = Question(question="请输入项目名称", header="名称", options=[])
    assert q.options == []


def test_question_options_two():
    """
    测试 Question options 为 2 个时合法。

    参数:
        options: 包含 2 个 QuestionOption 的列表

    返回值:
        None

    异常:
        AssertionError: 创建失败时抛出
    """
    q = Question(
        question="选择框架",
        header="框架",
        options=[
            QuestionOption(label="React", description="前端框架"),
            QuestionOption(label="Vue", description="前端框架"),
        ],
    )
    assert len(q.options) == 2


def test_question_options_five():
    """
    测试 Question options 为 5 个时合法（Pydantic max_length=5）。

    参数:
        options: 包含 5 个 QuestionOption 的列表

    返回值:
        None

    异常:
        AssertionError: 创建失败时抛出
    """
    opts = [QuestionOption(label=f"Opt{i}", description=f"选项{i}") for i in range(5)]
    q = Question(question="多选项", header="选项", options=opts)
    assert len(q.options) == 5


def test_question_options_one_raises_value_error():
    """
    测试 Question options 为 1 个时触发 ValueError。

    参数:
        options: 仅包含 1 个 QuestionOption 的列表

    返回值:
        None

    异常:
        ValidationError: options 非空但不足 2 个时触发（field_validator 抛 ValueError 被 Pydantic 包装）
    """
    with pytest.raises(ValidationError):
        Question(
            question="单选项",
            header="单选",
            options=[QuestionOption(label="A", description="唯一选项")],
        )


# =============================================================================
# AskUserQuestionInput Schema 测试
# =============================================================================


def test_ask_user_question_input_one_question():
    """
    测试 AskUserQuestionInput questions 为 1 个时合法。

    参数:
        questions: 包含 1 个 Question 的列表

    返回值:
        None

    异常:
        AssertionError: 创建失败时抛出
    """
    inp = AskUserQuestionInput(
        questions=[Question(question="Q1", header="H1", options=[])]
    )
    assert len(inp.questions) == 1


def test_ask_user_question_input_four_questions():
    """
    测试 AskUserQuestionInput questions 为 4 个时合法（边界值）。

    参数:
        questions: 包含 4 个 Question 的列表

    返回值:
        None

    异常:
        AssertionError: 创建失败时抛出
    """
    qs = [Question(question=f"Q{i}", header=f"H{i}", options=[]) for i in range(4)]
    inp = AskUserQuestionInput(questions=qs)
    assert len(inp.questions) == 4


def test_ask_user_question_input_zero_questions_raises():
    """
    测试 AskUserQuestionInput questions 为空列表时触发 ValidationError。

    参数:
        questions: 空列表

    返回值:
        None

    异常:
        ValidationError: questions 长度不足 1 时触发
    """
    with pytest.raises(ValidationError):
        AskUserQuestionInput(questions=[])


def test_inject_other_option_appends_other():
    """
    测试 _inject_other_option 为非空 options 问题自动追加 Other 选项。

    参数:
        questions: 包含非空 options 且不含 Other 的 Question

    返回值:
        None

    异常:
        AssertionError: Other 未追加时抛出
    """
    inp = AskUserQuestionInput(
        questions=[
            Question(
                question="框架选择",
                header="框架",
                options=[
                    QuestionOption(label="React", description="前端框架"),
                    QuestionOption(label="Vue", description="前端框架"),
                ],
            )
        ]
    )
    opts = inp.questions[0].options
    assert any(opt.label == "Other" for opt in opts)
    assert len(opts) == 3  # 原有 2 个 + 自动追加 1 个


def test_inject_other_option_skips_existing_other():
    """
    测试 _inject_other_option 在已存在 Other 选项时不重复追加。

    参数:
        questions: 已包含 label='Other' 的 Question

    返回值:
        None

    异常:
        AssertionError: Other 被重复追加时抛出
    """
    inp = AskUserQuestionInput(
        questions=[
            Question(
                question="选择",
                header="选",
                options=[
                    QuestionOption(label="A", description="选项A"),
                    QuestionOption(label="Other", description="其他"),
                ],
            )
        ]
    )
    opts = inp.questions[0].options
    other_count = sum(1 for opt in opts if opt.label == "Other")
    assert other_count == 1


def test_inject_other_option_skips_text_only():
    """
    测试 text_only=True 时跳过 Other 注入。

    参数:
        questions: text_only=True 且 options 非空的 Question

    返回值:
        None

    异常:
        AssertionError: Other 被注入时抛出
    """
    inp = AskUserQuestionInput(
        questions=[
            Question(
                question="描述",
                header="描述",
                options=[],
                text_only=True,
            )
        ]
    )
    opts = inp.questions[0].options
    assert not any(opt.label == "Other" for opt in opts)
    assert len(opts) == 0


# =============================================================================
# ask_user_question 工具逻辑测试
# =============================================================================


def test_ask_user_question_returns_command():
    """
    测试 ask_user_question 返回 Command 类型对象。

    参数:
        questions: 包含 1 个 Question 的列表
        runtime: Mock 的 ToolRuntime 对象，提供 tool_call_id

    返回值:
        None

    异常:
        AssertionError: 返回值非 Command 类型时抛出
    """
    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-test-001"
    q = Question(question="Q", header="H", options=[])
    result = ask_user_question(questions=[q], runtime=mock_runtime)
    assert isinstance(result, Command)


def test_ask_user_question_pending_question_structure():
    """
    测试 ask_user_question 返回的 pending_question 结构正确。

    验证字段包含 status、questions、tool_call_id。

    参数:
        questions: 包含 1 个 Question 的列表
        runtime: Mock 的 ToolRuntime 对象，提供 tool_call_id

    返回值:
        None

    异常:
        AssertionError: 结构字段缺失时抛出
    """
    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-test-002"
    q = Question(question="项目名称", header="名称", options=[])
    result = ask_user_question(questions=[q], runtime=mock_runtime)
    pending = result.update["pending_question"]
    assert pending["status"] == "pending"
    assert "questions" in pending
    assert len(pending["questions"]) == 1
    assert pending["tool_call_id"] == "call-test-002"
