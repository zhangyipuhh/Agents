# -*- coding:utf-8 -*-
"""
会话数据库测试模块

测试 app.shared.utils.auth.session_db 在 memory 模式下的 CRUD 操作。
"""
import asyncio

import pytest

from app.shared.utils.auth.session_db import SessionDB


@pytest.fixture(autouse=True)
def reset_session_db():
    """
    每个测试前重置 SessionDB 内存缓存和初始化状态。

    Returns:
        None
    """
    SessionDB._memory_cache.clear()
    SessionDB._initialized = False
    yield
    SessionDB._memory_cache.clear()
    SessionDB._initialized = False


def test_add_session():
    """
    测试添加会话后可以通过 get_session 查询到。

    Returns:
        None

    Raises:
        AssertionError: 会话未正确存储时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-001", 1, "user1"))
    session = asyncio.run(SessionDB.get_session("sess-001"))
    assert session is not None
    assert session["username"] == "user1"
    assert session["user_id"] == 1


def test_get_session_not_found():
    """
    测试查询不存在的会话返回 None。

    Returns:
        None

    Raises:
        AssertionError: 返回结果非 None 时抛出。
    """
    session = asyncio.run(SessionDB.get_session("nonexistent"))
    assert session is None


def test_verify_session():
    """
    测试 verify_session 正确判断会话归属。

    Returns:
        None

    Raises:
        AssertionError: 验证结果不符合预期时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-001", 1, "user1"))
    assert asyncio.run(SessionDB.verify_session("sess-001", "user1")) is True
    assert asyncio.run(SessionDB.verify_session("sess-001", "user2")) is False
    assert asyncio.run(SessionDB.verify_session("nonexistent", "user1")) is False


def test_delete_session():
    """
    测试删除会话成功后，再次查询返回 None。

    Returns:
        None

    Raises:
        AssertionError: 删除未生效时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-001", 1, "user1"))
    assert asyncio.run(SessionDB.delete_session("sess-001")) is True
    assert asyncio.run(SessionDB.get_session("sess-001")) is None


def test_get_user_sessions():
    """
    测试获取指定用户的所有会话列表。

    Returns:
        None

    Raises:
        AssertionError: 返回的会话数量或内容不符合预期时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-001", 1, "user1"))
    asyncio.run(SessionDB.add_session("sess-002", 1, "user1"))
    asyncio.run(SessionDB.add_session("sess-003", 2, "user2"))

    sessions = asyncio.run(SessionDB.get_user_sessions(1))
    assert len(sessions) == 2
    session_ids = {s["session_id"] for s in sessions}
    assert session_ids == {"sess-001", "sess-002"}
