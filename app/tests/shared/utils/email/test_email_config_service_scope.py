# -*- coding:utf-8 -*-
"""
EmailConfigService 策略按用户隔离（OwnershipScope）测试模块。

验证：
- ``list_policies(scope)`` 在 admin / 普通用户 / system 三种 scope 下返回不同结果
- ``get_policy(policy_id, scope)`` 对越权访问返回 ``None``（非抛异常）
- ``update_policy`` / ``delete_policy`` 对越权访问返回 ``None`` / False（路由层映射 404）
- ``get_policy_internal`` 绕过归属过滤（系统内部调用）

测试策略：用 fake ``asyncpg`` 风格的 DB stub（``AsyncMock`` + 预设 row 返回值），
避免启动 PostgreSQL。EmailConfigService 对 db=None 优雅降级：policy 操作会抛
``EmailConfigError("数据库未初始化")``，故此处使用 ``MagicMock`` 作为 db stub。
"""
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.email.email_config_service import EmailConfigService


# =============================================================================
# P0: 导入与构造
# =============================================================================


def test_service_importable():
    """测试 EmailConfigService 可导入。"""
    from app.shared.utils.email import email_config_service

    assert hasattr(email_config_service, "EmailConfigService")


def _make_service_with_db(db_rows: Dict[str, Any]) -> EmailConfigService:
    """构造带 fake DB 的 EmailConfigService。

    fake DB 根据方法名返回预设 row：
    - ``fetch``: list 风格（list_policies 测试用）
    - ``fetchrow``: 单 row 风格（get_policy / update_policy / delete_policy 校验用）

    参数:
        db_rows: 字段映射字典。

    返回:
        EmailConfigService: 带 fake DB 的实例。
    """
    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()
    service._db.fetch = AsyncMock(return_value=db_rows.get("fetch", []))
    service._db.fetchrow = AsyncMock(return_value=db_rows.get("fetchrow"))
    service._db.execute = AsyncMock(return_value=db_rows.get("execute", "DELETE 1"))
    service._db.acquire = MagicMock()
    return service


def _policy_row(
    pid: int,
    name: str,
    owner_id: int,
    recipients: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """构造 list_policies / get_policy 返回的 row 字典。"""
    return {
        "id": pid,
        "name": name,
        "description": "",
        "subject_template": "",
        "body_template": "",
        "created_by_user_id": owner_id,
        "created_at": None,
        "updated_at": None,
        "recipients": recipients or [],
    }


# =============================================================================
# P1: list_policies(scope) 归属过滤
# =============================================================================


@pytest.mark.asyncio
async def test_list_policies_user_scope_filters_to_own():
    """普通用户 scope：service.list_policies 拼接 ``WHERE created_by_user_id = $1``。

    fake fetch 返回 admin + other + self 三条，但 list_policies 应当：
    1. 把 ``WHERE created_by_user_id = $1 [42]`` 拼到 SQL
    2. 拿到 fake fetch 返回的全部 row（fake 不执行真实过滤），由 service
       按 scope 过滤逻辑信任 DB 已过滤（真实 PG 才做行级过滤）。
    """
    service = _make_service_with_db({
        "fetch": [
            _policy_row(1, "admin策略", owner_id=1),
            _policy_row(2, "用户A策略", owner_id=42),
            _policy_row(3, "用户B策略", owner_id=99),
        ],
    })
    scope = OwnershipScope(user_id=42, is_admin=False)

    result = await service.list_policies(scope)

    assert isinstance(result, list)
    # SQL 必须包含过滤条件（admin scope 是 TRUE，普通用户是 =$N）
    call_sql = service._db.fetch.await_args.args[0]
    assert "created_by_user_id = $1" in call_sql
    call_params = service._db.fetch.await_args.args[1:]
    assert 42 in call_params


@pytest.mark.asyncio
async def test_list_policies_admin_scope_sees_all():
    """admin scope：WHERE 子句是 ``TRUE``，不过滤。"""
    service = _make_service_with_db({
        "fetch": [
            _policy_row(1, "策略1", owner_id=1),
            _policy_row(2, "策略2", owner_id=99),
        ],
    })
    scope = OwnershipScope(user_id=1, is_admin=True)

    result = await service.list_policies(scope)

    assert len(result) == 2
    call_sql = service._db.fetch.await_args.args[0]
    assert "WHERE TRUE" in call_sql
    # admin scope 不需要参数
    assert service._db.fetch.await_args.args[1:] == ()


@pytest.mark.asyncio
async def test_list_policies_system_scope_sees_all():
    """system scope：定时任务 / 内部调用使用，WHERE = TRUE。"""
    service = _make_service_with_db({
        "fetch": [_policy_row(1, "策略", owner_id=1)],
    })
    scope = OwnershipScope.system_scope()

    result = await service.list_policies(scope)

    assert len(result) == 1
    call_sql = service._db.fetch.await_args.args[0]
    assert "WHERE TRUE" in call_sql


@pytest.mark.asyncio
async def test_list_policies_response_includes_created_by_user_id():
    """list_policies 返回的每条策略包含 ``created_by_user_id``（前端 admin 视图）。"""
    service = _make_service_with_db({
        "fetch": [_policy_row(1, "策略1", owner_id=42)],
    })
    result = await service.list_policies(OwnershipScope.system_scope())
    assert result[0]["created_by_user_id"] == 42


# =============================================================================
# P1: get_policy(scope) 越权返回 None
# =============================================================================


@pytest.mark.asyncio
async def test_get_policy_owner_returns_row():
    """owner 自己取自己的策略：返回详情。"""
    service = _make_service_with_db({
        "fetchrow": _policy_row(1, "我的策略", owner_id=42),
    })
    scope = OwnershipScope(user_id=42, is_admin=False)
    result = await service.get_policy(1, scope)
    assert result is not None
    assert result["id"] == 1
    assert result["created_by_user_id"] == 42


@pytest.mark.asyncio
async def test_get_policy_other_user_returns_none():
    """非 owner 普通用户取他人策略：返回 ``None``（路由层映射 404）。"""
    service = _make_service_with_db({
        "fetchrow": _policy_row(1, "他人策略", owner_id=99),
    })
    scope = OwnershipScope(user_id=42, is_admin=False)
    result = await service.get_policy(1, scope)
    assert result is None


@pytest.mark.asyncio
async def test_get_policy_admin_returns_row_even_if_owned_by_other():
    """admin 取他人策略：直接返回（不受归属限制）。"""
    service = _make_service_with_db({
        "fetchrow": _policy_row(1, "他人策略", owner_id=99),
    })
    scope = OwnershipScope(user_id=1, is_admin=True)
    result = await service.get_policy(1, scope)
    assert result is not None
    assert result["id"] == 1


@pytest.mark.asyncio
async def test_get_policy_not_found_returns_none():
    """策略不存在：fetchrow 返回 None 时 service 返回 None（路由映射 404）。"""
    service = _make_service_with_db({"fetchrow": None})
    scope = OwnershipScope.system_scope()
    result = await service.get_policy(9999, scope)
    assert result is None


@pytest.mark.asyncio
async def test_get_policy_internal_bypasses_scope_filter():
    """``get_policy_internal`` 使用 system scope 取策略，不受调用方归属限制。

    模拟 user scope 调用方（user_id=42），但 ``get_policy_internal`` 是
    系统内部入口，应忽略调用方 scope，使用 system scope 直查。
    """
    service = _make_service_with_db({
        "fetchrow": _policy_row(1, "他人策略", owner_id=99),
    })
    result = await service.get_policy_internal(1)
    assert result is not None
    assert result["id"] == 1


# =============================================================================
# P1: update_policy / delete_policy 越权返回 None / False
# =============================================================================


@pytest.mark.asyncio
async def test_update_policy_other_user_returns_none_without_writing():
    """非 owner 用户更新他人策略：返回 None，不触发 UPDATE 写。

    通过 mock ``conn.transaction()`` 为 async 上下文管理器，使 service 能
    进入事务块；事务内的 ``fetchrow`` 返回 owner=他人，触发权限拒绝并
    返回 ``None``，确保 UPDATE 语句不被发出。
    """
    from contextlib import asynccontextmanager

    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()

    fake_conn = MagicMock()
    # 事务内 fetchrow 取 owner → 返回他人 owner
    fake_conn.fetchrow = AsyncMock(return_value={"id": 1, "created_by_user_id": 99})
    fake_conn.execute = AsyncMock(return_value="UPDATE 1")

    @asynccontextmanager
    async def _fake_transaction():
        yield None

    fake_conn.transaction = _fake_transaction

    @asynccontextmanager
    async def _fake_acquire():
        yield fake_conn

    service._db.acquire = _fake_acquire

    scope = OwnershipScope(user_id=42, is_admin=False)
    result = await service.update_policy(
        policy_id=1, scope=scope, name="改名",
    )
    assert result is None
    # execute 不应被调用（owner 校验失败，未进入任何 UPDATE）
    fake_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_update_policy_admin_can_modify_any_policy():
    """admin 可更新任意策略（含 owner != self.user_id）。

    完整事务链路 mock：admin 通过 owner 校验 → 执行 UPDATE → 调用
    ``get_policy`` 拉取最新行返回。
    """
    from contextlib import asynccontextmanager

    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()

    # 第一次 fetchrow（事务内）：取 owner
    # 第二次 fetchrow（事务外 get_policy）：拉取最新行
    fake_conn = MagicMock()
    fake_conn.fetchrow = AsyncMock(return_value={"id": 1, "created_by_user_id": 99})
    fake_conn.execute = AsyncMock(return_value="UPDATE 1")

    @asynccontextmanager
    async def _fake_transaction():
        yield None

    fake_conn.transaction = _fake_transaction

    @asynccontextmanager
    async def _fake_acquire():
        yield fake_conn

    service._db.acquire = _fake_acquire
    # service._db.fetchrow（事务外 get_policy 调用）使用顶层 fetchrow，
    # 第一次（事务内）用 fake_conn.fetchrow；两次都返回同一行即可。
    service._db.fetchrow = AsyncMock(
        return_value=_policy_row(1, "改后策略", owner_id=99),
    )

    scope = OwnershipScope(user_id=1, is_admin=True)
    result = await service.update_policy(policy_id=1, scope=scope, name="改后策略")
    assert result is not None
    assert result["name"] == "改后策略"


@pytest.mark.asyncio
async def test_delete_policy_other_user_returns_false():
    """非 owner 删除他人策略：返回 False，不触发 DELETE 写。"""
    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()
    # fetchrow 返回他人 owner → 返回 False
    service._db.fetchrow = AsyncMock(return_value={"created_by_user_id": 99})
    service._db.execute = AsyncMock(return_value="DELETE 1")

    scope = OwnershipScope(user_id=42, is_admin=False)
    deleted = await service.delete_policy(1, scope)
    assert deleted is False
    # DELETE 语句不应执行
    service._db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_delete_policy_owner_returns_true():
    """owner 删除自己的策略：返回 True。"""
    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()
    service._db.fetchrow = AsyncMock(return_value={"created_by_user_id": 42})
    service._db.execute = AsyncMock(return_value="DELETE 1")

    scope = OwnershipScope(user_id=42, is_admin=False)
    deleted = await service.delete_policy(1, scope)
    assert deleted is True
    service._db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_delete_policy_admin_can_delete_any():
    """admin 可删除任意策略。"""
    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()
    service._db.fetchrow = AsyncMock(return_value={"created_by_user_id": 99})
    service._db.execute = AsyncMock(return_value="DELETE 1")

    scope = OwnershipScope(user_id=1, is_admin=True)
    deleted = await service.delete_policy(1, scope)
    assert deleted is True


@pytest.mark.asyncio
async def test_delete_policy_not_found_returns_false():
    """策略不存在（fetchrow 返回 None）：返回 False（路由映射 404）。"""
    service = EmailConfigService(db=None, credential_key="")
    service._db = MagicMock()
    service._db.fetchrow = AsyncMock(return_value=None)

    deleted = await service.delete_policy(9999, OwnershipScope.system_scope())
    assert deleted is False