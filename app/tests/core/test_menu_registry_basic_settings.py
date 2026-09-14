# -*- coding:utf-8 -*-
"""menu_registry 基本设置菜单测试"""
from app.core.menu_registry import MENU_CATALOG


def test_basic_settings_menu_registered():
    """system.basic-settings 菜单已注册"""
    menu = next((m for m in MENU_CATALOG if m.id == 'system.basic-settings'), None)
    assert menu is not None
    assert menu.label == '基本设置'
    assert menu.enabled is True
    assert menu.icon_key == 'settings'
    assert menu.required_role == 'admin'
    assert menu.level == 1


def test_basic_settings_menu_in_catalog():
    """system.basic-settings 在 MENU_CATALOG 中"""
    ids = [m.id for m in MENU_CATALOG]
    assert 'system.basic-settings' in ids
