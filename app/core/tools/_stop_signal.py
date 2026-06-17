#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
子智能体停止信号传递机制（2026-06-15 新增）

通过 ``contextvars.ContextVar`` 在主路由入口挂 FastAPI Request，
工具函数（sandbox / explore）内通过 ``get_current_request()`` 取出，
调用 ``await request.is_disconnected()`` 检测客户端断开。

## 设计要点

- **asyncio 任务在同一 context 内自动继承 ContextVar**，多请求并发时各请求独立隔离，无竞态。
- **同步函数（@tool 默认）也兼容**：工具函数先 ``get_current_request()`` 取出 Request，
  在需要时 ``await`` ``request.is_disconnected()``。同步 stream 循环内无法直接 await，
  需先改用 ``astream``（async for 兼容）。
- **finally 块必须 reset**：避免后续请求继承到错误的 request 引用导致内存泄漏 + 跨请求误判。

## 使用模式

主路由入口：

.. code-block:: python

    from app.core.tools._stop_signal import set_current_request, reset_current_request

    cv_token = set_current_request(request)
    try:
        # 业务逻辑
        ...
    finally:
        reset_current_request(cv_token)

工具函数内（async）：

.. code-block:: python

    from app.core.tools._stop_signal import get_current_request

    async def my_subagent_tool(runtime):
        request = get_current_request()  # 可能为 None（非 HTTP 上下文）
        async for chunk in child_agent.astream(...):
            if request is not None and (chunk_count % 5 == 0):
                if await request.is_disconnected():
                    # 停止 + cleanup
                    break

Date: 2026-06-15
Author: AI Assistant
"""

from contextvars import ContextVar
from typing import Optional

from fastapi import Request

# ContextVar 默认值为 None（保证非 HTTP 上下文也能安全调用 get）
_current_request: ContextVar[Optional[Request]] = ContextVar(
    "current_subagent_request",
    default=None,
)


def set_current_request(request: Optional[Request]) -> object:
    """
    在主路由入口调用，把当前 FastAPI Request 挂到 ContextVar。

    Args:
        request: FastAPI Request 对象；可传入 None 表示非 HTTP 上下文（测试场景）。

    Returns:
        object: ContextVar.set() 返回的 token，必须在 finally 块传给
        ``reset_current_request()``，否则会污染后续请求的 context。
    """
    return _current_request.set(request)


def reset_current_request(token) -> None:
    """
    在主路由 finally 块调用，重置 ContextVar 到入口前状态。

    Args:
        token: ``set_current_request()`` 返回的 token 对象。
    """
    _current_request.reset(token)


def get_current_request() -> Optional[Request]:
    """
    在工具函数（sandbox / explore 等）内调用，取出当前 Task 内挂的 Request。

    Returns:
        Optional[Request]: 当前请求对象；若未在 HTTP 上下文中调用或主路由未挂载，
        返回 None。调用方需对 None 做防御性处理。
    """
    return _current_request.get()
