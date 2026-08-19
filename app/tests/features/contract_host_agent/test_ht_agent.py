# -*- coding:utf-8 -*-
"""
合同主办 Agent (HtAgent) 冒烟测试模块

验证 HtAgent 的核心模块可正常导入、提示词非空以及路由正确注册。

Date: 2026-06-08
"""

import asyncio


def test_agent_config_importable():
    """测试 Agent 配置模块可正常导入"""
    from app.features.contract_host_agent.config import prompts
    assert hasattr(prompts, "DEFAULT_SYSTEM_PROMPT")


def test_agent_prompts_non_empty():
    """测试 DEFAULT_SYSTEM_PROMPT 非空"""
    from app.features.contract_host_agent.config import prompts
    assert isinstance(prompts.DEFAULT_SYSTEM_PROMPT, str)
    assert len(prompts.DEFAULT_SYSTEM_PROMPT) > 0


def test_tools_importable():
    """测试工具模块可正常导入"""
    from app.features.contract_host_agent import tools
    assert tools is not None


def test_router_registered(client):
    """测试路由 /api/contract 已注册到 FastAPI 应用"""
    routes = [r.path for r in client.app.routes]
    assert any("/api/contract" in p for p in routes if isinstance(p, str))


def test_get_tools_includes_base_file_tools():
    """
    测试 HtAgentConfig.get_tools() 已挂接 BaseTools 中的 open_file / open_file_by_id / read_cached_chunk。

    背景：早期 get_tools() 只硬编码了 get_current_time，导致 LLM 看不到文件加载与分块读取工具。
    本用例作为防回归：get_tools 返回的 tool name 列表必须含上述三个工具。
    """
    from app.features.contract_host_agent.config.HtAgentConfig import HtAgentConfig

    # get_tools() 不依赖运行时资源，可直接构造 config 实例调用
    cfg = HtAgentConfig()
    tools, tool_node = cfg.get_tools()

    # langchain 的 @tool 装饰后返回 StructuredTool 实例，其 .name 即注册到 LLM 的工具名
    def _tool_name(t):
        return getattr(t, "name", None) or getattr(t, "__name__", str(t))

    tool_names = {_tool_name(t) for t in (tools or [])}

    for expected in ("get_current_time", "open_file", "open_file_by_id", "read_cached_chunk"):
        assert expected in tool_names, f"工具 {expected} 未挂入 HtAgentConfig.get_tools()"

    # ToolNode 必须非 None（agent.py 依据 tool_node is None 决定是否加入 tools 节点）
    assert tool_node is not None


def test_ht_agent_constructor_accepts_base_system_prompt():
    """
    测试 HtAgent 构造时透传 base_system_prompt 到 HtAgentConfig（2026-08-19 透传回归）。

    用例目的：确保调用方在 HtAgent(checkpointer, store, ..., base_system_prompt="...") 时
    1) 不抛错（默认参数向后兼容）
    2) 实例字段 self.base_system_prompt 原样保存
    3) _ensure_agent 构造 HtAgentConfig 时把该值传给 config.base_system_prompt
       （避免只存 self 而漏传给 AgentConfig 的回归）

    测试方法：monkeypatch HtAgent 模块顶部的 get_agent 引用（包装类用
    ``from app.core.agent.agent import get_agent`` 已绑定到模块局部，所以
    monkeypatch 必须打在 HtAgent.get_agent 上，而不是源模块）。
    """
    from unittest.mock import patch
    from langgraph.store.memory import InMemoryStore

    # 包装类通过 ``from app.core.agent.agent import get_agent`` 把名字绑定到
    # 自身模块的全局命名空间；必须 patch 模块文件本身（不是包 __init__），
    # 才能换掉模块顶部那个引用。
    #
    # 注意：直接 ``import app.features.contract_host_agent.HtAgent as ht_module``
    # 在某些环境下会被 Python 解析为包属性（__init__.py 重导出了同名 HtAgent 类），
    # 导致拿到的是类而不是模块。所以改用 importlib.import_module 显式拿模块。
    import importlib
    ht_module = importlib.import_module('app.features.contract_host_agent.HtAgent')
    from app.features.contract_host_agent.HtAgent import HtAgent

    store = InMemoryStore()
    captured: dict = {}

    async def _fake_get_agent(config):
        captured["config"] = config
        # 返回 None，让 _ensure_agent 不再继续 chain；测试只看 config 字段
        return None

    with patch.object(ht_module, "get_agent", _fake_get_agent):
        instance = HtAgent(
            checkpointer=None,
            store=store,
            store_id="store_xyz",
            system_prompt="AGENT_SPECIFIC",
            base_system_prompt="",
        )

        # 字段原样保存
        assert instance.base_system_prompt == ""
        # system_prompt 仍走 "or DEFAULT_SYSTEM_PROMPT" 旧语义，本次未改
        assert instance.system_prompt == "AGENT_SPECIFIC"

        # 触发 _ensure_agent 让它构造 HtAgentConfig
        asyncio.run(instance._ensure_agent())

    assert "config" in captured, "get_agent 未被调用"
    assert captured["config"].base_system_prompt == ""
    # 同时确认其它字段正确透传，防止后续重构误改
    assert captured["config"].system_prompt == "AGENT_SPECIFIC"


def test_ht_agent_constructor_accepts_enabled_skill_names():
    """
    测试 HtAgent 构造时透传 enabled_skill_names 到 HtAgentConfig（2026-08-19 透传回归）。

    背景：contract_host_agent 走特性专属路由 contract_router.py::chat，不经过
    AgentConfigService.build_agent_instance()，原本 ``enabled_skill_names`` 默认 None
    被 SkillsAwarePrompt 解读为「加载全部 skill」，导致 LLM 系统提示词里
    ``<available_skills>`` 段把 skills 表全部 11 条 skill 都列出来。本用例确保
    HtAgent 包装类已经支持显式透传该字段，且 contract_router.get_ht_agent() 默认
    传 ``[]`` 关闭 skill 注入。

    用例目的：
    1) 默认 None 时字段原样保存
    2) 显式传 [] / ['hgsc'] 时字段原样保存
    3) _ensure_agent 构造 HtAgentConfig 时把 self.enabled_skill_names 传给 config
       （防「只存 self 而漏传给 AgentConfig」回归）
    """
    import importlib
    from unittest.mock import patch
    from langgraph.store.memory import InMemoryStore

    ht_module = importlib.import_module('app.features.contract_host_agent.HtAgent')
    from app.features.contract_host_agent.HtAgent import HtAgent

    store = InMemoryStore()
    captured: dict = {}

    async def _fake_get_agent(config):
        captured["config"] = config
        return None

    # 场景 1: 默认（不传 enabled_skill_names）→ None 透传
    with patch.object(ht_module, "get_agent", _fake_get_agent):
        instance = HtAgent(
            checkpointer=None,
            store=store,
            store_id="store_default",
        )
        assert instance.enabled_skill_names is None
        asyncio.run(instance._ensure_agent())
    assert captured["config"].enabled_skill_names is None

    # 场景 2: 显式传 [] → 空列表透传
    captured.clear()
    with patch.object(ht_module, "get_agent", _fake_get_agent):
        instance = HtAgent(
            checkpointer=None,
            store=store,
            store_id="store_empty",
            enabled_skill_names=[],
        )
        assert instance.enabled_skill_names == []
        asyncio.run(instance._ensure_agent())
    assert captured["config"].enabled_skill_names == [], (
        "显式传 [] 时必须原样透传到 HtAgentConfig.enabled_skill_names"
    )

    # 场景 3: 显式传非空白名单 → 原样透传
    captured.clear()
    with patch.object(ht_module, "get_agent", _fake_get_agent):
        instance = HtAgent(
            checkpointer=None,
            store=store,
            store_id="store_white",
            enabled_skill_names=["hgsc"],
        )
        assert instance.enabled_skill_names == ["hgsc"]
        asyncio.run(instance._ensure_agent())
    assert captured["config"].enabled_skill_names == ["hgsc"]


def test_contract_router_get_ht_agent_passes_empty_enabled_skill_names(monkeypatch):
    """
    测试 contract_router.get_ht_agent() 实例化 HtAgent 时显式传 enabled_skill_names=[]。

    背景：本轮修复 contract_host_agent 未绑定 skill 仍可加载全部 skill 的问题，
    通过在 contract_router 默认传 ``enabled_skill_names=[]`` 关闭 skill 注入。本用例
    作为防回归：get_ht_agent 拿到的 HtAgent 实例必须把 enabled_skill_names 设为 []。

    测试方法：monkeypatch get_async_checkpointer 避免真的初始化 checkpointer；
    monkeypatch HtAgent 构造器捕获入参。验证 HtAgent(...) 的 enabled_skill_names=
    实参是 []（空列表，不是 None）。
    """
    import asyncio
    from contextlib import contextmanager

    @contextmanager
    def _noop():
        yield

    async def _fake_checkpointer():
        return None

    captured: dict = {}

    def _fake_ht_agent(*args, **kwargs):
        captured["kwargs"] = kwargs
        captured["enabled_skill_names"] = kwargs.get("enabled_skill_names", "<missing>")
        # 不真的初始化 _agent，避免触发 get_agent；直接返回 stub
        class _Stub:
            pass
        return _Stub()

    # contract_router 模块顶部 ``from app.features.contract_host_agent.HtAgent import HtAgent``
    # 已经把名字绑定到模块局部，需要 patch 模块内的引用
    import importlib
    router_module = importlib.import_module(
        'app.features.contract_host_agent.router.contract_router'
    )

    monkeypatch.setattr(router_module, "get_async_checkpointer", _fake_checkpointer)
    monkeypatch.setattr(router_module, "HtAgent", _fake_ht_agent)

    # 重置模块级单例，让 get_ht_agent 真的走构造逻辑
    router_module._ht_agent = None

    result = asyncio.run(router_module.get_ht_agent())

    assert "kwargs" in captured, "HtAgent 未被实例化"
    assert captured["enabled_skill_names"] == [], (
        "contract_router.get_ht_agent() 必须传 enabled_skill_names=[] "
        "以关闭 contract_host_agent 的 skill 注入，避免 LLM 误加载项目文档 / 地图 / "
        "知识库 skill"
    )
    assert result is not None
