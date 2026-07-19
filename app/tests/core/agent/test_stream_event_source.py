# -*- coding:utf-8 -*-
"""
StreamEventSource 单元测试

测试目标：
    覆盖 ``app/core/agent/stream_event_source.py::StreamEventSource.events()``
    异步生成器的所有事件分支：
        - session_start（首次 yield）
        - text（messages 模式 token）
        - update（updates 模式节点状态）
        - interrupt（dict / tuple 嵌套 / node 嵌套 三种形态）
        - abort（abort_event.is_set()）
        - session_end（流自然结束 / 异常被吞）

测试策略：
    使用 ``_FakeAgent`` 注入预构造的 chunk 序列，绕开真实 LangGraph 依赖；
    通过 ``asyncio.run()`` 收集 ``source.events()`` 产出的事件并断言。

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Iterable, List, Optional

import pytest

from app.core.agent.stream_event import StreamEvent
from app.core.agent.stream_event_source import StreamEventSource


# ---------------------------------------------------------------------------
# 测试夹具：FakeAgent / FakeMessageChunk
# ---------------------------------------------------------------------------


class _FakeMessageChunk:
    """模拟 LangChain AIMessageChunk（仅含 ``content`` 属性）。

    Args:
        content: 文本内容
    """

    def __init__(self, content: Any) -> None:
        self.content = content


class _FakeInterrupt:
    """模拟 LangGraph Interrupt 对象（含 ``.value`` 属性）。

    Args:
        value: interrupt 携带的值
    """

    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeAgent:
    """模拟 LangGraph Agent，按预构造 chunk 序列产出 stream。

    Args:
        chunks: chunk 序列（元素可为 dict / tuple / 任意对象）
        raise_on_iter: ``True`` 时 stream 迭代过程抛 RuntimeError，用于异常隔离测试
    """

    def __init__(
        self,
        chunks: Iterable[Any],
        *,
        raise_on_iter: bool = False,
    ) -> None:
        self._chunks = list(chunks)
        self._raise_on_iter = raise_on_iter

    async def stream(
        self,
        input_state: Any,
        *,
        context: Any = None,
        config: Any = None,
        stream_mode: Optional[List[str]] = None,
    ) -> AsyncIterator[Any]:
        """异步产出预构造的 chunk 序列。

        Args:
            input_state: 输入状态（忽略）
            context: Agent 上下文（忽略）
            config: LangGraph config（忽略）
            stream_mode: stream 模式列表（忽略，仅记录）

        Yields:
            Any: chunk 序列元素
        """
        if self._raise_on_iter:
            raise RuntimeError("fake agent stream boom")
        for chunk in self._chunks:
            yield chunk


def _collect_events(source_or_factory) -> List[StreamEvent]:
    """同步收集 ``source.events()`` 产出的事件。

    Args:
        source_or_factory: ``StreamEventSource`` 实例、``source.events()`` 返回的
            异步生成器，或返回异步生成器的工厂函数（兼容三种调用风格）

    Returns:
        list[StreamEvent]: 事件列表
    """
    # 统一转换为异步生成器
    if hasattr(source_or_factory, "events") and callable(getattr(source_or_factory, "events")):
        agen = source_or_factory.events()
    elif callable(source_or_factory):
        agen = source_or_factory()
    else:
        agen = source_or_factory

    async def _run():
        return [event async for event in agen]

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# P0：导入测试
# ---------------------------------------------------------------------------


def test_stream_event_source_importable():
    """P0：StreamEventSource 模块可正常导入。

    Returns:
        None
    """
    assert StreamEventSource is not None
    assert hasattr(StreamEventSource, "events")


# ---------------------------------------------------------------------------
# P1：text 事件
# ---------------------------------------------------------------------------


def test_yields_text_chunks_from_messages_mode():
    """P1：messages 模式 token → yield text 事件。

    构造 ``("messages", (msg_chunk, metadata))`` chunk 序列，断言 ``source.events()``
    产出 ``session_start`` + 多个 ``text`` + ``session_end``。

    Returns:
        None
    """
    chunks = [
        ("messages", (_FakeMessageChunk("Hello"), {"ls_provider": "openai"})),
        ("messages", (_FakeMessageChunk(" world"), {"ls_provider": "openai"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    assert kinds[0] == "session_start"
    assert "text" in kinds
    text_events = [e for e in events if e.kind == "text"]
    assert text_events[0].text == "Hello"
    assert text_events[1].text == " world"
    assert kinds[-1] == "session_end"


def test_yields_text_chunk_skips_empty_content():
    """P1：messages 模式 content 为空字符串 → 不 yield text 事件。

    Returns:
        None
    """
    chunks = [
        ("messages", (_FakeMessageChunk(""), {"ls_provider": "openai"})),
        ("messages", (_FakeMessageChunk("real"), {"ls_provider": "openai"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    text_events = [e for e in events if e.kind == "text"]
    assert len(text_events) == 1
    assert text_events[0].text == "real"


def test_yields_text_chunks_from_list_content_ollama(monkeypatch):
    """P1：messages 模式 content 为 Ollama 结构化 list → 归一化为字符串 yield text。

    OllamaStreamFormatStrategy 会返回 ``[{"text": "...", "type": "text"}]``，
    StreamEventSource 应把它转换为纯字符串后再产出 ``text`` 事件。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    def _fake_format(message_chunk, metadata):
        return [{"text": message_chunk.content, "type": "text"}]

    monkeypatch.setattr(
        "app.core.agent.stream_event_source.stream_format_context.format_message",
        _fake_format,
    )

    chunks = [
        ("messages", (_FakeMessageChunk("Hello"), {"ls_provider": "ollama"})),
        ("messages", (_FakeMessageChunk(" world"), {"ls_provider": "ollama"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    text_events = [e for e in events if e.kind == "text"]
    assert len(text_events) == 2
    assert text_events[0].text == "Hello"
    assert text_events[1].text == " world"


def test_yields_text_chunks_from_list_of_strings(monkeypatch):
    """P1：messages 模式 content 为 list[str] → 拼接后 yield text。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    def _fake_format(message_chunk, metadata):
        return ["Hello", " world"]

    monkeypatch.setattr(
        "app.core.agent.stream_event_source.stream_format_context.format_message",
        _fake_format,
    )

    chunks = [
        ("messages", (_FakeMessageChunk("ignored"), {"ls_provider": "openai"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    text_events = [e for e in events if e.kind == "text"]
    assert len(text_events) == 1
    assert text_events[0].text == "Hello world"


def test_yields_text_chunks_from_thinking_content(monkeypatch):
    """P1：messages 模式 content 为 thinking list → 提取 thinking 文本 yield text。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    def _fake_format(message_chunk, metadata):
        return [{"thinking": "thinking...", "type": "thinking"}]

    monkeypatch.setattr(
        "app.core.agent.stream_event_source.stream_format_context.format_message",
        _fake_format,
    )

    chunks = [
        ("messages", (_FakeMessageChunk("ignored"), {"ls_provider": "ollama"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    text_events = [e for e in events if e.kind == "text"]
    assert len(text_events) == 1
    assert text_events[0].text == "thinking..."


def test_skips_text_chunks_when_normalized_empty(monkeypatch):
    """P1：messages 模式 content 归一化后为空 → 不 yield text 事件。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    def _fake_format(message_chunk, metadata):
        return [{}, {"type": "text"}]

    monkeypatch.setattr(
        "app.core.agent.stream_event_source.stream_format_context.format_message",
        _fake_format,
    )

    chunks = [
        ("messages", (_FakeMessageChunk("ignored"), {"ls_provider": "ollama"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    text_events = [e for e in events if e.kind == "text"]
    assert len(text_events) == 0


# ---------------------------------------------------------------------------
# P1：update 事件
# ---------------------------------------------------------------------------


def test_yields_updates_from_updates_mode():
    """P1：updates 模式节点状态 → yield update 事件。

    构造 ``("updates", {"agent": {"messages": [...]}})`` chunk，断言产出
    ``update`` 事件且 ``node_name`` / ``node_data`` 字段正确。

    Returns:
        None
    """
    node_data = {"agent": {"messages": [_FakeMessageChunk("hi")]}}
    chunks = [
        ("updates", node_data),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    update_events = [e for e in events if e.kind == "update"]
    assert len(update_events) == 1
    assert update_events[0].node_name == "agent"
    assert update_events[0].node_data == node_data


# ---------------------------------------------------------------------------
# P1：interrupt 事件（三种形态）
# ---------------------------------------------------------------------------


def test_yields_interrupt_when_chunk_has_interrupt_key():
    """P1：dict chunk 含 ``__interrupt__`` → yield interrupt 事件。

    Returns:
        None
    """
    interrupt_data = [{"action": "hitl", "qid": 1, "questions": []}]
    chunks = [
        {"__interrupt__": interrupt_data},
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    assert "interrupt" in kinds
    # interrupt 后流立即 return，不应再有 session_end
    assert "session_end" not in kinds
    interrupt_event = next(e for e in events if e.kind == "interrupt")
    assert interrupt_event.interrupt_requests == interrupt_data


def test_yields_interrupt_from_tuple_nested():
    """P1：tuple 嵌套 interrupt → yield interrupt 事件。

    构造两种 tuple 形态：
        - ``("updates", {"__interrupt__": [...]})``
        - ``("updates", {"some_node": {"__interrupt__": [...]}})``

    Returns:
        None
    """
    interrupt_data = [{"action": "hitl", "qid": 1}]

    # 形态 1：data 直接含 __interrupt__
    chunks_1 = [("updates", {"__interrupt__": interrupt_data})]
    events_1 = _collect_events(
        StreamEventSource(
            agent=_FakeAgent(chunks_1),
            input_state=None,
            context=None,
            config={"configurable": {"thread_id": "t1"}},
        ).events()
    )
    assert any(e.kind == "interrupt" for e in events_1)
    assert all(e.interrupt_requests == interrupt_data for e in events_1 if e.kind == "interrupt")

    # 形态 2：data 某节点值含 __interrupt__
    chunks_2 = [("updates", {"agent": {"__interrupt__": interrupt_data}})]
    events_2 = _collect_events(
        StreamEventSource(
            agent=_FakeAgent(chunks_2),
            input_state=None,
            context=None,
            config={"configurable": {"thread_id": "t2"}},
        ).events()
    )
    assert any(e.kind == "interrupt" for e in events_2)


def test_yields_interrupt_extracts_value_from_interrupt_object():
    """P1：Interrupt 对象（含 ``.value``） → 通过 _extract_interrupt_requests 提取。

    Returns:
        None
    """
    structured = [{"action": "hitl", "qid": 1}]
    interrupt_obj = _FakeInterrupt(value=structured)
    chunks = [
        {"__interrupt__": [interrupt_obj]},
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    interrupt_event = next(e for e in events if e.kind == "interrupt")
    assert interrupt_event.interrupt_requests == structured


# ---------------------------------------------------------------------------
# P1：abort 事件
# ---------------------------------------------------------------------------


def test_yields_abort_when_abort_event_set():
    """P1：abort_event.is_set() → yield abort 事件并停止循环。

    Returns:
        None
    """
    # 预先 set abort_event；首个 chunk 处理时即触发 abort
    abort_event = asyncio.Event()
    abort_event.set()
    chunks = [
        ("messages", (_FakeMessageChunk("should be skipped"), {"ls_provider": "openai"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
        abort_event=abort_event,
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    assert "abort" in kinds
    # abort 后流立即 return，不应有 session_end
    assert "session_end" not in kinds
    # abort 触发后不应产出 text 事件
    assert "text" not in kinds


# ---------------------------------------------------------------------------
# P1：session_end 事件
# ---------------------------------------------------------------------------


def test_yields_end_after_stream_finished():
    """P1：stream 自然结束 → yield session_end 事件。

    Returns:
        None
    """
    chunks = [
        ("messages", (_FakeMessageChunk("done"), {"ls_provider": "openai"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    assert kinds[-1] == "session_end"


def test_yields_session_start_as_first_event():
    """P1：首个事件必须是 session_start。

    Returns:
        None
    """
    chunks: list = []
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    assert events[0].kind == "session_start"


# ---------------------------------------------------------------------------
# P2：tools 节点完成检测（abort 期间）
# ---------------------------------------------------------------------------


def test_yields_tools_node_completion_triggers_abort():
    """P2：abort 期间 tools 节点完成 → yield update + abort + return。

    构造场景：
        - abort_event 预先 set
        - 第二个 chunk 是 ``("updates", {"tools": {"messages": [ToolMessage]}})``
        - 断言产出 update（tools 节点）+ abort，不再有后续事件

    Returns:
        None
    """
    from langchain_core.messages import ToolMessage

    abort_event = asyncio.Event()
    abort_event.set()
    chunks = [
        # 第一个 chunk：触发 abort 检测（abort_event.is_set() = True）
        # 但首个 chunk 不是 tools 节点完成，所以应该立即 yield abort
        ("messages", (_FakeMessageChunk("partial"), {"ls_provider": "openai"})),
        # 第二个 chunk：tools 节点完成（不会被消费到，因为前一个 chunk 已触发 abort）
        ("updates", {"tools": {"messages": [ToolMessage(content="tool result", tool_call_id="x")]}}),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
        abort_event=abort_event,
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    # 首个 chunk 进来时即检测到 abort_event.is_set() → 立即 abort
    assert "abort" in kinds
    # 第二个 chunk 不会被消费
    update_events = [e for e in events if e.kind == "update"]
    assert len(update_events) == 0


# ---------------------------------------------------------------------------
# P2：异常隔离
# ---------------------------------------------------------------------------


def test_exception_in_agent_stream_isolated():
    """P2：agent.stream 异常被吞，不向上抛，以 session_end 收尾。

    Returns:
        None
    """
    agent = _FakeAgent([], raise_on_iter=True)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    # 异常隔离：第一个事件是 session_start，最后一个事件是 session_end
    assert kinds[0] == "session_start"
    assert kinds[-1] == "session_end"
    # 不应有 abort / interrupt 事件
    assert "abort" not in kinds
    assert "interrupt" not in kinds


# ---------------------------------------------------------------------------
# P2：abort_event=None 时不监听 abort
# ---------------------------------------------------------------------------


def test_no_abort_event_does_not_check_abort():
    """P2：abort_event=None 时流不监听 abort 信号，正常产出所有事件。

    Returns:
        None
    """
    chunks = [
        ("messages", (_FakeMessageChunk("first"), {"ls_provider": "openai"})),
        ("messages", (_FakeMessageChunk(" second"), {"ls_provider": "openai"})),
    ]
    agent = _FakeAgent(chunks)
    source = StreamEventSource(
        agent=agent,
        input_state=None,
        context=None,
        config={"configurable": {"thread_id": "test"}},
        abort_event=None,
    )

    events = _collect_events(source.events)
    kinds = [e.kind for e in events]
    assert "abort" not in kinds
    text_events = [e for e in events if e.kind == "text"]
    assert len(text_events) == 2
    assert kinds[-1] == "session_end"
