# -*- coding:utf-8 -*-
"""
Agent 聊天并发队列

基于 asyncio.Semaphore 实现纯内存并发控制。
单例模式，全局共享同一队列实例。

扩展能力（2026-06-15）：
- enqueue_time：当前请求入队时间戳
- position()：当前调用方在 FIFO 队列中的位置（1-based）
- snapshot()：返回 {active_count, waiting_count, max_concurrency} 快照
- _waiter_tasks + _enqueue_times：维护等待者有序列表，供 position() 与 snapshot() 协同
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentConcurrencyQueue:
    """
    Agent 聊天并发队列

    限制同时处理的 Agent 聊天请求数量，超出上限时进入 FIFO 队列等待。

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

        Args:
            max_concurrency: 最大并发数，必须大于 0（仅在首次构造时生效）

        Returns:
            AgentConcurrencyQueue: 单例实例

        Raises:
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

        Returns:
            None
        """
        cls._instance = None

    def _initialize(self, max_concurrency: int) -> None:
        """
        初始化队列内部状态

        Args:
            max_concurrency: 最大并发数
        """
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active_count = 0
        self._waiting_count = 0
        self._active_lock = asyncio.Lock()
        # 2026-06-15 新增：按 FIFO 顺序记录当前所有等待者 task；
        # _enqueue_times 与之平行记录各 task 入队时间戳（秒，time.monotonic()）。
        self._waiter_tasks: List[asyncio.Task] = []
        self._enqueue_times: Dict[asyncio.Task, float] = {}
        # 2026-06-22 新增：槽位释放事件，供 SSE 轮询在槽位空闲时即时唤醒。
        self._slot_freed = asyncio.Event()

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

        Args:
            task: asyncio.Task 对象；默认 None 时取当前 task

        Returns:
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

        Args:
            task: asyncio.Task 对象；默认 None 时取当前 task

        Returns:
            位置（1-based）；未注册返回 -1；已激活返回 0
        """
        if task is None:
            task = asyncio.current_task()
        if task is None:
            return -1
        async with self._active_lock:
            try:
                idx = self._waiter_tasks.index(task)
                return idx + 1
            except ValueError:
                # 不在等待列表，可能已激活或从未入队
                return 0 if self._active_count > 0 else -1

    async def snapshot(self, task: Optional[asyncio.Task] = None) -> Dict[str, Any]:
        """
        获取当前队列的快照字典。

        Args:
            task: asyncio.Task 对象；用于计算 position；默认 None 时取当前 task

        Returns:
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
            try:
                pos = self._waiter_tasks.index(task) + 1 if task else -1
            except ValueError:
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

        用于 SSE 模式：在真正调用 acquire() 阻塞之前，先把请求登记进 _waiter_tasks，
        使 snapshot()/position() 能在排队期间正确计算「前面还有几人」。
        同一 task 多次调用仅计数一次（幂等）。

        Args:
            task: asyncio.Task 对象；默认 None 时取当前 task

        Returns:
            None
        """
        if task is None:
            task = asyncio.current_task()
        if task is None:
            return
        async with self._active_lock:
            if task in self._waiter_tasks:
                return
            self._waiting_count += 1
            self._waiter_tasks.append(task)
            self._enqueue_times[task] = time.monotonic()
        logger.debug(
            "[AgentConcurrencyQueue] task 预注册成功，当前活跃=%d，等待=%d",
            self._active_count,
            self._waiting_count,
        )

    async def acquire(self) -> None:
        """
        获取一个并发许可

        当活跃请求数达到上限时，调用方会进入 FIFO 等待。
        若本 task 已通过 enqueue() 预注册，则不会重复增加 waiting_count。
        """
        current_task: Optional[asyncio.Task] = asyncio.current_task()
        logger.debug("[AgentConcurrencyQueue] 请求获取许可，当前活跃=%d，等待=%d", self._active_count, self._waiting_count)
        async with self._active_lock:
            if current_task is not None and current_task in self._waiter_tasks:
                # 已预注册，无需重复计数；semaphore 尚未 acquire
                pass
            else:
                self._waiting_count += 1
                if current_task is not None:
                    self._waiter_tasks.append(current_task)
                    self._enqueue_times[current_task] = time.monotonic()
        acquired = False
        try:
            await self._semaphore.acquire()
            acquired = True
            async with self._active_lock:
                self._active_count += 1
                self._waiting_count -= 1
                # 成功占用槽位后清除释放信号，便于下次 release 重新触发
                self._slot_freed.clear()
                if current_task is not None:
                    # 从等待列表移除（保留 enqueue_times 直到 release 后清理）
                    try:
                        self._waiter_tasks.remove(current_task)
                    except ValueError:
                        pass
            logger.debug("[AgentConcurrencyQueue] 获取许可成功，当前活跃=%d，等待=%d", self._active_count, self._waiting_count)
        finally:
            if not acquired:
                async with self._active_lock:
                    # 只有真正阻塞过 waiting_count 才需要回滚；
                    # 若通过 enqueue 预注册后 acquire 被取消，enqueue 时加的 waiting_count 也需扣回。
                    if current_task is not None and current_task in self._waiter_tasks:
                        self._waiting_count -= 1
                        try:
                            self._waiter_tasks.remove(current_task)
                        except ValueError:
                            pass
                        self._enqueue_times.pop(current_task, None)
                    elif self._waiting_count > 0:
                        self._waiting_count -= 1
                logger.debug("[AgentConcurrencyQueue] 获取许可被取消，当前活跃=%d，等待=%d", self._active_count, self._waiting_count)

    async def release(self) -> None:
        """
        释放一个并发许可

        释放后等待队列中的下一个请求将获取许可并继续执行。
        当活跃计数已经为 0 时，跳过释放，避免信号量值超过最大并发数。
        """
        current_task: Optional[asyncio.Task] = asyncio.current_task()
        async with self._active_lock:
            if self._active_count > 0:
                self._active_count -= 1
                self._semaphore.release()
                # 通知正在轮询的 SSE 请求：槽位已空闲，可立即尝试 acquire
                self._slot_freed.set()
                if current_task is not None:
                    self._enqueue_times.pop(current_task, None)
                logger.debug("[AgentConcurrencyQueue] 释放许可成功，当前活跃=%d", self._active_count)
            else:
                logger.warning("[AgentConcurrencyQueue] 释放许可时活跃计数已为 0，跳过释放")

    async def __aenter__(self) -> "AgentConcurrencyQueue":
        """异步上下文管理器入口"""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.release()