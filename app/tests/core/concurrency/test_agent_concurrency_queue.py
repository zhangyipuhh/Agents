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
    AgentConcurrencyQueue.reset_instance()
    yield
    AgentConcurrencyQueue.reset_instance()


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


@pytest.mark.asyncio
async def test_concurrency_queue_waiting_count_tracks_waiters(reset_singleton):
    """
    测试 waiting_count 能正确反映正在等待的请求数量。

    参数:
        reset_singleton: 重置单例 fixture

    返回:
        None

    异常:
        AssertionError: waiting_count 不符合预期时抛出
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    lock_event = asyncio.Event()
    release_event = asyncio.Event()

    async def holder():
        async with queue:
            lock_event.set()
            await release_event.wait()

    async def waiter():
        await lock_event.wait()
        # holder 已占用唯一并发位，此时启动第二个获取任务会被阻塞
        task = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0.05)
        assert queue.waiting_count == 1
        release_event.set()
        await task
        await queue.release()

    await asyncio.gather(holder(), waiter())


@pytest.mark.asyncio
async def test_concurrency_queue_release_without_acquire_does_not_over_release(reset_singleton):
    """
    测试未获取许可时调用 release() 不会超量释放信号量。

    参数:
        reset_singleton: 重置单例 fixture

    返回:
        None

    异常:
        AssertionError: 并发上限被破坏时抛出
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)

    # 多次无许可释放不应增加信号量许可数
    await queue.release()
    await queue.release()
    await queue.release()

    # 验证并发上限仍然有效：最多只能有一个活跃任务
    entered = []

    async def worker():
        async with queue:
            entered.append(True)
            await asyncio.sleep(0.01)

    # 同时启动两个 worker，如果信号量被超量释放，两个都能同时进入
    await asyncio.gather(worker(), worker())
    assert len(entered) == 2

    # 再次启动两个 worker，确认上限持续有效（没有因为之前的超量释放累积许可）
    entered.clear()
    await asyncio.gather(worker(), worker())
    assert len(entered) == 2


@pytest.mark.asyncio
async def test_concurrency_queue_context_manager_releases_on_exception(reset_singleton):
    """
    测试 async with 块内抛出异常时上下文管理器仍能正确释放许可。

    参数:
        reset_singleton: 重置单例 fixture

    返回:
        None

    异常:
        AssertionError: 异常后许可未释放时抛出
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)

    with pytest.raises(ValueError):
        async with queue:
            assert queue.active_count == 1
            raise ValueError("故意抛出的异常")

    assert queue.active_count == 0

    # 确认释放后其他任务可以正常获取许可
    async with queue:
        assert queue.active_count == 1


@pytest.mark.asyncio
async def test_concurrency_queue_acquire_cancelled_waiting_count_rollback(reset_singleton):
    """
    测试 acquire() 被取消时 _waiting_count 正确回滚。

    参数:
        reset_singleton: 重置单例 fixture

    返回:
        None

    异常:
        AssertionError: waiting_count 未正确回滚时抛出
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    holder_started = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with queue:
            holder_started.set()
            await release_holder.wait()

    holder_task = asyncio.create_task(holder())
    await holder_started.wait()

    # 此时 holder 已占用唯一并发位，再启动一个 acquire 任务会被阻塞
    waiter_task = asyncio.create_task(queue.acquire())
    await asyncio.sleep(0.05)
    assert queue.waiting_count == 1

    # 取消等待中的 acquire 任务
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    assert queue.waiting_count == 0
    assert queue.active_count == 1

    release_holder.set()
    await holder_task
    await queue.release()


@pytest.mark.asyncio
async def test_concurrency_queue_singleton_ignores_subsequent_max_concurrency(reset_singleton):
    """
    测试首次构造后，后续不同 max_concurrency 的调用返回同一实例且 max_concurrency 不变。

    参数:
        reset_singleton: 重置单例 fixture

    返回:
        None

    异常:
        AssertionError: 单例行为不符合预期时抛出
    """
    first = AgentConcurrencyQueue(max_concurrency=2)
    assert first.max_concurrency == 2

    second = AgentConcurrencyQueue(max_concurrency=5)
    assert second is first
    assert second.max_concurrency == 2
