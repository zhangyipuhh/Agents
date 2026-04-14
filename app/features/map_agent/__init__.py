#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
地图智能体模块

该模块提供地图控制智能体的配置、工具和核心功能。

Date: 2026-04-14
Author: AI Assistant
"""

from app.features.map_agent.config import (
    MapConfigurableConfig,
    MapExecuteConfig,
    MapAgentState,
    MapAgentConfig,
    MapAgentContext,
    DEFAULT_SYSTEM_PROMPT
)

from app.features.map_agent.tools import (
    set_map_center,
    set_map_zoom,
    add_map_marker,
    remove_map_marker,
    clear_map_markers,
    get_map_state,
    draw_map_polygon,
    set_map_layer
)

__all__ = [
    # 配置类
    "MapConfigurableConfig",
    "MapExecuteConfig",
    "MapAgentState",
    "MapAgentConfig",
    "MapAgentContext",
    "DEFAULT_SYSTEM_PROMPT",
    # 工具函数
    "set_map_center",
    "set_map_zoom",
    "add_map_marker",
    "remove_map_marker",
    "clear_map_markers",
    "get_map_state",
    "draw_map_polygon",
    "set_map_layer"
]
