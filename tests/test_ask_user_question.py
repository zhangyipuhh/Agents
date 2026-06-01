"""ask_user_question 工具的单元测试

测试 Pydantic Schema 的必填约束、工具函数行为、hitl_check_node 节点行为。
"""
import asyncio
import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.tools.HumanInTheLoopTools import (
    AskUserQuestionInput,
    Question,
    QuestionOption,
)


class TestQuestionOption:
    """QuestionOption schema 校验"""

    def test_valid_option(self):
        # 正常输入：label + description 都合法
        opt = QuestionOption(label="React", description="Meta 出品的 UI 库")
        assert opt.label == "React"
        assert opt.description == "Meta 出品的 UI 库"

    def test_empty_label_rejected(self):
        # label 为空应被拒绝
        with pytest.raises(ValidationError):
            QuestionOption(label="", description="valid desc")

    def test_empty_description_rejected(self):
        # description 为空应被拒绝
        with pytest.raises(ValidationError):
            QuestionOption(label="valid label", description="")


class TestQuestion:
    """Question schema 校验"""

    def test_valid_question(self):
        # 正常 question：multiple 默认 False
        q = Question(
            question="你想用哪个框架？",
            header="框架",
            options=[
                QuestionOption(label="React", description="A"),
                QuestionOption(label="Vue", description="B"),
            ],
        )
        assert q.multiple is False  # 默认值

    def test_min_options_enforced(self):
        # options 至少 2 个，1 个应被拒绝
        with pytest.raises(ValidationError):
            Question(
                question="Q?",
                header="H",
                options=[QuestionOption(label="Only", description="only one")],
            )

    def test_max_options_enforced(self):
        # options 最多 4 个，5 个应被拒绝
        with pytest.raises(ValidationError):
            Question(
                question="Q?",
                header="H",
                options=[
                    QuestionOption(label=f"opt{i}", description=f"d{i}")
                    for i in range(5)
                ],
            )

    def test_header_too_long_rejected(self):
        # header 超过 30 字符应被拒绝
        with pytest.raises(ValidationError):
            Question(
                question="Q?",
                header="x" * 31,  # 31 字符
                options=[
                    QuestionOption(label="A", description="a"),
                    QuestionOption(label="B", description="b"),
                ],
            )


class TestAskUserQuestionInput:
    """AskUserQuestionInput schema 校验"""

    def test_valid_input(self):
        # 正常输入：单个 question
        inp = AskUserQuestionInput(
            questions=[
                Question(
                    question="Q1?",
                    header="H1",
                    options=[
                        QuestionOption(label="A", description="a"),
                        QuestionOption(label="B", description="b"),
                    ],
                )
            ]
        )
        assert len(inp.questions) == 1

    def test_empty_questions_rejected(self):
        # questions 数组为空应被拒绝
        with pytest.raises(ValidationError):
            AskUserQuestionInput(questions=[])

    def test_too_many_questions_rejected(self):
        # questions 最多 4 个，5 个应被拒绝
        with pytest.raises(ValidationError):
            AskUserQuestionInput(
                questions=[
                    Question(
                        question=f"Q{i}?",
                        header=f"H{i}",
                        options=[
                            QuestionOption(label="A", description="a"),
                            QuestionOption(label="B", description="b"),
                        ],
                    )
                    for i in range(5)
                ]
            )


class TestAskUserQuestionTool:
    """ask_user_question 工具函数行为测试"""

    def _make_runtime(self, tool_call_id="test_call_123"):
        """构造 mock 的 ToolRuntime"""
        from app.core.tools.HumanInTheLoopTools import ask_user_question
        self.ask_user_question = ask_user_question
        runtime = MagicMock()
        runtime.tool_call_id = tool_call_id
        return runtime

    def test_tool_returns_command_with_pending_question(self):
        # 工具应返回 Command(update=...) 包含 pending_question 和 messages
        runtime = self._make_runtime()
        questions = [
            Question(
                question="框架？",
                header="框架",
                options=[
                    QuestionOption(label="React", description="A"),
                    QuestionOption(label="Vue", description="B"),
                ],
            )
        ]

        result = self.ask_user_question.func(questions=questions, runtime=runtime)

        assert hasattr(result, "update")
        assert result.update["pending_question"]["status"] == "pending"
        assert len(result.update["pending_question"]["questions"]) == 1
        assert result.update["pending_question"]["tool_call_id"] == "test_call_123"

    def test_tool_includes_toolmessage(self):
        # Command 应包含 ToolMessage 配对 tool_call_id
        runtime = self._make_runtime("call_456")
        questions = [
            Question(
                question="Q?",
                header="H",
                options=[
                    QuestionOption(label="A", description="a"),
                    QuestionOption(label="B", description="b"),
                ],
            )
        ]

        result = self.ask_user_question.func(questions=questions, runtime=runtime)

        messages = result.update["messages"]
        assert len(messages) == 1
        assert messages[0].tool_call_id == "call_456"
        assert "questions_count" in json.loads(messages[0].content)

