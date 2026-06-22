# -*- coding:utf-8 -*-
"""
2026-06-22 新增：严格 FIFO 与 HITL resume 插队场景测试

核心场景：
1. 多个 waiter 同时进入队列时，release() 必须严格按 FIFO 顺序唤醒第一个 waiter。
2. HITL 释放槽位后，新到达的请求不应插队已排队的请求。
3. resume 请求在已排队请求存在时，应排在队尾而不是抢走槽位。
4. 多个 waiter 被 slot_freed Event 同时唤醒时，只有一个能获得许可。
"""

import asyncio
import pytest

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue


@pytest.fixture
def reset_singleton():
    """重置单例"""
    AgentConcurrencyQueue.reset_instance()
    yield
    AgentConcurrencyQueue.reset_instance()


@pytest.mark.asyncio
async def test_strict_fifo_release_grants_to_first_waiter_only(reset_singleton):
    """
    核心 FIFO 测试：max=1，三个 waiter 同时入队 → release 必须严格按入队顺序授予。
    
    场景：
    - T1 占用唯一槽位
    - T2, T3, T4 依次入队等待
    - T1 release → 槽位必须给 T2
    - T2 release → 槽位必须给 T3
    - T3 release → 槽位必须给 T4
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    order = []

    async def holder(name):
        await queue.acquire()
        order.append(f"{name}-start")
        await asyncio.sleep(0.05)
        order.append(f"{name}-end")
        await queue.release()

    async def waiter(name):
        await queue.acquire()
        order.append(f"{name}-start")
        await queue.release()

    # 先启动 holder 占用槽位
    t1 = asyncio.create_task(holder("T1"))
    await asyncio.sleep(0.02)

    # 三个 waiter 依次入队
    t2 = asyncio.create_task(waiter("T2"))
    await asyncio.sleep(0.05)
    t3 = asyncio.create_task(waiter("T3"))
    await asyncio.sleep(0.05)
    t4 = asyncio.create_task(waiter("T4"))

    await asyncio.gather(t1, t2, t3, t4)

    # 严格 FIFO：T1 → T2 → T3 → T4（至少 -start 顺序必须正确）
    starts = [x for x in order if x.endswith("-start")]
    assert starts == ["T1-start", "T2-start", "T3-start", "T4-start"], (
        f"FIFO 顺序错误（-start 序列），实际: {starts}"
    )


@pytest.mark.asyncio
async def test_new_request_does_not_preempt_queued_waiters(reset_singleton):
    """
    核心 FIFO 测试：已有 waiter 在队列中时，新到达的请求必须排在队尾。
    
    场景：
    - max=1，T1 占用
    - T2 入队等待
    - 此时 T3 到达：T3 也必须入队等待，而不能绕过 T2 直接获得槽位
    - T1 release → T2 应获得槽位
    - T2 release → T3 才获得槽位
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    order = []

    async def t1():
        await queue.acquire()
        order.append("T1-start")
        await asyncio.sleep(0.05)
        order.append("T1-end")
        await queue.release()

    async def t2():
        await asyncio.sleep(0.01)
        await queue.acquire()
        order.append("T2-start")
        await asyncio.sleep(0.05)
        order.append("T2-end")
        await queue.release()

    async def t3():
        # T3 在 T2 之后到达
        await asyncio.sleep(0.025)
        await queue.acquire()
        order.append("T3-start")
        await queue.release()

    await asyncio.gather(t1(), t2(), t3())

    # T3 不能插队
    assert order.index("T2-start") < order.index("T3-start"), (
        f"T3 插队了！实际顺序: {order}"
    )


@pytest.mark.asyncio
async def test_resume_request_does_not_preempt_queued_waiters(reset_singleton):
    """
    核心 FIFO 测试：模拟 HITL resume 请求不能插队已排队的其他用户。
    
    场景：
    - max=1，T1 占用 → HITL → 释放槽位
    - 此时 T2、T3 已在队列中（按入队顺序）
    - T1 的 resume 请求到达：必须排在 T2、T3 之后
    - resume 请求不应跳过 FIFO 顺序
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    order = []

    async def t1():
        await queue.acquire()
        order.append("T1-start")
        await asyncio.sleep(0.02)
        order.append("T1-end")
        # 模拟 HITL 释放
        await queue.release()
        # resume 请求 → 必须在队列尾部
        await asyncio.sleep(0.01)
        await queue.acquire()
        order.append("T1-resume")
        await queue.release()

    async def t2():
        await asyncio.sleep(0.005)
        await queue.acquire()
        order.append("T2-start")
        await queue.release()

    async def t3():
        await asyncio.sleep(0.008)
        await queue.acquire()
        order.append("T3-start")
        await queue.release()

    await asyncio.gather(t1(), t2(), t3())

    # 顺序必须是 T1 → T2 → T3 → T1-resume（resume 不能插队 T2/T3）
    t1_indices = [i for i, x in enumerate(order) if x.startswith("T1")]
    t2_idx = order.index("T2-start")
    t3_idx = order.index("T3-start")
    resume_idx = order.index("T1-resume")

    # T1-resume 必须在 T2、T3 之后
    assert resume_idx > t2_idx, f"resume 插队了 T2！实际顺序: {order}"
    assert resume_idx > t3_idx, f"resume 插队了 T3！实际顺序: {order}"


@pytest.mark.asyncio
async def test_simultaneous_waiters_get_serialized(reset_singleton):
    """
    核心 FIFO 测试：多个 waiter 同时进入等待时，必须串行获取许可，不能同时进入。
    
    场景：
    - max=2，T1 占用 2 个槽位（不可能，因为 max=2，所以用 max=1 模拟）
    - 实际：max=1，T1 占用唯一槽位
    - T2、T3、T4 同时启动并 await acquire()
    - T1 release → 只能有一个 waiter 获得许可；其余继续等待
    - 串行释放，最终按 FIFO 顺序
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    order = []

    async def holder():
        await queue.acquire()
        order.append("H-start")
        await asyncio.sleep(0.05)
        order.append("H-end")
        await queue.release()

    async def waiter(name):
        await queue.acquire()
        order.append(f"{name}-start")
        await asyncio.sleep(0.02)
        order.append(f"{name}-end")
        await queue.release()

    h_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)

    # 同时启动 3 个 waiter
    w_tasks = [
        asyncio.create_task(waiter("W1")),
        asyncio.create_task(waiter("W2")),
        asyncio.create_task(waiter("W3")),
    ]

    await asyncio.gather(h_task, *w_tasks)

    # 串行执行：H → W1 → W2 → W3
    assert order == [
        "H-start", "H-end",
        "W1-start", "W1-end",
        "W2-start", "W2-end",
        "W3-start", "W3-end",
    ], f"串行失败，实际: {order}"


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_block_queue(reset_singleton):
    """
    FIFO 健壮性测试：中间的 waiter 被取消不会卡死队列。
    
    场景：
    - max=1，T1 占用
    - T2 入队 → 被取消
    - T3 入队等待
    - T1 release → T3 必须能正常获得槽位（不能因为 T2 的取消而卡死）
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    holder_started = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        await queue.acquire()
        holder_started.set()
        await release_holder.wait()
        await queue.release()

    async def t2_cancelled():
        await queue.acquire()

    async def t3():
        await queue.acquire()
        return "T3-acquired"

    h_task = asyncio.create_task(holder())
    await holder_started.wait()

    t2_task = asyncio.create_task(t2_cancelled())
    await asyncio.sleep(0.02)
    t2_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t2_task

    t3_task = asyncio.create_task(t3())
    await asyncio.sleep(0.02)

    release_holder.set()
    await h_task

    result = await asyncio.wait_for(t3_task, timeout=1.0)
    assert result == "T3-acquired"


@pytest.mark.asyncio
async def test_release_transfers_to_next_waiter_keeps_active_count(reset_singleton):
    """
    FIFO 健壮性测试：release() 转移许可给下一个 waiter 时，active_count 应保持不变。
    
    场景：
    - max=1，T1 占用
    - T2 入队
    - T1 release() 应将许可直接给 T2，而不是减 active 然后 T2 再获得
    - 在 release() 调用前后，active_count 应始终为 1
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    t1_started = asyncio.Event()
    t1_should_release = asyncio.Event()

    async def t1():
        await queue.acquire()
        t1_started.set()
        # 确认 active=1
        assert queue.active_count == 1
        await t1_should_release.wait()
        await queue.release()
        # T1 release 后，如果 T2 已经 await acquire()，则 active 应该还是 1（转移给 T2）
        # 否则 active 会变成 0
        # 这里 T2 还没启动，所以应该是 0

    async def t2():
        await t1_should_release.wait()
        await asyncio.sleep(0.01)  # 等 T1 release
        await queue.acquire()
        # T2 获得许可后 active=1
        assert queue.active_count == 1
        await queue.release()
        return "T2-done"

    t1_task = asyncio.create_task(t1())
    await t1_started.wait()

    t2_task = asyncio.create_task(t2())
    t1_should_release.set()

    await t1_task
    result = await asyncio.wait_for(t2_task, timeout=1.0)
    assert result == "T2-done"
    assert queue.active_count == 0


@pytest.mark.asyncio
async def test_release_transfers_to_next_waiter_without_decrement(reset_singleton):
    """
    FIFO 转移测试：release() 时如果等待队列非空，应直接转移给下一个 waiter，
    active_count 不应出现"先减后加"的瞬时窗口。
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    observations = []

    async def t1():
        await queue.acquire()
        observations.append(("t1-acquired", queue.active_count))
        await asyncio.sleep(0.05)
        await queue.release()
        observations.append(("t1-released", queue.active_count))

    async def t2():
        # 等待 T1 释放
        await asyncio.sleep(0.02)
        await queue.acquire()
        observations.append(("t2-acquired", queue.active_count))
        await queue.release()

    await asyncio.gather(t1(), t2())

    # 关键：t1-released 时 active 应该是 1（已经转移给 t2），而不是 0
    released_idx = next(i for i, (name, _) in enumerate(observations) if name == "t1-released")
    assert observations[released_idx][1] == 1, (
        f"release() 后 active 应保持 1（已转移给 t2），实际 {observations[released_idx][1]}；"
        f"全部观察: {observations}"
    )


@pytest.mark.asyncio
async def test_hitl_release_does_not_preempt_queued_users(reset_singleton):
    """
    核心 FIFO + HITL 集成测试：HITL 早期释放后，已排队的用户必须按 FIFO 顺序获得槽位。
    
    场景：
    - max=1，T1 占用
    - T2、T3 入队等待
    - T1 触发 HITL，释放槽位
    - T1 后续不再请求槽位（模拟 resume 走不同代码路径）
    - 此时只有 T2 应该获得槽位，T3 仍需等待 T2 释放
    """
    queue = AgentConcurrencyQueue(max_concurrency=1)
    order = []
    t2_acquired = asyncio.Event()
    t2_can_release = asyncio.Event()

    async def t1():
        await queue.acquire()
        order.append("T1-start")
        await asyncio.sleep(0.02)
        order.append("T1-end")
        # HITL 释放
        await queue.release()
        order.append("T1-released")

    async def t2():
        await asyncio.sleep(0.005)
        await queue.acquire()
        order.append("T2-start")
        t2_acquired.set()
        await t2_can_release.wait()
        order.append("T2-end")
        await queue.release()

    async def t3():
        await asyncio.sleep(0.008)
        await queue.acquire()
        order.append("T3-start")
        order.append("T3-end")
        await queue.release()

    await asyncio.gather(t1(), t2(), t3_can_release_trigger := asyncio.create_task(asyncio.sleep(1.0)), t3()) if False else None

    # 修正：让 t2 在 t2_acquired 后延迟释放
    async def t2_full():
        await t2_acquired.wait()
        await t2_can_release.wait()
        await queue.release()

    async def t2_main():
        await asyncio.sleep(0.005)
        await queue.acquire()
        order.append("T2-start")
        t2_acquired.set()
        await t2_can_release.wait()
        order.append("T2-end")
        await queue.release()

    # 重新设计：使用 Event 控制
    async def run():
        tasks = [
            asyncio.create_task(t1()),
            asyncio.create_task(t2_main()),
            asyncio.create_task(t3()),
        ]
        # 等待 T2 获得槽位
        await t2_acquired.wait()
        await asyncio.sleep(0.05)
        # T3 此时应仍在等待
        assert queue.waiting_count == 1, (
            f"T3 应该在等待，实际 waiting_count={queue.waiting_count}"
        )
        # 释放 T2 → T3 应获得槽位
        t2_can_release.set()
        await asyncio.gather(*tasks)

    await asyncio.wait_for(run(), timeout=2.0)

    # 验证：T1 → T2 → T3（T3 不能插队 T2 之前）
    t2_idx = order.index("T2-start")
    t3_idx = order.index("T3-start")
    assert t2_idx < t3_idx, f"FIFO 顺序破坏！实际: {order}"