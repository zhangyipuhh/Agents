#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Throttler - 飞书 CardKit 更新节流器

职责：
    - 在 ``FeishuCardConsumer.on_text_chunk`` 中决定"是否触发 CardKit patch"
    - 双条件节流：**时间窗**（默认 600 ms）+ **字符增量**（默认 50 字符），
      两个条件同时满足才推 patch
    - 流结束时由 ``force_flush`` 强制更新内部长度基线（不影响后续 ``should_push``
      判定），用于 ``on_session_end`` 显式最后一次 patch 时的状态对齐

设计依据：
    - 飞书官方限频 50 QPS / 秒；600 ms 留余量
    - 50 字符增量避免无意义 patch（如逐 token 推送单字符）
    - 单卡片 ``asyncio.Lock`` 串行 patch（在 Consumer 层实现，本节流器不感知）

接口契约：
    - ``should_push(accumulated_len)``：返回 ``True`` 表示当前应触发 patch，
      并更新内部基线（last_pushed_at / last_pushed_len）；
      ``False`` 表示跳过本次（仅累积，不 patch）
    - ``force_flush(accumulated_len)``：流结束时调用，仅更新长度基线
      （不更新时间基线，避免影响后续 ``should_push`` 的时间窗判定）

线程安全：
    - 本节流器为单卡片私有，单 Consumer 内串行调用，无需加锁
    - 并发场景由 Consumer 层的 ``asyncio.Lock`` 串行化（本节流器不感知）

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

import time


class Throttler:
    """时间窗 + 字符增量双条件节流器。"""

    def __init__(
        self,
        min_interval_ms: int = 600,
        min_delta_chars: int = 50,
    ) -> None:
        """初始化节流器。

        Args:
            min_interval_ms: 最小时间间隔（毫秒），默认 600 ms
            min_delta_chars: 最小字符增量，默认 50 字符
        """
        self._min_interval: float = min_interval_ms / 1000.0
        self._min_delta: int = min_delta_chars
        # 用 -inf 表示"从未推送过"，保证首次 should_push 调用的时间窗判定
        # 始终为 True（无论 time.monotonic() 返回何值，包括测试 mock 与刚启动系统）
        self._last_pushed_at: float = float("-inf")
        self._last_pushed_len: int = 0

    def should_push(self, accumulated_len: int) -> bool:
        """判断当前是否应触发 patch。

        双条件同时满足才返回 ``True``：
            1. 距离上次 patch 的时间间隔 ≥ ``min_interval_ms``
            2. 累积字符增量 ≥ ``min_delta_chars``

        返回 ``True`` 时同步更新内部基线（last_pushed_at / last_pushed_len），
        保证下一次 ``should_push`` 调用基于新基线计算。

        Args:
            accumulated_len: 当前累积的字符总数

        Returns:
            bool: ``True`` 表示应触发 patch；``False`` 表示跳过
        """
        now = time.monotonic()
        time_ok = (now - self._last_pushed_at) >= self._min_interval
        len_ok = (accumulated_len - self._last_pushed_len) >= self._min_delta
        if time_ok and len_ok:
            self._last_pushed_at = now
            self._last_pushed_len = accumulated_len
            return True
        return False

    def force_flush(self, accumulated_len: int) -> None:
        """流结束时强制更新长度基线。

        仅更新 ``_last_pushed_len``，**不**更新 ``_last_pushed_at``——
        避免影响后续 ``should_push`` 的时间窗判定（如 resume 续跑场景下，
        Consumer 复用同一 Throttler 实例时不应被 force_flush 干扰时间窗）。

        Args:
            accumulated_len: 流结束时的最终字符总数
        """
        self._last_pushed_len = accumulated_len

    @property
    def min_interval_ms(self) -> int:
        """int: 最小时间间隔（毫秒，构造时传入）"""
        return int(self._min_interval * 1000)

    @property
    def min_delta_chars(self) -> int:
        """int: 最小字符增量（构造时传入）"""
        return self._min_delta

    @property
    def last_pushed_at(self) -> float:
        """float: 上次 patch 的 monotonic 时间戳（供测试断言）"""
        return self._last_pushed_at

    @property
    def last_pushed_len(self) -> int:
        """int: 上次 patch 时的累积字符数（供测试断言）"""
        return self._last_pushed_len
