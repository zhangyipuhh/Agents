# -*- coding:utf-8 -*-
"""
UserDB 登录锁定字段 + 方法的 memory 模式单元测试。

覆盖：
- ``UserDB.record_failed_login`` 返回当前失败次数并按策略写入 locked_until；
- ``UserDB.get_login_lock_state`` 可正确反映 locked_until（时间戳）；
- ``UserDB.clear_login_lock`` 清零失败次数与锁定；
- 已锁定时 ``verify_credentials`` 仍返 True（凭据正确）但调用方应基于 lock
  状态进一步拒绝；本测试只锁定 UserDB.locked_until_until 状态保证。

Author: AI Assistant
Date: 2026-08-07
"""

import asyncio
import time

import pytest

from app.shared.utils.auth.user_db import UserDB


@pytest.fixture(autouse=True)
def reset_user_db():
    """每个测试前/后重置 UserDB 内存状态。"""
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0


def _create_test_user() -> int:
    user_id = asyncio.run(
        UserDB.create_user("lockuser", "P@ssword1!")
    )
    return user_id


def test_record_failed_login_returns_count_and_sets_lock():
    """登录失败计数累计到阈值时设置 locked_until。"""
    user_id = _create_test_user()

    # 第一次失败：count=1，不锁定
    count = asyncio.run(UserDB.record_failed_login(user_id, max_attempts=3, lockout_seconds=60))
    assert count == 1
    state = asyncio.run(UserDB.get_login_lock_state(user_id))
    assert state["failed_login_count"] == 1
    assert state["locked_until"] is None

    # 第二次：count=2
    count = asyncio.run(UserDB.record_failed_login(user_id, max_attempts=3, lockout_seconds=60))
    assert count == 2
    # 第三次：count=3 触发锁定
    count = asyncio.run(UserDB.record_failed_login(user_id, max_attempts=3, lockout_seconds=60))
    assert count == 3
    state = asyncio.run(UserDB.get_login_lock_state(user_id))
    assert state["failed_login_count"] == 3
    assert state["locked_until"] is not None
    assert state["locked_until"] > time.time()


def test_clear_login_lock_resets_state():
    """clear_login_lock 必须清零失败计数与 locked_until。"""
    user_id = _create_test_user()
    asyncio.run(UserDB.record_failed_login(user_id, max_attempts=1, lockout_seconds=60))
    state = asyncio.run(UserDB.get_login_lock_state(user_id))
    assert state["locked_until"] is not None

    asyncio.run(UserDB.clear_login_lock(user_id))
    state = asyncio.run(UserDB.get_login_lock_state(user_id))
    assert state["failed_login_count"] == 0
    assert state["locked_until"] is None


def test_get_login_lock_state_for_unknown_user_returns_zero():
    """未存在的 user_id 必须返失败计数 = 0 / locked_until = None，不抛异常。"""
    state = asyncio.run(UserDB.get_login_lock_state(user_id=99999))
    assert state["failed_login_count"] == 0
    assert state["locked_until"] is None


def test_login_lock_required_role_does_not_skip_others():
    """锁定字段为所有用户启用，不区分角色。

    普通用户锁定字段同样生效（强制启用策略针对 admin + 用户自己启用）。
    """
    admin_id = asyncio.run(UserDB.create_user("lockadmin", "P@ssword1!", role="admin"))
    asyncio.run(UserDB.record_failed_login(admin_id, max_attempts=1, lockout_seconds=60))
    state = asyncio.run(UserDB.get_login_lock_state(admin_id))
    assert state["locked_until"] is not None
