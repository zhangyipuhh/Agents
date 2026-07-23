# -*- coding:utf-8 -*-
"""
MenuPermissionService 单元测试。

测试策略：
- 用 stub db（asyncpg.Pool 子类 mock）替代真实连接，验证 SQL 与参数
- 不依赖数据库实际 schema 与数据
"""

import asyncio

from app.core.menu_registry import MENU_CATALOG
from app.shared.utils.auth.menu_permission_service import MenuPermissionService


class StubDB:
    """最小化的 asyncpg.Pool stub，记录所有 SQL 调用。

    模拟 fetch / execute / fetchrow 接口，分别返回预置结果。
    """

    def __init__(self):
        self.executed: list = []  # (sql, params)
        self.fetch_returns: list = []  # 每次 fetch 返回一个列表

    async def fetch(self, sql, *params):
        self.executed.append((sql, list(params)))
        if self.fetch_returns:
            return self.fetch_returns.pop(0)
        return []

    async def fetchrow(self, sql, *params):
        self.executed.append((sql, list(params)))
        if self.fetch_returns:
            rows = self.fetch_returns.pop(0)
            return rows[0] if rows else None
        return None

    async def execute(self, sql, *params):
        self.executed.append((sql, list(params)))
        return "OK"


def _run(coro):
    """asyncio.run 包装。"""
    return asyncio.run(coro)


# ============ preload_all ============


def test_preload_all_loads_acl_into_cache():
    """preload_all 应执行 SELECT 并把 (user_id, menu_id) 关系写入缓存。"""
    db = StubDB()
    db.fetch_returns = [[
        {"user_id": 1, "menu_id": "profile"},
        {"user_id": 1, "menu_id": "user-management"},
        {"user_id": 2, "menu_id": "profile"},
    ]]
    svc = MenuPermissionService(db=db)
    _run(svc.preload_all())
    assert 1 in svc._cache
    assert "user-management" in svc._cache[1]
    assert svc._cache[1] == {"profile", "user-management"}
    assert svc._cache[2] == {"profile"}


def test_preload_all_no_op_when_db_is_none():
    """db=None 时 preload_all 是 no-op，不抛错。"""
    svc = MenuPermissionService(db=None)
    _run(svc.preload_all())
    assert svc._cache == {}


def test_preload_all_uses_register_schema_pattern():
    """preload_all 不应在 SQL 里执行 CREATE TABLE；建表由 @register_schema 完成。"""
    db = StubDB()
    db.fetch_returns = [[]]
    svc = MenuPermissionService(db=db)
    _run(svc.preload_all())
    for sql, _ in db.executed:
        assert "CREATE TABLE" not in sql.upper(), "preload_all 不应创建表"


# ============ get_visible_menu_ids ============


def test_get_visible_menu_ids_admin_returns_all_enabled():
    """admin 用户返所有 enabled 项的 id。"""
    svc = MenuPermissionService(db=None)
    visible = _run(svc.get_visible_menu_ids(user_id=1, is_admin=True))
    enabled_count = sum(1 for m in MENU_CATALOG if m.enabled)
    assert len(visible) == enabled_count
    assert "profile" in visible
    assert "permission-management" in visible


def test_get_visible_menu_ids_admin_ignores_cache():
    """admin 即便缓存为空也返全量。"""
    svc = MenuPermissionService(db=None)
    visible = _run(svc.get_visible_menu_ids(user_id=999, is_admin=True))
    assert len(visible) > 0


def test_get_visible_menu_ids_normal_returns_granted_intersect_enabled():
    """普通用户返 granted ∩ enabled。"""
    svc = MenuPermissionService(db=None)
    svc._cache[5] = {"profile", "user-management", "user-management.users", "agent-management"}
    visible = _run(svc.get_visible_menu_ids(user_id=5, is_admin=False))
    assert "profile" in visible
    assert "user-management" in visible
    assert "user-management.users" in visible
    assert "agent-management" in visible
    assert "task-scheduler" not in visible


def test_get_visible_menu_ids_normal_empty_cache_still_has_profile():
    """普通用户缓存为空时仅返 ['profile']。"""
    svc = MenuPermissionService(db=None)
    visible = _run(svc.get_visible_menu_ids(user_id=999, is_admin=False))
    assert visible == ["profile"]


def test_get_visible_menu_ids_db_none_admin_still_works():
    """db=None + admin 仍返全量（不依赖缓存）。"""
    svc = MenuPermissionService(db=None)
    visible = _run(svc.get_visible_menu_ids(user_id=1, is_admin=True))
    enabled_count = sum(1 for m in MENU_CATALOG if m.enabled)
    assert len(visible) == enabled_count


def test_get_visible_menu_ids_db_none_normal_fails_secure():
    """db=None + 普通用户 fail-secure：仅返 ['profile']。"""
    svc = MenuPermissionService(db=None)
    visible = _run(svc.get_visible_menu_ids(user_id=1, is_admin=False))
    assert visible == ["profile"]


def test_get_visible_menu_ids_excludes_disabled_items():
    """enabled=False 的菜单永远不返。"""
    svc = MenuPermissionService(db=None)
    svc._cache[1] = {"profile", "user-management.online-monitor"}
    original = next(m for m in MENU_CATALOG if m.id == "user-management.online-monitor")
    original.enabled = False
    try:
        visible = _run(svc.get_visible_menu_ids(user_id=1, is_admin=False))
        assert "user-management.online-monitor" not in visible
    finally:
        original.enabled = True


def test_get_visible_menu_ids_sorted_by_sort_order():
    """返回顺序按 sort_order 升序。"""
    svc = MenuPermissionService(db=None)
    visible = _run(svc.get_visible_menu_ids(user_id=1, is_admin=True))
    expected = sorted(
        [m.id for m in MENU_CATALOG if m.enabled],
        key=lambda mid: next(m.sort_order for m in MENU_CATALOG if m.id == mid)
    )
    assert visible == expected


# ============ get_user_grants ============


def test_get_user_grants_returns_cached_set():
    """get_user_grants 返缓存里的 menu_id set；缓存不存在返空 set。"""
    svc = MenuPermissionService(db=None)
    svc._cache[7] = {"profile", "user-management"}
    assert _run(svc.get_user_grants(user_id=7)) == {"profile", "user-management"}
    assert _run(svc.get_user_grants(user_id=999)) == set()


# ============ grant / revoke / replace（双写） ============


def test_grant_adds_to_cache_and_persists():
    """grant 应同时写 DB 与更新缓存。"""
    db = StubDB()
    svc = MenuPermissionService(db=db)
    _run(svc.grant(user_id=5, menu_ids={"profile", "user-management"}, operator_id=1))
    assert svc._cache[5] == {"profile", "user-management"}
    # 应执行 INSERT（含 ON CONFLICT）
    inserts = [s for s, _ in db.executed if "INSERT" in s.upper()]
    assert len(inserts) >= 1


def test_grant_no_op_when_db_is_none():
    """db=None 时 grant 仅更新缓存（不抛错；admin 用此路径内存生效，重启失效）。"""
    svc = MenuPermissionService(db=None)
    _run(svc.grant(user_id=5, menu_ids={"profile"}))
    assert svc._cache[5] == {"profile"}


def test_revoke_removes_from_cache_and_persists():
    """revoke 应同时删除 DB 行与更新缓存。"""
    db = StubDB()
    svc = MenuPermissionService(db=db)
    svc._cache[5] = {"profile", "user-management"}
    _run(svc.revoke(user_id=5, menu_ids={"user-management"}, operator_id=1))
    assert svc._cache[5] == {"profile"}
    deletes = [s for s, _ in db.executed if "DELETE" in s.upper()]
    assert len(deletes) >= 1


def test_revoke_no_op_when_menu_not_in_cache():
    """revoke 不存在的菜单：不报错，不写 DB。"""
    db = StubDB()
    svc = MenuPermissionService(db=db)
    _run(svc.revoke(user_id=5, menu_ids={"not-existing"}))
    assert db.executed == []


def test_replace_overwrites_user_grants():
    """replace 应先清空该用户的旧授权，再批量写新授权。"""
    db = StubDB()
    svc = MenuPermissionService(db=db)
    svc._cache[5] = {"profile", "user-management", "task-scheduler"}
    _run(svc.replace(user_id=5, menu_ids={"profile", "agent-management"}, operator_id=1))
    assert svc._cache[5] == {"profile", "agent-management"}
    # 应有 DELETE (user_id=...) 与至少一次 INSERT
    sql_types = [s.strip().split()[0].upper() for s, _ in db.executed]
    assert "DELETE" in sql_types
    assert "INSERT" in sql_types


def test_replace_with_empty_set_clears_all():
    """replace 传空 set：应清空该用户的所有授权。"""
    db = StubDB()
    svc = MenuPermissionService(db=db)
    svc._cache[5] = {"profile", "user-management"}
    _run(svc.replace(user_id=5, menu_ids=set(), operator_id=1))
    assert svc._cache[5] == set()


def test_replace_no_op_when_db_is_none():
    """db=None 时 replace 仅更新缓存。"""
    svc = MenuPermissionService(db=None)
    _run(svc.replace(user_id=5, menu_ids={"profile"}))
    assert svc._cache[5] == {"profile"}


# ============ 健壮性 ============


def test_get_visible_menu_ids_profile_always_present():
    """普通用户已授权 'profile' 也再追加一次（无副作用），未授权则强制追加。"""
    svc = MenuPermissionService(db=None)
    # 已授权
    svc._cache[1] = {"profile"}
    v = _run(svc.get_visible_menu_ids(user_id=1, is_admin=False))
    assert v.count("profile") == 1
    # 未授权
    svc._cache[2] = {"user-management"}
    v = _run(svc.get_visible_menu_ids(user_id=2, is_admin=False))
    assert "profile" in v