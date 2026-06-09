# -*- coding:utf-8 -*-
"""
地图 Agent (MapAgent) 冒烟测试模块

验证 MapAgent 的核心模块可正常导入、提示词非空以及路由正确注册。

Date: 2026-06-08
"""


def test_agent_config_importable():
    """测试 Agent 配置模块可正常导入"""
    from app.features.map_agent.config import prompts
    assert hasattr(prompts, "DEFAULT_SYSTEM_PROMPT")


def test_agent_prompts_non_empty():
    """测试 DEFAULT_SYSTEM_PROMPT 非空"""
    from app.features.map_agent.config import prompts
    assert isinstance(prompts.DEFAULT_SYSTEM_PROMPT, str)
    assert len(prompts.DEFAULT_SYSTEM_PROMPT) > 0


def test_tools_importable():
    """测试工具模块可正常导入"""
    from app.features.map_agent import tools
    assert tools is not None


def test_router_registered(client):
    """测试路由 /api/map 已注册到 FastAPI 应用"""
    routes = [r.path for r in client.app.routes]
    assert any("/api/map" in p for p in routes if isinstance(p, str))
