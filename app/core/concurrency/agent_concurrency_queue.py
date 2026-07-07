# -*- coding:utf-8 -*-
"""
Agent 聊天并发队列

基于 asyncio.Future 实现严格 FIFO 的纯内存并发控制。
单例模式，全局共享同一队列实例。

扩展能力（2026-06-15）：
- enqueue_time：当前请求入队时间戳
- position()：当前调用方在 FIFO 队列中的位置（1-based）
- snapshot()：返回 {active_count, waiting_count, max_concurrency} 快照

核心修复（2026-06-22）：
- 用 FIFO Future 队列替代 asyncio.Semaphore 的自由竞争，杜绝「后入队先获得许可」
  以及「多个 waiter 被同时唤醒后竞争导致同时进入」的乱序问题。
- release() 仅唤醒 FIFO 队列中的下一个有效 waiter；若该 waiter 已取消，则顺延。
- slot_freed 事件保留，用于 SSE 轮询在槽位释放后即时重新 snapshot。
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)


class _Waiter:
    """
    FIFO 等待者内部结构。

    属性:
        task: 等待的 asyncio.Task 对象
        future: 用于唤醒该等待者的 Future
        enqueue_time: 入队时间戳（time.monotonic()）
    """

    def __init__(self, task: asyncio.Task):
        """
        初始化等待者。

        参数:
            task: 关联的 asyncio.Task
        """
        self.task = task
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.enqueue_time: float = time.monotonic()


class AgentConcurrencyQueue:
    """
    Agent 聊天并发队列

    限制同时处理的 Agent 聊天请求数量，超出上限时进入严格 FIFO 队列等待。

    注意:
        本类为单例模式。仅首次构造时传入的 ``max_concurrency`` 会生效，
        后续构造将直接返回已创建的实例，传入的 ``max_concurrency`` 参数会被忽略。
    """

    _instance: Optional["AgentConcurrencyQueue"] = None

    def __new__(cls, max_concurrency: int = 3) -> "AgentConcurrencyQueue":
        """
        单例构造

        仅首次构造时 ``max_concurrency`` 会生效；后续构造将返回同一实例，
        并忽略传入的 ``max_concurrency`` 参数。

        参数:
            max_concurrency: 最大并发数，必须大于 0（仅在首次构造时生效）

        返回:
            AgentConcurrencyQueue: 单例实例

        异常:
            ValueError: 当 max_concurrency 小于等于 0 时
        """
        if max_concurrency <= 0:
            raise ValueError("max_concurrency 必须大于 0")

        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize(max_concurrency)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        重置单例实例（仅用于测试）

        返回:
            None
        """
        cls._instance = None

    def _initialize(self, max_concurrency: int) -> None:
        """
        初始化队列内部状态

        参数:
            max_concurrency: 最大并发数
        """
        self._max_concurrency = max_concurrency
        self._active_count = 0
        self._waiting_count = 0
        self._active_lock = asyncio.Lock()
        # 按 FIFO 顺序保存已预注册或正在等待的 task 对应的 _Waiter 对象。
        self._waiters: Deque[_Waiter] = deque()
        # task -> _Waiter 的快速索引（用于 position / snapshot / 取消清理）。
        self._waiter_index: Dict[asyncio.Task, _Waiter] = {}
        # task -> 入队时间戳。
        self._enqueue_times: Dict[asyncio.Task, float] = {}
        # 槽位释放事件，供 SSE 轮询即时唤醒。
        self._slot_freed = asyncio.Event()
        self._slot_freed.set()

    @property
    def max_concurrency(self) -> int:
        """获取最大并发数"""
        return self._max_concurrency

    @property
    def active_count(self) -> int:
        """获取当前活跃请求数"""
        return self._active_count

    @property
    def waiting_count(self) -> int:
        """获取当前等待请求数"""
        return self._waiting_count

    def enqueue_time(self, task: Optional[asyncio.Task] = None) -> Optional[float]:
        """
        获取指定 task（或当前 task）的入队时间戳（time.monotonic()，秒）。

        参数:
            task: asyncio.Task 对象；默认 None 时取当前 task

        返回:
            入队时间戳；如果 task 未在等待队列中，返回 None
        """
        if task is None:
            task = asyncio.current_task()
        if task is None:
            return None
        return self._enqueue_times.get(task)

    async def position(self, task: Optional[asyncio.Task] = None) -> int:
        """
        获取指定 task 在 FIFO 等待队列中的位置（1-based）。

        - 位置 1 表示自己是下一个将被激活的请求
        - 位置 N 表示自己前面还有 N-1 个请求
        - 如果 task 已经获得许可（不处于等待状态），返回 0
        - 如果 task 未注册，返回 -1

        参数:
            task: asyncio.Task 对象；默认 None 时取当前 task

        返回:
            位置（1-based）；未注册返回 -1；已激活返回 0
        """
        if task is None:
            task = asyncio.current_task()
        if task is None:
            return -1
        async with self._active_lock:
            waiter = self._waiter_index.get(task)
            if waiter is not None:
                # 通过 deque 索引计算位置（O(n)，n 为等待人数，可接受）
                for idx, w in enumerate(self._waiters):
                    if w is waiter:
                        return idx + 1
                # 理论上不会出现：索引存在但不在 _waiters 中
                return 0
            # 不在等待队列中：若当前有活跃请求，则认为已激活
            return 0 if self._active_count > 0 else -1

    async def snapshot(self, task: Optional[asyncio.Task] = None) -> Dict[str, Any]:
        """
        获取当前队列的快照字典。

        参数:
            task: asyncio.Task 对象；用于计算 position；默认 None 时取当前 task

        返回:
            dict: {
                "active_count": int,
                "waiting_count": int,
                "max_concurrency": int,
                "position": int,  # 1-based；未注册为 -1；已激活为 0
                "enqueue_time": float | None,
                "timestamp": float,  # 快照生成时刻
            }
        """
        if task is None:
            task = asyncio.current_task()
        async with self._active_lock:
            active = self._active_count
            waiting = self._waiting_count
            max_c = self._max_concurrency
            pos = -1
            waiter = self._waiter_index.get(task) if task else None
            if waiter is not None:
                for idx, w in enumerate(self._waiters):
                    if w is waiter:
                        pos = idx + 1
                        break
            if pos == -1:
                pos = 0 if self._active_count > 0 else -1
            enq = self._enqueue_times.get(task) if task else None
        return {
            "active_count": active,
            "waiting_count": waiting,
            "max_concurrency": max_c,
            "position": pos,
            "enqueue_time": enq,
            "timestamp": time.time(),
        }

    @property
    def slot_freed(self) -> asyncio.Event:
        """获取槽位释放事件（用于 SSE 轮询即时唤醒）。"""
        return self._slot_freed

    async def enqueue(self, task: Optional[asyncio.Task] = None) -> None:
        """
        预注册当前 task 到 FIFO 等待队列（不阻塞）。

        用于 SSE 模式：在真正调用 acquire() 阻塞之前，先把请求登记进 _waiters，
        使 snapshot()/position() 能在排队期间正确计算「前面还有几人」。
        同一 task 多次调用仅计数一次（幂等）。

        参数:
            task: asyncio.Task 对象；默认 None 时取当前 task

        返回:
            None
        """
        if task is None:
            task = asyncio.current_task()
        if task is None:
            return
        async with self._active_lock:
            if task in self._waiter_index:
                return
            waiter = _Waiter(task)
            self._waiters.append(waiter)
            self._waiter_index[task] = waiter
            self._waiting_count += 1
            self._enqueue_times[task] = waiter.enqueue_time
        logger.debug(
            "[AgentConcurrencyQueue] task 预注册成功，当前活跃=%d，等待=%d",
            self._active_count,
            self._waiting_count,
        )

    async def acquire(self, task: Optional[asyncio.Task] = None) -> None:
        """
        获取一个并发许可。

        当活跃请求数达到上限时，调用方会进入 FIFO 等待。
        若本 task 已通过 enqueue() 预注册，则不会重复增加 waiting_count。
        只有 FIFO 队列中的第一个有效 waiter 才能在槽位空闲时被授予许可。

        参数:
            task: asyncio.Task 对象；默认 None 时取当前 task
        """
        if task is None:
            task = asyncio.current_task()
        if task is None:
            raise RuntimeError("acquire 必须在 asyncio.Task 中调用")

        async with self._active_lock:
            waiter = self._waiter_index.get(task)
            if waiter is None:
                # 未预注册，现场加入队列
                waiter = _Waiter(task)
                self._waiters.append(waiter)
                self._waiter_index[task] = waiter
                self._waiting_count += 1
                self._enqueue_times[task] = waiter.enqueue_time
            else:
                # 已预注册，确保 enqueue_time 存在
                if task not in self._enqueue_times:
                    self._enqueue_times[task] = waiter.enqueue_time

            # 若自己是队列中第一个 waiter 且槽位空闲，立即获得许可
            if (
                self._active_count < self._max_concurrency
                and self._waiters
                and self._waiters[0] is waiter
            ):
                self._active_count += 1
                self._waiting_count -= 1
                self._waiters.popleft()
                self._waiter_index.pop(task, None)
                # 获得许可后清除释放信号，便于下次 release 重新触发
                self._slot_freed.clear()
                logger.debug(
                    "[AgentConcurrencyQueue] 立即获取许可成功，当前活跃=%d，等待=%d",
                    self._active_count,
                    self._waiting_count,
                )
                return

            # 需要等待：Future 已在 _Waiter 中创建
            future = waiter.future

        logger.debug(
            "[AgentConcurrencyQueue] 进入 FIFO 等待，当前活跃=%d，等待=%d",
            self._active_count,
            self._waiting_count,
        )
        try:
            await future
        except asyncio.CancelledError:
            # 等待中被取消：清理本 waiter，避免死锁或计数泄漏
            async with self._active_lock:
                self._remove_waiter(task)
            logger.debug(
                "[AgentConcurrencyQueue] 等待获取许可被取消，当前活跃=%d，等待=%d",
                self._active_count,
                self._waiting_count,
            )
            raise

    async def release(self, task: Optional[asyncio.Task] = None) -> None:
        """
        释放一个并发许可。

        释放后按 FIFO 顺序唤醒下一个有效 waiter 并授予许可；
        若等待队列中无有效 waiter，则减少 active_count 让出空槽。
        当活跃计数已经为 0 时，跳过释放，避免计数异常。

        参数:
            task: asyncio.Task 对象；默认 None 时取当前 task（仅用于日志/清理）
        """
        current_task: Optional[asyncio.Task] = task if task is not None else asyncio.current_task()
        async with self._active_lock:
            if self._active_count <= 0:
                logger.warning("[AgentConcurrencyQueue] 释放许可时活跃计数已为 0，跳过释放")
                return

            # 尝试将许可转移给 FIFO 中的下一个有效 waiter
            granted = False
            while self._waiters:
                next_waiter = self._waiters.popleft()
                next_task = next_waiter.task
                self._waiter_index.pop(next_task, None)
                self._waiting_count -= 1
                future = next_waiter.future
                if future is not None and not future.done():
                    future.set_result(None)
                    granted = True
                    logger.debug(
                        "[AgentConcurrencyQueue] 将许可转移给下一个 waiter，当前活跃=%d，等待=%d",
                        self._active_count,
                        self._waiting_count,
                    )
                    break
                # 若该 waiter 已取消/完成，顺延下一个
                logger.debug(
                    "[AgentConcurrencyQueue] 跳过已失效 waiter，顺延下一个"
                )

            if not granted:
                # 没有可唤醒的 waiter，真正释放槽位
                self._active_count -= 1
                logger.debug(
                    "[AgentConcurrencyQueue] 释放许可成功，当前活跃=%d，等待=%d",
                    self._active_count,
                    self._waiting_count,
                )

            # 清理释放者自身的入队时间戳
            if current_task is not None:
                self._enqueue_times.pop(current_task, None)

            # 通知正在轮询的 SSE 请求：槽位状态已变化，可立即重新 snapshot
            self._slot_freed.set()

    def _remove_waiter(self, task: asyncio.Task) -> None:
        """
        从等待队列中移除指定 task 并清理相关状态（必须在 _active_lock 内调用）。

        参数:
            task: 要移除的 asyncio.Task
        """
        waiter = self._waiter_index.pop(task, None)
        if waiter is not None:
            try:
                self._waiters.remove(waiter)
            except ValueError:
                pass
            self._waiting_count -= 1
            if waiter.future is not None and not waiter.future.done():
                waiter.future.cancel()
        self._enqueue_times.pop(task, None)

    async def __aenter__(self) -> "AgentConcurrencyQueue":
        """异步上下文管理器入口"""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.release()
