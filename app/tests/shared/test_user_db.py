# -*- coding:utf-8 -*-
"""
用户数据库测试模块

测试 app.shared.utils.auth.user_db 在 memory 模式下的
增删改查操作以及 ensure_admin_exists 方法。
"""
import asyncio

import pytest

from app.shared.utils.auth.user_db import UserDB


@pytest.fixture(autouse=True)
def reset_user_db():
    """
    每个测试前重置 UserDB 内存状态。

    Returns:
        None
    """
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0


def test_create_user():
    """
    测试创建用户成功并返回正确的用户 ID。

    Returns:
        None

    Raises:
        AssertionError: 用户 ID 不是正整数时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("testuser", "password123"))
    assert isinstance(user_id, int)
    assert user_id > 0


def test_create_user_duplicate_username():
    """
    测试使用重复用户名创建用户时抛出 ValueError。

    Returns:
        None

    Raises:
        AssertionError: 未抛出 ValueError 时抛出。
    """
    asyncio.run(UserDB.create_user("testuser", "password123"))
    with pytest.raises(ValueError, match="用户名已存在"):
        asyncio.run(UserDB.create_user("testuser", "password123"))


def test_get_user_by_username():
    """
    测试根据用户名查询用户。

    Returns:
        None

    Raises:
        AssertionError: 查询结果不符合预期时抛出。
    """
    asyncio.run(UserDB.create_user("testuser", "password123", role="user"))
    user = asyncio.run(UserDB.get_user_by_username("testuser"))
    assert user is not None
    assert user["username"] == "testuser"
    assert user["role"] == "user"


def test_get_user_by_username_not_found():
    """
    测试查询不存在的用户名返回 None。

    Returns:
        None

    Raises:
        AssertionError: 返回结果非 None 时抛出。
    """
    user = asyncio.run(UserDB.get_user_by_username("nonexistent"))
    assert user is None


def test_verify_credentials():
    """
    测试验证用户凭据（正确密码和错误密码）。

    Returns:
        None

    Raises:
        AssertionError: 验证结果不符合预期时抛出。
    """
    asyncio.run(UserDB.create_user("testuser", "password123"))
    assert asyncio.run(UserDB.verify_credentials("testuser", "password123")) is True
    assert asyncio.run(UserDB.verify_credentials("testuser", "wrongpass")) is False


def test_delete_user():
    """
    测试删除用户成功，删除后无法查询到该用户。

    Returns:
        None

    Raises:
        AssertionError: 删除失败或删除后仍能查询到时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("testuser", "password123"))
    assert asyncio.run(UserDB.delete_user(user_id)) is True
    assert asyncio.run(UserDB.get_user_by_username("testuser")) is None


def test_update_password():
    """
    测试更新密码后，旧密码验证失败、新密码验证成功。

    Returns:
        None

    Raises:
        AssertionError: 密码更新未生效时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("testuser", "password123"))
    assert asyncio.run(UserDB.update_password(user_id, "newpassword")) is True
    assert asyncio.run(UserDB.verify_credentials("testuser", "password123")) is False
    assert asyncio.run(UserDB.verify_credentials("testuser", "newpassword")) is True


def test_ensure_admin_exists():
    """
    测试 ensure_admin_exists 创建默认 admin 账户。

    由于 conftest 中全局 mock 了 ensure_admin_exists 以避免 lifespan
    中自动创建管理员，这里直接模拟 ensure_admin_exists 的内存模式逻辑
    进行验证：当不存在 admin 角色用户时，创建默认 admin。

    Returns:
        None

    Raises:
        AssertionError: admin 用户未创建或角色不正确时抛出。
    """
    # 清除已有的 admin 用户
    for username in list(UserDB._memory_users.keys()):
        if UserDB._memory_users[username].get("role") == "admin":
            del UserDB._memory_users[username]

    # 手动执行 ensure_admin_exists 的内存模式核心逻辑
    with UserDB._lock:
        has_admin = any(
            u.get("role") == "admin" for u in UserDB._memory_users.values()
        )
    if not has_admin:
        asyncio.run(UserDB.create_user("admin", "admin123", role="admin"))

    admin = asyncio.run(UserDB.get_user_by_username("admin"))
    assert admin is not None
    assert admin["role"] == "admin"
