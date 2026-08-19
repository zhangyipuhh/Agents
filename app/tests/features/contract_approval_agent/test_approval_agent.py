# -*- coding:utf-8 -*-
"""
合同审批 Agent (ApprovalAgent) 冒烟测试模块

验证 ApprovalAgent 的核心模块可正常导入、提示词非空以及路由正确注册。

Date: 2026-06-08
"""

import asyncio


def test_agent_config_importable():
    """测试 Agent 配置模块可正常导入"""
    from app.features.contract_approval_agent.config import prompts
    assert hasattr(prompts, "DEFAULT_SYSTEM_PROMPT")


def test_agent_prompts_non_empty():
    """测试 DEFAULT_SYSTEM_PROMPT 非空"""
    from app.features.contract_approval_agent.config import prompts
    assert isinstance(prompts.DEFAULT_SYSTEM_PROMPT, str)
    assert len(prompts.DEFAULT_SYSTEM_PROMPT) > 0


def test_tools_importable():
    """测试工具模块可正常导入"""
    from app.features.contract_approval_agent import tools
    assert tools is not None


def test_router_registered(client):
    """测试路由 /api/contract 已注册到 FastAPI 应用"""
    routes = [r.path for r in client.app.routes]
    assert any("/api/contract" in p for p in routes if isinstance(p, str))


def test_approval_agent_constructor_accepts_base_system_prompt():
    """
    测试 ApprovalAgent 构造时透传 base_system_prompt 到 ApprovalAgentConfig（2026-08-19 透传回归）。

    验证三件事：
    1) 构造时不抛错（新参数默认 None，向后兼容）
    2) 实例字段 self.base_system_prompt 原样保存
    3) _ensure_agent 构造 ApprovalAgentConfig 时把该值传给 config.base_system_prompt

    monkeypatch ApprovalAgent 模块顶部的 get_agent 引用（包装类通过
    ``from app.core.agent.agent import get_agent`` 绑定到模块局部）。
    """
    from unittest.mock import patch
    from langgraph.store.memory import InMemoryStore

    # 包装类通过 ``from app.core.agent.agent import get_agent`` 把名字绑定到
    # 自身模块的全局命名空间；必须 patch 模块文件本身（不是包 __init__），
    # 才能换掉模块顶部那个引用。
    #
    # 注意：直接 ``import ...ApprovalAgent as appr_module`` 在某些环境下会被 Python 解析为
    # 包属性（__init__.py 重导出了同名 ApprovalAgent 类），导致拿到的是类而不是模块。
    # 改用 importlib.import_module 显式拿模块。
    import importlib
    appr_module = importlib.import_module('app.features.contract_approval_agent.ApprovalAgent')
    from app.features.contract_approval_agent.ApprovalAgent import ApprovalAgent

    store = InMemoryStore()
    captured: dict = {}

    async def _fake_get_agent(config):
        captured["config"] = config
        return None

    with patch.object(appr_module, "get_agent", _fake_get_agent):
        instance = ApprovalAgent(
            checkpointer=None,
            store=store,
            store_id="store_appr",
            system_prompt="APPR_SPECIFIC",
            base_system_prompt="",
        )

        assert instance.base_system_prompt == ""
        assert instance.system_prompt == "APPR_SPECIFIC"

        asyncio.run(instance._ensure_agent())

    assert "config" in captured, "get_agent 未被调用"
    assert captured["config"].base_system_prompt == ""
    assert captured["config"].system_prompt == "APPR_SPECIFIC"
