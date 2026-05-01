#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
MapAgent 配置文件

该模块定义了 MapAgentConfig 数据类，用于封装地图控制 Agent 的所有配置参数。
支持配置模型参数、检查点器、存储库、系统提示词等核心功能。
使用 field() 处理默认值，解决了 dataclass 的类属性共享陷阱问题。

Date: 2026-04-14
Author: AI Assistant
"""

from dataclasses import dataclass, field
from langgraph.prebuilt import ToolNode
from app.core.agent.AgentConfig import (
    ConfigurableConfig as BaseConfigurableConfig,
    AgentState as BaseAgentState,
    AgentConfig as BaseAgentConfig,
    ExecuteConfig as BaseExecuteConfig,
)

from app.features.map_agent.config.MapAgentContext import MapAgentContext


class MapConfigurableConfig(BaseConfigurableConfig):
    """
    可配置参数，如 thread_id（线程ID，用于区分不同会话）等
    """


class MapExecuteConfig(BaseExecuteConfig):
    """
    LangGraph 可运行配置结构，继承自 BaseExecuteConfig

    用于配置 LangGraph 运行时的各种参数，如线程ID、回调等。
    与 LangGraph 的 invoke 方法的 config 参数兼容。
    """


class MapAgentState(BaseAgentState):
    """
    状态类，需要传入一个继承自 MessagesState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值
    具体实现的agent需要继承该类
    """

    map_center: dict = {"latitude": 0, "longitude": 0}
    """地图中心点坐标，包含 latitude 和 longitude"""

    map_zoom: int = 10
    """地图缩放级别，范围 1-20"""

    map_markers: list = []
    """地图标记列表，每个标记包含 id、latitude、longitude、title、description"""

    map_layer: str = "standard"
    """地图图层类型：standard（标准）、satellite（卫星）、terrain（地形）、hybrid（混合）"""

    map_polygons: list = []
    """地图多边形列表，每个多边形包含 id、coordinates、title、color"""


@dataclass(kw_only=True)
class MapAgentConfig(BaseAgentConfig):
    """
    MapAgent 配置类

    封装 Agent 的所有配置参数，用于初始化和管理 Agent 实例。
    该类使用数据类实现，支持默认值配置，便于灵活创建 Agent。
    支持继承，子类可重写默认值或添加新字段。
    """

    state_class: type[MapAgentState] = field(default=None)
    """
    状态类，需要传入一个继承自 AgentState 的 TypedDict 类型，用于管理对话状态，在会话中是可被操作的值   
    """

    context_class: type[MapAgentContext] = field(default=None)

    def get_tools(self) -> tuple[list[str], ToolNode]:
        """
        获取所有地图控制工具名称列表

        返回:
            tuple[list[str], ToolNode]: 工具名称列表和对应的 ToolNode 对象
        """
        import logging

        from app.features.map_agent.tools.MapTools import (
            set_map_center,
            set_map_zoom,
            add_map_marker,
            remove_map_marker,
            clear_map_markers,
            get_map_state,
            draw_map_polygon,
            set_map_layer,
        )
        from app.core.tools.BaseTools import get_current_time
        from app.core.tools.mcp_registry import MCPToolsRegistry
        from app.features.map_agent.config.config import map_agent_settings
        from app.core.tools.FilesystemReadTools import get_file_paths, search_agent
        tools = [
            #get_current_time,
            # set_map_center,
            # set_map_zoom,
            # add_map_marker,
            # remove_map_marker,
            # clear_map_markers,
            # get_map_state,
            # draw_map_polygon,
            # set_map_layer,
            get_file_paths,
            search_agent,
        ]

        try:
            from app.core.tools.mcp_tool_adapter import adapt_mcp_tool, MCPToolConfig

            registry = MCPToolsRegistry.get_instance()
            tools_with_server = registry.get_tools_with_server(tags=map_agent_settings.mcp_tags)
            
            if tools_with_server:
                for mcp_tool, server_name, server_config in tools_with_server:
                    tool_config_dict = server_config.get("tool_config", {})
                    tool_config = MCPToolConfig(
                        enable_injection=tool_config_dict.get("enable_injection", True),
                        default_param_keys=tool_config_dict.get("default_param_keys", []),
                        unwrap_result=tool_config_dict.get("unwrap_result", False),
                        hidden_param_keys=tool_config_dict.get("hidden_param_keys", [])
                    )
                    adapted_tool = adapt_mcp_tool(
                        mcp_tool,
                        mcp_server_name=server_name,
                        mcp_client=registry._pool,
                        tool_config=tool_config
                    )
                    tools.append(adapted_tool)
                
                logging.info(
                    "MapAgent loaded %d MCP tools with tags %s",
                    len(tools_with_server),
                    map_agent_settings.mcp_tags,
                )
            else:
                logging.warning(
                    "MapAgent no MCP tools found with tags %s",
                    map_agent_settings.mcp_tags,
                )
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.warning("MapAgent MCP tools unavailable, using static tools only")

        return tools, ToolNode(tools)
