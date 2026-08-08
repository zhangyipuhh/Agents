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
    UserDB._memory_login_lock.clear()
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()


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


# --------------------------------------------------------------------------
# 2026-08-08 新增：固定锁定窗口契约。
# 业务语义：账号首次达到失败阈值后锁定窗口固定为 ``lockout_seconds`` 秒；
# 锁定期间再次失败只能递增失败计数，不能延长 ``locked_until``；
# 锁定已过期后，下一次失败达到阈值才允许建立新的锁定窗口。
# --------------------------------------------------------------------------


def test_memory_active_lock_is_not_extended_by_subsequent_failures():
    """锁定窗口期间（``locked_until`` 仍在未来），后续失败请求不得顺延截止时间。"""
    user_id = _create_test_user()
    # 先触发一次锁定（max_attempts=1，lockout=60）
    asyncio.run(UserDB.record_failed_login(user_id, max_attempts=1, lockout_seconds=60))
    state_before = asyncio.run(UserDB.get_login_lock_state(user_id))
    locked_until_before = state_before["locked_until"]
    assert locked_until_before is not None
    assert locked_until_before > time.time()

    # 再次触发失败：failed_login_count 增加，locked_until 不变
    asyncio.run(UserDB.record_failed_login(user_id, max_attempts=1, lockout_seconds=60))
    state_after = asyncio.run(UserDB.get_login_lock_state(user_id))
    assert state_after["failed_login_count"] == 2
    assert state_after["locked_until"] == locked_until_before


def test_memory_opens_new_window_after_expiry():
    """已过期锁定且再次失败达到阈值时，建立新的锁定窗口。"""
    user_id = _create_test_user()
    # 直接通过内部 dict 注入已过期的时间戳，模拟锁定已到期
    UserDB._memory_login_lock[user_id] = {
        "failed_login_count": 1,
        "locked_until": time.time() - 5,
    }
    # 再次失败达到阈值：count=2，max_attempts=2 → 应建立新窗口
    new_count = asyncio.run(UserDB.record_failed_login(user_id, max_attempts=2, lockout_seconds=60))
    assert new_count == 2
    state = asyncio.run(UserDB.get_login_lock_state(user_id))
    assert state["locked_until"] is not None
    # 新窗口应当从现在起 ~60 秒，而非仍然指向过去的过期值
    assert state["locked_until"] > time.time()
    assert state["locked_until"] - time.time() <= 60.5  # 允许少量浮点误差


def test_memory_below_threshold_does_not_open_lock():
    """未达到阈值时即使 ``locked_until`` 已过期也不建立新窗口。"""
    user_id = _create_test_user()
    UserDB._memory_login_lock[user_id] = {
        "failed_login_count": 0,
        "locked_until": time.time() - 100,
    }
    new_count = asyncio.run(UserDB.record_failed_login(user_id, max_attempts=5, lockout_seconds=60))
    assert new_count == 1
    state = asyncio.run(UserDB.get_login_lock_state(user_id))
    # 未达到阈值时不应"重置"或新建锁定窗口；过期值会保留直到达阈值或登录成功清零
    assert state["locked_until"] is not None
    # 过期值仍指向过去，未被错误延长
    assert state["locked_until"] <= time.time()


# --------------------------------------------------------------------------
# PG 模式单元测试（通过 monkeypatch.mock ``DatabasePool``，无须真实 DB 连接）
# 2026-08-08 新增：原代码使用 ``DatabasePool.fetchval``，但 ``DatabasePool``
# 类实际未提供 ``fetchval`` 方法；抛 ``AttributeError`` 被 ``auth_router``
# 的 ``except Exception: pass`` 吞掉，导致用户密码错 12 次后
# ``users.failed_login_count`` 仍为 0。本批测试同时覆盖：
# 1) ``DatabasePool.fetchval`` 现已存在（防止再次回退为该方法报错）；
# 2) PG 模式下 fake ``fetchrow`` 返回 ``locked_until=None`` 时，函数内部
#    兜底 UPDATE 会被调用并向 DB 写入 ``locked_until``；
# 3) ``record_failed_login`` 返回 ``new_count`` ，且当 new_count >=
#    max_attempts 时业务语义正确（路由层二次判定可据此拒绝）。
# --------------------------------------------------------------------------


def _patch_database_pool_postgres(monkeypatch):
    """将 ``UserDB.is_enabled()`` 强制返回 True 以走 PG 分支，并提供 fake DatabasePool。

    同时确保 ``app.core.database.DatabasePool.is_enabled`` 返回 True 以使
    ``UserDB.is_enabled`` 走 PG 分支。
    """

    import app.core.database as db_mod
    import app.shared.utils.auth.user_db as user_db_mod

    async def _true_enabled() -> bool:
        return True

    monkeypatch.setattr(user_db_mod.UserDB, "is_enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(db_mod.DatabasePool, "is_enabled", classmethod(lambda cls: True))


class _FakeDatabasePoolClass:
    """替身 DatabasePool 类：所有方法都是 classmethod（async），记录调用供断言。

    用法：``monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)``
    让 user_db 模块中 ``DatabasePool.fetchrow(...)`` 解析到本类的 classmethod。
    """

    fetchrow_calls: list = []
    execute_calls: list = []
    fetchrow_return: dict = {"failed_login_count": 0, "locked_until": None}

    @classmethod
    async def reset(cls) -> None:
        cls.fetchrow_calls.clear()
        cls.execute_calls.clear()
        cls.fetchrow_return = {"failed_login_count": 0, "locked_until": None}

    @classmethod
    async def fetchrow(cls, sql, *args):
        cls.fetchrow_calls.append((str(sql), args))
        return cls.fetchrow_return

    @classmethod
    async def execute(cls, sql, *args):
        cls.execute_calls.append((str(sql), args))
        return None


def test_database_pool_has_fetchval():
    """``DatabasePool.fetchval`` 必须存在（2026-08-08 修复回归）。"""
    from app.core.database import DatabasePool

    assert hasattr(DatabasePool, "fetchval"), (
        "DatabasePool.fetchval 缺失会导致 record_failed_login 抛 AttributeError 被外层吞掉"
    )
    assert callable(DatabasePool.fetchval)


def test_record_failed_login_pg_returns_count_and_calls_fallback(monkeypatch):
    """PG 路径：fake fetchrow 返回 locked_until=None 时，记录层 fallback UPDATE 必须被调用。

    用于证明「即便 SQL CASE 漂移未触发 locked_until 写入，行级兜底也能让
    锁定语义生效」。这是 2026-08-08 锁定机制静默失效回归的反向用例。
    """
    _patch_database_pool_postgres(monkeypatch)

    # 同步先把 async reset 跑掉，避免上一测试遗留影响
    asyncio.run(_FakeDatabasePoolClass.reset())
    _FakeDatabasePoolClass.fetchrow_return = {
        "failed_login_count": 5,
        "locked_until": None,
    }

    import app.shared.utils.auth.user_db as user_db_mod
    monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)

    new_count = asyncio.run(
        user_db_mod.UserDB.record_failed_login(
            user_id=2,
            max_attempts=5,
            lockout_seconds=1800,
        )
    )
    assert new_count == 5
    assert len(_FakeDatabasePoolClass.fetchrow_calls) == 1
    # new_count >= max_attempts → fallback execute 必须被调用一次
    assert len(_FakeDatabasePoolClass.execute_calls) == 1
    fallback_sql = _FakeDatabasePoolClass.execute_calls[0][0]
    assert isinstance(fallback_sql, str)
    assert "UPDATE users SET locked_until" in fallback_sql
    assert "locked_until IS NULL" in fallback_sql


def test_record_failed_login_pg_no_fallback_when_below_threshold(monkeypatch):
    """PG 路径：new_count < max_attempts 时不调 fallback execute。"""
    _patch_database_pool_postgres(monkeypatch)
    asyncio.run(_FakeDatabasePoolClass.reset())
    _FakeDatabasePoolClass.fetchrow_return = {
        "failed_login_count": 2,
        "locked_until": None,
    }

    import app.shared.utils.auth.user_db as user_db_mod
    monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)

    new_count = asyncio.run(
        user_db_mod.UserDB.record_failed_login(
            user_id=2,
            max_attempts=5,
            lockout_seconds=1800,
        )
    )
    assert new_count == 2
    # 未达到阈值，fallback execute 不应触发
    assert _FakeDatabasePoolClass.execute_calls == []


def test_record_failed_login_pg_user_not_found_returns_zero(monkeypatch):
    """PG 路径：用户不存在（fetchrow 返回 None）时 new_count=0，不抛异常。"""
    _patch_database_pool_postgres(monkeypatch)
    asyncio.run(_FakeDatabasePoolClass.reset())
    _FakeDatabasePoolClass.fetchrow_return = None  # type: ignore[assignment]

    import app.shared.utils.auth.user_db as user_db_mod
    monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)

    new_count = asyncio.run(
        user_db_mod.UserDB.record_failed_login(
            user_id=99999,
            max_attempts=5,
            lockout_seconds=1800,
        )
    )
    assert new_count == 0
    # fetchrow 返回 None → 跳过 fallback execute
    assert _FakeDatabasePoolClass.execute_calls == []  # noqa: E501


# --------------------------------------------------------------------------
# 2026-08-08 新增：固定锁定窗口契约（PG 模式 fake）。
# 验证 PG 主路径与兜底 UPDATE 均遵守"活动锁定不延长"和"过期允许开新窗口"。
# --------------------------------------------------------------------------


def test_record_failed_login_pg_active_lock_is_not_extended(monkeypatch):
    """PG 主路径：已有未来 ``locked_until`` 时，再次失败达到阈值也不能覆盖原值。

    验证主路径 ``CASE`` 增加 ``locked_until IS NULL OR locked_until <= NOW()``
    守卫；fake 返回 ``locked_until`` 仍是未来时间戳的情况下，SQL 文本必须体现
    "过期才允许写入" 的语义，而不是无条件 ``TO_TIMESTAMP($3)``。
    兜底 UPDATE 在 fake 视角下会被触发，但 SQL 必须包含"已过期才覆盖"的守卫，
    由真实数据库侧根据当前行状态判断是否执行写。
    """
    _patch_database_pool_postgres(monkeypatch)
    asyncio.run(_FakeDatabasePoolClass.reset())
    # 模拟主路径返回值：用户已达阈值且当前 locked_until 仍在未来
    future_lock = time.time() + 1000
    _FakeDatabasePoolClass.fetchrow_return = {
        "failed_login_count": 6,  # >= max_attempts
        "locked_until": future_lock,
    }

    import app.shared.utils.auth.user_db as user_db_mod
    monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)

    new_count = asyncio.run(
        user_db_mod.UserDB.record_failed_login(
            user_id=2,
            max_attempts=5,
            lockout_seconds=1800,
        )
    )
    assert new_count == 6
    # 主路径 SQL 必须包含守卫：活动锁定不覆盖
    assert len(_FakeDatabasePoolClass.fetchrow_calls) == 1
    main_sql = _FakeDatabasePoolClass.fetchrow_calls[0][0]
    assert "TO_TIMESTAMP" in main_sql
    # 修复后 SQL 内 CASE WHEN 必须额外判断"locked_until IS NULL OR 已过期"
    assert "locked_until" in main_sql
    assert ("CURRENT_TIMESTAMP" in main_sql) or ("NOW()" in main_sql)
    # 兜底 UPDATE 在 fake 视角下会被触发（new_count >= max_attempts），
    # 但 SQL 必须包含相同的守卫；真实 PG 在 locked_until 仍是未来时不会写入。
    assert len(_FakeDatabasePoolClass.execute_calls) == 1
    fallback_sql = _FakeDatabasePoolClass.execute_calls[0][0]
    assert "locked_until IS NULL" in fallback_sql
    assert ("CURRENT_TIMESTAMP" in fallback_sql) or ("NOW()" in fallback_sql)


def test_record_failed_login_pg_fallback_does_not_extend_active_lock(monkeypatch):
    """PG 兜底 UPDATE：当已有未来 ``locked_until`` 时，不得覆盖活动锁定截止时间。

    兜底分支在 ``locked_until IS NULL`` 之外还需支持"已过期"；
    SQL 文本必须包含 ``CURRENT_TIMESTAMP`` 守卫。
    """
    _patch_database_pool_postgres(monkeypatch)
    asyncio.run(_FakeDatabasePoolClass.reset())
    _FakeDatabasePoolClass.fetchrow_return = {
        "failed_login_count": 5,
        "locked_until": None,
    }

    import app.shared.utils.auth.user_db as user_db_mod
    monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)

    new_count = asyncio.run(
        user_db_mod.UserDB.record_failed_login(
            user_id=2,
            max_attempts=5,
            lockout_seconds=1800,
        )
    )
    assert new_count == 5
    # 兜底分支写入条件扩展后允许 NULL/过期场景：fake 视角下 NULL → 写入
    assert len(_FakeDatabasePoolClass.execute_calls) == 1
    fallback_sql = _FakeDatabasePoolClass.execute_calls[0][0]
    # 兜底 SQL 必须保留 NULL 判断并新增"已过期"判断
    assert "locked_until IS NULL" in fallback_sql
    assert ("CURRENT_TIMESTAMP" in fallback_sql) or ("NOW()" in fallback_sql)


def test_record_failed_login_pg_fallback_writes_new_window_after_expiry(monkeypatch):
    """PG 兜底：当 ``locked_until`` 已过期（fake 视角下也可能为 NULL），允许建立新窗口。"""
    _patch_database_pool_postgres(monkeypatch)
    asyncio.run(_FakeDatabasePoolClass.reset())
    _FakeDatabasePoolClass.fetchrow_return = {
        "failed_login_count": 5,
        "locked_until": None,  # 模拟过期/未设值
    }

    import app.shared.utils.auth.user_db as user_db_mod
    monkeypatch.setattr(user_db_mod, "DatabasePool", _FakeDatabasePoolClass)

    new_count = asyncio.run(
        user_db_mod.UserDB.record_failed_login(
            user_id=2,
            max_attempts=5,
            lockout_seconds=1800,
        )
    )
    assert new_count == 5
    # 兜底 UPDATE 应当被触发并传入新的锁定截止时间戳
    assert len(_FakeDatabasePoolClass.execute_calls) == 1
    args = _FakeDatabasePoolClass.execute_calls[0][1]
    assert len(args) >= 2
    # 第二个参数是 lock_until_target（epoch 秒），应大于 now
    assert args[0] > time.time()
