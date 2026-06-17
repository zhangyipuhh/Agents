# -*- coding:utf-8 -*-
"""
map_router 客户端断开检测测试（2026-06-15 新增）

覆盖需求：
- 用户点击停止按钮 → 前端 reader.cancel() 断开 SSE → 后端 is_disconnected() 检测
- generate_stream_response 主循环在客户端断开时立即 return（不再继续 LangGraph astream）
- /api/map/chat 和 /api/map/knowledge-chat 路由都把 request 传给业务生成器

测试策略：
- 直接 import generate_stream_response 函数（不依赖 conftest 的 app fixture 启动真实 FastAPI）
- 用 mock MapAgent 替换 get_map_agent，让 astream 产生可控的 chunk 序列
- 第一次 is_disconnected() 返回 False（继续 yield），第二次返回 True（应跳出循环）
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest


def _make_fake_request(disconnect_sequence):
    """
    构造一个模拟的 FastAPI Request 对象
    每次 await request.is_disconnected() 返回序列中的下一个布尔值

    Args:
        disconnect_sequence: list[bool]，按调用顺序返回

    Returns:
        Mock 对象，带 is_disconnected 协程方法
    """
    fake = Mock()
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


def test_generate_stream_response_importable():
    """P0: generate_stream_response 可被 import（不会被 conftest 误伤）"""
    from app.features.map_agent.router.map_router import generate_stream_response

    assert generate_stream_response is not None
    assert callable(generate_stream_response)


def test_generate_stream_response_signature_accepts_request():
    """P0: generate_stream_response 签名包含 request: Request = None 形参（向后兼容）"""
    import inspect

    from app.features.map_agent.router.map_router import generate_stream_response

    sig = inspect.signature(generate_stream_response)
    assert "request" in sig.parameters
    # 默认值为 None（不破坏调用方便）
    assert sig.parameters["request"].default is None


def test_generate_stream_response_stops_on_client_disconnect():
    """
    P1: 客户端断开（is_disconnected 返回 True）时立即跳出 stream 循环
    验证：
    - 第一次循环 is_disconnected() == False → 继续 yield
    - 第二次循环 is_disconnected() == True → 跳出循环，return 而非继续
    - 不会继续消费 stream 中剩余的 chunks
    """
    from app.features.map_agent.router import map_router

    # 构造一个会 yield 多次的 fake map_agent.stream
    chunks = [
        ("updates", {"llm_call": {"messages": [Mock(content="hello")]}}),
        ("updates", {"llm_call": {"messages": [Mock(content="world")]}}),
        ("updates", {"llm_call": {"messages": [Mock(content="more")]}}),
        ("updates", {"llm_call": {"messages": [Mock(content="should_not_appear")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    # 第一次 False（继续 yield），第二次 True（应跳出循环）
    fake_request = _make_fake_request([False, True, True, True])

    # 替换 get_map_agent，让 MapAgent.stream 走 fake_stream
    fake_agent = Mock()
    fake_agent.stream = fake_stream

    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
        async def collect():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="test",
                session_id="sid_test",
                context=None,
                geometry_data={},
                attachments=[],
                resume=None,
                request=fake_request,
            ):
                results.append(item)
            return results

        results = asyncio.run(collect())

    # 第一次 is_disconnected()==False 时已 yield 1 个 chunk；第二次 True 时跳出循环
    # 因此结果中只应有 1 个 SSE 输出（与 hello 对应的 update 事件）
    assert len(results) == 1, f"期望 yield 1 次后跳出，实际 {len(results)} 次"
    # 验证 is_disconnected 至少被调用过（说明断连检测逻辑生效）
    assert fake_request._call_count["n"] >= 1


def test_generate_stream_response_runs_to_end_when_not_disconnected():
    """
    P1: 客户端未断开时（is_disconnected 始终 False），正常 yield 所有 chunk + end 事件
    """
    from app.features.map_agent.router import map_router

    chunks = [
        ("updates", {"llm_call": {"messages": [Mock(content="hello")]}}),
        ("updates", {"llm_call": {"messages": [Mock(content="world")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    # 全部返回 False（未断开）
    fake_request = _make_fake_request([False, False, False, False, False])

    # 替换 get_map_agent，让 MapAgent.stream 走 fake_stream
    fake_agent = Mock()
    fake_agent.stream = fake_stream

    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
        async def collect():
            results = []
            async for item in map_router.generate_stream_response(
                user_input="test",
                session_id="sid_test",
                context=None,
                geometry_data={},
                attachments=[],
                resume=None,
                request=fake_request,
            ):
                results.append(item)
            return results

        results = asyncio.run(collect())

    # 2 个 update chunk + 1 个 end 事件 = 3 个 SSE 输出
    assert len(results) == 3, f"期望 3 个 SSE 输出，实际 {len(results)}"
    # 最后一个是 end 事件
    last = results[-1]
    assert "data:" in last
    assert '"type": "end"' in last


def test_generate_stream_response_works_without_request():
    """
    P1: request=None 时（向后兼容：旧调用方不传 request）仍能正常工作
    不抛异常、不进入断连检查分支
    """
    from app.features.map_agent.router import map_router

    chunks = [
        ("updates", {"llm_call": {"messages": [Mock(content="hello")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    fake_agent = Mock()
    fake_agent.stream = fake_stream

    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)):
        async def collect():
            results = []
            # 关键：request=None（默认参数）
            async for item in map_router.generate_stream_response(
                user_input="test",
                session_id="sid_test",
                context=None,
                geometry_data={},
                attachments=[],
                resume=None,
            ):
                results.append(item)
            return results

        results = asyncio.run(collect())

    # 1 个 update + 1 个 end = 2 个 SSE 输出
    assert len(results) == 2
    assert '"type": "end"' in results[-1]
