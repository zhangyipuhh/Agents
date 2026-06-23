# -*- coding:utf-8 -*-
"""
map_agent 工具注册测试模块

验证迁移后的 MapTools 已用 @register_tool 装饰并注册到 ToolRegistry。
"""
import pytest


def test_map_tools_importable():
    """测试迁移后的 MapTools 模块可导入。"""
    from app.shared.tools.skills.map_agent import MapTools
    assert MapTools is not None


def test_set_map_center_registered():
    """测试 set_map_center 已注册到 ToolRegistry。"""
    # 先 import 触发 @register_tool 装饰器执行
    from app.shared.tools.skills.map_agent import MapTools  # noqa: F401
    from app.shared.tools.registry import ToolRegistry

    info = ToolRegistry._tools.get("set_map_center")
    assert info is not None
    assert info["agent"] == "map_agent"


def test_all_map_tools_registered():
    """测试 8 个地图工具全部注册。"""
    from app.shared.tools.skills.map_agent import MapTools  # noqa: F401
    from app.shared.tools.registry import ToolRegistry

    expected = [
        "set_map_center", "set_map_zoom", "add_map_marker",
        "remove_map_marker", "clear_map_markers", "get_map_state",
        "draw_map_polygon", "set_map_layer",
    ]
    for name in expected:
        assert name in ToolRegistry._tools, f"工具 {name} 未注册"
        assert ToolRegistry._tools[name]["agent"] == "map_agent"
