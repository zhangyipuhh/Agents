# -*- coding:utf-8 -*-
"""
map_router 子智能体停止信号端到端测试（2026-06-15 新增）

覆盖：
- generate_stream_response 入口挂载 request 到 ContextVar
- 工具函数能通过 get_current_request() 取出 request
- generate_stream_response finally 块清理 ContextVar（不影响后续请求）
- 客户端断开时主 astream 跳出 + 子智能体（sandbox/explore）也跳出
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
    构造一个模拟 FastAPI Request 对象的工厂函数（同 test_subagent_stop.py）。
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
    """
    from app.features.map_agent.router import map_router

    fake_request = _make_fake_request([False, False, False])

    # 构造一个会在第一次 yield 时取出 request 的 fake stream
    captured_request = {"value": None}

    async def fake_stream(*args, **kwargs):
        # 第一次 yield 时记录 contextvar 中的 request
        captured_request["value"] = get_current_request()
        yield ("updates", {"llm_call": {"messages": []}})

    fake_agent = MagicMock()
    fake_agent.stream = fake_stream

    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
        async def collect():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="test",
                session_id="sid",
                context=None,
                geometry_data={},
                attachments=[],
                resume=None,
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
    """
    from app.features.map_agent.router import map_router

    fake_request_1 = _make_fake_request([False])
    fake_request_2 = _make_fake_request([False])

    # 第一个 fake stream：让循环立即跳出
    async def fake_stream_1(*args, **kwargs):
        return
        yield  # noqa: 让 fake_stream 变成 generator

    async def fake_stream_2(*args, **kwargs):
        return
        yield

    fake_agent_1 = MagicMock()
    fake_agent_1.stream = fake_stream_1
    fake_agent_2 = MagicMock()
    fake_agent_2.stream = fake_stream_2

    # 第一次运行：设置 request_1
    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent_1)):
        async def run_1():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="t1",
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
    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent_2)):
        async def run_2():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="t2",
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
    P1: 客户端断开时，generate_stream_response 的 astream 循环立即跳出（不继续消耗 token）。
    """
    from app.features.map_agent.router import map_router

    # 第二次 is_disconnected 返回 True，触发跳出
    fake_request = _make_fake_request([False, True, True, True])

    chunk_count = {"n": 0}

    async def fake_stream(*args, **kwargs):
        # yield 多次让循环有足够机会检测断开
        for i in range(5):
            chunk_count["n"] += 1
            yield ("updates", {"llm_call": {"messages": [MagicMock(content=f"chunk{i}")]}})

    fake_agent = MagicMock()
    fake_agent.stream = fake_stream

    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
        async def collect():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="test",
                session_id="sid",
                request=fake_request,
            ):
                results.append(item)
            return results

        results = asyncio.run(collect())

    # 验证：is_disconnected 第二次返回 True 后跳出
    # 第一次 yield 走完处理（len=1），第二次 yield 循环开始 is_disconnected=True 立即 return
    # 所以 fake_stream 应只被消费 2 次（yield 1+1，第三次已跳出）
    assert chunk_count["n"] == 2, (
        f"客户端断开后应跳出循环，期望 yield 2 次（第一次处理完 + 第二次检测到断开），"
        f"实际 {chunk_count['n']} 次"
    )
    # 验证：is_disconnected 被调用
    assert fake_request._call_count["n"] >= 2


def test_router_no_request_does_not_block():
    """
    P1: request=None（非 HTTP 上下文）时，generate_stream_response 正常运行不抛错。
    """
    from app.features.map_agent.router import map_router

    async def fake_stream(*args, **kwargs):
        yield ("updates", {"llm_call": {"messages": []}})

    fake_agent = MagicMock()
    fake_agent.stream = fake_stream

    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
        async def collect():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="test",
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
    from app.features.map_agent.router import map_router

    request_a = _make_fake_request([False, False])
    request_b = _make_fake_request([False, False])
    # 用 list 记录（保留所有调用，支持两个并发任务各一次）
    captured_requests = []

    async def fake_stream(*args, **kwargs):
        # 记录执行时 contextvar 中的 request
        captured_requests.append(get_current_request())
        yield ("updates", {"llm_call": {"messages": []}})

    fake_agent = MagicMock()
    fake_agent.stream = fake_stream

    async def run_with(request):
        with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
            async for _ in map_router.generate_stream_response(
                user_input="t",
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
