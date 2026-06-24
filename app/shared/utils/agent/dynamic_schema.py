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
import logging
from typing import Any, Callable

from app.core.agent.AgentConfig import AgentState
from app.core.agent.AgentContext import AgentContext


logger = logging.getLogger(__name__)


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

# 2026-06-24 新增：AgentConfig 保留字段集合
# 这些字段不能通过 config_schema 覆盖（运行时对象 / 句柄无法被 JSON 描述）。
# state_class / context_class 由 schema 动态生成；checkpointer / store 是 LangGraph 运行时句柄。
RESERVED_CONFIG_FIELDS = {
    "state_class", "context_class", "checkpointer", "store",
}
"""AgentConfig 中不可被 schema 覆盖的字段集合。"""

# 2026-06-24 新增：AgentConfig 字段元信息
# 用于前端「添加字段」时从 AgentConfig 已有字段模板选择。
# 每个字段包含 type (TYPE_MAP 支持的基础类型) 和 default (运行时默认值)。
# 字段顺序按 AgentConfig 定义顺序排列。
_AGENT_CONFIG_FIELDS = [
    ("model_type",                   "str"),
    ("model_name",                   "str"),
    ("temperature",                  "float"),
    ("api_key",                      "str"),
    ("base_url",                     "str"),
    ("max_tokens",                   "int"),
    ("max_tokens_before_summary",    "int"),
    ("max_summary_tokens",           "int"),
    ("system_prompt",                "str"),
    ("name",                         "str"),
    ("max_input_tokens",             "int"),
    ("trim_tool_messages",           "bool"),
    ("keep_last_n_tools",            "int"),
    ("IS_MULTIMODAL",                "bool"),
    ("llm_retry_max_attempts",       "int"),
    ("llm_retry_initial_interval",   "float"),
    ("tool_retry_max_attempts",      "int"),
    ("tool_retry_initial_interval",  "float"),
    ("summarize_retry_max_attempts",  "int"),
    ("summarize_retry_initial_interval", "float"),
]
"""AgentConfig 字段清单（按定义顺序），用于前端字段模板选择与运行时校验。"""

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


# ============================================================
# 2026-06-24 新增：三层嵌套 config_schema 解析函数
# ============================================================

def parse_config_schema(config_schema: dict) -> dict:
    """把 config_schema 拆分为 (agent_config_overrides, state_schema, context_schema)。

    参数:
        config_schema: 三层嵌套字典，结构：
            {
                <AgentConfig 字段>: {"type": "...", "default": ...},
                state_fields:   {<字段>: {...}},
                context_fields: {<字段>: {...}},
            }
            也兼容旧的两段结构：{"state_fields": {...}, "context_fields": {...}}
            或纯 dict（视为顶层字段全部为 AgentConfig 字段覆盖）

    返回:
        dict: 包含以下键：
            - agent_config_overrides: dict —— AgentConfig 字段覆盖（含 Python 原生类型值）
            - state_schema: dict —— state_fields 子字典
            - context_schema: dict —— context_fields 子字典
            - raw_root_fields: dict —— config_schema 中不属于保留段的顶层字段
              （含 type/default 信息，供后续 service 层做白名单过滤）

    说明:
        - state_fields / context_fields 子段必须是 dict；缺失时回退到空 dict
        - 顶层非 state_fields/context_fields 的字段视为 AgentConfig 字段覆盖
        - RESERVED_CONFIG_FIELDS 中的字段被过滤（不能被覆盖）
        - RESERVED_STATE_FIELDS / RESERVED_CONTEXT_FIELDS 中的字段仅允许重写默认值
    """
    if not config_schema:
        config_schema = {}
    if not isinstance(config_schema, dict):
        logger.warning("config_schema is not a dict, using empty defaults")
        config_schema = {}

    # 提取 state_fields / context_fields
    state_schema = config_schema.get("state_fields") or {}
    context_schema = config_schema.get("context_fields") or {}
    if not isinstance(state_schema, dict):
        logger.warning("config_schema.state_fields is not a dict, using empty dict")
        state_schema = {}
    if not isinstance(context_schema, dict):
        logger.warning("config_schema.context_fields is not a dict, using empty dict")
        context_schema = {}

    # 提取顶层 AgentConfig 字段（排除保留段 + 保留字段）
    raw_root_fields = {}
    for key, value in config_schema.items():
        if key in ("state_fields", "context_fields"):
            continue
        if key in RESERVED_CONFIG_FIELDS:
            logger.warning(
                "config_schema contains reserved field '%s', ignored", key
            )
            continue
        if not isinstance(value, dict):
            logger.warning(
                "config_schema top-level field '%s' is not a dict, ignored", key
            )
            continue
        raw_root_fields[key] = value

    # 转换为 Python 原生类型
    agent_config_overrides = build_agent_config_overrides(config_schema)

    return {
        "agent_config_overrides": agent_config_overrides,
        "state_schema": state_schema,
        "context_schema": context_schema,
        "raw_root_fields": raw_root_fields,
    }


def build_agent_config_overrides(config_schema: dict) -> dict:
    """从 config_schema 中提取 AgentConfig 字段覆盖（Python 原生类型值）。

    参数:
        config_schema: 三层嵌套字典（可为空 dict）

    返回:
        dict: 如 {"temperature": 0.7, "max_tokens": 4096}
              仅返回 schema 中显式声明且不在 RESERVED_CONFIG_FIELDS 中的字段
              不在 schema 中的字段保留 AgentConfig 默认值，不在此返回

    说明:
        - 类型字符串通过 TYPE_MAP 转换为 Python 原生类型
        - dict / list 等可变类型使用 copy.deepcopy 避免跨实例污染
        - 缺失 "default" 键的字段会被跳过（仅声明类型无值，不覆盖）
    """
    import copy as _copy

    if not config_schema or not isinstance(config_schema, dict):
        return {}

    overrides: dict = {}
    for key, value in config_schema.items():
        if key in ("state_fields", "context_fields"):
            continue
        if key in RESERVED_CONFIG_FIELDS:
            continue
        if not isinstance(value, dict):
            continue
        if "default" not in value:
            continue

        py_type = TYPE_MAP.get(value.get("type", "str"), str)
        raw_default = value["default"]

        # 类型转换 / 校验
        try:
            converted = _convert_to_python_type(raw_default, py_type)
        except (ValueError, TypeError) as e:
            logger.warning(
                "config_schema field '%s' default value %r cannot be converted to %s: %s",
                key, raw_default, py_type, e,
            )
            continue

        if isinstance(converted, (dict, list)):
            overrides[key] = _copy.deepcopy(converted)
        else:
            overrides[key] = converted

    return overrides


def _convert_to_python_type(value: Any, py_type: type) -> Any:
    """把 schema 中的 default 值转换为指定 Python 类型。

    参数:
        value: 原始值（来自 JSON 反序列化，可能是 str / int / float / bool / dict / list / None）
        py_type: 目标 Python 类型

    返回:
        Any: 转换后的值

    异常:
        ValueError: 无法转换时抛出
    """
    if value is None:
        return None
    if py_type is str:
        return str(value)
    if py_type is int:
        return int(value)
    if py_type is float:
        return float(value)
    if py_type is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)
    if py_type is dict:
        if not isinstance(value, dict):
            raise ValueError(f"expected dict, got {type(value).__name__}")
        return dict(value)
    if py_type is list:
        if not isinstance(value, list):
            raise ValueError(f"expected list, got {type(value).__name__}")
        return list(value)
    return value


def get_agent_config_field_schema(field_name: str) -> dict | None:
    """获取 AgentConfig 中某个字段的 schema 定义（type + 默认值）。

    用于前端「添加字段」时从 AgentConfig 已有字段模板选择。

    参数:
        field_name: 字段名

    返回:
        dict | None: 如 {"type": "float", "default": 0, "field_name": "temperature"}
                      字段不存在或属于保留字段时返回 None

    说明:
        - 返回的 default 是 AgentConfig.dataclass 的字段默认值
        - 调用方应允许用户修改 default 值（覆盖原始默认值）
    """
    # 延迟导入避免循环依赖
    from app.core.agent.AgentConfig import AgentConfig

    field_names = {f[0] for f in _AGENT_CONFIG_FIELDS}
    if field_name not in field_names:
        return None
    if field_name in RESERVED_CONFIG_FIELDS:
        return None

    # 从 dataclass 字段获取默认值
    from dataclasses import fields as _dc_fields
    for f in _dc_fields(AgentConfig):
        if f.name == field_name:
            py_type = next((t for n, t in _AGENT_CONFIG_FIELDS if n == field_name), "str")
            default = f.default
            # default 是 dataclasses.MISSING 时返回 None
            try:
                if default is f.default_factory():  # type: ignore[misc]
                    pass
            except TypeError:
                pass
            return {
                "field_name": field_name,
                "type": py_type,
                "default": default if not isinstance(default, type) else None,
            }
    return None


def get_agent_config_field_templates() -> list:
    """获取 AgentConfig 所有可被 schema 覆盖的字段模板列表。

    返回:
        list: 每项为 {"field_name": str, "type": str, "default": Any}
              按 AgentConfig 定义顺序排列，不含 RESERVED_CONFIG_FIELDS
    """
    templates = []
    for field_name, type_str in _AGENT_CONFIG_FIELDS:
        if field_name in RESERVED_CONFIG_FIELDS:
            continue
        schema = get_agent_config_field_schema(field_name)
        if schema:
            templates.append(schema)
    return templates


def _get_type_str(annotation) -> str:
    """将 Python 类型注解转换为 TYPE_MAP 支持的类型字符串。

    参数:
        annotation: Python 类型注解对象

    返回:
        str: TYPE_MAP 中的类型键（str/int/float/bool/dict/list）

    说明:
        - 对 typing.Optional[X] 会递归解析非 None 的参数
        - 对泛型如 dict[str, dict] / list[str] 统一返回 dict/list
        - 无法识别的类型默认回退为 "str"
    """
    import typing

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # 处理 Optional[X]（即 Union[X, None]）
    if origin is typing.Union and type(None) in args:
        non_none_args = [a for a in args if a is not type(None)]
        if non_none_args:
            return _get_type_str(non_none_args[0])

    # 处理泛型 dict / list
    if origin in (dict, typing.Dict):
        return "dict"
    if origin in (list, typing.List):
        return "list"

    # 处理原生类型
    if annotation is str:
        return "str"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is bool:
        return "bool"
    if annotation is dict:
        return "dict"
    if annotation is list:
        return "list"

    return "str"


def get_agent_state_field_templates() -> list:
    """获取 AgentState 所有可被 schema 覆盖的保留字段模板列表。

    返回:
        list: 每项为 {"field_name": str, "type": str, "default": Any}
              按 AgentState 定义顺序排列，不含 messages（运行时必需字段）

    说明:
        - messages 是 LangGraph MessagesState 的必需字段，运行时由调用方显式传入，
          不适合通过 schema 覆盖默认值，因此不出现在模板列表中。
        - 保留字段（如 error_limit / limit）的类型注解沿用基类，默认值来自
          _BASE_STATE_DEFAULTS。
    """
    templates = []
    for field_name, annotation in AgentState.__annotations__.items():
        if field_name == "messages":
            continue
        type_str = _get_type_str(annotation)
        default = _BASE_STATE_DEFAULTS.get(field_name)
        templates.append({
            "field_name": field_name,
            "type": type_str,
            "default": default,
        })
    return templates


def get_agent_context_field_templates() -> list:
    """获取 AgentContext 所有可被 schema 覆盖的保留字段模板列表。

    返回:
        list: 每项为 {"field_name": str, "type": str, "default": Any}
              按 AgentContext 定义顺序排列

    说明:
        - 所有保留字段（session_id / namespace / store_id 等）均可通过 schema
          重写默认值，类型注解沿用基类，默认值来自 _BASE_CONTEXT_DEFAULTS。
    """
    templates = []
    for field_name, annotation in AgentContext.__annotations__.items():
        type_str = _get_type_str(annotation)
        default = _BASE_CONTEXT_DEFAULTS.get(field_name)
        templates.append({
            "field_name": field_name,
            "type": type_str,
            "default": default,
        })
    return templates
