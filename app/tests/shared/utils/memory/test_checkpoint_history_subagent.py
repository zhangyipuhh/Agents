# -*- coding:utf-8 -*-
"""
CheckpointHistoryService 子智能体历史能力测试

覆盖 2026-06-16 新增能力：
    - _is_ai_message 兼容 Mock 后缀类型名匹配
    - _extract_ai_tool_call_ids 三种来源（OpenAI / Anthropic / content_blocks）
    - get_subagent_history 反查子 thread
    - merge_main_and_subagent_messages 按时序合并
    - collect_subagent_thread_ids_for_cleanup 收集子 thread_id

设计说明：
    不依赖真实 LangChain，构造动态类模拟 AIMessage/ToolMessage，
    Mock checkpointer.aget 返回可控 channel_values。
    异步测试通过 asyncio.run() 驱动（与项目其他测试一致）。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.memory.checkpoint_history import CheckpointHistoryService


# ===== Mock 消息类（type(x).__name__ 即匹配名）=====

AIMessage = type("AIMessage", (object,), {})
MockAIMessage = type("MockAIMessage", (object,), {})
HumanMessage = type("HumanMessage", (object,), {})
ToolMessage = type("ToolMessage", (object,), {})
SystemMessage = type("SystemMessage", (object,), {})


def _make_msg(type_cls, content=None, **kwargs):
    """构造一个 Mock 消息实例，type(x).__name__ == type_cls.__name__"""
    inst = type_cls.__new__(type_cls)
    inst.content = content
    for k, v in kwargs.items():
        setattr(inst, k, v)
    return inst


# ===== _is_ai_message =====

def test_is_ai_message_real_ai():
    """type(x).__name__ 为 'AIMessage' 应识别为 AI 消息"""
    msg = _make_msg(AIMessage, content="hi")
    assert CheckpointHistoryService._is_ai_message(msg) is True


def test_is_ai_message_mock_ai():
    """type(x).__name__ 为 'MockAIMessage' 仍应识别（兼容测试 Mock）"""
    msg = _make_msg(MockAIMessage, content="hi")
    assert CheckpointHistoryService._is_ai_message(msg) is True


def test_is_ai_message_human():
    """HumanMessage 不应识别为 AI"""
    msg = _make_msg(HumanMessage, content="hi")
    assert CheckpointHistoryService._is_ai_message(msg) is False


def test_is_ai_message_tool():
    """ToolMessage 不应识别为 AI"""
    msg = _make_msg(ToolMessage, content="result", tool_call_id="c1")
    assert CheckpointHistoryService._is_ai_message(msg) is False


# ===== _extract_ai_tool_call_ids =====

def test_extract_ai_tool_call_ids_openai_style():
    """OpenAI 风格：从 msg.tool_calls 提取 id 与 name"""
    msg = _make_msg(
        AIMessage,
        content="",
        tool_calls=[
            {"id": "call_001", "name": "sandbox", "args": {"prompt": "p"}},
        ],
    )
    result = CheckpointHistoryService._extract_ai_tool_call_ids(msg)
    assert result == [{"id": "call_001", "name": "sandbox"}]


def test_extract_ai_tool_call_ids_anthropic_style():
    """Anthropic 风格：从 content list 提取 type='tool_use' 块"""
    msg = _make_msg(
        AIMessage,
        content=[
            {"type": "text", "text": "thinking"},
            {"type": "tool_use", "id": "call_002", "name": "explore", "input": {}},
        ],
    )
    result = CheckpointHistoryService._extract_ai_tool_call_ids(msg)
    assert result == [{"id": "call_002", "name": "explore"}]


def test_extract_ai_tool_call_ids_content_blocks():
    """langchain-core 1.x：从 content_blocks 提取 tool_call 块"""
    msg = _make_msg(
        AIMessage,
        content="",
        content_blocks=[
            {"type": "tool_call", "id": "call_003", "name": "sandbox", "args": {}},
        ],
    )
    result = CheckpointHistoryService._extract_ai_tool_call_ids(msg)
    assert result == [{"id": "call_003", "name": "sandbox"}]


def test_extract_ai_tool_call_ids_no_calls():
    """无 tool_calls 时返回空列表"""
    msg = _make_msg(AIMessage, content="plain text")
    assert CheckpointHistoryService._extract_ai_tool_call_ids(msg) == []


# ===== get_subagent_history =====

def _make_state_with_messages(messages):
    """构造 checkpointer.aget 返回的 state 字典"""
    return {"channel_values": {"messages": messages}}


def test_get_subagent_history_success():
    """反查存在的子 thread 应返回结构化消息列表"""
    human = _make_msg(HumanMessage, content="sub prompt")
    ai = _make_msg(AIMessage, content="sub reply")
    tool = _make_msg(ToolMessage, content="tool out", tool_call_id="c1")
    cp = MagicMock()
    cp.aget = AsyncMock(return_value=_make_state_with_messages([human, ai, tool]))

    result = asyncio.run(CheckpointHistoryService.get_subagent_history(
        checkpointer=cp, tool_call_id="call_xxx", include_tool=True
    ))
    assert result["thread_id"] == "call_xxx"
    assert result["total"] == 3
    types_in_order = [m["type"] for m in result["messages"]]
    assert types_in_order == ["user", "ai", "tool"]


def test_get_subagent_history_exclude_tool():
    """include_tool=False 时 ToolMessage 应被过滤"""
    human = _make_msg(HumanMessage, content="h")
    ai = _make_msg(AIMessage, content="a")
    tool = _make_msg(ToolMessage, content="t", tool_call_id="c1")
    cp = MagicMock()
    cp.aget = AsyncMock(return_value=_make_state_with_messages([human, ai, tool]))

    result = asyncio.run(CheckpointHistoryService.get_subagent_history(
        checkpointer=cp, tool_call_id="call_xxx", include_tool=False
    ))
    assert result["total"] == 2
    assert all(m["type"] != "tool" for m in result["messages"])


def test_get_subagent_history_empty_thread_id():
    """空 thread_id 应短路返回空结果而不调用 checkpointer"""
    cp = MagicMock()
    cp.aget = AsyncMock()
    result = asyncio.run(CheckpointHistoryService.get_subagent_history(
        checkpointer=cp, tool_call_id=""
    ))
    assert result["total"] == 0
    assert result["messages"] == []
    cp.aget.assert_not_called()


def test_get_subagent_history_thread_not_exists():
    """checkpointer.aget 返回 None 时返回空结果"""
    cp = MagicMock()
    cp.aget = AsyncMock(return_value=None)
    result = asyncio.run(CheckpointHistoryService.get_subagent_history(
        checkpointer=cp, tool_call_id="missing"
    ))
    assert result["total"] == 0


# ===== collect_subagent_thread_ids_for_cleanup =====

def test_collect_subagent_thread_ids_dedup():
    """同一主 thread 下多个 AI 消息含重复 tool_call_id 应去重"""
    h = _make_msg(HumanMessage, content="h")
    ai1 = _make_msg(
        AIMessage, content="",
        tool_calls=[{"id": "call_a", "name": "sandbox"}],
    )
    ai2 = _make_msg(
        AIMessage, content="",
        tool_calls=[{"id": "call_b", "name": "explore"}],
    )
    ai3 = _make_msg(
        AIMessage, content="",
        tool_calls=[{"id": "call_a", "name": "sandbox"}],  # 重复
    )
    cp = MagicMock()
    cp.aget = AsyncMock(
        return_value=_make_state_with_messages([h, ai1, ai2, ai3])
    )

    ids = asyncio.run(CheckpointHistoryService.collect_subagent_thread_ids_for_cleanup(
        checkpointer=cp, session_id="main-1"
    ))
    assert ids == ["call_a", "call_b"]


def test_collect_subagent_thread_ids_no_calls():
    """无 tool_calls 时返回空列表"""
    h = _make_msg(HumanMessage, content="h")
    ai = _make_msg(AIMessage, content="just text")
    cp = MagicMock()
    cp.aget = AsyncMock(return_value=_make_state_with_messages([h, ai]))

    ids = asyncio.run(CheckpointHistoryService.collect_subagent_thread_ids_for_cleanup(
        checkpointer=cp, session_id="main-2"
    ))
    assert ids == []


# ===== merge_main_and_subagent_messages =====

def test_merge_with_subagent_call():
    """主消息中含 tool_call=sandbox，应在 AI 消息后插入 subagent 元素"""
    h = _make_msg(HumanMessage, content="hi")
    ai_main = _make_msg(
        AIMessage, content="ok",
        tool_calls=[{"id": "call_x", "name": "sandbox", "args": {}}],
        id="m-ai-1",
    )
    h2 = _make_msg(HumanMessage, content="thanks")
    raw = [h, ai_main, h2]
    main_dicts = [
        {"id": "m-h-1", "type": "user", "role": "user", "content": "hi"},
        {"id": "m-ai-1", "type": "ai", "role": "assistant", "content": "ok"},
        {"id": "m-h-2", "type": "user", "role": "user", "content": "thanks"},
    ]

    # 子 thread 中存有 HumanMessage + AIMessage
    sub_h = _make_msg(HumanMessage, content="sub prompt")
    sub_ai = _make_msg(AIMessage, content="sub answer")
    cp = MagicMock()
    cp.aget = AsyncMock(
        return_value=_make_state_with_messages([sub_h, sub_ai])
    )

    merged = asyncio.run(CheckpointHistoryService.merge_main_and_subagent_messages(
        checkpointer=cp,
        main_messages=main_dicts,
        raw_main_messages=raw,
    ))

    # 期望顺序：m-h-1, m-ai-1, subagent(call_x), m-h-2
    assert len(merged) == 4
    assert merged[0]["id"] == "m-h-1"
    assert merged[1]["id"] == "m-ai-1"
    assert merged[2]["type"] == "subagent"
    assert merged[2]["thread_id"] == "call_x"
    assert merged[2]["tool"] == "sandbox"
    assert merged[2]["parent_message_id"] == "m-ai-1"
    assert len(merged[2]["messages"]) == 2
    assert merged[3]["id"] == "m-h-2"


def test_merge_no_subagent():
    """主消息无 tool_call 时不插入 subagent 元素"""
    h = _make_msg(HumanMessage, content="hi")
    ai = _make_msg(AIMessage, content="ok", id="m-1")
    raw = [h, ai]
    main_dicts = [
        {"id": "m-h", "type": "user", "role": "user", "content": "hi"},
        {"id": "m-1", "type": "ai", "role": "assistant", "content": "ok"},
    ]
    cp = MagicMock()
    cp.aget = AsyncMock()

    merged = asyncio.run(CheckpointHistoryService.merge_main_and_subagent_messages(
        checkpointer=cp, main_messages=main_dicts, raw_main_messages=raw
    ))
    assert merged == main_dicts
    cp.aget.assert_not_called()


def test_merge_main_dict_only_no_raw():
    """raw_main_messages 为 None 时仅返回 main_messages"""
    main_dicts = [
        {"id": "m-h", "type": "user", "role": "user", "content": "hi"},
    ]
    cp = MagicMock()
    cp.aget = AsyncMock()

    merged = asyncio.run(CheckpointHistoryService.merge_main_and_subagent_messages(
        checkpointer=cp, main_messages=main_dicts, raw_main_messages=None
    ))
    assert merged == main_dicts
    cp.aget.assert_not_called()


# ===== 2026-06-16 修复：非子智能体工具 tool_call 过滤 =====

def test_merge_filters_non_subagent_tool_calls():
    """
    主消息同时含 sandbox + generate_report 两个 tool_call，
    仅 sandbox 产生 subagent 元素，generate_report 被过滤。
    防回归：用户报告 generate_report 被误包装为 type:"subagent"。
    """
    h = _make_msg(HumanMessage, content="hi")
    # 同一 AIMessage 含两个 tool_call（混用子智能体与普通工具）
    ai_main = _make_msg(
        AIMessage, content="",
        tool_calls=[
            {"id": "call_sb", "name": "sandbox", "args": {}},
            {"id": "call_gr", "name": "generate_report", "args": {}},
        ],
        id="m-ai-1",
    )
    h2 = _make_msg(HumanMessage, content="thanks")
    raw = [h, ai_main, h2]
    main_dicts = [
        {"id": "m-h-1", "type": "user", "role": "user", "content": "hi"},
        {"id": "m-ai-1", "type": "ai", "role": "assistant", "content": ""},
        {"id": "m-h-2", "type": "user", "role": "user", "content": "thanks"},
    ]

    # 子 thread 状态（仅 sandbox 对应的子 thread 有数据；generate_report 无子 thread）
    sub_state = {
        "channel_values": {
            "messages": [
                _make_msg(HumanMessage, content="sub prompt"),
                _make_msg(AIMessage, content="sub answer"),
            ]
        }
    }
    cp = MagicMock()
    cp.aget = AsyncMock(return_value=sub_state)

    merged = asyncio.run(CheckpointHistoryService.merge_main_and_subagent_messages(
        checkpointer=cp, main_messages=main_dicts, raw_main_messages=raw
    ))

    # 期望顺序：m-h-1, m-ai-1, subagent(call_sb), m-h-2
    # generate_report 被过滤，不产生 subagent 元素
    assert len(merged) == 4, f"期望 4 条，实际 {len(merged)}：{merged}"
    assert merged[0]["id"] == "m-h-1"
    assert merged[1]["id"] == "m-ai-1"
    assert merged[2]["type"] == "subagent"
    assert merged[2]["thread_id"] == "call_sb"
    assert merged[2]["tool"] == "sandbox"
    # 关键断言：merged 中不应存在 generate_report 对应的 subagent 元素
    subagent_thread_ids = [m.get("thread_id") for m in merged if m.get("type") == "subagent"]
    assert "call_gr" not in subagent_thread_ids, "generate_report 不应产生 subagent 元素"
    assert merged[3]["id"] == "m-h-2"


def test_merge_only_generate_report_no_subagent():
    """
    主消息仅含 generate_report tool_call 时，不应产生任何 subagent 元素。
    防回归：原实现会把所有 tool_call 包成 type:"subagent"。
    """
    h = _make_msg(HumanMessage, content="hi")
    ai = _make_msg(
        AIMessage, content="ok",
        tool_calls=[{"id": "call_gr_only", "name": "generate_report", "args": {}}],
        id="m-1",
    )
    raw = [h, ai]
    main_dicts = [
        {"id": "m-h", "type": "user", "role": "user", "content": "hi"},
        {"id": "m-1", "type": "ai", "role": "assistant", "content": "ok"},
    ]
    cp = MagicMock()
    cp.aget = AsyncMock()

    merged = asyncio.run(CheckpointHistoryService.merge_main_and_subagent_messages(
        checkpointer=cp, main_messages=main_dicts, raw_main_messages=raw
    ))

    # 关键断言：不应有任何 subagent 元素
    assert len(merged) == 2
    assert all(m.get("type") != "subagent" for m in merged), "普通工具不应产生 subagent 元素"
    # 也不应调用 checkpointer.aget（没必要反查）
    cp.aget.assert_not_called()


def test_collect_subagent_thread_ids_filters_non_subagent():
    """
    collect_subagent_thread_ids_for_cleanup 同样按 is_subagent_tool 过滤，
    仅收集 sandbox / explore 等子智能体工具的 thread_id。
    防回归：删除会话时不应尝试清理普通工具的 tool_call_id。
    """
    h = _make_msg(HumanMessage, content="h")
    # 主消息同时含 sandbox + generate_report + explore
    ai = _make_msg(
        AIMessage, content="",
        tool_calls=[
            {"id": "call_sb", "name": "sandbox"},
            {"id": "call_gr", "name": "generate_report"},
            {"id": "call_ex", "name": "explore"},
        ],
    )
    cp = MagicMock()
    cp.aget = AsyncMock(
        return_value=_make_state_with_messages([h, ai])
    )

    ids = asyncio.run(CheckpointHistoryService.collect_subagent_thread_ids_for_cleanup(
        checkpointer=cp, session_id="main-x"
    ))

    # 关键断言：generate_report 不在清理列表中
    assert "call_sb" in ids
    assert "call_ex" in ids
    assert "call_gr" not in ids, f"generate_report 不应被收集清理：{ids}"
    assert len(ids) == 2
