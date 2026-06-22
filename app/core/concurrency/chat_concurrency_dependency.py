# -*- coding:utf-8 -*-
"""
聊天并发控制 FastAPI 依赖

为 Agent 聊天路由提供统一的并发队列依赖。
支持 SSE 流式与 HTTP 非流式两种模式。

核心能力（2026-06-15 重构）：
- SSE 模式：排队期间持续 yield 自定义 queue 事件给前端；获取许可后 yield None 让路由继续。
- HTTP 模式：排队时立即抛 HTTPException(429) 拒绝。
- HITL interrupt 早期释放：暴露 request.state.concurrency_release_handle 句柄，
  让路由在 yield interrupt 业务事件之前主动释放许可，避免 resume 请求卡在队列。
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Literal, Optional

from fastapi import HTTPException, Request

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue
from app.core.config.settings import settings

logger = logging.getLogger(__name__)


QueueMode = Literal["sse", "http"]

# 后台轮询频率：每 1 秒向前端推送一次排队状态
QUEUE_POLL_INTERVAL_SECONDS = 1.0


def _build_queue_event(snapshot: Dict[str, Any], event_name: str) -> Dict[str, Any]:
    """
    构造 queue SSE 事件 payload

    Args:
        snapshot: AgentConcurrencyQueue.snapshot() 返回的字典
        event_name: "waiting" | "ready"

    Returns:
        dict: 直接 yield 给路由再序列化为 SSE 的 payload
    """
    return {
        "type": "queue",
        "event": event_name,
        "waiting_count": snapshot["waiting_count"],
        "active_count": snapshot["active_count"],
        "max_concurrency": snapshot["max_concurrency"],
        "position": snapshot["position"],
        "timestamp": snapshot["timestamp"],
    }


async def chat_concurrency_dependency(
    request: Request,
    mode: QueueMode = "sse",
) -> AsyncGenerator[Optional[Dict[str, Any]], None]:
    """
    FastAPI 依赖：为聊天路由提供并发队列控制

    SSE 模式（默认）：
        - 排队期间持续 yield queue SSE 事件给前端
        - 获取许可瞬间 yield "ready" 事件再 yield None
        - 路由执行期间通过 release_done.wait() 阻塞；HITL interrupt 时路由可主动调用
          request.state.concurrency_release_handle() 立即释放许可（核心修复）

    HTTP 模式：
        - 若需要排队立即抛 HTTPException(429, detail={...})
        - 若无需等待直接 yield None 让路由继续

    Args:
        request: FastAPI 请求对象
        mode: "sse" | "http"

    Yields:
        SSE 模式：queue 事件 dict（waiting/ready）或 None（进入路由）
        HTTP 模式：仅 None（满员时直接抛 429）

    Raises:
        HTTPException: HTTP 模式且需要排队时抛 429
    """
    queue = AgentConcurrencyQueue(max_concurrency=settings.agent_chat_max_concurrency)

    # ====== HTTP 模式：先 enqueue，只有排到第一位且槽位空闲才允许通过 ======
    if mode == "http":
        # 2026-06-22 修复：HTTP 请求也必须先 enqueue，避免非流式请求绕过 SSE 排队队列插队。
        await queue.enqueue()
        snap = await queue.snapshot()
        if snap["position"] == 1 and snap["active_count"] < snap["max_concurrency"]:
            # 轮到本请求且槽位空闲：获取许可 → yield None
            await queue.acquire()
            try:
                yield None
            finally:
                await queue.release()
        else:
            # 前面已有其他 waiter 或槽位已满：抛 429 + 排队信息
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "queue_full",
                    "waiting_count": snap["waiting_count"],
                    "active_count": snap["active_count"],
                    "max_concurrency": snap["max_concurrency"],
                    "message": "当前并发请求已达上限，请稍后重试",
                },
            )
        return

    # ====== SSE 模式：排队推送 + 许可后释放句柄 + interrupt 早期释放 ======
    # 2026-06-22 修复：所有 SSE 请求统一先 enqueue，严格按 FIFO 顺序获取许可，
    # 杜绝 HITL 释放后 resume 请求或新请求插队已排队请求的问题。
    await queue.enqueue()

    # 释放句柄：HITL 早期释放 + finally 兜底
    release_done = asyncio.Event()
    release_source = {"kind": "fallback"}  # "explicit" | "fallback"

    async def _release_once() -> None:
        """释放许可一次（防止重复释放）"""
        if release_done.is_set():
            return
        release_source["kind"] = "explicit"
        release_done.set()
        await queue.release()
        logger.debug(
            "[chat_concurrency_dependency] 主动释放许可，当前活跃=%d",
            queue.active_count,
        )

    request.state.concurrency_release_handle = _release_once
    request.state.concurrency_release_done = release_done

    try:
        # 2026-06-22 修复：在独立 task 中执行 acquire()，主循环定期 yield waiting 事件。
        # 这样 release() 通过 Future 精确唤醒 FIFO 下一个 waiter，避免 slot_freed Event
        # 与轮询之间的信号丢失或 race；同时保留 1 秒一次的 waiting 心跳推送。
        acquire_task = asyncio.create_task(queue.acquire())
        try:
            while not acquire_task.done():
                if release_done.is_set():
                    acquire_task.cancel()
                    try:
                        await acquire_task
                    except asyncio.CancelledError:
                        pass
                    break

                snap = await queue.snapshot()
                yield _build_queue_event(snap, "waiting")

                # 等待 acquire_task 完成或 1 秒超时， whichever 先来
                try:
                    await asyncio.wait_for(
                        asyncio.shield(acquire_task),
                        timeout=QUEUE_POLL_INTERVAL_SECONDS,
                    )
                    break
                except asyncio.TimeoutError:
                    continue

            if acquire_task.done() and not acquire_task.cancelled():
                # acquire 成功，检查是否有异常
                acquire_task.result()
        except asyncio.CancelledError:
            if not acquire_task.done():
                acquire_task.cancel()
                try:
                    await acquire_task
                except asyncio.CancelledError:
                    pass
            raise

        if not release_done.is_set():
            # 获取许可瞬间：yield ready 事件
            ready_snap = await queue.snapshot()
            yield _build_queue_event(ready_snap, "ready")

            # yield None 进入路由
            yield None

            # 等待路由主动 release（HITL 场景）或 finally 兜底
            await release_done.wait()

    finally:
        # 兜底 release（如果 release_done 未被 set，如客户端异常断开 / 路由异常退出）
        if not release_done.is_set():
            try:
                await queue.release()
                logger.debug(
                    "[chat_concurrency_dependency] finally 兜底释放许可，当前活跃=%d",
                    queue.active_count,
                )
            except Exception as e:
                logger.warning("[chat_concurrency_dependency] finally 兜底 release 异常: %s", e)
        # 清理 request.state
        for attr in ("concurrency_release_handle", "concurrency_release_done"):
            try:
                if hasattr(request.state, attr):
                    delattr(request.state, attr)
            except Exception:
                pass


def _is_interrupt_chunk(chunk: str) -> bool:
    """
    判定 SSE chunk 是否为 HITL interrupt 类型业务事件。

    解析 ``data: <json>`` 形式的 SSE 字符串，检查 ``type == "interrupt"``。
    任何解析失败或非字符串输入均返回 False，避免误判业务事件。

    Args:
        chunk: 业务生成器产出的 SSE 字符串。

    Returns:
        bool: 是否为 interrupt 类型事件。
    """
    if not isinstance(chunk, str) or not chunk.startswith("data: "):
        return False
    try:
        payload = json.loads(chunk[6:].strip())
        return payload.get("type") == "interrupt"
    except Exception:
        return False


async def stream_with_concurrency(
    request: Request,
    dep,
    business_gen,
) -> AsyncGenerator[str, None]:
    """
    通用 SSE 流式包装器（并发控制 + 业务流衔接 + HITL 早期释放）。

    职责：
    1. 消费 ``chat_concurrency_dependency`` 的 yield 链（queue waiting/ready 事件）
       → 序列化为 ``data: {json}\\n\\n`` 透传给前端。
    2. 消费 ``business_gen`` 的 yield 链（业务 chunk）→ 透传。
    3. HITL 关键：检测到 ``type='interrupt'`` 业务事件时，yield 之前主动调用
       ``request.state.concurrency_release_handle()`` 释放许可，确保 resume 请求无排队。
    4. finally 兜底：路由或客户端异常退出时显式 ``aclose(dep)``，触发
       ``chat_concurrency_dependency`` 的 finally 块做 release 兜底。

    Args:
        request: FastAPI 请求对象（用于读取 ``concurrency_release_handle``）。
        dep: ``chat_concurrency_dependency(request, mode="sse")`` 返回的 async generator
             （**必须是 generator object**，不能是 ``Depends`` 注入值——否则会被
             FastAPI 包装为 context manager 并 yield 第一个 queue 事件的 dict）。
        business_gen: 业务层 ``generate_stream_response`` 返回的 async generator。

    Yields:
        SSE 字符串（含 queue 事件 + 业务 chunk）。

    Note:
        ``finally`` 中的幂等性由 ``chat_concurrency_dependency`` 内
        ``release_done.is_set()`` 守卫保证——HITL 场景下 handle 已主动 release，
        finally 不会重复 release。
    """
    try:
        # 第一段：消费依赖 yield 链（queue 事件或 None）
        # 防御性：dep 可能为 None 或非 async iterable（极端场景，如测试中传入 mock），
        # 此处先检查再 async for，避免 TypeError 阻断整个 SSE 流。
        if dep is not None and hasattr(dep, "__aiter__"):
            async for item in dep:
                if item is not None:
                    # queue 事件（waiting/ready） → 直接 yield 给前端
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    continue
                # item is None → 已获取许可，进入业务流
                break
        elif dep is not None:
            logger.warning(
                "[stream_with_concurrency] dep 缺少 __aiter__，跳过 dep 消费：%r", dep,
            )

        # 第二段：消费业务流
        async for chunk in business_gen:
            # HITL 关键：在 yield interrupt 之前主动释放许可
            if _is_interrupt_chunk(chunk):
                handle = getattr(request.state, "concurrency_release_handle", None)
                if handle is not None:
                    try:
                        await handle()
                    except Exception as e:
                        logger.warning(
                            "[stream_with_concurrency] interrupt 主动释放许可异常: %s", e,
                        )
            yield chunk
    finally:
        # 显式 aclose dep → 触发 chat_concurrency_dependency 的 finally 兜底
        aclose = getattr(dep, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception as e:
                logger.warning("[stream_with_concurrency] dep.aclose 异常: %s", e)