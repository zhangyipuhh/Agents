# -*- coding:utf-8 -*-
"""
chat_concurrency_dependency 集成测试（2026-06-15 重构）

覆盖：
- SSE 模式：queue waiting/ready 事件、yield None 进入路由
- HTTP 模式：429 即时拒绝、acquire/release 一致
- HITL 早期释放：concurrency_release_handle 主动调用 + finally 兜底
- 单次依赖 yield 链自动衔接业务流
"""
import asyncio
from typing import AsyncGenerator, List

import httpx
import pytest
from fastapi import FastAPI, Depends
from httpx import ASGITransport

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue
from app.core.concurrency.chat_concurrency_dependency import chat_concurrency_dependency


@pytest.fixture
def reset_singleton():
    """重置单例"""
    AgentConcurrencyQueue.reset_instance()
    yield
    AgentConcurrencyQueue.reset_instance()


# =====================================================================
# 现有用例：保留并适配新签名（HTTPException 替代 SSE 流）
# =====================================================================


@pytest.fixture
def app_fixture(reset_singleton):
    """创建测试用 FastAPI 应用（SSE 模式路由）"""
    app = FastAPI()
    app.state.second_started = asyncio.Event()

    @app.get("/chat")
    async def chat(dep=Depends(chat_concurrency_dependency)):
        # 依赖已获取队列许可，设置事件表示本请求已开始执行
        app.state.second_started.set()
        await asyncio.sleep(0.05)
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_dependency_blocks_when_full(app_fixture):
    """测试并发满时后续请求排队"""
    queue = AgentConcurrencyQueue(max_concurrency=1)
    second_started = app_fixture.state.second_started

    async def slow_holder():
        async with queue:
            await asyncio.sleep(0.2)

    # 先占住唯一并发位
    task = asyncio.create_task(slow_holder())
    # 等待 holder 获取到许可
    await asyncio.sleep(0.01)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_fixture), base_url="http://test"
    ) as client:
        try:
            # 此时 /chat 应该等待
            response_task = asyncio.create_task(client.get("/chat"))
            # 在 holder 未释放前，第二个请求不应开始执行
            await asyncio.sleep(0.05)
            assert not second_started.is_set()

            response = await response_task
            assert response.status_code == 200
            # holder 释放后，/chat 应获取许可并执行
            assert second_started.is_set()
        finally:
            await task


# =====================================================================
# 2026-06-15 新增：SSE 模式 yield queue waiting/ready 事件
# =====================================================================


@pytest.mark.asyncio
async def test_sse_dependency_no_queue_event_when_available(reset_singleton):
    """无需等待时直接 yield None，无 queue 事件。"""
    AgentConcurrencyQueue(max_concurrency=1)

    # 构造一个最小 Request 替身
    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    items: List = []
    gen = chat_concurrency_dependency(_FakeRequest(), mode="sse")
    async for item in gen:
        items.append(item)
    # 无等待 → 应该只 yield None 一次
    assert items == [None]
    # 释放后 active_count 归 0
    assert AgentConcurrencyQueue().active_count == 0


@pytest.mark.asyncio
async def test_sse_dependency_emits_waiting_event_when_full(reset_singleton):
    """满员时 SSE 模式先 yield queue waiting 事件，再 yield ready + None。"""
    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()

    # 用一个 holder 占用许可
    holder_started = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with queue:
            holder_started.set()
            await release_holder.wait()

    holder_task = asyncio.create_task(holder())
    await holder_started.wait()

    # 第二个请求走 SSE 依赖
    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    collected: List[dict] = []
    none_count = 0

    async def drive_dep():
        nonlocal none_count
        async for item in chat_concurrency_dependency(_FakeRequest(), mode="sse"):
            if item is None:
                none_count += 1
                break
            collected.append(item)

    driver = asyncio.create_task(drive_dep())
    # 给依赖一点时间 yield 第一个 waiting 事件
    await asyncio.sleep(0.05)
    assert len(collected) >= 1
    first = collected[0]
    assert first["type"] == "queue"
    assert first["event"] == "waiting"
    assert first["max_concurrency"] == 1
    assert "waiting_count" in first
    assert "active_count" in first
    assert "position" in first

    # 释放 holder 让依赖拿到许可
    release_holder.set()
    await holder_task

    # 收集到 ready 事件和 None（业务入口）
    await driver
    assert none_count == 1
    # 检查最后两个事件：ready + None（None 不计入 collected）
    assert collected[-1]["type"] == "queue"
    assert collected[-1]["event"] == "ready"


@pytest.mark.asyncio
async def test_sse_dependency_auto_resumes_after_ready_event(reset_singleton):
    """核心衔接验证：waiting → ready → 业务 chunk 在同一 async for 链中连续产出。"""
    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()

    holder_started = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with queue:
            holder_started.set()
            await release_holder.wait()

    holder_task = asyncio.create_task(holder())
    await holder_started.wait()

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    collected: List = []

    async def business_gen() -> AsyncGenerator[str, None]:
        yield "data: {\"type\":\"update\",\"data\":{\"x\":1}}\n\n"
        yield "data: {\"type\":\"end\",\"message\":\"ok\"}\n\n"

    async def driver():
        async for item in chat_concurrency_dependency(_FakeRequest(), mode="sse"):
            if item is None:
                # 衔接：依赖返回 None → 进入业务流
                async for chunk in business_gen():
                    collected.append(chunk)
                break
            collected.append(item)

    drv = asyncio.create_task(driver())
    await asyncio.sleep(0.05)
    # 此时应该至少有一个 waiting 事件
    assert any(
        isinstance(x, dict) and x.get("event") == "waiting" for x in collected
    )

    release_holder.set()
    await holder_task
    await drv

    # 收集顺序：waiting (若干) → ready → business chunk 1 → business chunk 2
    events = [c for c in collected if isinstance(c, dict)]
    assert events[-1]["event"] == "ready"
    # 业务 chunk 也已收集
    assert any(isinstance(x, str) and "type" in x and "update" in x for x in collected)
    assert any(isinstance(x, str) and "type" in x and "end" in x for x in collected)


# =====================================================================
# 2026-06-15 新增：HITL 早期释放句柄
# =====================================================================


@pytest.mark.asyncio
async def test_sse_dependency_release_handle_releases_immediately_on_call(reset_singleton):
    """测试通过 concurrency_release_handle 主动释放：active_count 立即减 1。"""
    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()

    captured = {}

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    async def driver():
        async for item in chat_concurrency_dependency(_FakeRequest(), mode="sse"):
            if item is None:
                captured["handle"] = _FakeRequest().state.concurrency_release_handle
                captured["active_before"] = queue.active_count
                await _FakeRequest().state.concurrency_release_handle()
                captured["active_after"] = queue.active_count
                break
            # 跳过 queue 事件

    # 用 queue.acquire 占用许可
    await queue.acquire()
    drv = asyncio.create_task(driver())
    await asyncio.sleep(0.05)
    await drv

    assert captured["active_before"] == 1
    assert captured["active_after"] == 0


@pytest.mark.asyncio
async def test_sse_dependency_release_handle_is_idempotent(reset_singleton):
    """多次调用 release handle 不会重复释放。"""
    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()
    await queue.acquire()

    captured = {}

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    async def driver():
        async for item in chat_concurrency_dependency(_FakeRequest(), mode="sse"):
            if item is None:
                h = _FakeRequest().state.concurrency_release_handle
                await h()
                await h()  # 第二次
                await h()  # 第三次
                break

    drv = asyncio.create_task(driver())
    await asyncio.sleep(0.05)
    await drv
    # active_count 应该正好是 0，不应超量释放
    assert queue.active_count == 0


@pytest.mark.asyncio
async def test_sse_dependency_releases_on_hitl_interrupt_path(reset_singleton):
    """HITL 核心场景：业务生成器 yield interrupt → 路由在 yield 前调用 release_handle → active_count 立即归 0 → 第二个并发请求立即 acquire 成功。"""
    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()

    captured = {}

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    async def business_gen_with_interrupt() -> AsyncGenerator[str, None]:
        yield 'data: {"type":"update","data":{"x":1}}\n\n'
        # HITL interrupt 事件
        interrupt_chunk = 'data: {"type":"interrupt","data":{"requests":[]}}\n\n'

        # 模拟路由在 yield 前调用 release_handle
        h = _FakeRequest().state.concurrency_release_handle
        if h is not None:
            captured["active_before_handle"] = queue.active_count
            await h()
            captured["active_after_handle"] = queue.active_count
        yield interrupt_chunk
        return  # 结束流

    async def driver():
        async for item in chat_concurrency_dependency(_FakeRequest(), mode="sse"):
            if item is None:
                async for chunk in business_gen_with_interrupt():
                    collected.append(chunk)
                break
            collected.append(item)

    collected: List = []
    # 占用唯一许可
    await queue.acquire()
    drv = asyncio.create_task(driver())
    await asyncio.sleep(0.05)
    await drv

    assert captured["active_before_handle"] == 1
    assert captured["active_after_handle"] == 0
    # 许可释放后，第二个并发请求应该立即 acquire 成功（无排队）
    await asyncio.wait_for(queue.acquire(), timeout=0.5)
    assert queue.active_count == 1
    await queue.release()


@pytest.mark.asyncio
async def test_sse_dependency_finally_release_when_handle_never_called(reset_singleton):
    """客户端异常断开（handle 未调用）场景，依赖 finally 兜底 release。"""
    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    async def driver():
        # 直接退出 async for，不调用 release_handle
        async for item in chat_concurrency_dependency(_FakeRequest(), mode="sse"):
            if item is None:
                return
            # 跳过 queue 事件

    # 占用唯一许可
    await queue.acquire()
    assert queue.active_count == 1
    drv = asyncio.create_task(driver())
    await asyncio.sleep(0.05)
    # 让 driver 退出（拿到 None 后 return）
    await drv
    # finally 兜底：active_count 归 0
    await asyncio.sleep(0.05)
    assert queue.active_count == 0


# =====================================================================
# 2026-06-15 新增：HTTP 模式 429 即时拒绝
# =====================================================================


@pytest.mark.asyncio
async def test_http_dependency_raises_429_when_full(reset_singleton):
    """HTTP 模式满员时抛 429 + 排队详情。"""
    from fastapi import HTTPException

    AgentConcurrencyQueue(max_concurrency=1)
    queue = AgentConcurrencyQueue()

    # 占用唯一许可
    await queue.acquire()

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    with pytest.raises(HTTPException) as exc_info:
        async for _ in chat_concurrency_dependency(_FakeRequest(), mode="http"):
            pass  # 满员应立即抛 429，根本不会进入循环

    assert exc_info.value.status_code == 429
    detail = exc_info.value.detail
    assert detail["error"] == "queue_full"
    assert detail["max_concurrency"] == 1
    assert detail["active_count"] == 1
    assert "message" in detail

    await queue.release()


@pytest.mark.asyncio
async def test_http_dependency_yields_none_when_available(reset_singleton):
    """HTTP 模式无需等待时直接 yield None。"""
    AgentConcurrencyQueue(max_concurrency=1)

    class _FakeRequest:
        class _State:
            pass
        def __init__(self):
            self.state = self._State()

    items = []
    async for item in chat_concurrency_dependency(_FakeRequest(), mode="http"):
        items.append(item)
    assert items == [None]
    assert AgentConcurrencyQueue().active_count == 0