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

    # ====== HTTP 模式：直接尝试 acquire，满员则抛 429 ======
    if mode == "http":
        snap = await queue.snapshot()
        if snap["active_count"] < snap["max_concurrency"]:
            # 无需排队：直接获取许可 → yield None
            await queue.acquire()
            try:
                yield None
            finally:
                await queue.release()
        else:
            # 满员：抛 429 + 排队信息
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
    pre_snap = await queue.snapshot()
    need_wait = pre_snap["active_count"] >= pre_snap["max_concurrency"]

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
        if need_wait:
            # 2026-06-22 修复：真正阻塞前先预注册到等待队列，
            # 使后续 snapshot()/position() 能正确计算"前面还有几人"。
            await queue.enqueue()
            # 排队期间持续推送 queue waiting 事件给前端
            while True:
                if release_done.is_set():
                    break
                snap = await queue.snapshot()
                # 关键修复（2026-06-15）：
                # 当并发槽位已经空闲（active_count < max_concurrency）时，
                # 跳出轮询循环进入 acquire()，避免「槽位空闲但轮询不退出」
                # 的死锁场景。之前唯一退出条件是 release_done.is_set()，
                # 但 release_done 只在 HITL _release_once() 中被 set，
                # 其他请求通过 finally 兜底正常释放时 release_done 不会动，
                # 导致每 1 秒重复 yield waiting 事件、永远不调用 acquire()，
                # 用户消息卡死、黄色排队横幅永久不消失。
                if snap["active_count"] < snap["max_concurrency"]:
                    logger.debug(
                        "[chat_concurrency_dependency] 槽位已空闲（active=%d, max=%d），跳出轮询进入 acquire()",
                        snap["active_count"],
                        snap["max_concurrency"],
                    )
                    break
                yield _build_queue_event(snap, "waiting")
                # 每 1 秒推送一次；若其他请求释放槽位（slot_freed）或 HITL 提前释放（release_done），
                # 立即醒来重新 snapshot，实现槽位空闲时毫秒级响应。
                slot_wait = asyncio.create_task(queue.slot_freed.wait())
                release_wait = asyncio.create_task(release_done.wait())
                try:
                    done, pending = await asyncio.wait(
                        [slot_wait, release_wait],
                        timeout=QUEUE_POLL_INTERVAL_SECONDS,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    for task in (slot_wait, release_wait):
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                if release_wait in done:
                    # release_done 被 set（HITL 提前释放）→ 跳出循环
                    break
                # slot_freed 被 set 或超时 → 回到循环开头重新 snapshot
                continue

        # acquire（可能立即成功 / 已释放的快速路径）
        await queue.acquire()

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