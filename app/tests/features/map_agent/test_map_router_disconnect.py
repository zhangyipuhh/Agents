# -*- coding:utf-8 -*-
"""
map_router 客户端断开检测测试（2026-06-15 新增，2026-06-22 扩展）

覆盖需求：
- 用户点击停止按钮 → 前端 reader.cancel() 断开 SSE → 后端 is_disconnected() 检测
- generate_stream_response 主循环在客户端断开时**精确延迟中断**：
  * 检测到 disconnect 仅标记，不 return
  * 跳过 messages 模式（不推 LLM token 给已断开的前端）
  * 继续消费 updates 模式
  * 当 "tools" 节点完成 chunk（data["tools"]["messages"] 包含 ToolMessage）时 break
  * 这样保证当前工具/子智能体完成 ToolMessage 写入 state 后才真正断开
- /api/map/knowledge-chat 路由把 request 传给业务生成器（旧 /api/map/chat 已迁移至 /api/agent/chat）
- **2026-06-22 新增**：多工具并行调用场景验证（依赖 LangGraph ToolNode 全或无语义）

测试策略：
- 直接 import generate_stream_response 函数（不依赖 conftest 的 app fixture 启动真实 FastAPI）
- 用 mock MapAgent 替换 get_map_agent，让 astream 产生可控的 chunk 序列
- 用 Mock 对象模拟 ToolMessage 验证类型判断逻辑
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


def test_generate_stream_response_delayed_disconnect_single_tool():
    """
    P1（2026-06-22 改造）：单工具场景 - 客户端断开后延迟到工具完成才真正断开

    流程：
    - 第一次 yield LLM 节点的 update（is_disconnected=False，正常 yield）
    - 第二次循环检测到 is_disconnected=True → 标记 disconnect_requested，跳过 messages
    - 第三次 yield "tools" 节点完成 chunk（含 ToolMessage）→ 真正断开
    - 之后不应再有 chunk（不应继续到 llm_call 等节点）

    验证：
    - yield 数量为 3：LLM update + client_disconnected 标记 + tools 完成 update
    - 没有 end 事件（因为精确延迟中断 break 后不进入 yield end 路径——但 end 是 yield 之后才发生？）

    注：end 事件是在循环结束后 yield 的，break 后循环退出但仍会执行最后的 yield end，
    所以预期是 4 个 yield：LLM update + client_disconnected + tools update + end
    """
    from app.features.map_agent.router import map_router

    # 构造 mock ToolMessage（通过 __class__.__name__ 兼容）
    class MockToolMessage:
        def __init__(self, content="tool result"):
            self.content = content
            self.tool_call_id = "call_1"

    # 构造一个 LLM update + 工具完成 update 的 chunk 序列
    chunks = [
        # LLM 节点 update
        ("updates", {"llm_call": {"messages": [Mock(content="thinking...")]}}),
        # tools 节点完成（包含 1 个 ToolMessage）
        ("updates", {"tools": {"messages": [MockToolMessage("tool result")]}}),
        # 后续 LLM 节点（不应被处理）
        ("updates", {"llm_call": {"messages": [Mock(content="should_not_appear")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    # 第二次 is_disconnected 返回 True（模拟客户端在 LLM 思考时点击停止）
    fake_request = _make_fake_request([False, True, True, True])

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

    # 预期 yield 4 个事件：
    # 1. LLM update（is_disconnected=False 时正常 yield）
    # 2. client_disconnected 标记
    # 3. tools 节点完成 update（disconnect_executed=True，break 前 yield）
    # 4. end 事件（break 退出循环后，循环结束统一 yield）
    assert len(results) == 4, f"期望 4 个 SSE 输出，实际 {len(results)}: {results}"

    # 验证 SSE 内容
    assert "llm_call" in results[0] or "thinking" in results[0]
    assert '"type": "client_disconnected"' in results[1]
    assert "tools" in results[2]
    assert '"type": "end"' in results[3]

    # 验证 is_disconnected 至少被调用过
    assert fake_request._call_count["n"] >= 1


def test_generate_stream_response_delayed_disconnect_multiple_tools():
    """
    P1（2026-06-22 改造）：多工具并行场景 - 客户端断开后等到所有工具完成才断开

    验证 LangGraph ToolNode 的"全或无"语义：
    - LLM 一次性发起 3 个 tool_calls（多工具并行）
    - LangGraph ToolNode 用 asyncio.gather 等所有 3 个 tool_calls 都完成
    - 然后才 yield "tools" 节点完成 chunk（包含 3 个 ToolMessage）
    - SSE 路由检测到 3 个 ToolMessage → 真正断开
    - 不会在 1 个或 2 个工具完成时就提前断开
    """
    from app.features.map_agent.router import map_router

    class MockToolMessage:
        def __init__(self, content="result", tool_call_id=None):
            self.content = content
            self.tool_call_id = tool_call_id or f"call_{id(self)}"

    # 模拟多工具并行：3 个 ToolMessage 一次性出现
    chunks = [
        # LLM 节点 update（含 3 个 tool_calls）
        ("updates", {
            "llm_call": {"messages": [Mock(content="I'll call 3 tools in parallel")]}
        }),
        # tools 节点完成（包含 3 个 ToolMessage，模拟 asyncio.gather 全部完成）
        ("updates", {
            "tools": {"messages": [
                MockToolMessage("result_1", "call_1"),
                MockToolMessage("result_2", "call_2"),
                MockToolMessage("result_3", "call_3"),
            ]}
        }),
        # 后续不应被处理
        ("updates", {"llm_call": {"messages": [Mock(content="should_not_appear")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    # 第二次 is_disconnected 返回 True
    fake_request = _make_fake_request([False, True, True, True])

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

    # 4 个事件：LLM update + client_disconnected + tools update（含 3 个 ToolMessage） + end
    assert len(results) == 4, f"期望 4 个 SSE 输出，实际 {len(results)}: {results}"
    assert '"type": "client_disconnected"' in results[1]
    # tools 节点完成 chunk 应包含 3 个 ToolMessage
    # 注意：JSON 序列化时 MockToolMessage 会变成 "<MockToolMessage object at 0x...>" 格式
    # 所以验证 "tools" 节点被 yield 且包含 3 个 MockToolMessage 字符串
    assert "tools" in results[2]
    # 计算结果[2]中 MockToolMessage 字符串出现次数
    mock_count = results[2].count("MockToolMessage object")
    assert mock_count == 3, f"期望 tools 节点完成 chunk 包含 3 个 MockToolMessage，实际 {mock_count} 个"
    assert '"type": "end"' in results[3]


def test_generate_stream_response_no_disconnect_during_non_tools_update():
    """
    P1（2026-06-22 改造）：客户端断开后遇到非 tools 节点 update，不应立即断开

    场景：客户端在 LLM 调用阶段断开，后续流中先出现 summarize 节点 update，
    然后才是 tools 节点。SSE 路由应继续等待 tools 节点完成才真正断开。
    """
    from app.features.map_agent.router import map_router

    class MockToolMessage:
        def __init__(self, content="tool result"):
            self.content = content
            self.tool_call_id = "call_1"

    chunks = [
        # LLM 节点 update
        ("updates", {"llm_call": {"messages": [Mock(content="hello")]}}),
        # summarize 节点 update（非 tools 节点，不应触发断开）
        ("updates", {"summarize": {"messages": []}}),
        # hitl_check 节点 update
        ("updates", {"hitl_check": {"messages": []}}),
        # tools 节点完成（最终触发断开）
        ("updates", {"tools": {"messages": [MockToolMessage("result")]}}),
        # 后续不应被处理
        ("updates", {"llm_call": {"messages": [Mock(content="should_not_appear")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    fake_request = _make_fake_request([False, True, True, True, True, True])

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

    # 预期 yield 5 个事件：
    # 1. LLM update
    # 2. client_disconnected 标记
    # 3. summarize update（不应触发断开）
    # 4. hitl_check update（不应触发断开）
    # 5. tools update + end
    # 实际是 6 个：5 个 update + 1 个 end
    assert len(results) == 6, f"期望 6 个 SSE 输出，实际 {len(results)}: {results}"

    # 验证 client_disconnected 在第二个事件
    assert '"type": "client_disconnected"' in results[1]
    # 验证 summarize 和 hitl_check 都被 yield（虽然客户端断开）
    assert "summarize" in results[2]
    assert "hitl_check" in results[3]
    # 验证 tools 节点完成时触发断开
    assert "tools" in results[4]
    assert '"type": "end"' in results[5]


def test_generate_stream_response_skips_messages_after_disconnect():
    """
    P1（2026-06-22 改造）：客户端断开后跳过 messages 模式（不再推 LLM token）

    验证 messages 模式 chunk 在 disconnect_requested=True 时被跳过，
    不浪费带宽，前端也不会看到不完整的 LLM 输出。
    """
    from app.features.map_agent.router import map_router

    class MockToolMessage:
        def __init__(self, content="tool result"):
            self.content = content
            self.tool_call_id = "call_1"

    # Mock AIMessage for messages 模式
    mock_ai_msg = Mock()
    mock_ai_msg.__class__.__name__ = "AIMessageChunk"

    # 模拟流：先 messages 模式输出 LLM token（disconnect 后应被跳过）
    # 然后 tools 节点完成（触发断开）
    chunks = [
        # LLM update 节点
        ("updates", {"llm_call": {"messages": [Mock(content="thinking...")]}}),
        # messages 模式：LLM token（disconnect 后应被跳过）
        ("messages", (mock_ai_msg, {"langgraph_node": "llm_call"})),
        # tools 节点完成
        ("updates", {"tools": {"messages": [MockToolMessage("result")]}}),
    ]

    async def fake_stream(*args, **kwargs):
        for c in chunks:
            yield c

    # 第二次 is_disconnected 返回 True
    fake_request = _make_fake_request([False, True, True, True])

    fake_agent = Mock()
    fake_agent.stream = fake_stream

    # Mock format_message to return a content string
    with patch.object(map_router, "get_map_agent", AsyncMock(return_value=fake_agent)), \
         patch("app.core.format.stream.stream_format_context.format_message", return_value="chunk_content"):
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

    # 4 个事件：LLM update + client_disconnected + tools update + end
    # messages 模式（"chunk_content"）不应出现在结果中
    for r in results:
        assert "chunk_content" not in r, \
            f"messages 模式在 disconnect 后应被跳过，但出现了: {r}"


def test_generate_stream_response_legacy_immediate_disconnect():
    """
    P1（向后兼容测试）：现有测试用例验证"立即断开"行为已被替换为"延迟断开"

    原行为：检测到 disconnect 立即 return（仅 yield 1 个 chunk）
    新行为：检测到 disconnect 仅标记，继续 yield 直到 tools 节点完成

    旧测试期望的是原行为，本测试明确：原有测试已被新行为覆盖，新行为更安全
    （避免 orphan tool_calls 导致 LLM API 报错）。
    """
    # 此测试作为文档说明：旧的"立即 return"行为已被替换
    # 实际新行为在 test_generate_stream_response_delayed_disconnect_single_tool 中验证
    # 不在此重复实现，仅文档化变更
    pass


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
