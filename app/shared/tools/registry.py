#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
工具注册表模块

提供 @register_tool 装饰器和 ToolRegistry 类，用于将工具函数按 agent 维度注册，
供 AgentConfig.get_tools() 在运行时按 agent_name + enabled_tool_names 过滤加载。

Date: 2026-06-23
Author: AI Assistant
"""

from typing import Callable, Dict, List, Optional


class ToolRegistry:
    """工具注册表单例。

    通过 @register_tool 装饰器收集所有工具函数，按 agent_name 分组。
    AgentConfigService 加载 agent 配置时调用 get_tools_for_agent() 获取该 agent 启用的工具列表。
    """

    _tools: Dict[str, dict] = {}
    """工具注册表，key=tool_name，value={"func", "agent", "description", "module_path"}。"""

    @classmethod
    def register(cls, name: str, agent: str, description: str, module_path: str = "") -> Callable:
        """@register_tool 装饰器工厂。

        参数:
            name: 工具唯一名称（与 @tool 装饰的函数名一致）
            agent: 所属 agent 名称（如 "map_agent"）
            description: 工具描述
            module_path: 模块路径（可选，默认用 func.__module__）

        返回:
            Callable: 装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            cls._tools[name] = {
                "func": func,
                "agent": agent,
                "description": description,
                "module_path": module_path or func.__module__,
            }
            return func
        return decorator

    @classmethod
    def get_tools_for_agent(
        cls,
        agent_name: str,
        enabled_tool_names: Optional[List[str]] = None,
    ) -> List[Callable]:
        """根据 agent_name 和 enabled_tool_names 返回工具列表。

        参数:
            agent_name: 智能体名称
            enabled_tool_names: 启用的工具名列表。None 表示返回该 agent 所有工具。

        返回:
            List[Callable]: 工具函数列表
        """
        if enabled_tool_names is None:
            return [
                info["func"]
                for info in cls._tools.values()
                if info["agent"] == agent_name
            ]
        return [
            cls._tools[name]["func"]
            for name in enabled_tool_names
            if name in cls._tools and cls._tools[name]["agent"] == agent_name
        ]

    @classmethod
    def list_all(cls) -> Dict[str, dict]:
        """返回所有已注册工具（调试用）。

        返回:
            Dict[str, dict]: 工具名到工具信息的映射副本
        """
        return dict(cls._tools)

    @classmethod
    def clear(cls) -> None:
        """清空注册表（测试用）。"""
        cls._tools.clear()


register_tool = ToolRegistry.register
"""@register_tool 装饰器别名。"""
