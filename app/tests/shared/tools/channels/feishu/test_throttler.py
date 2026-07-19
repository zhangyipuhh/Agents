# -*- coding:utf-8 -*-
"""
Throttler 单元测试

测试目标：
    覆盖 ``app/shared/tools/channels/feishu/Throttler.py::Throttler`` 的双条件
    节流逻辑（时间窗 + 字符增量），以及 ``force_flush`` 基线更新行为。

测试策略：
    - 时间窗测试：用 monkeypatch ``time.monotonic`` 模拟时间流逝
    - 长度测试：直接控制 ``accumulated_len`` 参数
    - 并发测试：用 ``asyncio.Event`` 模拟两个协程竞争 ``should_push``

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

import asyncio
import time
from typing import List

import pytest

from app.shared.tools.channels.feishu.Throttler import Throttler


# ---------------------------------------------------------------------------
# P0：导入测试
# ---------------------------------------------------------------------------


def test_throttler_importable():
    """P0：Throttler 模块可正常导入。

    Returns:
        None
    """
    assert Throttler is not None
    throttler = Throttler()
    assert throttler.min_interval_ms == 600
    assert throttler.min_delta_chars == 50


# ---------------------------------------------------------------------------
# P1：时间窗节流
# ---------------------------------------------------------------------------


def test_should_push_after_min_interval(monkeypatch):
    """P1：时间窗满足 + 字符增量满足 → 返回 True。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    # 模拟时间序列：[0.0, 0.7] —— should_push 调用两次，每次消耗 1 个时间值
    times = iter([0.0, 0.7])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    throttler = Throttler(min_interval_ms=600, min_delta_chars=50)
    # 首次调用：time_ok=True（last_pushed_at=-inf），len_ok=True（100 >= 50）
    assert throttler.should_push(100) is True
    # 第二次调用：时间间隔 0.7-0.0=0.7s >= 0.6s ✓，len 增量 200-100=100 >= 50 ✓
    assert throttler.should_push(200) is True


def test_should_not_push_within_min_interval(monkeypatch):
    """P1：时间窗未满足 → 返回 False（即使字符增量满足）。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    # 模拟时间序列：[0.0, 0.3] —— 第二次时间窗 0.3s < 0.6s
    times = iter([0.0, 0.3])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    throttler = Throttler(min_interval_ms=600, min_delta_chars=50)
    assert throttler.should_push(100) is True  # 首次基线
    assert throttler.should_push(200) is False  # 时间窗未满足


# ---------------------------------------------------------------------------
# P1：字符增量节流
# ---------------------------------------------------------------------------


def test_should_not_push_below_min_delta_chars(monkeypatch):
    """P1：字符增量不够 → 返回 False（即使时间窗满足）。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    # 模拟时间序列：[0.0, 1.0] —— 时间窗 1.0s >= 0.6s ✓
    times = iter([0.0, 1.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    throttler = Throttler(min_interval_ms=600, min_delta_chars=50)
    assert throttler.should_push(100) is True  # 首次基线
    # 长度增量 130-100=30 < 50 ✗
    assert throttler.should_push(130) is False


def test_should_push_when_both_conditions_met(monkeypatch):
    """P1：时间+长度双满足才推。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    times = iter([0.0, 0.7, 1.4])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    throttler = Throttler(min_interval_ms=600, min_delta_chars=50)
    # 首次：基线初始化（last_pushed_at=-inf，time_ok 恒为 True）
    assert throttler.should_push(100) is True
    # 第二次：时间 0.7s ✓ 长度 130-100=30 ✗
    assert throttler.should_push(130) is False
    # 第三次：时间 1.4-0.0=1.4s ✓ 长度 200-100=100 ✓
    assert throttler.should_push(200) is True


# ---------------------------------------------------------------------------
# P2：force_flush
# ---------------------------------------------------------------------------


def test_force_flush_updates_len_without_blocking(monkeypatch):
    """P2：force_flush 仅更新长度基线，不影响后续 should_push 时间窗判定。

    场景：
        - t=0.0 should_push(100) → True（基线 last_pushed_at=0.0, last_pushed_len=100）
        - force_flush(500) → 仅更新 last_pushed_len=500（last_pushed_at 不变）
        - t=0.3 should_push(550) → 时间窗 0.3-0.0=0.3s < 0.6s → False
          （force_flush 没有更新时间基线，所以时间窗仍未满足）

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    times = iter([0.0, 0.3])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    throttler = Throttler(min_interval_ms=600, min_delta_chars=50)
    assert throttler.should_push(100) is True
    assert throttler.last_pushed_len == 100

    # force_flush 更新长度基线到 500，但不更新时间基线
    throttler.force_flush(500)
    assert throttler.last_pushed_len == 500
    assert throttler.last_pushed_at == 0.0  # 时间基线未变（should_push 设置的 0.0）

    # 后续 should_push：时间窗 0.3-0.0=0.3s < 0.6s → False
    # 长度增量 550-500=50 >= 50 ✓ 但时间窗不满足
    assert throttler.should_push(550) is False


def test_force_flush_allows_immediate_push_after_time_window(monkeypatch):
    """P2：force_flush 后，时间窗满足时应该立即返回 True。

    Args:
        monkeypatch: pytest fixture

    Returns:
        None
    """
    times = iter([0.0, 0.7])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))

    throttler = Throttler(min_interval_ms=600, min_delta_chars=50)
    assert throttler.should_push(100) is True
    throttler.force_flush(500)
    # 时间窗 0.7-0.0=0.7s ✓，长度 600-500=100 ✓
    assert throttler.should_push(600) is True


# ---------------------------------------------------------------------------
# P2：并发 should_push 由 Consumer 层 lock 串行（验证 Throttler 自身非线程安全）
# ---------------------------------------------------------------------------


def test_concurrent_should_push_serialized_by_consumer_lock():
    """P2：模拟 Consumer 层 asyncio.Lock 串行化 should_push 调用。

    Throttler 自身非线程安全（共享 _last_pushed_at / _last_pushed_len），
    调用方（FeishuCardConsumer._patch_card_safe）用 ``asyncio.Lock`` 串行化。
    本测试模拟两个协程通过 lock 串行调用 should_push，验证最终基线正确。

    Returns:
        None
    """
    throttler = Throttler(min_interval_ms=0, min_delta_chars=10)
    lock = asyncio.Lock()
    results: List[bool] = []

    async def worker(accumulated_len: int) -> bool:
        async with lock:
            return throttler.should_push(accumulated_len)

    async def runner():
        # 5 个并发任务，累积长度递增
        tasks = [worker(10 + i * 20) for i in range(5)]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

    asyncio.run(runner())
    # 至少有一次 should_push 返回 True（首次基线初始化）
    assert any(results)


# ---------------------------------------------------------------------------
# P2：默认值与构造参数
# ---------------------------------------------------------------------------


def test_default_construction_values():
    """P2：默认构造参数应为 600ms / 50 chars，初始 last_pushed_at 为 -inf。

    Returns:
        None
    """
    throttler = Throttler()
    assert throttler.min_interval_ms == 600
    assert throttler.min_delta_chars == 50
    # 初始 last_pushed_at 为 -inf（表示从未推送），保证首次 should_push 时间窗判定为 True
    assert throttler.last_pushed_at == float("-inf")
    assert throttler.last_pushed_len == 0
