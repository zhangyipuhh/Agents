# -*- coding:utf-8 -*-
"""
UserDB.ensure_admin_bootstrap 单元测试（等保三级 Task 2，2026-08-09 新增）。

覆盖：
- bootstrap_enabled=False 且不存在 admin 时 fail-loud（RuntimeError）；
- bootstrap_enabled=True + 强口令时创建 admin；
- 已存在 admin 且哈希命中已知弱默认集时，bootstrap_enabled=True 会轮换并清空 Token；
- 已存在 admin 且哈希非弱默认时静默返回；
- bootstrap_enabled=False 但 admin 哈希命中已知弱默认集时也 fail-loud（运维应主动重置）。

所有用例在 memory 模式下跑（不依赖 PostgreSQL）；UserDB.verify_credentials
在 memory 与 postgres 模式下都复用同一密码哈希工具，迁移检测逻辑相同。

注意：conftest.py 中的 ``_mock_user_db`` session 级 autouse fixture 会把
``UserDB.ensure_admin_exists`` 替换为 ``AsyncMock()``，防止 lifespan 期间真正创建 admin。
本测试用 ``_restore_ensure_admin_exists`` fixture 在每个用例内 ``importlib.reload``
模块以恢复真实的 classmethod（reload 只对方法描述符有效，类自身对象不变，
因此 ``UserDB._memory_users`` 等内存态保留）。
"""
from __future__ import annotations

import asyncio
import importlib

import pytest

from app.shared.utils.auth.password_policy import validate_password

STRONG_PASSWORD = "P@ssword1!"


class _Settings:
    """最小 settings 替身，仅暴露 ensure_admin_exists 关心的三个属性。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _clear_memory_users():
    """清空 UserDB 内存态，确保每个用例独立。"""
    from app.shared.utils.auth.user_db import UserDB

    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    UserDB._memory_login_lock.clear()


@pytest.fixture(autouse=True)
def _restore_ensure_admin_exists():
    """把 ``_mock_user_db`` session 级 autouse patch 撤销，本文件测试走真实实现。

    策略：``importlib.reload(user_db)`` 重新执行模块顶层代码，把
    ``UserDB.ensure_admin_exists`` 描述符重新绑定为模块源代码里的真实 classmethod。
    reload 不会替换 UserDB 类对象本身，所以 ``UserDB._memory_users`` 等类变量
    保持原状（同一 id）；同时我们在 setup / teardown 清空内存态避免污染。

    Yields:
        None。
    """
    from app.shared.utils.auth import user_db

    importlib.reload(user_db)
    _clear_memory_users()
    yield
    _clear_memory_users()


def test_bootstrap_disabled_without_admin_fails_loud():
    """bootstrap_enabled=False 且无 admin → RuntimeError（fail-loud）。"""
    from app.shared.utils.auth import user_db

    settings = _Settings(
        bootstrap_enabled=False,
        default_admin_username="admin",
        default_admin_password="",
    )
    with pytest.raises(RuntimeError):
        asyncio.run(user_db.UserDB.ensure_admin_exists(settings))


def test_bootstrap_creates_strong_admin():
    """bootstrap_enabled=True + 强口令 → 创建 admin，可用新口令登录。"""
    from app.shared.utils.auth import user_db

    settings = _Settings(
        bootstrap_enabled=True,
        default_admin_username="admin",
        default_admin_password=STRONG_PASSWORD,
    )
    asyncio.run(user_db.UserDB.ensure_admin_exists(settings))
    admin = asyncio.run(user_db.UserDB.get_user_by_username("admin"))
    assert admin is not None
    assert admin["role"] == "admin"
    assert asyncio.run(
        user_db.UserDB.verify_credentials("admin", STRONG_PASSWORD)
    ) is True


def test_bootstrap_rotates_known_weak_default():
    """已存在 admin 且哈希命中 admin123 → bootstrap_enabled=True 时轮换为强口令。"""
    from app.shared.utils.auth import user_db

    # 直接预制历史弱默认哈希，模拟已存在的 admin（绕过 create_user 的当前口令边界校验）
    user_db.UserDB._memory_users["admin"] = {
        "id": 1,
        "username": "admin",
        "password_hash": user_db.UserDB.hash_password("admin123"),
        "role": "admin",
    }
    settings = _Settings(
        bootstrap_enabled=True,
        default_admin_username="admin",
        default_admin_password=STRONG_PASSWORD,
    )
    asyncio.run(user_db.UserDB.ensure_admin_exists(settings))
    # 旧弱口令被轮换 → 不再可通过 admin123 登录
    assert asyncio.run(
        user_db.UserDB.verify_credentials("admin", "admin123")
    ) is False
    # 新强口令可用
    assert asyncio.run(
        user_db.UserDB.verify_credentials("admin", STRONG_PASSWORD)
    ) is True


def test_bootstrap_weak_password_raises_when_enabled():
    """bootstrap_enabled=True 但 default_admin_password 不满足强度 → RuntimeError。"""
    from app.shared.utils.auth import user_db

    settings = _Settings(
        bootstrap_enabled=True,
        default_admin_username="admin",
        default_admin_password="admin123",  # 弱默认
    )
    with pytest.raises(RuntimeError):
        asyncio.run(user_db.UserDB.ensure_admin_exists(settings))
    # admin 仍未被创建
    assert asyncio.run(user_db.UserDB.get_user_by_username("admin")) is None


def test_bootstrap_existing_admin_strong_password_silent():
    """已存在 admin 且哈希非弱默认 → 静默返回，不修改密码。"""
    from app.shared.utils.auth import user_db

    # 用强口令先建 admin（模拟已部署的生产库）
    asyncio.run(user_db.UserDB.create_user("admin", STRONG_PASSWORD, role="admin"))
    settings = _Settings(
        bootstrap_enabled=False,
        default_admin_username="admin",
        default_admin_password="",
    )
    asyncio.run(user_db.UserDB.ensure_admin_exists(settings))
    # 强口令仍可登录（未被轮换）
    assert asyncio.run(
        user_db.UserDB.verify_credentials("admin", STRONG_PASSWORD)
    ) is True


def test_bootstrap_existing_weak_admin_disabled_fails_loud():
    """已存在 admin 且哈希命中弱默认集，但 bootstrap_enabled=False → RuntimeError。"""
    from app.shared.utils.auth import user_db

    # 直接预制历史弱默认哈希，模拟已存在的 admin（绕过 create_user 的当前口令边界校验）
    user_db.UserDB._memory_users["admin"] = {
        "id": 1,
        "username": "admin",
        "password_hash": user_db.UserDB.hash_password("123456"),
        "role": "admin",
    }
    settings = _Settings(
        bootstrap_enabled=False,
        default_admin_username="admin",
        default_admin_password="",
    )
    with pytest.raises(RuntimeError):
        asyncio.run(user_db.UserDB.ensure_admin_exists(settings))


def test_bootstrap_custom_username():
    """default_admin_username 可定制；创建时按 settings 决定。"""
    from app.shared.utils.auth import user_db

    settings = _Settings(
        bootstrap_enabled=True,
        default_admin_username="ops",
        default_admin_password=STRONG_PASSWORD,
    )
    asyncio.run(user_db.UserDB.ensure_admin_exists(settings))
    ops = asyncio.run(user_db.UserDB.get_user_by_username("ops"))
    assert ops is not None
    assert ops["role"] == "admin"
    # "admin" 默认用户名不存在
    assert asyncio.run(user_db.UserDB.get_user_by_username("admin")) is None


def test_strONG_password_satisfies_policy():
    """sanity: STRONG_PASSWORD 满足密码强度校验（避免后续用例因政策变化失效）。"""
    ok, err = validate_password(STRONG_PASSWORD)
    assert ok is True, f"STRONG_PASSWORD must satisfy validate_password: {err}"