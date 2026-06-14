# -*- coding:utf-8 -*-
"""
subagent_message_extractor 单元测试

覆盖：
    - HumanMessage / AIMessage / ToolMessage / 未知类型的结构化提取
    - AIMessage 的 tool_calls 三种来源（OpenAI / Anthropic / content_blocks）
    - ToolMessage 的 tool_call_id / name 提取
    - 边界条件：空列表、None、解析失败的容错

设计说明：
    通过 type() 在模块级动态构造多种 Mock 类，每个类名即 type(msg).__name__，
    模拟 LangChain BaseMessage 派生的多种类型（包括 MockHumanMessage 等）。
"""
from types import SimpleNamespace

from app.core.tools.subagent_message_extractor import (
    extract_structured_messages,
    _classify_role,
    _normalize_content,
    _extract_tool_calls_from_ai,
)


# 模块级动态构造的 Mock 消息类（每个类名即 type(msg).__name__）
HumanMessage = type("HumanMessage", (object,), {})
AIMessage = type("AIMessage", (object,), {})
ToolMessage = type("ToolMessage", (object,), {})
SystemMessage = type("SystemMessage", (object,), {})
MockHumanMessage = type("MockHumanMessage", (object,), {})
MockAIMessage = type("MockAIMessage", (object,), {})
MockToolMessage = type("MockToolMessage", (object,), {})
WeirdMessage = type("WeirdMessage", (object,), {})


def _make(type_cls, content=None, **kwargs):
    """构造一个 Mock 消息实例"""
    inst = type_cls.__new__(type_cls)
    inst.content = content
    for k, v in kwargs.items():
        setattr(inst, k, v)
    return inst


# ===== _classify_role =====

def test_classify_role_known_types():
    """_classify_role 对已知类型应返回正确 role"""
    assert _classify_role("HumanMessage") == "user"
    assert _classify_role("AIMessage") == "ai"
    assert _classify_role("ToolMessage") == "tool"
    assert _classify_role("SystemMessage") == "system"
    assert _classify_role("MockHumanMessage") == "user"
    assert _classify_role("MockAIMessage") == "ai"


def test_classify_role_unknown_returns_unknown():
    """_classify_role 对未知类型返回 'unknown'"""
    assert _classify_role("WeirdMessage") == "unknown"
    assert _classify_role("") == "unknown"


# ===== _normalize_content =====

def test_normalize_content_string_passthrough():
    """字符串 content 应原样返回"""
    assert _normalize_content("hello") == "hello"


def test_normalize_content_none_to_empty_string():
    """None content 应转为空字符串"""
    assert _normalize_content(None) == ""


def test_normalize_content_list_preserves_structure():
    """list content 应保留结构不强制 join"""
    content = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
    assert _normalize_content(content) == content


def test_normalize_content_dict_preserves_structure():
    """dict content 应原样返回"""
    content = {"type": "text", "text": "hi"}
    assert _normalize_content(content) == content


def test_normalize_content_other_type_stringified():
    """其它类型调用 str() 兜底"""
    assert _normalize_content(42) == "42"


# ===== _extract_tool_calls_from_ai =====

def test_extract_tool_calls_from_ai_openai_style():
    """OpenAI 风格：从 msg.tool_calls 提取"""
    msg = SimpleNamespace(
        tool_calls=[{"name": "ls", "args": {"path": "/tmp"}, "id": "call_1"}]
    )
    result = _extract_tool_calls_from_ai(msg)
    assert result == [{"name": "ls", "args": {"path": "/tmp"}, "id": "call_1"}]


def test_extract_tool_calls_from_ai_anthropic_style_content():
    """Anthropic 风格：从 msg.content list 中提取 type='tool_use'"""
    msg = SimpleNamespace(
        tool_calls=[],
        content=[{"type": "text", "text": "thinking..."},
                 {"type": "tool_use", "name": "read_file",
                  "input": {"file_path": "/a.txt"}, "id": "toolu_1"}],
    )
    result = _extract_tool_calls_from_ai(msg)
    assert len(result) == 1
    assert result[0]["name"] == "read_file"
    assert result[0]["args"] == {"file_path": "/a.txt"}


def test_extract_tool_calls_from_ai_content_blocks():
    """langchain-core 1.x：msg.content_blocks 中 type='tool_call'/'non_standard'"""
    msg = SimpleNamespace(
        tool_calls=[],
        content=[],
        content_blocks=[
            {"type": "tool_call", "name": "write_file", "args": {"p": "/x"}, "id": "cb_1"},
            {"type": "non_standard", "value": {"type": "tool_use", "name": "execute",
                                                "input": {"cmd": "ls"}, "id": "ns_1"}},
        ],
    )
    result = _extract_tool_calls_from_ai(msg)
    assert len(result) == 2
    names = {r["name"] for r in result}
    assert names == {"write_file", "execute"}


def test_extract_tool_calls_from_ai_empty():
    """无 tool_calls / content / content_blocks 时返回空列表"""
    msg = SimpleNamespace(to_calls=None, content="", content_blocks=None)
    result = _extract_tool_calls_from_ai(msg)
    assert result == []


# ===== extract_structured_messages =====

def test_extract_structured_messages_empty():
    """空入参返回空列表"""
    assert extract_structured_messages([]) == []
    assert extract_structured_messages(None) == []


def test_extract_structured_messages_skip_none():
    """消息列表中含 None 时跳过"""
    result = extract_structured_messages([None, None])
    assert result == []


def test_extract_structured_messages_human():
    """HumanMessage 应归类为 user role"""
    h = _make(HumanMessage, content="hello")
    result = extract_structured_messages([h])
    assert len(result) == 1
    assert result[0]["type"] == "HumanMessage"
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "hello"


def test_extract_structured_messages_ai_with_tool_calls():
    """AIMessage 含 tool_calls 时应提取"""
    a = _make(AIMessage, content="thinking")
    a.tool_calls = [{"name": "ls", "args": {"p": "/tmp"}, "id": "c1"}]

    result = extract_structured_messages([a])
    assert len(result) == 1
    assert result[0]["type"] == "AIMessage"
    assert result[0]["role"] == "ai"
    assert result[0]["tool_calls"] == [{"name": "ls", "args": {"p": "/tmp"}, "id": "c1"}]


def test_extract_structured_messages_ai_with_anthropic_tool_use():
    """AIMessage Anthropic 风格：content 中含 type='tool_use' 块"""
    a = _make(AIMessage, content=[
        {"type": "text", "text": "thinking"},
        {"type": "tool_use", "name": "execute", "input": {"cmd": "ls"}, "id": "tu_1"},
    ])
    result = extract_structured_messages([a])
    assert len(result) == 1
    assert len(result[0]["tool_calls"]) == 1
    assert result[0]["tool_calls"][0]["name"] == "execute"


def test_extract_structured_messages_tool():
    """ToolMessage 应提取 tool_call_id 和 name"""
    t = _make(ToolMessage, content="result data")
    t.tool_call_id = "call_42"
    t.name = "ls"

    result = extract_structured_messages([t])
    assert len(result) == 1
    assert result[0]["type"] == "ToolMessage"
    assert result[0]["role"] == "tool"
    assert result[0]["content"] == "result data"
    assert result[0]["tool_call_id"] == "call_42"
    assert result[0]["name"] == "ls"


def test_extract_structured_messages_unknown_type_fallback():
    """未知类型应降级为 Unknown 条目（type 字段保留原类名，role='unknown'）"""
    w = _make(WeirdMessage, content="x")
    result = extract_structured_messages([w])
    assert len(result) == 1
    assert result[0]["type"] == "WeirdMessage"
    assert result[0]["role"] == "unknown"


def test_extract_structured_messages_mixed_types():
    """混合类型列表应按顺序处理"""
    h = _make(HumanMessage, content="hi")
    a = _make(AIMessage, content="hello")
    t = _make(ToolMessage, content="result")
    t.tool_call_id = "c1"
    t.name = "ls"

    result = extract_structured_messages([h, a, t])
    assert len(result) == 3
    assert [r["role"] for r in result] == ["user", "ai", "tool"]
    assert result[2]["tool_call_id"] == "c1"


def test_extract_structured_messages_content_list_preserved():
    """content 为 list[ContentBlock] 时结构保留"""
    a = _make(AIMessage, content=[
        {"type": "text", "text": "x"},
        {"type": "thinking", "thinking": "y"},
    ])

    result = extract_structured_messages([a])
    assert isinstance(result[0]["content"], list)
    assert len(result[0]["content"]) == 2


def test_extract_structured_messages_mock_human():
    """Mock 后缀类型也应被识别（_classify_role 兼容）"""
    m = _make(MockHumanMessage, content="mock hi")
    result = extract_structured_messages([m])
    assert result[0]["type"] == "MockHumanMessage"
    assert result[0]["role"] == "user"


def test_extract_structured_messages_skips_unparseable_via_str_fallback():
    """单条消息解析失败时应降级为 Unknown（用 str() 兜底）"""
    class BadMessage:
        """content 访问会抛异常的对象"""

        @property
        def content(self):
            raise RuntimeError("boom")

    bad = BadMessage()
    result = extract_structured_messages([bad])
    # 解析失败但 str() 也失败时会跳过该条（返回空列表）
    # 因为 str(bad) 不抛异常，所以会生成 Unknown 条目
    assert len(result) == 1
    assert result[0]["type"] == "Unknown"
    assert result[0]["role"] == "unknown"
