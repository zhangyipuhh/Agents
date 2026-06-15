# -*- coding:utf-8 -*-
"""
AgentConcurrencyQueue 单元测试
"""

import asyncio
import pytest

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue


@pytest.fixture
def reset_singleton():
    """重置单例实例"""
    AgentConcurrencyQueue._instance = None
    AgentConcurrencyQueue._lock = asyncio.Lock()
    yield
    AgentConcurrencyQueue._instance = None
    AgentConcurrencyQueue._lock = asyncio.Lock()


@pytest.mark.asyncio
async def test_concurrency_queue_acquire_release(reset_singleton):
    """测试获取和释放许可"""
    queue = AgentConcurrencyQueue(max_concurrency=2)
    async with queue:
        assert queue.active_count == 1
    assert queue.active_count == 0


@pytest.mark.asyncio
async def test_concurrency_queue_waits_when_full(reset_singleton):
    """测试超出并发数时进入队列等待"""
    queue = AgentConcurrencyQueue(max_concurrency=1)
    order = []

    async def worker(name):
        async with queue:
            order.append(f"{name}-start")
            await asyncio.sleep(0.05)
            order.append(f"{name}-end")

    await asyncio.gather(worker("a"), worker("b"))
    assert order == ["a-start", "a-end", "b-start", "b-end"]
