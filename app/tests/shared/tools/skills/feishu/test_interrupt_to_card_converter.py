# -*- coding:utf-8 -*-
"""
InterruptToCardConverter 单元测试

覆盖：
    - 导入存在性
    - to_interactive_card：单题单选 / 多题 / 按钮 value 携带 session_id+chat_id
    - options=[] 退化
    - multiSelect 退化为单选
    - 选项数超过上限被截断
    - parse_card_action_value 解析 dict / JSON 字符串 / 失败
"""
import pytest

from app.shared.tools.skills.feishu.InterruptToCardConverter import (
    InterruptToCardConverter,
    parse_card_action_value,
)


SID = "feishu:p2p:ou_alice"
CHAT_ID = "oc_chat_001"


# ---------------------------------------------------------------------------
# P0 导入/存在性
# ---------------------------------------------------------------------------
def test_InterruptToCardConverter_importable():
    """P0：模块可正常导入。"""
    assert InterruptToCardConverter is not None


# ---------------------------------------------------------------------------
# P1 to_interactive_card 单题单选
# ---------------------------------------------------------------------------
def test_to_interactive_card_single_question_single_select():
    """P1：1 题 3 选项 → 3 按钮 + 1 "其他"按钮，共 4 个。"""
    req = {
        "action": "ask_user_question",
        "questions": [
            {
                "question": "你想用哪种方案？",
                "options": [
                    {"label": "A 方案"},
                    {"label": "B 方案"},
                    {"label": "C 方案"},
                ],
                "multiSelect": False,
            }
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)

    assert card["config"]["wide_screen_mode"] is True
    elements = card["body"]["elements"]
    # 第一个元素：题目 markdown
    assert elements[0]["tag"] == "markdown"
    assert "Q1:" in elements[0]["content"]
    assert "你想用哪种方案" in elements[0]["content"]
    assert "单选" in elements[0]["content"]
    # 第二个元素：action 容器（含按钮）
    assert elements[1]["tag"] == "action"
    actions = elements[1]["actions"]
    assert len(actions) == 4  # 3 选项 + "其他"
    assert actions[0]["tag"] == "button"
    assert actions[0]["type"] == "primary"
    assert actions[0]["text"]["content"] == "A 方案"
    assert actions[1]["text"]["content"] == "B 方案"
    assert actions[2]["text"]["content"] == "C 方案"
    assert "其他" in actions[3]["text"]["content"]


# ---------------------------------------------------------------------------
# P1 多题
# ---------------------------------------------------------------------------
def test_to_interactive_card_multi_questions():
    """P1：2 题 → 2 个 markdown 题目 + 2 个 action 容器 + 1 个 hr 分隔。"""
    req = {
        "action": "ask_user_question",
        "questions": [
            {
                "question": "Q1 text",
                "options": [{"label": "1a"}, {"label": "1b"}],
                "multiSelect": False,
            },
            {
                "question": "Q2 text",
                "options": [{"label": "2a"}],
                "multiSelect": True,
            },
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)
    elements = card["body"]["elements"]
    # 期望：[q1_md, q1_action, hr, q2_md, q2_action]
    tags = [e["tag"] for e in elements]
    assert "markdown" in tags
    assert "action" in tags
    assert "hr" in tags
    # Q2 是多选，markdown 元素含"多选"
    md_elems = [e for e in elements if e["tag"] == "markdown"]
    assert any("多选" in e["content"] for e in md_elems)
    assert any("单选" in e["content"] for e in md_elems)


# ---------------------------------------------------------------------------
# P1 按钮 value 携带 session_id + chat_id
# ---------------------------------------------------------------------------
def test_to_interactive_card_button_value_carries_session_id_and_chat_id():
    """P1：每个按钮 value 含 session_id / chat_id / qid / oid / action。"""
    req = {
        "action": "ask_user_question",
        "questions": [
            {
                "question": "Q1",
                "options": [{"label": "A"}, {"label": "B"}],
                "multiSelect": False,
            }
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)
    actions = card["body"]["elements"][1]["actions"]
    for oid, action in enumerate(actions[:2]):
        assert action["value"]["action"] == "hitl_answer"
        assert action["value"]["session_id"] == SID
        assert action["value"]["chat_id"] == CHAT_ID
        assert action["value"]["qid"] == 0
        assert action["value"]["oid"] == oid


# ---------------------------------------------------------------------------
# P2 options=[] 退化
# ---------------------------------------------------------------------------
def test_to_interactive_card_options_count_zero():
    """P2：options=[] → 走文本提示卡片，仅 1 个 markdown 元素。"""
    req = {
        "action": "ask_user_question",
        "questions": [
            {"question": "Q?", "options": [], "multiSelect": False}
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)
    elements = card["body"]["elements"]
    # 仅 markdown（题目） + action（只有"其他"按钮）
    md_elems = [e for e in elements if e["tag"] == "markdown"]
    assert any("Q?" in e["content"] for e in md_elems)
    action_elems = [e for e in elements if e["tag"] == "action"]
    # options=[] 时仍添加"其他"按钮
    assert len(action_elems) == 1
    assert len(action_elems[0]["actions"]) == 1


def test_to_interactive_card_no_questions_fallback():
    """P2：questions=[] → 退化到"（暂无可回答的问题）"占位。"""
    req = {"action": "ask_user_question", "questions": []}
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)
    elements = card["body"]["elements"]
    assert len(elements) == 1
    assert "无可回答" in elements[0]["content"]


def test_to_interactive_card_none_request_fallback():
    """P2：request=None → 不抛异常。"""
    card = InterruptToCardConverter.to_interactive_card(None, SID, CHAT_ID)
    elements = card["body"]["elements"]
    assert len(elements) == 1
    assert "无可回答" in elements[0]["content"]


# ---------------------------------------------------------------------------
# P2 multiSelect 退化
# ---------------------------------------------------------------------------
def test_to_interactive_card_multiselect_rendered_as_select_hint():
    """P2：multiSelect=true 时 markdown 元素标注"多选"，按钮仍按单选实现。"""
    req = {
        "action": "ask_user_question",
        "questions": [
            {
                "question": "选多个",
                "options": [{"label": "X"}, {"label": "Y"}],
                "multiSelect": True,
            }
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)
    md_elems = [e for e in card["body"]["elements"] if e["tag"] == "markdown"]
    assert any("多选" in e["content"] for e in md_elems)
    # 按钮仍按单选实现（每个选项 1 个按钮 + 其他）
    actions = [
        e for e in card["body"]["elements"] if e["tag"] == "action"
    ][0]["actions"]
    assert len(actions) == 3


# ---------------------------------------------------------------------------
# P2 选项数超过上限
# ---------------------------------------------------------------------------
def test_to_interactive_card_truncates_excess_options():
    """P2：>5 个选项 → 前 5 个保留并追加截断提示。"""
    options = [{"label": f"opt{i}"} for i in range(8)]
    req = {
        "action": "ask_user_question",
        "questions": [
            {"question": "Q", "options": options, "multiSelect": False}
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(req, SID, CHAT_ID)
    elements = card["body"]["elements"]
    action_elems = [e for e in elements if e["tag"] == "action"]
    assert len(action_elems) == 1
    # 5 个选项 + "其他" = 6
    assert len(action_elems[0]["actions"]) == 6
    # 截断提示存在
    md_elems = [e for e in elements if e["tag"] == "markdown"]
    assert any("省略" in e["content"] for e in md_elems)


# ---------------------------------------------------------------------------
# P2 自定义 header_title
# ---------------------------------------------------------------------------
def test_to_interactive_card_custom_header_title():
    """P2：自定义 header_title 生效（HITL 卡片默认 template=orange）。"""
    req = {
        "action": "ask_user_question",
        "questions": [
            {"question": "Q", "options": [{"label": "A"}], "multiSelect": False}
        ],
    }
    card = InterruptToCardConverter.to_interactive_card(
        req, SID, CHAT_ID, header_title="🤖 请确认"
    )
    assert card["schema"] == "2.0"
    assert card["header"]["template"] == "orange"
    assert card["header"]["title"]["content"] == "🤖 请确认"
    assert "card" not in card  # v2.0 schema 不再有外层 card


# ---------------------------------------------------------------------------
# P1 parse_card_action_value
# ---------------------------------------------------------------------------
def test_parse_card_action_value_dict():
    """P1：入参为 dict 直接返回。"""
    v = {"action": "hitl_answer", "qid": 0, "oid": 1}
    assert parse_card_action_value(v) == v


def test_parse_card_action_value_json_string():
    """P1：入参为 JSON 字符串时解析。"""
    raw = '{"action":"hitl_answer","qid":1,"oid":2}'
    parsed = parse_card_action_value(raw)
    assert parsed == {"action": "hitl_answer", "qid": 1, "oid": 2}


def test_parse_card_action_value_invalid_returns_none():
    """P1：非法 JSON 返回 None。"""
    assert parse_card_action_value("not-json") is None
    assert parse_card_action_value(None) is None
    assert parse_card_action_value(12345) is None