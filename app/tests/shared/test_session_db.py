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


def test_add_session_with_project_id():
    """2026-06-30 新增：add_session 接受 project_id 参数并持久化。"""
    asyncio.run(SessionDB.add_session("sess-p001", 1, "user1", project_id=42))
    session = asyncio.run(SessionDB.get_session("sess-p001"))
    assert session is not None
    assert session["project_id"] == 42


def test_update_session_project():
    """2026-06-30 新增：update_session_project 修改会话关联的项目。"""
    asyncio.run(SessionDB.add_session("sess-p002", 1, "user1"))
    # 初始 project_id 为 None
    session = asyncio.run(SessionDB.get_session("sess-p002"))
    assert session["project_id"] is None

    # 绑定
    asyncio.run(SessionDB.update_session_project("sess-p002", 5))
    session = asyncio.run(SessionDB.get_session("sess-p002"))
    assert session["project_id"] == 5

    # 解除（传 None）
    asyncio.run(SessionDB.update_session_project("sess-p002", None))
    session = asyncio.run(SessionDB.get_session("sess-p002"))
    assert session["project_id"] is None


def test_get_user_sessions_includes_project_id():
    """2026-06-30 新增：get_user_sessions 返回的会话应包含 project_id 字段。"""
    asyncio.run(SessionDB.add_session("sess-p003", 1, "user1", project_id=99))
    sessions = asyncio.run(SessionDB.get_user_sessions(1))
    assert len(sessions) >= 1
    sess = next(s for s in sessions if s["session_id"] == "sess-p003")
    assert sess["project_id"] == 99


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


def test_add_session_default_agent_fields():
    """
    测试新添加的会话默认 agent_type='default' 且 agent_display_name=''。

    Returns:
        None

    Raises:
        AssertionError: 默认值不符合预期时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-agent-default", 1, "user1"))
    session = asyncio.run(SessionDB.get_session("sess-agent-default"))
    assert session is not None
    assert session.get("agent_type") == "default"
    assert session.get("agent_display_name") == ""


def test_update_session_agent_updates_memory():
    """
    测试 update_session_agent 正确更新内存缓存中的 agent_type 和 agent_display_name。

    Returns:
        None

    Raises:
        AssertionError: 更新未生效或字段值不正确时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-agent-update", 1, "user1"))
    asyncio.run(SessionDB.update_session_agent("sess-agent-update", "map_agent", "地图智能体"))
    session = asyncio.run(SessionDB.get_session("sess-agent-update"))
    assert session is not None
    assert session["agent_type"] == "map_agent"
    assert session["agent_display_name"] == "地图智能体"


def test_get_session_returns_agent_fields():
    """
    测试 get_session 返回的字典包含 agent_type 和 agent_display_name 字段。

    Returns:
        None

    Raises:
        AssertionError: 字段缺失时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-agent-fields", 1, "user1"))
    asyncio.run(SessionDB.update_session_agent("sess-agent-fields", "devops_agent", "DevOps 智能体"))
    session = asyncio.run(SessionDB.get_session("sess-agent-fields"))
    assert session is not None
    assert "agent_type" in session
    assert "agent_display_name" in session
    assert session["agent_type"] == "devops_agent"
    assert session["agent_display_name"] == "DevOps 智能体"


def test_get_user_sessions_returns_agent_fields():
    """
    测试 get_user_sessions 返回的列表项包含 agent_type 和 agent_display_name。

    Returns:
        None

    Raises:
        AssertionError: 字段缺失或值不正确时抛出。
    """
    asyncio.run(SessionDB.add_session("sess-agent-list-001", 1, "user1"))
    asyncio.run(SessionDB.update_session_agent("sess-agent-list-001", "audit_agent", "审计智能体"))

    sessions = asyncio.run(SessionDB.get_user_sessions(1))
    target = next((s for s in sessions if s["session_id"] == "sess-agent-list-001"), None)
    assert target is not None
    assert target.get("agent_type") == "audit_agent"
    assert target.get("agent_display_name") == "审计智能体"
