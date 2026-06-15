# -*- coding:utf-8 -*-
"""
Agent 聊天并发队列

基于 asyncio.Semaphore 实现纯内存并发控制。
单例模式，全局共享同一队列实例。
"""

import asyncio
import logging
from typing import Optional

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

    async def acquire(self) -> None:
        """
        获取一个并发许可

        当活跃请求数达到上限时，调用方会进入 FIFO 等待。
        """
        logger.debug("[AgentConcurrencyQueue] 请求获取许可，当前活跃=%d，等待=%d", self._active_count, self._waiting_count)
        async with self._active_lock:
            self._waiting_count += 1
        acquired = False
        try:
            await self._semaphore.acquire()
            acquired = True
            async with self._active_lock:
                self._active_count += 1
                self._waiting_count -= 1
            logger.debug("[AgentConcurrencyQueue] 获取许可成功，当前活跃=%d，等待=%d", self._active_count, self._waiting_count)
        finally:
            if not acquired:
                async with self._active_lock:
                    self._waiting_count -= 1
                logger.debug("[AgentConcurrencyQueue] 获取许可被取消，当前活跃=%d，等待=%d", self._active_count, self._waiting_count)

    async def release(self) -> None:
        """
        释放一个并发许可

        释放后等待队列中的下一个请求将获取许可并继续执行。
        当活跃计数已经为 0 时，跳过释放，避免信号量值超过最大并发数。
        """
        async with self._active_lock:
            if self._active_count > 0:
                self._active_count -= 1
                self._semaphore.release()
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
