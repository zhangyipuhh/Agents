# -*- coding:utf-8 -*-
"""
UserDB 注册审批相关方法测试(2026-08-30 新增)

覆盖：
- create_user 接受 status / register_ip 参数；
- get_user_by_username / get_user_by_id / list_users 返回注册审批相关字段；
- update_user_status 含并发守卫(仅 pending_approval 可修改)与 status 白名单；
- list_pending_users 仅返回 status='pending_approval' 用户。
"""
import asyncio
import pytest
from app.shared.utils.auth.user_db import UserDB


@pytest.fixture(autouse=True)
def reset_user_db():
    """
    每个测试前/后重置 UserDB 内存状态。

    Returns:
        None
    """
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0


def test_create_user_default_status_is_active():
    """
    测试默认 status='active'。

    Returns:
        None

    Raises:
        AssertionError: 默认 status 不是 active 时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("alice", "P@ssword1!"))
    user = asyncio.run(UserDB.get_user_by_username("alice"))
    assert user is not None
    assert user["status"] == "active"


def test_create_user_accepts_status_pending_approval():
    """
    测试 create_user 接受 status='pending_approval' 与 register_ip 参数。

    Returns:
        None

    Raises:
        AssertionError: status/register_ip 未被保存时抛出。
    """
    user_id = asyncio.run(
        UserDB.create_user("bob", "P@ssword1!", status="pending_approval", register_ip="10.0.0.5")
    )
    user = asyncio.run(UserDB.get_user_by_username("bob"))
    assert user["status"] == "pending_approval"
    assert user["register_ip"] == "10.0.0.5"


def test_get_user_by_username_returns_status_field():
    """
    测试 get_user_by_username 返回 status / register_ip / status_reason 字段。

    Returns:
        None

    Raises:
        AssertionError: 字段缺失或值错误时抛出。
    """
    asyncio.run(UserDB.create_user("carol", "P@ssword1!", status="pending_approval"))
    user = asyncio.run(UserDB.get_user_by_username("carol"))
    assert "status" in user
    assert "register_ip" in user
    assert "status_reason" in user
    assert user["status"] == "pending_approval"
    assert user["register_ip"] is None
    assert user["status_reason"] is None


def test_get_user_by_id_returns_status_field():
    """
    测试 get_user_by_id 返回 status 字段(默认 active)。

    Returns:
        None

    Raises:
        AssertionError: 字段缺失或值错误时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("dave", "P@ssword1!"))
    user = asyncio.run(UserDB.get_user_by_id(user_id))
    assert user["status"] == "active"


def test_list_users_returns_status_field():
    """
    测试 list_users 返回每个用户的 status 字段。

    Returns:
        None

    Raises:
        AssertionError: 列表缺失 status 或值错误时抛出。
    """
    asyncio.run(UserDB.create_user("eve", "P@ssword1!"))
    asyncio.run(UserDB.create_user("frank", "P@ssword1!", status="pending_approval"))
    users = asyncio.run(UserDB.list_users())
    assert len(users) == 2
    statuses = {u["username"]: u["status"] for u in users}
    assert statuses == {"eve": "active", "frank": "pending_approval"}


def test_update_user_status_approve():
    """
    测试 update_user_status 审批通过：active + approved_by_user_id + approved_at。

    Returns:
        None

    Raises:
        AssertionError: 返回 False 或字段未更新时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("grace", "P@ssword1!", status="pending_approval"))
    result = asyncio.run(UserDB.update_user_status(
        user_id=user_id, status="active", reason=None, operator_user_id=1
    ))
    assert result is True
    user = asyncio.run(UserDB.get_user_by_id(user_id))
    assert user["status"] == "active"
    assert user["approved_by_user_id"] == 1
    assert user["approved_at"] is not None


def test_update_user_status_reject_with_reason():
    """
    测试 update_user_status 拒绝：写入 status_reason。

    Returns:
        None

    Raises:
        AssertionError: 拒绝原因未保存时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("henry", "P@ssword1!", status="pending_approval"))
    result = asyncio.run(UserDB.update_user_status(
        user_id=user_id, status="rejected", reason="信息不实", operator_user_id=1
    ))
    assert result is True
    user = asyncio.run(UserDB.get_user_by_id(user_id))
    assert user["status"] == "rejected"
    assert user["status_reason"] == "信息不实"


def test_update_user_status_concurrent_guard_returns_false():
    """
    测试并发守卫：用户已是 active 时再次调用 update_user_status 必须返回 False。

    Returns:
        None

    Raises:
        AssertionError: 守卫失效时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("ivy", "P@ssword1!", status="active"))
    result = asyncio.run(UserDB.update_user_status(
        user_id=user_id, status="rejected", reason="X", operator_user_id=1
    ))
    assert result is False
    user = asyncio.run(UserDB.get_user_by_id(user_id))
    assert user["status"] == "active"


def test_update_user_status_invalid_status_raises():
    """
    测试 update_user_status 收到非法 status 时抛 ValueError。

    Returns:
        None

    Raises:
        AssertionError: 未抛 ValueError 或文案不匹配时抛出。
    """
    user_id = asyncio.run(UserDB.create_user("jack", "P@ssword1!", status="pending_approval"))
    with pytest.raises(ValueError, match="status 必须是"):
        asyncio.run(UserDB.update_user_status(
            user_id=user_id, status="invalid", reason=None, operator_user_id=1
        ))


def test_update_user_status_user_not_found_returns_false():
    """
    测试用户不存在时 update_user_status 返回 False。

    Returns:
        None

    Raises:
        AssertionError: 返回 True 或抛异常时抛出。
    """
    result = asyncio.run(UserDB.update_user_status(
        user_id=99999, status="active", reason=None, operator_user_id=1
    ))
    assert result is False


def test_list_pending_users_filters_correctly():
    """
    测试 list_pending_users 只返回 status='pending_approval' 用户,且包含 register_ip 字段。

    Returns:
        None

    Raises:
        AssertionError: 过滤错误或字段缺失时抛出。
    """
    asyncio.run(UserDB.create_user("kate", "P@ssword1!"))
    asyncio.run(UserDB.create_user("liam", "P@ssword1!", status="pending_approval"))
    asyncio.run(UserDB.create_user("mia", "P@ssword1!", status="pending_approval"))
    pending = asyncio.run(UserDB.list_pending_users())
    usernames = [u["username"] for u in pending]
    assert sorted(usernames) == ["liam", "mia"]
    for u in pending:
        assert u["status"] == "pending_approval"
        assert "register_ip" in u