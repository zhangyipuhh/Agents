#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
动态 State/Context 构建器模块

根据数据库 agents 表的 state_schema / context_schema JSON 动态生成
AgentState / AgentContext 的子类。

合并逻辑：
- 基类所有字段保留。
- 数据库 schema 中的字段追加（同名则重写默认值）。
- 保留字段（messages / session_id 等）由基类提供类型注解，schema 仅可重写默认值。

实现说明：
    TypedDict 原生不在运行时应用字段默认值（默认值仅用于类型检查），
    且 typing_extensions 的 _TypedDictMeta 元类硬编码了 __call__，
    无法通过自定义元类覆写。因此本模块采用工厂包装器 _TypedDictWithDefaults，
    在实例化后补全缺失字段的默认值。

Date: 2026-06-23
Author: AI Assistant
"""

from typing import Any

from app.core.agent.AgentConfig import AgentState
from app.core.agent.AgentContext import AgentContext


RESERVED_STATE_FIELDS = {
    "messages", "error_limit", "limit", "file_chunk_read_progress",
    "tool_progress", "intermediate_results", "pending_question",
    "question_answers", "agent_name",
}
"""AgentState 基类保留字段集合，schema 中同名字段仅允许重写默认值，不可重写类型注解。"""

RESERVED_CONTEXT_FIELDS = {
    "session_id", "namespace", "store_id", "image_ids",
    "host_session_id", "process_data",
}
"""AgentContext 基类保留字段集合。"""

TYPE_MAP = {
    "str": str, "int": int, "float": float, "bool": bool,
    "dict": dict, "list": list,
}
"""schema type 字符串到 Python 类型的映射。"""


class _TypedDictWithDefaults:
    """TypedDict 工厂包装器，在实例化时自动应用 schema 定义的默认值。

    TypedDict 原生不会在运行时应用字段默认值（默认值仅用于类型检查），
    且 _TypedDictMeta 元类硬编码了 __call__ 行为，无法通过自定义元类覆写。
    本包装器通过 __call__ 在实例化后补全缺失字段的默认值。

    Attributes:
        _cls: 被包装的 TypedDict 子类
        _defaults: 需在实例化时补全的字段默认值字典
        __name__: 透传自被包装类，供测试与调试访问
        __annotations__: 透传自被包装类，供类型检查与测试访问
    """

    def __init__(self, typed_dict_cls: type, defaults: dict):
        """初始化包装器。

        参数:
            typed_dict_cls: 被包装的 TypedDict 子类（由 _TypedDictMeta 创建）
            defaults: 需在实例化时补全的字段默认值字典
        """
        self._cls = typed_dict_cls
        self._defaults = defaults
        self.__name__ = typed_dict_cls.__name__
        self.__annotations__ = typed_dict_cls.__annotations__

    def __call__(self, *args, **kwargs):
        """创建 TypedDict 实例并补全缺失字段的默认值。

        参数:
            *args: 位置参数（透传给 TypedDict 构造）
            **kwargs: 关键字参数（透传给 TypedDict 构造）

        返回:
            dict: 创建的 TypedDict 实例，缺失字段已用默认值补全
        """
        instance = self._cls(*args, **kwargs)
        for key, value in self._defaults.items():
            if key not in instance:
                instance[key] = value
        return instance


def build_agent_state(agent_name: str, state_schema: dict) -> type:
    """根据数据库 state_schema 动态生成 AgentState 子类。

    参数:
        agent_name: 智能体名称（用于生成类名，下划线会被移除）
        state_schema: 数据库 agents.state_schema JSON，格式为
            {"field_name": {"type": "str|int|...", "default": <value>}}

    返回:
        type: 动态生成的 AgentState 子类包装器，实例化时自动应用默认值

    说明:
        - 保留字段（RESERVED_STATE_FIELDS）的类型注解沿用基类，仅允许重写默认值
        - 非保留字段追加新的类型注解和默认值
        - 类名格式为 {PascalCaseAgentName}AgentState（如 map_agent → MapAgentAgentState）
    """
    annotations = {}
    defaults = {}
    for fname, fdef in state_schema.items():
        if fname in RESERVED_STATE_FIELDS:
            # 保留字段：类型注解沿用基类，仅重写默认值
            if "default" in fdef:
                defaults[fname] = fdef["default"]
            continue
        py_type = TYPE_MAP.get(fdef.get("type", "str"), str)
        annotations[fname] = py_type
        if "default" in fdef:
            defaults[fname] = fdef["default"]

    base_annotations = dict(AgentState.__annotations__)
    merged_annotations = {**base_annotations, **annotations}
    namespace = {**defaults, "__annotations__": merged_annotations}
    class_name = f"{agent_name.title().replace('_', '')}AgentState"
    typed_dict_cls = type(AgentState)(class_name, (AgentState,), namespace)
    return _TypedDictWithDefaults(typed_dict_cls, defaults)


def build_agent_context(agent_name: str, context_schema: dict) -> type:
    """根据数据库 context_schema 动态生成 AgentContext 子类。

    参数:
        agent_name: 智能体名称（用于生成类名，下划线会被移除）
        context_schema: 数据库 agents.context_schema JSON，格式为
            {"field_name": {"type": "str|int|...", "default": <value>}}

    返回:
        type: 动态生成的 AgentContext 子类包装器，实例化时自动应用默认值

    说明:
        - 保留字段（RESERVED_CONTEXT_FIELDS）的类型注解沿用基类，仅允许重写默认值
        - 非保留字段追加新的类型注解和默认值
        - 类名格式为 {PascalCaseAgentName}AgentContext（如 map_agent → MapAgentAgentContext）
    """
    annotations = {}
    defaults = {}
    for fname, fdef in context_schema.items():
        if fname in RESERVED_CONTEXT_FIELDS:
            if "default" in fdef:
                defaults[fname] = fdef["default"]
            continue
        py_type = TYPE_MAP.get(fdef.get("type", "str"), str)
        annotations[fname] = py_type
        if "default" in fdef:
            defaults[fname] = fdef["default"]

    base_annotations = dict(AgentContext.__annotations__)
    merged_annotations = {**base_annotations, **annotations}
    namespace = {**defaults, "__annotations__": merged_annotations}
    class_name = f"{agent_name.title().replace('_', '')}AgentContext"
    typed_dict_cls = type(AgentContext)(class_name, (AgentContext,), namespace)
    return _TypedDictWithDefaults(typed_dict_cls, defaults)


def build_context(agent_name: str, context_schema: dict, request: Any) -> AgentContext:
    """运行时构造 context 实例。

    参数:
        agent_name: 智能体名称
        context_schema: 数据库 context_schema JSON
        request: 请求对象，需包含 session_id / store_id / context_overrides 属性

    返回:
        AgentContext: 构造好的上下文实例，包含请求中的 session_id / store_id
        以及 context_overrides 中的覆盖值

    说明:
        - context_overrides 中的键值会覆盖 schema 默认值
        - 缺失的 session_id / store_id 回退为 "default"
    """
    cls = build_agent_context(agent_name, context_schema)
    overrides = getattr(request, "context_overrides", {}) or {}
    instance = cls(
        session_id=getattr(request, "session_id", "default"),
        store_id=getattr(request, "store_id", "default"),
        **overrides,
    )
    return instance
