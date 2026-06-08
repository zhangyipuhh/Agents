# -*- coding:utf-8 -*-
"""
AI 代码检查 Agent (AICodingCheckAgent) 冒烟测试模块

验证 AICodingCheckAgent 的核心模块可正常导入、评审提示词非空以及路由正确注册。

Date: 2026-06-08
"""


def test_agent_config_importable():
    """测试 Agent 配置模块可正常导入"""
    from app.features.AI_Coding_Check_agent.config import prompts
    assert hasattr(prompts, "REVIEW_SYSTEM_PROMPT")


def test_agent_prompts_non_empty():
    """测试 REVIEW_SYSTEM_PROMPT 非空"""
    from app.features.AI_Coding_Check_agent.config import prompts
    assert isinstance(prompts.REVIEW_SYSTEM_PROMPT, str)
    assert len(prompts.REVIEW_SYSTEM_PROMPT) > 0


def test_tools_importable():
    """测试工具模块可正常导入"""
    from app.features.AI_Coding_Check_agent import tools
    assert tools is not None


def test_router_registered(client):
    """测试路由 /api/ai-coding-check 已注册到 FastAPI 应用"""
    routes = [r.path for r in client.app.routes]
    assert any("/api/ai-coding-check" in p for p in routes if isinstance(p, str))
