# -*- coding:utf-8 -*-
"""skill_admin_router 模块测试。

测试 skill_admin_router 的可导入性与 router 实例存在性。
"""


def test_skill_admin_router_importable():
    """验证 skill_admin_router 模块可导入且包含 router 实例。"""
    from app.routers import skill_admin_router
    assert hasattr(skill_admin_router, "router")
