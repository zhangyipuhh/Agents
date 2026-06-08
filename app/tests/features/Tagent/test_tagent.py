# -*- coding:utf-8 -*-
"""
T Agent (Tagent) 冒烟测试模块

验证 Tagent 的核心模块可正常导入以及工具模块可正常导入。

Date: 2026-06-08
"""


def test_agent_config_importable():
    """测试 Agent 配置模块可正常导入"""
    from app.features.Tagent.config import TagentConfig
    assert TagentConfig is not None


def test_tools_importable():
    """测试工具模块可正常导入"""
    from app.features.Tagent import tools
    assert tools is not None
