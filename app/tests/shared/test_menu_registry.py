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


# 2026-07-23 回归保护：「邮件设置」升级为一级菜单
# 2026-07-31 调整：再降级为「消息设置」(messaging) 下的二级菜单
def test_email_settings_promoted_to_level1():
    """task-scheduler.email-settings 当前是 messaging 下的二级菜单（level=2, parent_id='messaging'）。

    历史说明：
    - 2026-07-23 曾升级为一级菜单（level=1, sort_order=9）
    - 2026-07-31 起降级为 messaging 下的二级菜单（level=2, sort_order=1, parent_id='messaging'）
    - id 永不改（硬规则），老 ACL 自动保留
    """
    item = next(m for m in MENU_CATALOG if m.id == "task-scheduler.email-settings")
    assert item.level == 2
    assert item.parent_id == "messaging"
    assert item.sort_order == 1
    assert item.required_role == "admin"


def test_task_scheduler_children_no_longer_include_email_settings():
    """task-scheduler 的二级子菜单集合不应再包含 email-settings。

    2026-07-31 调整：email-settings 当前是 messaging 的子菜单，不是 task-scheduler 的子菜单。
    """
    children = [m for m in MENU_CATALOG if m.level == 2 and m.parent_id == "task-scheduler"]
    child_ids = {m.id for m in children}
    assert "task-scheduler.email-settings" not in child_ids
    # task-scheduler 仍应有 5 个二级菜单（定时任务/脚本扫描/脚本扫描入库/API接口配置/服务器管理）
    assert len(children) == 5


# 2026-07-31 新增：「消息设置」一级菜单注册回归保护
def test_messaging_is_new_level1_parent():
    """messaging 是新增的一级菜单（level=1, parent_id=None, sort_order=10）。"""
    item = next(m for m in MENU_CATALOG if m.id == "messaging")
    assert item.level == 1
    assert item.parent_id is None
    assert item.label == "消息设置"
    assert item.icon_key == "message"
    assert item.sort_order == 10
    assert item.required_role == "admin"
    assert item.enabled is True


def test_email_settings_now_under_messaging_not_task_scheduler():
    """task-scheduler.email-settings 是 messaging 的子菜单，不是 task-scheduler 的子菜单。"""
    # 验证 email-settings 在 messaging 下
    children = [m for m in MENU_CATALOG if m.level == 2 and m.parent_id == "messaging"]
    child_ids = {m.id for m in children}
    assert "task-scheduler.email-settings" in child_ids
    # 验证 email-settings 不在 task-scheduler 下
    ts_children = [m for m in MENU_CATALOG if m.level == 2 and m.parent_id == "task-scheduler"]
    ts_child_ids = {m.id for m in ts_children}
    assert "task-scheduler.email-settings" not in ts_child_ids


def test_get_visible_for_user_admin_includes_messaging():
    """admin 可见 messaging 一级菜单（按 sort_order 排在末尾）。"""
    visible = get_visible_for_user(user_id=1, is_admin=True, granted_menu_ids=None)
    visible_ids = {m.id for m in visible}
    assert "messaging" in visible_ids
    assert "task-scheduler.email-settings" in visible_ids


def test_get_visible_for_user_normal_grant_email_settings_subtab_does_not_auto_show_messaging():
    """普通用户授权子菜单 `task-scheduler.email-settings` 后,父级 `messaging` 不会自动出现在 visible_menus。

    后端 get_visible_for_user 严格按 ACL 交集；父级 `messaging` 的可见性由前端
    isMenuVisible 的 PARENT_TO_CHILDREN_ALIAS 派生（不依赖后端推导）。
    """
    # 普通用户被授予 task-scheduler.email-settings 自身（不是子 tab）
    visible = get_visible_for_user(
        user_id=2, is_admin=False,
        granted_menu_ids={"task-scheduler.email-settings"},
    )
    visible_ids = {m.id for m in visible}
    # 后端 visible_menus 严格按 ACL 交集
    assert "task-scheduler.email-settings" in visible_ids
    # 父级 messaging 不会自动出现在 visible_menus（前端 isMenuVisible 用 alias 补齐）
    assert "messaging" not in visible_ids


def test_get_visible_for_user_normal_grant_messaging_directly_shows_both():
    """普通用户显式授权父菜单 `messaging` 时,父级和子级都在 visible_menus 里。

    这是最直接的 ACL 路径：admin 在「权限管理 → 菜单管理」勾选 messaging 父级授权给用户。
    """
    visible = get_visible_for_user(
        user_id=3, is_admin=False,
        granted_menu_ids={"messaging"},
    )
    visible_ids = {m.id for m in visible}
    assert "messaging" in visible_ids
    # task-scheduler.email-settings 不会因父级授权自动出现（子菜单独立授权粒度）
    # 这是保留「子 Tab 独立授权」契约 —— admin 仍可按 Tab 粒度细分
    assert "task-scheduler.email-settings" not in visible_ids


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


# 2026-07-23 回归保护：「邮件设置」的三个内部 Tab 注册为可独立授权的二级菜单
def test_email_settings_submenu_tabs_registered():
    """
    EmailSettingsManager.vue 内部的三个 Tab 必须注册为二级菜单，
    否则 MenuPermissionManager.vue::getChildren 返回空数组，
    权限管理 UI 看不到子 Tab，无法按 Tab 粒度授权。
    """
    ids = {m.id for m in get_full_catalog()}
    assert "task-scheduler.email-settings.server" in ids
    assert "task-scheduler.email-settings.policies" in ids
    assert "task-scheduler.email-settings.test" in ids

    # 父级必须是 messaging 下的二级菜单（level=2，parent_id='messaging'）
    parent = next(m for m in MENU_CATALOG if m.id == "task-scheduler.email-settings")
    assert parent.level == 2
    assert parent.parent_id == "messaging"

    # 子级必须 level=2 且 parent_id 指向「消息设置」一级菜单（2026-07-31 调整：父级从 email-settings 改为 messaging）
    for child_id in [
        "task-scheduler.email-settings.server",
        "task-scheduler.email-settings.policies",
        "task-scheduler.email-settings.test",
    ]:
        c = next(m for m in MENU_CATALOG if m.id == child_id)
        assert c.level == 2
        assert c.parent_id == "messaging"
        assert c.required_role == "admin"
        assert c.enabled is True


def test_email_settings_submenu_tabs_sort_order():
    """三个子 Tab 的 sort_order 升序：server(1) < policies(2) < test(3)。"""
    children = [
        next(m for m in MENU_CATALOG if m.id == "task-scheduler.email-settings.server"),
        next(m for m in MENU_CATALOG if m.id == "task-scheduler.email-settings.policies"),
        next(m for m in MENU_CATALOG if m.id == "task-scheduler.email-settings.test"),
    ]
    orders = [c.sort_order for c in children]
    assert orders == sorted(orders)
    assert len(set(orders)) == 3  # 三者各不相同