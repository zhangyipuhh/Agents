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
        # options 超过 5 个应被拒绝
        with pytest.raises(ValidationError):
            Question(
                question="Q?",
                header="H",
                options=[
                    {"label": f"L{i}", "description": f"d{i}"} for i in range(6)
                ],
            )

    def test_empty_options_valid(self):
        """options=[] 是合法的（纯文本问题）"""
        q = Question(question="项目名称？", header="项目", options=[])
        assert q.options == []
        assert q.text_only is False  # 默认 False

    def test_options_with_single_item_rejected(self):
        """options 非空但只有 1 个应被拒绝（强制至少 2 个）"""
        with pytest.raises(ValidationError):
            Question(
                question="Q?",
                header="H",
                options=[{"label": "Only", "description": "only one"}],
            )

    def test_text_only_field_default_false(self):
        """text_only 默认 False"""
        q = Question(
            question="Q?",
            header="H",
            options=[{"label": "A", "description": "a"}, {"label": "B", "description": "b"}],
        )
        assert q.text_only is False

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


class TestAutoInjectOther:
    """AskUserQuestionInput._inject_other_option 自动注入 Other 测试"""

    def test_other_auto_injected_for_ai_omitted(self):
        """AI 没传 Other 时自动追加到末尾"""
        from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput
        inp = AskUserQuestionInput(questions=[
            {
                "question": "用啥框架？",
                "header": "框架",
                "options": [
                    {"label": "React", "description": "JS库"},
                    {"label": "Vue", "description": "渐进式"},
                ],
            }
        ])
        labels = [o.label for o in inp.questions[0].options]
        assert labels == ["React", "Vue", "Other"]

    def test_other_not_duplicated_if_ai_provided(self):
        """AI 已传 Other 时不重复追加"""
        from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput
        inp = AskUserQuestionInput(questions=[
            {
                "question": "用啥框架？",
                "header": "框架",
                "options": [
                    {"label": "React", "description": "JS库"},
                    {"label": "Other", "description": "自己填"},
                ],
            }
        ])
        labels = [o.label for o in inp.questions[0].options]
        assert labels == ["React", "Other"]
        assert len(labels) == 2

    def test_text_only_skips_other_injection(self):
        """text_only=True 的问题不注入 Other"""
        from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput
        inp = AskUserQuestionInput(questions=[
            {
                "question": "项目名称？",
                "header": "项目",
                "options": [],
                "text_only": True,
            }
        ])
        assert inp.questions[0].options == []

    def test_empty_options_skips_other_injection_without_text_only(self):
        """options=[] 不传 text_only 也合法（不注入 Other）"""
        from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput
        inp = AskUserQuestionInput(questions=[
            {
                "question": "你的建议？",
                "header": "建议",
                "options": [],
            }
        ])
        assert inp.questions[0].options == []

    def test_mixed_questions_inject_selectively(self):
        """混合问题：text_only 不注入，有 options 的注入"""
        from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput
        inp = AskUserQuestionInput(questions=[
            {
                "question": "项目名称？",
                "header": "项目",
                "options": [],
                "text_only": True,
            },
            {
                "question": "用啥框架？",
                "header": "框架",
                "options": [
                    {"label": "React", "description": "JS库"},
                    {"label": "Vue", "description": "渐进式"},
                ],
            },
        ])
        assert inp.questions[0].options == []  # text_only
        assert [o.label for o in inp.questions[1].options] == ["React", "Vue", "Other"]  # 注入

    def test_llm_provided_4_business_plus_other_accepted(self):
        """真实场景：LLM 传 4 业务选项 + 1 Other（=5 个）应被接受且不重复"""
        from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput
        inp = AskUserQuestionInput(questions=[
            {
                "question": "请选择项目类型（可多选）",
                "header": "项目类型",
                "options": [
                    {"label": "工业用地", "description": "工业生产、制造加工类项目"},
                    {"label": "住宅用地 (Recommended)", "description": "住宅小区、公寓等居住类项目"},
                    {"label": "商业用地", "description": "商场、写字楼等商业经营类项目"},
                    {"label": "公共服务用地", "description": "学校、医院等公共服务类项目"},
                    {"label": "Other", "description": "输入自定义回答"},
                ],
                "multiple": True,
            }
        ])
        labels = [o.label for o in inp.questions[0].options]
        assert labels == [
            "工业用地", "住宅用地 (Recommended)", "商业用地",
            "公共服务用地", "Other",
        ]  # 不重复追加


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


class TestHitlCheckNode:
    """hitl_check_node 节点行为测试"""

    def _make_agent(self):
        """构造 Agent 子类用于测试（不调 __init__）"""
        from app.core.agent.agent import Agent
        agent = Agent.__new__(Agent)
        return agent

    def test_no_pending_returns_state_unchanged(self):
        """无 pending_question 时直接透传"""
        agent = self._make_agent()
        state = {"messages": [], "pending_question": None}
        runtime = MagicMock()

        result = asyncio.run(agent.hitl_check_node(state, runtime))

        assert result == state

    def test_pending_triggers_interrupt_with_correct_payload(self):
        """有 pending 时调 interrupt 并解析 answers"""
        agent = self._make_agent()

        pending = {
            "status": "pending",
            "questions": [
                {
                    "question": "Q1?",
                    "header": "H1",
                    "options": [
                        {"label": "A", "description": "a"},
                        {"label": "B", "description": "b"},
                    ],
                    "multiple": False,
                }
            ],
            "tool_call_id": "call_123",
        }
        state = {"messages": [], "pending_question": pending}
        runtime = MagicMock()

        from langchain_core.messages import HumanMessage
        import app.core.agent.agent as agent_module

        captured = {}

        def fake_interrupt(value):
            captured["payload"] = value
            return {"answers": [["A"]]}

        original_interrupt = agent_module.interrupt
        agent_module.interrupt = fake_interrupt
        try:
            result = asyncio.run(agent.hitl_check_node(state, runtime))
        finally:
            agent_module.interrupt = original_interrupt

        # 验证 interrupt payload 结构（LangGraph 新版格式）
        assert captured["payload"]["action"] == "ask_user_question"
        assert len(captured["payload"]["questions"]) == 1

        # 验证返回结构
        assert result["pending_question"] is None
        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert "A" in messages[0].content
        assert "Q1?" in messages[0].content

    def test_appends_to_question_answers_history(self):
        """question_answers 应追加新记录（用 Overwrite）"""
        agent = self._make_agent()

        pending = {
            "status": "pending",
            "questions": [
                {"question": "Q1?", "header": "H1", "options": [], "multiple": False}
            ],
            "tool_call_id": "call_x",
        }
        state = {
            "messages": [],
            "pending_question": pending,
            "question_answers": [{"old": "record"}],
        }
        runtime = MagicMock()

        from langgraph.types import Overwrite
        import app.core.agent.agent as agent_module

        def fake_interrupt(value):
            return {"answers": [["B"]]}

        original_interrupt = agent_module.interrupt
        agent_module.interrupt = fake_interrupt
        try:
            result = asyncio.run(agent.hitl_check_node(state, runtime))
        finally:
            agent_module.interrupt = original_interrupt

        # 验证 Overwrite 追加
        assert isinstance(result["question_answers"], Overwrite)
        new_list = result["question_answers"].value
        assert len(new_list) == 2
        assert new_list[0] == {"old": "record"}
        assert new_list[1]["answers"] == [["B"]]
        assert "timestamp" in new_list[1]

    def test_multiple_questions_all_recorded(self):
        """多问题场景：所有 question 都被回灌"""
        agent = self._make_agent()

        pending = {
            "status": "pending",
            "questions": [
                {"question": "框架？", "header": "框架", "options": [], "multiple": False},
                {"question": "TypeScript？", "header": "TS", "options": [], "multiple": False},
            ],
            "tool_call_id": "call_multi",
        }
        state = {"messages": [], "pending_question": pending}
        runtime = MagicMock()

        import app.core.agent.agent as agent_module

        def fake_interrupt(value):
            return {"answers": [["React"], ["Yes"]]}

        original_interrupt = agent_module.interrupt
        agent_module.interrupt = fake_interrupt
        try:
            result = asyncio.run(agent.hitl_check_node(state, runtime))
        finally:
            agent_module.interrupt = original_interrupt

        content = result["messages"][0].content
        assert "React" in content
        assert "Yes" in content
        assert "框架" in content
        assert "TypeScript" in content

    def test_unanswered_questions_marked(self):
        """用户没回答的问题标记为'未回答'"""
        agent = self._make_agent()

        pending = {
            "status": "pending",
            "questions": [
                {"question": "Q1?", "header": "H1", "options": [], "multiple": False},
                {"question": "Q2?", "header": "H2", "options": [], "multiple": False},
            ],
            "tool_call_id": "call_partial",
        }
        state = {"messages": [], "pending_question": pending}
        runtime = MagicMock()

        import app.core.agent.agent as agent_module

        def fake_interrupt(value):
            return {"answers": [["A"]]}  # 第二个未答

        original_interrupt = agent_module.interrupt
        agent_module.interrupt = fake_interrupt
        try:
            result = asyncio.run(agent.hitl_check_node(state, runtime))
        finally:
            agent_module.interrupt = original_interrupt

        content = result["messages"][0].content
        assert "A" in content
        assert "未回答" in content

