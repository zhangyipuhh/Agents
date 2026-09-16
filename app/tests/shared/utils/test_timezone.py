# -*- coding:utf-8 -*-
"""
test_timezone - 项目统一时间工厂单元测试（2026-09-16 落地）

覆盖:
    - now_asia_shanghai() 返回 aware 北京时区
    - now_asia_shanghai_naive() 返回北京时刻的 naive datetime
    - now_utc_aware() 返回 aware UTC
    - 三个工厂函数与 datetime.now() 实测差值 < 2 秒
    - 三个工厂函数互相时序正确（naive == aware.replace(tzinfo=None)）
    - naive isoformat 不带 tzinfo,aware isoformat 带 +08:00 / +00:00

Date: 2026-09-16
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.shared.utils.timezone import (
    now_asia_shanghai,
    now_asia_shanghai_naive,
    now_utc_aware,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


class TestNowAsiaShanghai:
    """now_asia_shanghai() 返回 aware 北京时区。"""

    def test_now_asia_shanghai_returns_aware_with_shanghai_tz(self):
        """返回值必须带 Asia/Shanghai tzinfo。"""
        result = now_asia_shanghai()
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(hours=8)

    def test_now_asia_shanghai_within_2_seconds_of_datetime_now(self):
        """与 datetime.now() 实测差值 < 2 秒(忽略时区比对只比对 epoch)。"""
        before = datetime.now()
        result = now_asia_shanghai()
        after = datetime.now()
        # 三个 epoch 应在 2 秒内
        assert before.timestamp() - 2 <= result.timestamp() <= after.timestamp() + 2

    def test_now_asia_shanghai_isoformat_has_offset(self):
        """isoformat 必须带 +08:00 offset。"""
        result = now_asia_shanghai()
        iso = result.isoformat()
        # 形如 2026-09-16T16:00:00.123456+08:00
        assert "+08:00" in iso


class TestNowAsiaShanghaiNaive:
    """now_asia_shanghai_naive() 返回北京时刻的 naive datetime。"""

    def test_now_asia_shanghai_naive_strips_tzinfo(self):
        """返回值必须 tzinfo=None。"""
        result = now_asia_shanghai_naive()
        assert isinstance(result, datetime)
        assert result.tzinfo is None

    def test_now_asia_shanghai_naive_matches_aware_value(self):
        """naive 值 == aware.replace(tzinfo=None)(同一调用点附近)。"""
        aware = now_asia_shanghai()
        # 同一时刻,naive 工厂应返回相同 wall clock
        naive = now_asia_shanghai_naive()
        # 容差 1 秒
        assert abs((aware.replace(tzinfo=None) - naive).total_seconds()) < 1

    def test_now_asia_shanghai_naive_isoformat_no_offset(self):
        """isoformat 不带任何 tzinfo offset 标记。"""
        result = now_asia_shanghai_naive()
        iso = result.isoformat()
        # 形如 2026-09-16T16:00:00.123456,不应包含 + 或 - offset
        assert "+" not in iso
        # 末尾也不能是 -HH:MM
        assert not re.search(r"-\d{2}:\d{2}$", iso)


class TestNowUtcAware:
    """now_utc_aware() 返回 aware UTC。"""

    def test_now_utc_aware_returns_aware_with_utc_tz(self):
        """返回值必须带 UTC tzinfo。"""
        result = now_utc_aware()
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_now_utc_aware_within_2_seconds_of_datetime_now(self):
        """与 datetime.now() epoch 差值 < 2 秒。"""
        before = datetime.now()
        result = now_utc_aware()
        after = datetime.now()
        assert before.timestamp() - 2 <= result.timestamp() <= after.timestamp() + 2

    def test_now_utc_aware_isoformat_has_zero_offset(self):
        """isoformat 必须带 +00:00 offset。"""
        result = now_utc_aware()
        iso = result.isoformat()
        assert "+00:00" in iso

    def test_now_utc_aware_is_8_hours_behind_asia_shanghai(self):
        """同一时刻 UTC = Asia/Shanghai - 8h。"""
        # 同一调用点对比:aware 减 aware 永远等于 8h(零依赖,无执行时间漂移)
        # 校验逻辑:把 utc 转成 sh 时区,wall clock 应 == sh
        utc = now_utc_aware()
        sh = now_asia_shanghai()
        # sh 应 == utc.astimezone(SHANGHAI)
        utc_as_sh = utc.astimezone(SHANGHAI)
        # 两次调用间有微小漂移,容差 1 秒
        assert abs((sh - utc_as_sh).total_seconds()) < 1
        # 同时刻 UTC 与 sh 时差应 == 8h
        assert (sh.utcoffset() - utc.utcoffset()) == timedelta(hours=8)


class TestCrossFactoryConsistency:
    """三个工厂函数同时调用时序一致性。"""

    def test_three_factories_all_recent(self):
        """三个工厂函数返回的时刻都贴近"现在"。"""
        before = datetime.now()
        sh = now_asia_shanghai()
        sh_naive = now_asia_shanghai_naive()
        utc = now_utc_aware()
        after = datetime.now()
        # naive 转 epoch 比对(before/after 都是 naive UTC 概念)
        for dt, label in [(sh, "sh"), (sh_naive, "sh_naive"), (utc, "utc")]:
            assert before.timestamp() - 2 <= dt.timestamp() <= after.timestamp() + 2, (
                f"{label} 时间漂移: {dt} vs before={before} after={after}"
            )

    def test_naive_factory_wall_clock_is_shanghai(self):
        """naive 工厂的 wall clock 应 == Asia/Shanghai 当地时刻。"""
        naive = now_asia_shanghai_naive()
        # 用真值比对:同时刻 aware = naive + 8h
        aware = now_asia_shanghai()
        assert abs((aware.replace(tzinfo=None) - naive).total_seconds()) < 1

    def test_utc_factory_wall_clock_is_utc(self):
        """UTC aware 工厂的 wall clock 应 == UTC 当地时刻。"""
        utc_aware = now_utc_aware()
        # 同时刻 naive utc = utc_aware.replace(tzinfo=None)
        # 用真实 UTC 时刻对比
        true_utc = datetime.now(UTC)
        # 同一调用点,差值应 < 1 秒
        assert abs((utc_aware - true_utc).total_seconds()) < 1
