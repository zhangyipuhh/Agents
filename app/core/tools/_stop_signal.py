#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
子智能体停止信号传递机制

包含两种机制：

1. **ContextVar 挂载 FastAPI Request**（2026-06-15 新增）：
   通过 ``contextvars.ContextVar`` 在主路由入口挂 FastAPI Request，
   工具函数（sandbox / explore）内通过 ``get_current_request()`` 取出，
   调用 ``await request.is_disconnected()`` 检测客户端断开。
   - 用于"双保险"：当 abort signal 兜底失效时，reader 关闭仍能触发 is_disconnected。
   - 用于"非 abort 触发的中断"：如浏览器关闭、网络异常等。

2. **全局 abort signals dict**（2026-07-06 新增）：
   按 ``session_id`` 索引 ``asyncio.Event``，主路由入口 ``register_abort_signal(session_id)``
   创建 event，工具函数 ``get_abort_signal(session_id)`` 取出并 ``is_set()`` 检测。
   - **主动 abort 通道**：用户点击"停止"按钮时，前端调 ``POST /api/agent/{session_id}/abort``
     → 后端路由 ``trigger_abort(session_id)`` → ``event.set()`` → 工具下次 check 时感知。
   - **核心优势**：工具检测到 abort 后**主动构造 ToolMessage 返回**（stopped_by_user 分支），
     而不是被 CancelledError 暴力中断 → 避免 orphan tool_calls → 避免下次会话触发 2013 错误。
   - **生命周期**：
     - ``register_abort_signal`` 在 _stream_helper 入口调用，创建并注册
     - ``trigger_abort`` 由 /abort 路由调用，event.set()
     - ``unregister_abort_signal`` 在 _stream_helper finally 调用，清理
   - **不依赖 reader**：abort signal 走全局 dict，不依赖前端 SSE 连接状态

## 设计要点

- **asyncio 任务在同一 context 内自动继承 ContextVar**，多请求并发时各请求独立隔离，无竞态。
- **ContextVar 用于 is_disconnected 兜底**；**全局 dict 用于主动 abort**。
- **工具内部检测 abort → 主动构造 ToolMessage 返回**（LangGraph 推荐做法），
  而不是让 LangGraph 抛 CancelledError → 避免 ToolMessage 写入前的异常打断。

## 使用模式

### 主动 abort（2026-07-06 新增）

主路由入口（_stream_helper.py）：

.. code-block:: python

    from app.core.tools._stop_signal import (
        register_abort_signal, unregister_abort_signal, trigger_abort,
        set_current_request, reset_current_request,
    )

    abort_event = register_abort_signal(session_id)
    cv_token = set_current_request(request)
    try:
        # 业务逻辑
        ...
    finally:
        unregister_abort_signal(session_id)
        reset_current_request(cv_token)

工具函数内（async）：

.. code-block:: python

    from app.core.tools._stop_signal import get_abort_signal

    async def my_subagent_tool(runtime):
        session_id = context.get("session_id", "default")
        abort_event = get_abort_signal(session_id)
        # 进入 stream 前的预检查（捕捉"刚点 stop 就进 sandbox"）
        if abort_event is not None and abort_event.is_set():
            stopped_by_user = True
            # 走 stopped_by_user 分支构造 ToolMessage 返回
        async for chunk in child_agent.astream(...):
            if abort_event is not None and (chunk_count % 5 == 0):
                if abort_event.is_set():
                    stopped_by_user = True
                    break
            ...
        # stopped_by_user 时构造 ToolMessage + return Command
        # 走 LangGraph state 推进 → yield tools 节点 update → 前端收到白名单事件

/abort 路由（agent_router.py）：

.. code-block:: python

    from app.core.tools._stop_signal import trigger_abort

    @router.post("/{session_id}/abort")
    async def abort_stream(session_id: str):
        trigger_abort(session_id)
        return {"status": "aborted", "session_id": session_id}

### is_disconnected 兜底（2026-06-15 既有）

主路由入口同样调用 ``set_current_request(request)``（保留原机制）；工具函数可同时
通过 ``get_current_request()`` 取出 Request，在 is_disconnected 检查时用。生产环境
abort 优先（用户主动停止时走 /abort → 主动触发）；is_disconnected 用于"非主动关闭"
（浏览器关闭、网络断、客户端崩溃）。

Date: 2026-06-15 (initial), 2026-07-06 (abort signals dict)
Author: AI Assistant
"""

import asyncio
from contextvars import ContextVar
from typing import Optional

from fastapi import Request

# ContextVar 默认值为 None（保证非 HTTP 上下文也能安全调用 get）
_current_request: ContextVar[Optional[Request]] = ContextVar(
    "current_subagent_request",
    default=None,
)

# 全局 abort signals，按 session_id 索引
# 2026-07-06 新增：用于主动 abort 通道（前端调 /abort → trigger_abort → event.set()）
# 使用 dict（非 ContextVar）的原因：abort 路由与 stream 路由在不同请求中，
# ContextVar 无法跨请求传递；dict 是模块级全局状态，在同一进程内可跨请求访问。
# 生命周期：register_abort_signal 在 stream 入口注册 → unregister_abort_signal 在 stream finally 清理
_abort_signals: dict[str, asyncio.Event] = {}


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


# ============================================================
# 2026-07-06 新增：主动 abort signals（按 session_id 索引）
# ============================================================

def register_abort_signal(session_id: str) -> asyncio.Event:
    """
    在 _stream_helper 入口调用，为指定 session 创建并注册一个 asyncio.Event。

    Args:
        session_id: 会话 ID（thread_id）。

    Returns:
        asyncio.Event: 新创建的 event 引用。调用方可保留该引用用于直接 .set()，
        但更推荐通过 ``trigger_abort(session_id)`` 间接触发（更安全）。

    设计要点：
    - 同一 session_id 重复注册会覆盖旧 event（先 unregister 再 register）。
      正常情况下不会发生，因为 _stream_helper 入口是单一入口；但测试场景或
      异常重入时需要防御。
    - 不存在"并发 register 竞态"：asyncio 是单线程，dict.setitem 原子。
    """
    # 防御：清理旧 event（避免内存泄漏 + 旧引用意外触发）
    old = _abort_signals.pop(session_id, None)
    if old is not None and not old.is_set():
        # 旧 event 未被 set，直接丢弃；已被 set 的也丢弃（语义无影响）
        pass
    event = asyncio.Event()
    _abort_signals[session_id] = event
    return event


def trigger_abort(session_id: str) -> bool:
    """
    触发指定 session 的 abort signal。由 /abort 路由调用。

    Args:
        session_id: 会话 ID。

    Returns:
        bool: True 表示 event 存在并已 set；False 表示 event 不存在（session 未注册，
        可能已结束或从未启动）。调用方可忽略返回值（abort 永远 idempotent）。

    行为：
    - 如果 session 已注册且 event 未 set：set event，触发工具下次检查时感知
    - 如果 session 已注册但 event 已 set：noop（idempotent，多次触发无害）
    - 如果 session 未注册：noop（不抛错，前端可能误调，后端容错）
    """
    event = _abort_signals.get(session_id)
    if event is None:
        return False
    event.set()
    return True


def unregister_abort_signal(session_id: str) -> None:
    """
    在 _stream_helper finally 块调用，清理已结束的 session 的 abort signal。

    Args:
        session_id: 会话 ID。

    设计要点：
    - 必须调用，否则 dict 持续增长导致内存泄漏（每个 session 一条记录）。
    - 即便 event 已被 set，也清理（已经触发过的事件，引用计数归零后被 GC）。
    - 异常路径也需调用（与 set_current_request 配套）。
    """
    _abort_signals.pop(session_id, None)


def get_abort_signal(session_id: str) -> Optional[asyncio.Event]:
    """
    在工具函数（sandbox / explore）内调用，取出当前 session 的 abort event。

    Args:
        session_id: 会话 ID（从 runtime.context 取出）。

    Returns:
        Optional[asyncio.Event]: 当前 session 的 event 对象；若 session 未注册
        （可能未启动流或流已结束），返回 None。调用方需对 None 做防御性处理。

    使用模式：
        abort_event = get_abort_signal(session_id)
        if abort_event is not None and abort_event.is_set():
            stopped_by_user = True
            break
    """
    return _abort_signals.get(session_id)
