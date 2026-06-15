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
            # 排队期间持续推送 queue waiting 事件给前端
            while True:
                if release_done.is_set():
                    break
                snap = await queue.snapshot()
                yield _build_queue_event(snap, "waiting")
                # 每 1 秒推送一次（HITL 触发时 release_done 会被 set，循环立即退出）
                try:
                    await asyncio.wait_for(
                        release_done.wait(),
                        timeout=QUEUE_POLL_INTERVAL_SECONDS,
                    )
                    # release_done 被 set（HITL 提前释放）→ 跳出循环
                    break
                except asyncio.TimeoutError:
                    # 正常超时 → 继续推送下一次
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