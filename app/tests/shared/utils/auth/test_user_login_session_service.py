# -*- coding:utf-8 -*-
"""
user_login_session_service 单元测试（等保三级 §1.5，2026-08-12 新增）

覆盖：
- UserLoginSessionService 业务编排方法(create / check_idle / touch / revoke / revoke_user_sessions)
- UserLoginSessionStore 内存模式 CRUD（不依赖真实 DB）
- 关键反向用例（fake 必须模拟完整语义）：
  * 写入 aware datetime 到 naive TIMESTAMP 列必须抛 DataError

时间约束（2026-08-08 MFA 401 bug 教训）：
- 写入 PG naive TIMESTAMP 列必须用 datetime.utcnow()（naive datetime）
- 禁止 datetime.now(timezone.utc)（aware）→ asyncpg DataError

Author: AI Assistant
Date: 2026-08-12
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def reset_memory_store():
    """每个测试前清空内存模式 store。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionStore,
    )

    UserLoginSessionStore._memory_sessions.clear()
    yield
    UserLoginSessionStore._memory_sessions.clear()


@pytest.fixture(autouse=True)
def _force_memory_mode_by_default(monkeypatch):
    """默认强制 service 走内存模式（避免依赖真实 DB）。

    使用 monkeypatch.setattr（pytest 同一实例，跨 fixture/test 一致）。
    单个测试若需要 postgres 路径，可在自己的 monkeypatch 中再次 setattr。
    """
    from app.core.database import DatabasePool

    monkeypatch.setattr(DatabasePool, "is_enabled", lambda: False)


# ============================================================
# P0: 导入 / 存在性
# ============================================================


def test_service_module_importable():
    """P0: 模块可导入且暴露单例。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
        user_login_session_service,
    )

    assert isinstance(user_login_session_service, UserLoginSessionService)
    assert hasattr(UserLoginSessionStore, "insert")
    assert hasattr(UserLoginSessionStore, "fetch")
    assert hasattr(UserLoginSessionStore, "touch")
    assert hasattr(UserLoginSessionStore, "revoke")
    assert hasattr(UserLoginSessionStore, "revoke_user_except")


# ============================================================
# P1: 成功路径（happy path）
# ============================================================


def test_create_login_session_returns_session_uuid():
    """P1: 创建会话成功返回非空 session_uuid，且内存存储可查询到记录。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(
            user_id=42,
            username="alice",
            refresh_token_ttl_seconds=86400,
        )
    )
    assert isinstance(session_uuid, str)
    assert len(session_uuid) >= 32

    record = _run_async(UserLoginSessionStore.fetch(session_uuid))
    assert record is not None
    assert record["user_id"] == 42
    assert record["username"] == "alice"
    assert record["revoked_at"] is None
    assert record["last_active_at"] is not None


def test_touch_last_active_updates_timestamp():
    """P1: touch_last_active 刷新 last_active_at 为当前时间。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(user_id=1, username="bob", refresh_token_ttl_seconds=3600)
    )

    # 推进系统时间（注入 last_active_at 为 1 小时前）
    past = datetime.utcnow() - timedelta(hours=1)
    UserLoginSessionStore._memory_sessions[session_uuid]["last_active_at"] = past

    before = _run_async(UserLoginSessionStore.fetch(session_uuid))["last_active_at"]
    assert before == past

    ok = _run_async(svc.touch_last_active(session_uuid))
    assert ok is True

    after = _run_async(UserLoginSessionStore.fetch(session_uuid))["last_active_at"]
    assert after > past
    # 必须是 naive datetime（写入 PG TIMESTAMP 朴素列的硬约束）
    assert after.tzinfo is None


def test_check_idle_within_timeout_returns_false():
    """P1: 距离 last_active_at 在阈值内时返回 (False, last_active_at)。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(user_id=1, username="carol", refresh_token_ttl_seconds=86400)
    )

    is_expired, last_active = _run_async(svc.check_idle(session_uuid, idle_timeout_seconds=1800))
    assert is_expired is False
    assert last_active is not None


def test_check_idle_beyond_timeout_returns_true():
    """P1: 距离 last_active_at 超过阈值时返回 (True, last_active_at)。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(user_id=1, username="dave", refresh_token_ttl_seconds=86400)
    )

    # 注入 last_active_at 为 2 小时前
    past = datetime.utcnow() - timedelta(hours=2)
    UserLoginSessionStore._memory_sessions[session_uuid]["last_active_at"] = past

    is_expired, last_active = _run_async(svc.check_idle(session_uuid, idle_timeout_seconds=1800))
    assert is_expired is True
    assert last_active == past


def test_check_idle_nonexistent_session_returns_true():
    """P1: 会话不存在返回 (True, None)。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    is_expired, last_active = _run_async(svc.check_idle("nonexistent-uuid", idle_timeout_seconds=1800))
    assert is_expired is True
    assert last_active is None


def test_check_idle_revoked_session_returns_true():
    """P1: 已撤销会话返回 (True, last_active_at)。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(user_id=1, username="eve", refresh_token_ttl_seconds=86400)
    )
    UserLoginSessionStore._memory_sessions[session_uuid]["revoked_at"] = datetime.utcnow()
    UserLoginSessionStore._memory_sessions[session_uuid]["revoke_reason"] = "logout"

    is_expired, last_active = _run_async(svc.check_idle(session_uuid, idle_timeout_seconds=1800))
    assert is_expired is True


def test_revoke_session_marks_revoked():
    """P1: revoke_session 标记 revoked_at 与 revoke_reason。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(user_id=1, username="frank", refresh_token_ttl_seconds=86400)
    )
    ok = _run_async(svc.revoke_session(session_uuid, reason="logout"))
    assert ok is True

    record = _run_async(UserLoginSessionStore.fetch(session_uuid))
    assert record["revoked_at"] is not None
    assert record["revoke_reason"] == "logout"


def test_revoke_user_sessions_excludes_target():
    """P1: revoke_user_sessions 排除 except_uuid，撤销其它会话。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    keep_uuid = _run_async(
        svc.create_login_session(user_id=10, username="grace", refresh_token_ttl_seconds=86400)
    )
    _run_async(
        svc.create_login_session(user_id=10, username="grace", refresh_token_ttl_seconds=86400)
    )
    _run_async(
        svc.create_login_session(user_id=10, username="grace", refresh_token_ttl_seconds=86400)
    )
    # 另一个用户的会话不应被撤销
    other_uuid = _run_async(
        svc.create_login_session(user_id=11, username="henry", refresh_token_ttl_seconds=86400)
    )

    count = _run_async(
        svc.revoke_user_sessions(user_id=10, except_session_uuid=keep_uuid, reason="replaced")
    )
    assert count == 2  # 除了 keep + other 共 3 条 user_id=10，撤销 2 条

    keep = _run_async(UserLoginSessionStore.fetch(keep_uuid))
    assert keep["revoked_at"] is None
    other = _run_async(UserLoginSessionStore.fetch(other_uuid))
    assert other["revoked_at"] is None


# ============================================================
# P2: 边界条件 / 异常
# ============================================================


def test_create_login_session_invalid_user_id_raises():
    """P2: user_id=0 抛 ValueError。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    with pytest.raises(ValueError):
        _run_async(svc.create_login_session(user_id=0, username="x", refresh_token_ttl_seconds=60))


def test_create_login_session_empty_username_raises():
    """P2: username 为空抛 ValueError。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    with pytest.raises(ValueError):
        _run_async(svc.create_login_session(user_id=1, username="", refresh_token_ttl_seconds=60))


def test_touch_last_active_empty_session_returns_false():
    """P2: session_uuid 为空时返回 False（不抛错）。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    ok = _run_async(svc.touch_last_active(""))
    assert ok is False


def test_revoke_session_empty_session_returns_false():
    """P2: session_uuid 为空时返回 False（不抛错）。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    ok = _run_async(svc.revoke_session("", reason="logout"))
    assert ok is False


def test_session_uuid_is_urlsafe_token():
    """P2: session_uuid 使用 secrets.token_urlsafe，熵足够。"""
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
    )

    svc = UserLoginSessionService()
    uuids = set()
    for _ in range(10):
        uuids.add(
            _run_async(
                svc.create_login_session(user_id=1, username="x", refresh_token_ttl_seconds=60)
            )
        )
    # 10 次生成应得到 10 个不同 uuid
    assert len(uuids) == 10


# ============================================================
# 反向用例：fake 必须模拟完整语义（2026-08-08 MFA bug 教训）
# ============================================================
# 当 service 写入 aware datetime 到 naive TIMESTAMP 列时，
# 必须能在测试中捕获。fake 的 execute(sql, args) 必须检测到这种类型冲突。
# ============================================================


def test_write_aware_datetime_to_naive_column_raises(monkeypatch):
    """
    反向：aware datetime 写入 naive TIMESTAMP 列必须抛 RuntimeError。

    业务侧（service）已 hardcoded 用 datetime.utcnow()（naive），但若有人错误地
    修改为 datetime.now(timezone.utc)，必须能被 fake / 真实生产路径检测到。

    本测试通过 monkeypatch 让 store 走 postgres 分支，并模拟 asyncpg 行为：
    真实 asyncpg 对 aware → naive 列会抛 DataError。
    """
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )
    from app.core.database import DatabasePool

    # 强制 postgres 分支
    monkeypatch.setattr(DatabasePool, "is_enabled", lambda: True)

    # 模拟 asyncpg DataError：aware datetime 不能写入 naive TIMESTAMP 列
    # DatabasePool.execute(cls, query, *args) — classmethod 自动传入 cls,
    # 后续 *args 才是参数列表。
    async def _mock_execute(cls, sql, *bind_args, **kwargs):
        for arg in bind_args:
            if isinstance(arg, datetime) and arg.tzinfo is not None:
                raise RuntimeError(
                    "DataError: invalid input for query argument ... "
                    "(can't subtract offset-naive and offset-aware datetimes)"
                )
        return "INSERT 0 1"

    # 通过 monkeypatch.setattr 在 class 上替换 classmethod（pytest 推荐做法）
    monkeypatch.setattr(DatabasePool, "execute", _mock_execute)

    # 直接调用 store.insert 触发；aware datetime 必须被检测
    aware_dt = datetime.now(timezone.utc)
    with pytest.raises(RuntimeError, match="offset-naive"):
        _run_async(
            UserLoginSessionStore.insert(
                {
                    "session_uuid": "test-uuid",
                    "user_id": 1,
                    "username": "test",
                    "login_at": aware_dt,
                    "last_active_at": aware_dt,
                    "expires_at": aware_dt,
                    "ip_address": None,
                    "user_agent": None,
                }
            )
        )


def test_write_naive_datetime_does_not_raise():
    """
    正向：naive datetime（datetime.utcnow()）可正常写入。

    Returns:
        None
    """
    from app.shared.utils.auth.user_login_session_service import (
        UserLoginSessionService,
        UserLoginSessionStore,
    )

    svc = UserLoginSessionService()
    session_uuid = _run_async(
        svc.create_login_session(user_id=1, username="naive_ok", refresh_token_ttl_seconds=60)
    )
    # 写入应成功（memory 模式）
    record = _run_async(UserLoginSessionStore.fetch(session_uuid))
    assert record is not None
    assert record["last_active_at"].tzinfo is None
