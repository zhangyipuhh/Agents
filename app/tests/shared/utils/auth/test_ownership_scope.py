# -*- coding:utf-8 -*-
"""
OwnershipScope 通用模块单元测试。

覆盖：
- ``from_request`` 从 request.state 构造 scope（含 admin / 普通用户 / 缺失字段）
- ``system_scope`` / ``for_user`` 工厂方法
- ``can_access`` 判定矩阵（system / admin / owner / 越权 / owner_id=None）
- ``sql_filter`` 生成 SQL 子句（含 param_index 透传、admin / user 两种）
"""
from types import SimpleNamespace

import pytest

from app.shared.utils.auth.ownership_scope import OwnershipScope


# =============================================================================
# P0: 导入与构造
# =============================================================================


def test_ownership_scope_module_importable():
    """测试 OwnershipScope 模块可导入。"""
    from app.shared.utils.auth import ownership_scope

    assert hasattr(ownership_scope, "OwnershipScope")
    assert hasattr(ownership_scope, "OwnershipScope") is True


def test_ownership_scope_is_frozen():
    """测试 OwnershipScope 为 frozen dataclass，字段不可变。"""
    scope = OwnershipScope(user_id=1, is_admin=False)
    with pytest.raises(Exception):
        scope.user_id = 2  # type: ignore[misc]


# =============================================================================
# P1: 工厂方法
# =============================================================================


def test_from_request_admin_returns_admin_scope():
    """``from_request`` 在 request.state.role='admin' 时返回 is_admin=True scope。"""
    request = SimpleNamespace(state=SimpleNamespace(user_id=1, role="admin"))
    scope = OwnershipScope.from_request(request)
    assert scope.user_id == 1
    assert scope.is_admin is True
    assert scope.system is False


def test_from_request_normal_user_returns_user_scope():
    """``from_request`` 在 request.state.role='user' 时返回 is_admin=False scope。"""
    request = SimpleNamespace(state=SimpleNamespace(user_id=42, role="user"))
    scope = OwnershipScope.from_request(request)
    assert scope.user_id == 42
    assert scope.is_admin is False
    assert scope.system is False


def test_from_request_missing_state_defaults_to_user_and_no_id():
    """``request.state`` 缺失 user_id / role 时降级为 user + user_id=None。"""
    request = SimpleNamespace(state=SimpleNamespace())  # 无字段
    scope = OwnershipScope.from_request(request)
    assert scope.user_id is None
    assert scope.is_admin is False
    assert scope.system is False


def test_from_request_none_user_id_treated_as_no_id():
    """user_id 为 None / 0 时 user_id 归一为 None（避免 0 与数据库自增 ID 混淆）。"""
    request = SimpleNamespace(state=SimpleNamespace(user_id=0, role="user"))
    scope = OwnershipScope.from_request(request)
    assert scope.user_id is None


def test_system_scope_is_system_and_no_user():
    """``system_scope()`` 返回 system=True、user_id=None 的内部 scope。"""
    scope = OwnershipScope.system_scope()
    assert scope.system is True
    assert scope.is_admin is False
    assert scope.user_id is None


def test_for_user_constructs_user_scope():
    """``for_user(user_id, is_admin)`` 构造普通用户 scope。"""
    scope = OwnershipScope.for_user(user_id=7, is_admin=False)
    assert scope.user_id == 7
    assert scope.is_admin is False
    assert scope.system is False


# =============================================================================
# P1: can_access 判定矩阵
# =============================================================================


@pytest.mark.parametrize(
    "scope,owner_id,expected",
    [
        # 系统内部：永真
        (OwnershipScope.system_scope(), 99, True),
        # admin：永真
        (OwnershipScope(user_id=1, is_admin=True), 99, True),
        (OwnershipScope(user_id=1, is_admin=True), 1, True),
        # 普通用户自己创建：通过
        (OwnershipScope(user_id=5, is_admin=False), 5, True),
        # 普通用户他人创建：拒绝
        (OwnershipScope(user_id=5, is_admin=False), 6, False),
        # 普通用户 owner_id=None：拒绝（兜底）
        (OwnershipScope(user_id=5, is_admin=False), None, False),
        # 普通用户自身 user_id=None：拒绝（兜底）
        (OwnershipScope(user_id=None, is_admin=False), 5, False),
    ],
)
def test_can_access_returns_correct_value(scope, owner_id, expected):
    """can_access 覆盖 system / admin / owner / 越权 / 缺失字段 5 类判定。"""
    assert scope.can_access(owner_id) is expected


def test_can_access_with_non_int_owner_raises():
    """``owner_id`` 为非数字类型（无 ``__int__``）时，``int(...)`` 强转抛
    ``TypeError``，``can_access`` 不应静默吞掉。

    使用一个不含 ``__int__`` 的自定义类作为 owner_id。``MagicMock`` 不
    适用：它会自动生成 ``__int__`` 并返回整数（mock 默认行为），无法触
    发 TypeError。
    """
    class _NoInt:
        """不实现 ``__int__`` 的简单类 — 用于锁定 ``can_access`` 强转行为。"""

        pass

    scope = OwnershipScope(user_id=5, is_admin=False)
    with pytest.raises(TypeError):
        scope.can_access(_NoInt())


# =============================================================================
# P1: sql_filter 辅助
# =============================================================================


def test_sql_filter_admin_returns_true_no_params():
    """admin scope 返回 ``("TRUE", [])``，调用方拼到 WHERE 后无影响。"""
    scope = OwnershipScope(user_id=1, is_admin=True)
    sql, params = scope.sql_filter("created_by_user_id", param_index=2)
    assert sql == "TRUE"
    assert params == []


def test_sql_filter_system_returns_true_no_params():
    """system scope 返回 ``("TRUE", [])``。"""
    scope = OwnershipScope.system_scope()
    sql, params = scope.sql_filter("created_by_user_id", param_index=3)
    assert sql == "TRUE"
    assert params == []


def test_sql_filter_user_returns_column_equals_placeholder_with_user_id():
    """普通用户 scope 返回 ``("created_by_user_id = $N", [user_id])``。"""
    scope = OwnershipScope(user_id=42, is_admin=False)
    sql, params = scope.sql_filter("created_by_user_id", param_index=5)
    assert sql == "created_by_user_id = $5"
    assert params == [42]


def test_sql_filter_user_default_placeholder_uses_n_marker():
    """``param_index=None`` 时生成 ``$N`` 占位符标记，便于调用方手工替换。"""
    scope = OwnershipScope(user_id=42, is_admin=False)
    sql, params = scope.sql_filter("created_by_user_id")
    assert sql == "created_by_user_id = $N"
    assert params == [42]


def test_sql_filter_user_with_missing_user_id_returns_false():
    """普通用户但 user_id 缺失（理论兜底）返回 ``("FALSE", [])``，拒绝任何数据。"""
    scope = OwnershipScope(user_id=None, is_admin=False)
    sql, params = scope.sql_filter("created_by_user_id", param_index=1)
    assert sql == "FALSE"
    assert params == []


def test_sql_filter_custom_column_name():
    """``column`` 参数透传自定义列名，便于未来其他业务表复用。"""
    scope = OwnershipScope(user_id=42, is_admin=False)
    sql, params = scope.sql_filter("owner_user_id", param_index=2)
    assert sql == "owner_user_id = $2"
    assert params == [42]