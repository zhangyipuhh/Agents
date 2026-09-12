# -*- coding:utf-8 -*-
"""login_lockout 共享登录锁定助手测试（等保三级 §1.4 失败锁定）。"""


def test_login_lockout_importable():
    """助手模块可导入。"""
    from app.shared.utils.auth.login_lockout import (
        check_login_lock,
        record_failed_login_and_is_locked,
    )
    assert callable(check_login_lock)
    assert callable(record_failed_login_and_is_locked)


def test_check_login_lock_returns_none_for_unknown_user(monkeypatch):
    """不存在的用户名返回 None（反枚举：不暴露账号是否存在）。"""
    import asyncio
    from app.shared.utils.auth.login_lockout import check_login_lock

    async def fake_get_user(username):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )
    assert asyncio.run(check_login_lock("ghost")) is None


def test_check_login_lock_returns_none_when_not_locked(monkeypatch):
    """用户存在但未锁定返回 None。"""
    import asyncio
    from app.shared.utils.auth.login_lockout import check_login_lock

    async def fake_get_user(username):
        return {"id": 1, "username": "u"}

    async def fake_lock_state(user_id):
        return {"locked_until": None}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_login_lock_state", fake_lock_state,
    )
    assert asyncio.run(check_login_lock("u")) is None


def test_check_login_lock_returns_state_when_locked(monkeypatch):
    """locked_until 在未来时返回锁定状态 dict。"""
    import asyncio
    import time
    from app.shared.utils.auth.login_lockout import check_login_lock

    async def fake_get_user(username):
        return {"id": 1, "username": "u"}

    async def fake_lock_state(user_id):
        return {"locked_until": time.time() + 600}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_login_lock_state", fake_lock_state,
    )
    state = asyncio.run(check_login_lock("u"))
    assert state is not None
    assert state["user_id"] == 1


def test_record_failure_locked_at_max_attempts(monkeypatch):
    """失败计数达到阈值即判定锁定（兜底二次判定，不依赖 SQL CASE）。"""
    import asyncio
    from types import SimpleNamespace
    from app.shared.utils.auth.login_lockout import record_failed_login_and_is_locked

    async def fake_get_user(username):
        return {"id": 1, "username": "u"}

    async def fake_record(user_id, max_attempts, lockout_seconds):
        return 5

    async def fake_lock_state(user_id):
        return {"locked_until": None}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username", fake_get_user,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.record_failed_login", fake_record,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_login_lock_state", fake_lock_state,
    )
    app = SimpleNamespace(state=SimpleNamespace(mfa_service=None))
    assert asyncio.run(
        record_failed_login_and_is_locked("u", app)
    ) is True


def test_record_failure_unknown_user_returns_false(monkeypatch):
    """不存在的用户名不累计、返回 False（反枚举）。"""
    import asyncio
    from types import SimpleNamespace
    from app.shared.utils.auth.login_lockout import record_failed_login_and_is_locked

    async def fake_get_user(username):
        return None

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )
    app = SimpleNamespace(state=SimpleNamespace(mfa_service=None))
    assert asyncio.run(
        record_failed_login_and_is_locked("ghost", app)
    ) is False
