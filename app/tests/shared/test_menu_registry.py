# -*- coding:utf-8 -*-
"""
menu_registry 单元测试。

覆盖点：
- MENU_CATALOG id 唯一性
- 二级菜单的 parent_id 必须指向已存在的一级菜单
- get_enabled_items 仅返回 enabled=True
- get_visible_for_user：admin 返全量；普通用户按 granted 过滤；空 granted 强制包含 profile
"""

import pytest

from app.core.menu_registry import (
    MENU_CATALOG,
    MenuItem,
    get_enabled_items,
    get_full_catalog,
    get_visible_for_user,
)


def test_catalog_has_no_duplicate_ids():
    """MENU_CATALOG 所有条目的 id 必须唯一。"""
    ids = [m.id for m in MENU_CATALOG]
    duplicates = {x for x in ids if ids.count(x) > 1}
    assert not duplicates, f"duplicate menu ids: {duplicates}"


def test_level_1_menus_have_no_parent():
    """一级菜单（level=1）的 parent_id 必须为 None。"""
    for m in MENU_CATALOG:
        if m.level == 1:
            assert m.parent_id is None, f"{m.id} is level 1 but parent_id={m.parent_id}"


def test_level_2_menus_parent_id_must_exist():
    """二级菜单的 parent_id 必须指向 MENU_CATALOG 中已存在的 level=1 条目。"""
    level1_ids = {m.id for m in MENU_CATALOG if m.level == 1}
    for m in MENU_CATALOG:
        if m.level == 2:
            assert m.parent_id is not None, f"{m.id} is level 2 but parent_id is None"
            assert m.parent_id in level1_ids, (
                f"{m.id} parent_id={m.parent_id} not in level1_ids={level1_ids}"
            )


def test_get_full_catalog_returns_all_items():
    """get_full_catalog 返回所有条目（含 enabled=False）。"""
    items = get_full_catalog()
    assert len(items) == len(MENU_CATALOG)
    assert {m.id for m in items} == {m.id for m in MENU_CATALOG}


def test_get_enabled_items_excludes_disabled():
    """get_enabled_items 不返回 enabled=False 的条目。"""
    enabled = get_enabled_items()
    for m in enabled:
        assert m.enabled is True
    assert len(enabled) <= len(MENU_CATALOG)


def test_get_visible_for_user_admin_returns_all_enabled():
    """admin 用户看到所有 enabled=True 项。"""
    visible = get_visible_for_user(user_id=1, is_admin=True, granted_menu_ids=set())
    expected = {m.id for m in get_enabled_items()}
    actual = {m.id for m in visible}
    assert actual == expected
    # admin 忽略 granted_menu_ids（即便传空 set 也不影响）
    assert len(visible) == len(get_enabled_items())


def test_get_visible_for_user_admin_with_granted_still_returns_all():
    """admin 即便 granted 传空也不影响全量。"""
    visible_empty = get_visible_for_user(1, is_admin=True, granted_menu_ids=set())
    visible_full = get_visible_for_user(1, is_admin=True, granted_menu_ids={"profile", "user-management"})
    assert {m.id for m in visible_empty} == {m.id for m in visible_full}


def test_get_visible_for_user_normal_filters_by_granted():
    """普通用户按 granted 过滤；只看到 granted ∩ enabled。"""
    granted = {"profile", "user-management", "user-management.users"}
    visible = get_visible_for_user(user_id=2, is_admin=False, granted_menu_ids=granted)
    actual_ids = {m.id for m in visible}
    # profile 必含；user-management 与 user-management.users 都在 granted 且 enabled
    assert "profile" in actual_ids
    assert "user-management" in actual_ids
    assert "user-management.users" in actual_ids
    # 未授权的菜单不会出现
    assert "agent-management" not in actual_ids
    assert "task-scheduler" not in actual_ids


def test_get_visible_for_user_normal_empty_granted_still_has_profile():
    """普通用户即便 granted 为空，也保证能看到 profile。"""
    visible = get_visible_for_user(user_id=3, is_admin=False, granted_menu_ids=set())
    assert len(visible) == 1
    assert visible[0].id == "profile"


def test_get_visible_for_user_normal_none_granted_same_as_empty():
    """granted=None 与 granted=set() 行为一致。"""
    v_none = get_visible_for_user(4, is_admin=False, granted_menu_ids=None)
    v_empty = get_visible_for_user(4, is_admin=False, granted_menu_ids=set())
    assert {m.id for m in v_none} == {m.id for m in v_empty}


def test_get_visible_for_user_excludes_disabled_even_if_granted():
    """enabled=False 的菜单即便在 granted 里也不返回（admin 配权限时手动启用才可见）。"""
    # 临时改一个 menu 为 enabled=False
    original = next(m for m in MENU_CATALOG if m.id == "user-management.online-monitor")
    original.enabled = False
    try:
        granted = {"profile", "user-management.online-monitor"}
        visible = get_visible_for_user(5, is_admin=False, granted_menu_ids=granted)
        actual_ids = {m.id for m in visible}
        assert "user-management.online-monitor" not in actual_ids
        assert "profile" in actual_ids
    finally:
        original.enabled = True  # 还原


def test_get_visible_for_user_sorted_by_sort_order():
    """get_visible_for_user 返回结果按 sort_order 升序。"""
    granted = {"profile", "task-scheduler", "user-management", "agent-management"}
    visible = get_visible_for_user(6, is_admin=False, granted_menu_ids=granted)
    sort_orders = [m.sort_order for m in visible]
    assert sort_orders == sorted(sort_orders)


def test_menu_item_required_role_validation():
    """MenuItem 的 required_role 字段允许 None 或 'admin'（其他值类型上是 str 即可，不强校验枚举）。"""
    # 验证 None 和 'admin' 都能构造
    m_none = MenuItem(id="x", level=1, label="X", icon_key="x", sort_order=1)
    m_admin = MenuItem(id="y", level=1, label="Y", icon_key="y", sort_order=2, required_role="admin")
    assert m_none.required_role is None
    assert m_admin.required_role == "admin"


def test_menu_item_default_enabled_true():
    """MenuItem.enabled 默认 True。"""
    m = MenuItem(id="z", level=1, label="Z", icon_key="z", sort_order=1)
    assert m.enabled is True