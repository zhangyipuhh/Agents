# -*- coding:utf-8 -*-
"""
并发控制模块

提供 Agent 聊天请求的内存并发队列控制。

- AgentConcurrencyQueue：基于 asyncio.Semaphore 的纯内存并发队列（FIFO 等待）
- chat_concurrency_dependency：FastAPI 异步生成器依赖，支持 SSE/HTTP 双模式
- stream_with_concurrency：通用 SSE 流式包装器，消费 dep yield 链 + 业务流，
  含 HITL interrupt 主动释放 + finally aclose 兜底（供所有 SSE 聊天路由复用）

注意：
    ``chat_concurrency_dependency`` 内部会 yield 多个 queue 事件 dict，
    **不应**直接作为 ``Depends`` 使用——FastAPI 的 yield-based dependency
    包装会注入 generator 第一个 yield 的值（dict），导致下游 ``async for`` 失败。
    正确做法：在路由体内手动 ``chat_concurrency_dependency(request, mode="sse")``
    获取 generator，再传给 ``stream_with_concurrency``。
"""

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue
from app.core.concurrency.chat_concurrency_dependency import (
    chat_concurrency_dependency,
    stream_with_concurrency,
)

__all__ = [
    "AgentConcurrencyQueue",
    "chat_concurrency_dependency",
    "stream_with_concurrency",
]
