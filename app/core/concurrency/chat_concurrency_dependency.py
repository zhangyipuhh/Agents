# -*- coding:utf-8 -*-
"""
聊天并发控制 FastAPI 依赖

为 Agent 聊天路由提供统一的并发队列依赖。
"""

import logging
from typing import AsyncGenerator

from fastapi import Request

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue

logger = logging.getLogger(__name__)


async def chat_concurrency_dependency(request: Request) -> AsyncGenerator[None, None]:
    """
    FastAPI 依赖：为聊天路由提供并发队列控制

    进入路由前获取队列许可，路由执行完成后释放许可。
    对 SSE 流式响应，生成器完全消费后才会释放。

    Args:
        request: FastAPI 请求对象

    Yields:
        None
    """
    queue = AgentConcurrencyQueue()
    await queue.acquire()
    logger.debug(
        "[chat_concurrency_dependency] 请求 %s 获取许可，活跃=%d，等待=%d",
        request.url.path,
        queue.active_count,
        queue.waiting_count,
    )
    try:
        yield
    finally:
        await queue.release()
        logger.debug(
            "[chat_concurrency_dependency] 请求 %s 释放许可，活跃=%d，等待=%d",
            request.url.path,
            queue.active_count,
            queue.waiting_count,
        )
