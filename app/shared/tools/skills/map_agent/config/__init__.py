#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
map_agent 配置模块

为 map_agent 工具提供报告生成所需的配置数据模型与配置工厂函数。
从 e:\\laboratory\\AI\\Agents\\dev-main\\app\\features\\map_agent\\config\\ 迁移而来。

主要导出：
- MapAgentSettings：MapAgent 专用 Pydantic BaseSettings 配置（从 .env 加载 mcp_tags 等）
- map_agent_settings：MapAgentSettings 单例
- ProjectSiteSelectionCollection：多项目选址数据集合模型
- get_report_config(data, collection)：报告配置工厂函数

Date: 2026-06-26
Author: AI Assistant
"""

from app.shared.tools.skills.map_agent.config.settings import MapAgentSettings
from app.shared.tools.skills.map_agent.config.config import (
    map_agent_settings,
    ProjectSiteSelectionCollection,
    get_report_config,
)

__all__ = [
    "MapAgentSettings",
    "map_agent_settings",
    "ProjectSiteSelectionCollection",
    "get_report_config",
]
