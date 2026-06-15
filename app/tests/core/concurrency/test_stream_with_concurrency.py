# -*- coding:utf-8 -*-
"""
stream_with_concurrency 单元测试（2026-06-15 新增）

覆盖：
- 通用 SSE 流式包装器：消费 dep yield 链 + 业务流衔接
- HITL interrupt 业务事件触发主动 release
- finally 兜底：业务流结束 / 业务流异常 / 客户端异常断开均触发 dep.aclose
- 防御性：dep 无 aclose 时不崩溃
- 辅助函数 _is_interrupt_chunk 单测
"""
import asyncio
import json
from typing import AsyncGenerator, List
from unittest.mock import MagicMock

import pytest

from app.core.concurrency.chat_concurrency_dependency import (
    _is_interrupt_chunk,
    stream_with_concurrency,
)


# =====================================================================
# 辅助 Fake
# =====================================================================


class _FakeRequest:
    """最小 FastAPI Request 替身（仅暴露 .state）"""

    class _State:
        pass

    def __init__(self):
        self.state = self._State()


def _make_dep_with_items(items: List):
    """
    构造一个 mock dep，模拟 chat_concurrency_dependency 的 yield 行为。

    Args:
        items: 要 yield 的元素列表

    Returns:
        (dep, aclose_called): dep 是 async generator，aclose_called 是 list[1] 用于断言
    """
    aclose_called = {"count": 0}

    async def gen():
        try:
            for item in items:
                yield item
            # 模拟 chat_concurrency_dependency 的 finally 后挂起
            await asyncio.Event().wait()
        finally:
            aclose_called["count"] += 1

    dep = gen()
    return dep, aclose_called


def _make_business_gen(chunks: List[str]):
    """
    构造业务生成器（同步列表 yield）

    Args:
        chunks: SSE 字符串列表

    Returns:
        async generator
    """
    async def gen() -> AsyncGenerator[str, None]:
        for c in chunks:
            yield c
    return gen()


def _make_failing_business_gen(exc: Exception):
    """构造一个 yield 第一项后抛异常的 business_gen"""
    async def gen() -> AsyncGenerator[str, None]:
        yield 'data: {"type":"text","data":{"x":1}}\n\n'
        raise exc
    return gen()


# =====================================================================
# _is_interrupt_chunk 单元测试
# =====================================================================


def test_is_interrupt_chunk_detects_interrupt_event():
    """_is_interrupt_chunk 对 'data: {"type":"interrupt",...}' 返回 True。"""
    chunk = 'data: {"type":"interrupt","data":{"requests":[]}}\n\n'
    assert _is_interrupt_chunk(chunk) is True


def test_is_interrupt_chunk_detects_non_interrupt_text_event():
    """_is_interrupt_chunk 对 'type':'text' 返回 False。"""
    chunk = 'data: {"type":"text","data":{"content":"hi"}}\n\n'
    assert _is_interrupt_chunk(chunk) is False


def test_is_interrupt_chunk_returns_false_for_non_string():
    """非字符串输入返回 False，不抛异常。"""
    assert _is_interrupt_chunk(None) is False
    assert _is_interrupt_chunk(123) is False
    assert _is_interrupt_chunk({"type": "interrupt"}) is False


def test_is_interrupt_chunk_returns_false_for_invalid_json():
    """data: 后的内容不是合法 JSON 时返回 False。"""
    assert _is_interrupt_chunk("data: not-json\n\n") is False
    assert _is_interrupt_chunk("data: \n\n") is False


def test_is_interrupt_chunk_returns_false_for_non_data_prefix():
    """不以 'data: ' 开头的字符串返回 False。"""
    assert _is_interrupt_chunk('{"type":"interrupt"}') is False
    assert _is_interrupt_chunk("event: foo\ndata: ...") is False


# =====================================================================
# stream_with_concurrency 主流程
# =====================================================================


@pytest.mark.asyncio
async def test_stream_with_concurrency_consumes_queue_event_then_business_chunks():
    """核心衔接：dep 先 yield queue 事件再 yield None，business_gen yield 业务 chunk → SSE 顺序正确。"""
    dep, aclose_called = _make_dep_with_items([
        {"type": "queue", "event": "waiting", "position": 1, "waiting_count": 1, "active_count": 1, "max_concurrency": 1, "timestamp": 1.0},
        None,  # 进入业务流
    ])
    business_gen = _make_business_gen([
        'data: {"type":"update","data":{"x":1}}\n\n',
        'data: {"type":"end","message":"ok"}\n\n',
    ])
    request = _FakeRequest()

    collected: List[str] = []
    async for chunk in stream_with_concurrency(request, dep, business_gen):
        collected.append(chunk)

    # 期望：第 1 帧是 queue waiting SSE，第 2 帧是业务 update，第 3 帧是业务 end
    assert len(collected) == 3
    assert collected[0].startswith("data: ")
    payload = json.loads(collected[0][6:].strip())
    assert payload["type"] == "queue"
    assert payload["event"] == "waiting"
    assert "update" in collected[1]
    assert "end" in collected[2]

    # finally 触发 aclose
    assert aclose_called["count"] == 1


@pytest.mark.asyncio
async def test_stream_with_concurrency_aclose_dep_after_business_finished():
    """业务流正常结束后 dep.aclose 被调用一次。"""
    dep, aclose_called = _make_dep_with_items([None])
    business_gen = _make_business_gen([
        'data: {"type":"end","message":"ok"}\n\n',
    ])
    request = _FakeRequest()

    async for _ in stream_with_concurrency(request, dep, business_gen):
        pass

    assert aclose_called["count"] == 1


@pytest.mark.asyncio
async def test_stream_with_concurrency_aclose_dep_on_business_exception():
    """business_gen 抛异常时 dep.aclose 仍被调用（finally 兜底）。"""
    dep, aclose_called = _make_dep_with_items([None])

    class _BoomError(RuntimeError):
        pass

    business_gen = _make_failing_business_gen(_BoomError("biz failed"))
    request = _FakeRequest()

    with pytest.raises(_BoomError):
        async for _ in stream_with_concurrency(request, dep, business_gen):
            pass

    # finally 兜底：即使业务流异常，dep 仍被 aclose
    assert aclose_called["count"] == 1


@pytest.mark.asyncio
async def test_stream_with_concurrency_calls_release_handle_on_interrupt_chunk():
    """业务流 yield interrupt 事件时，request.state.concurrency_release_handle 被调用。"""
    dep, aclose_called = _make_dep_with_items([None])

    # 业务流包含一个 interrupt chunk
    interrupt_chunk = 'data: {"type":"interrupt","data":{"requests":[]}}\n\n'
    business_gen = _make_business_gen([
        'data: {"type":"text","data":{"x":1}}\n\n',
        interrupt_chunk,
        'data: {"type":"end","message":"ok"}\n\n',
    ])

    request = _FakeRequest()
    handle_mock = MagicMock()
    request.state.concurrency_release_handle = handle_mock

    async for _ in stream_with_concurrency(request, dep, business_gen):
        pass

    # release_handle 应被调用一次（interrupt 之前）
    assert handle_mock.call_count == 1
    assert aclose_called["count"] == 1


@pytest.mark.asyncio
async def test_stream_with_concurrency_skips_release_handle_for_non_interrupt_chunk():
    """业务流仅 yield 非 interrupt chunk 时，release_handle 不被调用。"""
    dep, aclose_called = _make_dep_with_items([None])
    business_gen = _make_business_gen([
        'data: {"type":"text","data":{"x":1}}\n\n',
        'data: {"type":"update","data":{"y":2}}\n\n',
        'data: {"type":"end","message":"ok"}\n\n',
    ])

    request = _FakeRequest()
    handle_mock = MagicMock()
    request.state.concurrency_release_handle = handle_mock

    async for _ in stream_with_concurrency(request, dep, business_gen):
        pass

    # release_handle 应**不**被调用
    assert handle_mock.call_count == 0
    assert aclose_called["count"] == 1


@pytest.mark.asyncio
async def test_stream_with_concurrency_handles_dep_without_aclose():
    """dep 无 aclose 方法时（如 None），不崩溃，且业务流正常透传。"""
    # 传入 None（getattr 防御）
    business_gen = _make_business_gen([
        'data: {"type":"end","message":"ok"}\n\n',
    ])
    request = _FakeRequest()

    collected: List[str] = []
    async for chunk in stream_with_concurrency(request, None, business_gen):
        collected.append(chunk)

    # business_gen 的 chunk 仍被透传
    assert len(collected) == 1
    assert "end" in collected[0]
