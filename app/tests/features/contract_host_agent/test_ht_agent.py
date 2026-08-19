# -*- coding:utf-8 -*-
"""
合同主办 Agent (HtAgent) 冒烟测试模块

验证 HtAgent 的核心模块可正常导入、提示词非空以及路由正确注册。

Date: 2026-06-08
"""


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
