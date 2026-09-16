#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
项目统一时间工厂（2026-09-16 落地）。

背景：
    Docker 镜像（``python:3.11-slim``）默认时区为 UTC，且未设 ``TZ`` 环境变量。
    全项目 100+ 处 ``datetime.now()``（naive，无时区）在容器内一律返回 UTC naive，
    导致业务展示、SQL 直查、API 响应全部晚 8 小时。

    本模块统一暴露三个工厂函数，所有业务代码不再直接调用 ``datetime.now()``。
    调用方按 DB 列类型与展示场景选用：
        - ``now_asia_shanghai()``     → aware 北京时区（通用、序列化、调试）
        - ``now_asia_shanghai_naive()`` → 北京 naive（写 PG ``TIMESTAMP`` 朴素列）
        - ``now_utc_aware()``         → aware UTC（写 PG ``TIMESTAMPTZ`` 列 / SSE 事件时间戳）

    配套 ``app/Dockerfile`` 装 ``tzdata`` + ``ENV TZ=Asia/Shanghai``，使
    ``date`` / ``log`` / ``cron`` 等系统级时间也对齐北京；Python 代码统一走本模块
    工厂函数，**不**依赖容器时区（容器即便漂回 UTC，工厂函数仍返回正确时区）。

    不替代以下设计契约（**保持不变**）：
        - ``datetime.utcnow()``（mfa / log / user_login_session 写 naive 列）
        - ``datetime.now(timezone.utc).replace(tzinfo=None)``（同上）
        - ``datetime.now().timestamp()`` / 耗时差值（与时区无关）
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

# 模块级常量：避免每次调用都重建 ZoneInfo（IANA 解析有成本）
_ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
_UTC = ZoneInfo("UTC")


def now_asia_shanghai() -> datetime:
    """返回当前北京时间（aware，带 ``Asia/Shanghai`` tzinfo）。

    Returns:
        datetime: tzinfo=ZoneInfo("Asia/Shanghai") 的 aware datetime。

    使用场景:
        - SSE 事件时间戳展示（与 ``now_utc_aware`` 二选一）
        - 调试日志 / 业务展示
        - 写 ``TIMESTAMPTZ`` 列（asyncpg 会自动转 UTC 存）

    与 ``datetime.now(ZoneInfo("Asia/Shanghai"))`` 等价，但避免散落字面量。
    """
    return datetime.now(_ASIA_SHANGHAI)


def now_asia_shanghai_naive() -> datetime:
    """返回当前北京时刻的 naive datetime（tzinfo=None）。

    Returns:
        datetime: 无 tzinfo，值等于北京当前时刻。

    使用场景:
        - 写 PG ``TIMESTAMP`` 朴素列（落库后 DB 直查即北京时刻，符合用户期望）
        - 字符串格式化（``strftime`` 不需要 tzinfo）

    重要约束:
        - **不要**写 ``TIMESTAMPTZ`` 列（asyncpg 会按 UTC 解释，**多 8 小时 bug**）
        - **不要**与 DB ``DEFAULT NOW()``（UTC）直接比较——两者时区口径不同
    """
    return datetime.now(_ASIA_SHANGHAI).replace(tzinfo=None)


def now_utc_aware() -> datetime:
    """返回当前 UTC 时刻（aware，带 ``UTC`` tzinfo）。

    Returns:
        datetime: tzinfo=ZoneInfo("UTC") 的 aware datetime。

    使用场景:
        - 写 PG ``TIMESTAMPTZ`` 列（与 PG ``DEFAULT NOW()`` 时序一致）
        - SSE 事件时间戳（``.isoformat()`` 带 ``+00:00``，前端解析无歧义）
        - 与 DB ``DEFAULT NOW()`` 读出的 aware UTC 直接比较
    """
    return datetime.now(_UTC)
