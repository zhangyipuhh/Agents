# -*- coding:utf-8 -*-
"""
_stream_helper 子智能体停止信号端到端测试（2026-06-15 新增，2026-06-23 迁移）

覆盖：
- generate_stream_response 入口挂载 request 到 ContextVar
- 工具函数能通过 get_current_request() 取出 request
- generate_stream_response finally 块清理 ContextVar（不影响后续请求）
- 客户端断开时主 astream 跳出 + 子智能体（sandbox/explore）也跳出

2026-06-23 迁移：测试目标从 map_router.generate_stream_response 迁移到
_stream_helper.generate_stream_response（统一签名：agent, input_state, context, session_id, request）
"""

import asyncio
from unittest.mock import MagicMock, Mock

import pytest

from app.core.tools._stop_signal import (
    get_current_request,
    reset_current_request,
    set_current_request,
)


# ============================================================
# 公共 helper
# ============================================================


def _make_fake_request(disconnect_sequence):
    """
    构造一个模拟 FastAPI Request 对象的工厂函数。

    Args:
        disconnect_sequence: list[bool]，按调用顺序返回的断开状态序列

    Returns:
        MagicMock: 带 is_disconnected 协程方法的模拟 Request 对象
    """
    fake = MagicMock(name="fake_request")
    call_count = {"n": 0}
    disconnect_sequence = list(disconnect_sequence)

    async def _is_disconnected():
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(disconnect_sequence):
            return disconnect_sequence[idx]
        return False

    fake.is_disconnected = _is_disconnected
    fake._call_count = call_count
    return fake


# ============================================================
# 1) generate_stream_response 入口挂载 + finally 清理
# ============================================================


def test_generate_stream_response_sets_contextvar():
    """
    P1: 进入 generate_stream_response 后，工具函数能通过 get_current_request() 取出 request。

    验证 _stream_helper.generate_stream_response 在调用 agent.stream 前已通过
    set_current_request(request) 把 FastAPI Request 挂到 ContextVar。
    """
    from app.routers._stream_helper import generate_stream_response

    fake_request = _make_fake_request([False, False, False])

    # 构造一个会在第一次 yield 时取出 request 的 fake stream
    captured_request = {"value": None}

    async def fake_stream(*args, **kwargs):
        # 第一次 yield 时记录 contextvar 中的 request
        captured_request["value"] = get_current_request()
        yield ("updates", {"llm_call": {"messages": []}})

    fake_agent = Mock()
    fake_agent.stream = fake_stream

    async def collect():
        results = []
        async for item in generate_stream_response(
            agent=fake_agent,
            input_state=Mock(),
            context=None,
            session_id="sid",
            request=fake_request,
        ):
            results.append(item)
            if len(results) >= 3:  # tool_start + 1 chunk + end
                break
        return results

    asyncio.run(collect())

    # 验证：fake_stream 在执行时能从 ContextVar 取出 fake_request
    assert captured_request["value"] is fake_request, (
        "工具函数在 astream 循环内应能通过 get_current_request() 取出 request"
    )


def test_generate_stream_response_resets_contextvar_on_finally():
    """
    P1: generate_stream_response 退出后 ContextVar 被清理（不影响后续请求）。

    验证 _stream_helper.generate_stream_response 的 finally 块正确调用
    reset_current_request(cv_token) 清理 ContextVar。
    """
    from app.routers._stream_helper import generate_stream_response

    fake_request_1 = _make_fake_request([False])
    fake_request_2 = _make_fake_request([False])

    # 第一个 fake stream：让循环立即跳出
    async def fake_stream_1(*args, **kwargs):
        return
        yield  # noqa: 让 fake_stream 变成 generator

    async def fake_stream_2(*args, **kwargs):
        return
        yield

    fake_agent_1 = Mock()
    fake_agent_1.stream = fake_stream_1
    fake_agent_2 = Mock()
    fake_agent_2.stream = fake_stream_2

    # 第一次运行：设置 request_1
    async def run_1():
        results = []
        async for item in generate_stream_response(
            agent=fake_agent_1,
            input_state=Mock(),
            context=None,
            session_id="sid",
            request=fake_request_1,
        ):
            results.append(item)
        return results

    asyncio.run(run_1())

    # 第一次运行后：ContextVar 应已 reset（== None）
    assert get_current_request() is None, (
        "第一次 generate_stream_response 退出后，ContextVar 应被重置为 None"
    )

    # 第二次运行：设置 request_2
    async def run_2():
        results = []
        async for item in generate_stream_response(
            agent=fake_agent_2,
            input_state=Mock(),
            context=None,
            session_id="sid",
            request=fake_request_2,
        ):
            results.append(item)
        return results

    asyncio.run(run_2())

    # 第二次运行后：ContextVar 应再次 reset
    assert get_current_request() is None


# ============================================================
# 2) 主 astream 检测到客户端断开时跳出循环
# ============================================================


def test_router_disconnect_propagates_to_main_astream():
    """
    P1（2026-06-22 改造）：客户端断开时精确延迟中断

    旧实现：客户端断开后立即 return（仅 yield 2 次）
    新实现：客户端断开后仅标记 disconnect_requested=True，继续消费 stream；
    当遇到 "tools" 节点完成 chunk 时才真正断开。

    本测试的 fake_stream 中所有 chunks 都是 llm_call 节点（非 tools 节点），
    所以客户端断开后所有 5 个 chunks 都被消费（用于"延迟中断"逻辑保持继续处理），
    但 messages 模式被跳过。循环自然结束后 yield end 事件。

    验证：
    - chunk_count["n"] == 5（所有 chunks 都被消费，因为没有 tools 节点完成触发断开）
    - 第一次 yield 是 llm_call update（disconnect 前）
    - 第二个 SSE 事件是 client_disconnected 标记
    - 之后都是 llm_call update
    - 最后一个是 end 事件
    """
    from app.routers._stream_helper import generate_stream_response

    # 第二次 is_disconnected 返回 True，触发标记 disconnect_requested
    fake_request = _make_fake_request([False, True, True, True])

    chunk_count = {"n": 0}

    async def fake_stream(*args, **kwargs):
        # yield 多次让循环有足够机会检测断开
        for i in range(5):
            chunk_count["n"] += 1
            yield ("updates", {"llm_call": {"messages": [MagicMock(content=f"chunk{i}")]}})

    fake_agent = Mock()
    fake_agent.stream = fake_stream

    async def collect():
        results = []
        async for item in generate_stream_response(
            agent=fake_agent,
            input_state=Mock(),
            context=None,
            session_id="sid",
            request=fake_request,
        ):
            results.append(item)
        return results

    results = asyncio.run(collect())

    # 2026-06-22 精确延迟中断新行为：
    # - 第一次 yield 走完处理（is_disconnected=False）
    # - 第二次循环开始 is_disconnected=True → 标记 disconnect_requested，yield client_disconnected
    # - 后续所有 llm_call 节点 updates 都被消费（不是 tools 节点，不触发断开）
    # - 循环自然结束，yield end 事件
    # 所以 fake_stream 应被消费 5 次（所有 chunks）
    assert chunk_count["n"] == 5, (
        f"精确延迟中断：客户端断开后所有 chunks 都应被消费直到 tools 节点完成，"
        f"期望 yield 5 次，实际 {chunk_count['n']} 次"
    )
    # 验证 SSE 事件数量
    # 1. llm_call update (chunk0, disconnect 前)
    # 2. client_disconnected 标记
    # 3-6. llm_call update (chunk1-chunk4)
    # 7. end 事件
    assert len(results) == 7, f"期望 7 个 SSE 输出，实际 {len(results)}"
    # 验证 is_disconnected 被调用
    assert fake_request._call_count["n"] >= 1


def test_router_no_request_does_not_block():
    """
    P1: request=None（非 HTTP 上下文）时，generate_stream_response 正常运行不抛错。
    """
    from app.routers._stream_helper import generate_stream_response

    async def fake_stream(*args, **kwargs):
        yield ("updates", {"llm_call": {"messages": []}})

    fake_agent = Mock()
    fake_agent.stream = fake_stream

    async def collect():
        results = []
        async for item in generate_stream_response(
            agent=fake_agent,
            input_state=Mock(),
            context=None,
            session_id="sid",
            request=None,  # 关键：非 HTTP 上下文
        ):
            results.append(item)
        return results

    # 关键：不应抛错
    results = asyncio.run(collect())
    assert len(results) >= 1


# ============================================================
# 3) 并发请求隔离：两个并发 generate_stream_response 各自 request 互不污染
# ============================================================


@pytest.mark.asyncio
async def test_concurrent_router_requests_isolated():
    """
    P2: 两个并发 generate_stream_response 各自挂不同 request，
    工具函数内 get_current_request() 拿到自己请求的 request（contextvars 隔离性）。
    """
    from app.routers._stream_helper import generate_stream_response

    request_a = _make_fake_request([False, False])
    request_b = _make_fake_request([False, False])
    # 用 list 记录（保留所有调用，支持两个并发任务各一次）
    captured_requests = []

    async def fake_stream(*args, **kwargs):
        # 记录执行时 contextvar 中的 request
        captured_requests.append(get_current_request())
        yield ("updates", {"llm_call": {"messages": []}})

    fake_agent = Mock()
    fake_agent.stream = fake_stream

    async def run_with(request):
        async for _ in generate_stream_response(
            agent=fake_agent,
            input_state=Mock(),
            context=None,
            session_id="sid",
            request=request,
        ):
            pass

    # 并发执行
    await asyncio.gather(run_with(request_a), run_with(request_b))

    # 验证：两个任务拿到的 Request 互不串台
    assert request_a in captured_requests
    assert request_b in captured_requests
    assert request_a is not request_b
    # 验证：contextvar 在两个 generate_stream_response 退出后都已重置
    assert get_current_request() is None
