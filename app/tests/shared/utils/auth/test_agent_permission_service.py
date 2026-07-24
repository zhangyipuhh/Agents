# -*- coding:utf-8 -*-
"""
AgentPermissionService 单元测试。

覆盖点：
- db=None 下降级：preload_all no-op；grant/revoke/replace 只写内存
- grant / revoke / replace 内存 + DB 双写
- get_user_agent_grants 读取缓存
- get_visible_agents：admin 旁路 + 普通用户按 ACL 过滤
- migrate_from_users_allowed_agents 幂等性
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


# =============================================================================
# P0: 导入与基础可用性
# =============================================================================


def test_agent_permission_service_importable():
    """测试模块可导入。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    assert AgentPermissionService is not None


def test_init_user_agent_acl_schema_callable():
    """测试 init_user_agent_acl_schema 是可调用的协程函数。"""
    from app.shared.utils.auth.agent_permission_service import init_user_agent_acl_schema

    assert callable(init_user_agent_acl_schema)


def test_migrate_function_importable():
    """测试迁移函数可导入。"""
    from app.shared.utils.auth.agent_permission_service import migrate_from_users_allowed_agents

    assert callable(migrate_from_users_allowed_agents)


# =============================================================================
# P1: db=None 降级
# =============================================================================


@pytest.mark.asyncio
async def test_preload_all_db_none_is_noop():
    """db=None 时 preload_all 应该是 no-op，不抛错。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    await svc.preload_all()
    assert svc._cache == {}


@pytest.mark.asyncio
async def test_grant_db_none_only_writes_memory():
    """db=None 时 grant 仅写内存。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    await svc.grant(1, {"map_agent", "project"})
    assert svc._cache[1] == {"map_agent", "project"}


@pytest.mark.asyncio
async def test_revoke_db_none_only_writes_memory():
    """db=None 时 revoke 仅写内存。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    svc._cache[1] = {"map_agent", "project"}
    await svc.revoke(1, {"map_agent"})
    assert svc._cache[1] == {"project"}


@pytest.mark.asyncio
async def test_replace_db_none_only_writes_memory():
    """db=None 时 replace 仅写内存。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    svc._cache[1] = {"old_agent"}
    await svc.replace(1, {"new_agent1", "new_agent2"})
    assert svc._cache[1] == {"new_agent1", "new_agent2"}


# =============================================================================
# P1: get_user_agent_grants
# =============================================================================


@pytest.mark.asyncio
async def test_get_user_agent_grants_returns_empty_for_unknown_user():
    """get_user_agent_grants 未授权用户返空 set。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    granted = await svc.get_user_agent_grants(999)
    assert granted == set()


@pytest.mark.asyncio
async def test_get_user_agent_grants_sync_returns_empty_for_unknown_user():
    """get_user_agent_grants_sync 未授权用户返空 set。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    granted = svc.get_user_agent_grants_sync(999)
    assert granted == set()


@pytest.mark.asyncio
async def test_get_user_agent_grants_returns_set_copy():
    """get_user_agent_grants 返回的 set 是 copy（不能影响缓存）。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    svc._cache[1] = {"map_agent"}
    granted = await svc.get_user_agent_grants(1)
    granted.add("new_agent")
    # 缓存不应被修改
    assert svc._cache[1] == {"map_agent"}


# =============================================================================
# P1: get_visible_agents
# =============================================================================


def test_get_visible_agents_admin_returns_all():
    """admin 走全量，绕过 ACL。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    svc._cache[1] = {"map_agent"}  # 即便有 ACL，admin 也不受限制
    all_agents = ["map_agent", "project", "knowledge_ydt"]
    visible = svc.get_visible_agents(user_id=1, all_agent_names=all_agents, is_admin=True)
    assert visible == all_agents


def test_get_visible_agents_normal_user_filters_by_acl():
    """普通用户按 ACL 过滤。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    svc._cache[1] = {"map_agent", "project"}
    all_agents = ["map_agent", "project", "knowledge_ydt"]
    visible = svc.get_visible_agents(user_id=1, all_agent_names=all_agents, is_admin=False)
    assert sorted(visible) == ["map_agent", "project"]


def test_get_visible_agents_normal_user_no_acl_returns_empty():
    """普通用户无 ACL 时返空列表。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    svc = AgentPermissionService(db=None)
    all_agents = ["map_agent", "project", "knowledge_ydt"]
    visible = svc.get_visible_agents(user_id=999, all_agent_names=all_agents, is_admin=False)
    assert visible == []


# =============================================================================
# P1: grant / revoke / replace 内存 + DB 双写
# =============================================================================


@pytest.mark.asyncio
async def test_grant_writes_db():
    """grant 内存 + DB 双写。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    db = MagicMock()
    db.execute = AsyncMock()
    svc = AgentPermissionService(db=db)
    await svc.grant(1, {"map_agent", "project"}, operator_id=99)
    # 内存
    assert svc._cache[1] == {"map_agent", "project"}
    # DB execute 调用次数 = 2 次（每个 agent 一次）
    assert db.execute.await_count == 2
    # 验证 SQL 调用形式（asyncpg 形式：await db.execute(sql, p1, p2, ...)
    # await_args.args 是 (sql, p1, p2, ...) 形式
    first_call_args = db.execute.await_args_list[0].args
    sql = first_call_args[0]
    params = first_call_args[1:]
    assert "INSERT INTO user_agent_acl" in sql
    assert params[0] == 1  # user_id
    assert params[1] in ("map_agent", "project")  # agent_name
    assert params[2] == 99  # operator_id


@pytest.mark.asyncio
async def test_revoke_writes_db():
    """revoke 内存 + DB 双写。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    db = MagicMock()
    db.execute = AsyncMock()
    svc = AgentPermissionService(db=db)
    svc._cache[1] = {"map_agent", "project", "knowledge_ydt"}
    await svc.revoke(1, {"map_agent", "project"}, operator_id=99)
    # 内存
    assert svc._cache[1] == {"knowledge_ydt"}
    # DB
    assert db.execute.await_count == 1
    args = db.execute.await_args_list[0].args
    assert "DELETE FROM user_agent_acl" in args[0]
    assert args[1] == 1
    assert sorted(args[2]) == ["map_agent", "project"]


@pytest.mark.asyncio
async def test_revoke_no_match_skips_db():
    """revoke 没有匹配项时跳过 DB 写入。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    db = MagicMock()
    db.execute = AsyncMock()
    svc = AgentPermissionService(db=db)
    svc._cache[1] = {"map_agent"}
    await svc.revoke(1, {"project"}, operator_id=99)
    assert db.execute.await_count == 0


@pytest.mark.asyncio
async def test_replace_writes_db():
    """replace 内存 + DB 双写（先删后插）。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    db = MagicMock()
    db.execute = AsyncMock()
    svc = AgentPermissionService(db=db)
    svc._cache[1] = {"old_agent"}
    await svc.replace(1, {"map_agent", "project"}, operator_id=99)
    # 内存
    assert svc._cache[1] == {"map_agent", "project"}
    # DB：1 次 DELETE + 2 次 INSERT = 3 次
    assert db.execute.await_count == 3
    # 第一条应该是 DELETE
    first_call_args = db.execute.await_args_list[0].args
    assert "DELETE FROM user_agent_acl" in first_call_args[0]


@pytest.mark.asyncio
async def test_replace_empty_writes_db():
    """replace 空列表仅 DELETE 不 INSERT。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    db = MagicMock()
    db.execute = AsyncMock()
    svc = AgentPermissionService(db=db)
    svc._cache[1] = {"map_agent"}
    await svc.replace(1, set(), operator_id=99)
    assert svc._cache[1] == set()
    # 仅 1 次 DELETE
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_grant_empty_skips_db():
    """grant 空集合不写 DB。"""
    from app.shared.utils.auth.agent_permission_service import AgentPermissionService

    db = MagicMock()
    db.execute = AsyncMock()
    svc = AgentPermissionService(db=db)
    await svc.grant(1, set(), operator_id=99)
    assert db.execute.await_count == 0


# =============================================================================
# P1: 迁移函数
# =============================================================================


@pytest.mark.asyncio
async def test_migrate_executes_insert_from_jsonb():
    """迁移函数调用 INSERT with jsonb_array_elements_text。"""
    from app.shared.utils.auth.agent_permission_service import migrate_from_users_allowed_agents

    db = MagicMock()
    db.execute = AsyncMock(return_value="INSERT 0 5")
    result = await migrate_from_users_allowed_agents(db)
    assert result == 5
    db.execute.assert_awaited_once()
    sql = db.execute.call_args[0][0]
    assert "INSERT INTO user_agent_acl" in sql
    assert "jsonb_array_elements_text" in sql
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql


@pytest.mark.asyncio
async def test_migrate_returns_inserted_count():
    """迁移函数正确解析返回行数。"""
    from app.shared.utils.auth.agent_permission_service import migrate_from_users_allowed_agents

    db = MagicMock()
    db.execute = AsyncMock(return_value="INSERT 0 12")
    result = await migrate_from_users_allowed_agents(db)
    assert result == 12


@pytest.mark.asyncio
async def test_migrate_returns_zero_on_unparseable_status():
    """迁移函数 status 不可解析时返 0（不抛错）。"""
    from app.shared.utils.auth.agent_permission_service import migrate_from_users_allowed_agents

    db = MagicMock()
    db.execute = AsyncMock(return_value="UNEXPECTED STATUS")
    result = await migrate_from_users_allowed_agents(db)
    assert result == 0
