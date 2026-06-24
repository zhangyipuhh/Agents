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

import copy
from typing import Any, Callable

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

# === 新增（2026-06-24）：基类保留字段的运行时默认值 ===
# TypedDict 的类型注解默认值（形如 `error_limit: int = 5`）仅用于静态类型检查，
# 运行时不会生效。动态生成的 state / context 包装器必须显式声明这些默认值，
# 以保证调用方只传 messages / session_id 等必需字段时，state / context 实例仍
# 包含全部基类字段，避免 LangGraph 节点或工具访问 state[key] / context[key] 时
# 抛 KeyError。
# 与 AgentState（app/core/agent/AgentConfig.py:51-101）、
# AgentContext（app/core/agent/AgentContext.py:17-43）的字段定义保持一致。
_BASE_STATE_DEFAULTS: dict = {
    "error_limit": 5,
    "limit": 25,
    "file_chunk_read_progress": 1,
    "tool_progress": {},          # dict[str, dict]
    "intermediate_results": {},   # dict[str, Any]
    "pending_question": None,
    "question_answers": [],
    "agent_name": None,
}
"""AgentState 基类保留字段的运行时默认值，作为 build_agent_state 的兜底。"""

_BASE_CONTEXT_DEFAULTS: dict = {
    "session_id": "default",
    "namespace": {},
    "store_id": "default",
    "image_ids": [],
    "host_session_id": None,
    "process_data": {},
}
"""AgentContext 基类保留字段的运行时默认值，作为 build_agent_context 的兜底。"""

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

        说明:
            对 dict / list 等可变类型默认值使用 copy.deepcopy，
            避免多个实例共享同一对象引用导致跨实例污染。
        """
        instance = self._cls(*args, **kwargs)
        for key, value in self._defaults.items():
            if key not in instance:
                if isinstance(value, (dict, list)):
                    instance[key] = copy.deepcopy(value)
                else:
                    instance[key] = value
        return instance


def build_agent_state(agent_name: str, state_schema: dict) -> Callable:
    """根据数据库 state_schema 动态生成 AgentState 子类。

    参数:
        agent_name: 智能体名称（用于生成类名，下划线会被移除）
        state_schema: 数据库 agents.state_schema JSON，格式为
            {"field_name": {"type": "str|int|...", "default": <value>}}

    返回:
        Callable: 动态生成的 AgentState 子类包装器（_TypedDictWithDefaults），
        实例化时自动应用默认值。注意返回的是可调用包装器而非原生 type，
        调用方应将其视为可调用对象。

    说明:
        - 保留字段（RESERVED_STATE_FIELDS）的类型注解沿用基类，仅允许重写默认值
        - 非保留字段追加新的类型注解和默认值
        - 类名格式为 {PascalCaseAgentName}AgentState（如 map_agent → MapAgentAgentState）
        - 2026-06-24 修复：基类保留字段（error_limit / limit / agent_name 等）的
          运行时默认值由 _BASE_STATE_DEFAULTS 兜底，调用方只需显式传入 messages 等
          必需字段，无需重复传入保留字段。三级优先级：
          调用方 kwargs > schema 重写 > _BASE_STATE_DEFAULTS
    """
    # 2026-06-24 修复：以基类保留字段默认值作为兜底（详见 _BASE_STATE_DEFAULTS 注释）
    defaults = dict(_BASE_STATE_DEFAULTS)
    annotations = {}
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


def build_agent_context(agent_name: str, context_schema: dict) -> Callable:
    """根据数据库 context_schema 动态生成 AgentContext 子类。

    参数:
        agent_name: 智能体名称（用于生成类名，下划线会被移除）
        context_schema: 数据库 agents.context_schema JSON，格式为
            {"field_name": {"type": "str|int|...", "default": <value>}}

    返回:
        Callable: 动态生成的 AgentContext 子类包装器（_TypedDictWithDefaults），
        实例化时自动应用默认值。注意返回的是可调用包装器而非原生 type，
        调用方应将其视为可调用对象。

    说明:
        - 保留字段（RESERVED_CONTEXT_FIELDS）的类型注解沿用基类，仅允许重写默认值
        - 非保留字段追加新的类型注解和默认值
        - 类名格式为 {PascalCaseAgentName}AgentContext（如 map_agent → MapAgentAgentContext）
        - 2026-06-24 修复：基类保留字段（session_id / store_id / image_ids 等）
          的运行时默认值由 _BASE_CONTEXT_DEFAULTS 兜底，调用方只需显式传入
          session_id 等必需字段，无需重复传入保留字段。三级优先级：
          调用方 kwargs > schema 重写 > _BASE_CONTEXT_DEFAULTS
    """
    # 2026-06-24 修复：以基类保留字段默认值作为兜底（详见 _BASE_CONTEXT_DEFAULTS 注释）
    defaults = dict(_BASE_CONTEXT_DEFAULTS)
    annotations = {}
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
        - context_overrides 中的保留字段（RESERVED_CONTEXT_FIELDS，如 session_id /
          store_id）会被过滤，避免与显式传入的 session_id / store_id 发生
          "got multiple values for keyword argument" 冲突
    """
    cls = build_agent_context(agent_name, context_schema)
    overrides = getattr(request, "context_overrides", {}) or {}
    # 过滤保留字段，避免与显式传入的 session_id / store_id 等关键字参数冲突
    safe_overrides = {
        k: v for k, v in overrides.items()
        if k not in RESERVED_CONTEXT_FIELDS
    }
    instance = cls(
        session_id=getattr(request, "session_id", "default"),
        store_id=getattr(request, "store_id", "default"),
        **safe_overrides,
    )
    return instance
