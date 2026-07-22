# -*- coding:utf-8 -*-
"""SSH 超时参数约束。"""

from typing import Any


def clamp_timeout(value: Any, default: int = 30, lo: int = 1, hi: int = 120) -> int:
    """将超时值限制在指定范围内。

    Args:
        value: 原始超时值。
        default: 无法转换时的默认值。
        lo: 最小超时值。
        hi: 最大超时值。

    Returns:
        int: 范围内的超时值。
    """
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, result))
