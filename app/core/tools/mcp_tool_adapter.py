#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP 工具转换器模块

提供将 MCP Tool 对象转换为 LangChain BaseTool 的功能，
解决 MCP Python SDK v1.27.0 的 Tool 对象与 LangChain bind_tools() 不兼容的问题。

主要功能：
- JSON Schema 的 $ref 和 $defs 引用解析
- 将 JSON Schema 转换为 Pydantic 模型
- 适配 MCP Tool 为 LangChain BaseTool
- 支持运行时参数注入

Date: 2026-04-26
Author: 张镒谱
"""

import asyncio
import inspect
import json
import logging
import copy
from datetime import datetime
from typing import Any, ClassVar, List, Optional, Type

from langgraph.config import get_stream_writer
from pydantic import BaseModel, ConfigDict, Field, create_model

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.core.tools.events import create_tool_event

logger = logging.getLogger(__name__)


def _resolve_ref(ref: str, defs: dict) -> dict:
    """
    解析 $ref 引用
    
    从扁平化的 $defs 字典中查找并返回指定路径对应的 schema 定义。
    使用深度复制确保返回的数据与原始定义分离，避免意外修改。

    Args:
        ref: $ref 字符串，格式如 "#/$defs/Feature"
        defs: $defs 定义的字典（已扁平化，不包含 $defs 键）

    Returns:
        解析后的 schema 字典
    """
    # 仅支持本地引用（以 #/ 开头），抛出异常阻止远程引用
    if not ref.startswith("#/"):
        raise ValueError(f"Only local references are supported, got: {ref}")

    # 移除 #/ 前缀并按路径分隔符拆分
    path_parts = ref[2:].split("/")
    current = defs

    # 逐层遍历路径，每一层都是一个键名
    for part in path_parts:
        # 跳过路径中的 $defs 标记
        if part == "$defs":
            continue
        # 键不存在时抛出异常
        if part not in current:
            raise KeyError(f"Reference '{ref}' not found in defs")
        # 移动到下一层
        current = current[part]

    # 返回深拷贝防止意外修改原始定义
    return copy.deepcopy(current)


def _collect_defs(schema: dict[str, Any], defs: dict = None) -> dict:
    """
    递归收集 JSON Schema 中所有的 $defs 定义
    
    采用深度优先遍历策略，将嵌套结构中的所有 $defs 定义
    合并到扁平化字典中，便于后续引用解析。

    Args:
        schema: JSON Schema 字典
        defs: 已收集的 $defs 定义（用于递归）

    Returns:
        收集到的所有 $defs 定义
    """
    # 首次调用时初始化空字典
    if defs is None:
        defs = {}
    
    # 非字典类型直接返回（如基本类型值）
    if not isinstance(schema, dict):
        return defs
    
    # 合并当前层级的 $defs 定义到结果字典
    if "$defs" in schema:
        defs.update(copy.deepcopy(schema["$defs"]))
    
    # 遍历所有键值对，继续递归收集
    for key, value in schema.items():
        # 跳过已处理的 $defs 键
        if key == "$defs":
            continue
        # 字典类型递归处理
        elif isinstance(value, dict):
            _collect_defs(value, defs)
        # 列表类型遍历检查每个元素
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _collect_defs(item, defs)
    
    return defs


def _normalize_schema(schema: dict[str, Any], all_defs: dict = None) -> dict[str, Any]:
    """
    规范化 JSON Schema，解析所有 $ref 引用
    
    两阶段处理：首先收集所有 $defs 定义到扁平化字典，
    然后递归替换所有 $ref 引用为实际定义。解析失败时保留原引用并记录警告。

    Args:
        schema: 原始 JSON Schema
        all_defs: 所有 $defs 定义（用于递归）

    Returns:
        规范化后的 JSON Schema
    """
    # 非字典类型直接返回
    if not isinstance(schema, dict):
        return schema

    # 首次调用时收集所有 $defs 定义
    if all_defs is None:
        all_defs = _collect_defs(schema)

    result = {}

    # 遍历 schema 中的每个键值对
    for key, value in schema.items():
        # 跳过 $defs 节点（已收集到 all_defs 中）
        if key == "$defs":
            continue
        # 处理 $ref 引用：解析引用并合并到结果中
        elif key == "$ref":
            if isinstance(value, str):
                try:
                    # 解析引用获取实际 schema
                    resolved = _resolve_ref(value, all_defs)
                    # 递归规范化解析后的 schema（处理嵌套引用）
                    resolved = _normalize_schema(resolved, all_defs)
                    # 合并到结果字典
                    result.update(resolved)
                except (KeyError, ValueError) as e:
                    # 解析失败时记录警告并保留原引用
                    logger.warning(f"Failed to resolve $ref '{value}': {e}")
                    result[key] = value
            else:
                result[key] = value
        # 字典类型递归规范化
        elif isinstance(value, dict):
            result[key] = _normalize_schema(value, all_defs)
        # 列表类型遍历处理每个字典元素
        elif isinstance(value, list):
            result[key] = [
                _normalize_schema(item, all_defs) if isinstance(item, dict) else item
                for item in value
            ]
        # 基本类型直接复制
        else:
            result[key] = value

    return result


class _NormalizedSchemaModel(BaseModel):
    """
    自定义 Pydantic 模型基类，存储已经解析好 $ref 引用的 schema
    
    当 LangChain 的 bind_tools() 调用 model_json_schema() 时，
    返回已经解析好的 schema，避免 $ref 引用解析错误。
    
    类变量 _normalized_schema 用于缓存规范化后的 schema，
    优先返回缓存数据以提升性能。
    """
    # 类级别变量：存储规范化后的 schema 缓存
    _normalized_schema: ClassVar[dict] = {}
    
    @classmethod
    def model_json_schema(cls, **kwargs) -> dict:
        """
        返回规范化后的 JSON Schema
        
        如果存在缓存的规范化 schema，直接返回缓存；
        否则调用父类方法生成 schema。
        
        Returns:
            JSON Schema 字典
        """
        # 优先返回缓存的规范化 schema
        if cls._normalized_schema:
            return cls._normalized_schema
        # 无缓存时调用父类方法
        return super().model_json_schema(**kwargs)


def json_schema_to_pydantic_model(
    schema: dict[str, Any], model_name: str = "ToolArgs"
) -> Type[BaseModel]:
    """
    将 JSON Schema 转换为 Pydantic 模型
    
    支持 JSON Schema 类型到 Python 类型的映射，包括：
    - string -> str
    - number -> float
    - integer -> int
    - boolean -> bool
    - array -> list
    - object -> 嵌套 Pydantic 模型或 dict
    
    处理 $ref 和 $defs 引用解析，以及 anyOf/oneOf 联合类型。

    Args:
        schema: JSON Schema 字典
        model_name: 生成的模型名称

    Returns:
        Pydantic 模型类
    """
    # 第一步：规范化 schema，解析所有 $ref 引用
    normalized_schema = _normalize_schema(schema)
    # 提取属性定义和必填字段列表
    properties = normalized_schema.get("properties", {})
    required = normalized_schema.get("required", [])

    # 与 Pydantic 类型注解可能冲突的字段名（保留字）
    CONFLICTING_FIELD_NAMES = {"type", "default", "title", "description", "examples"}

    # 存储字段定义的字典
    field_definitions = {}
    
    # 遍历每个属性字段
    for field_name, field_schema in properties.items():
        json_type = field_schema.get("type")

        # 检查字段名称是否与类型注解冲突，冲突时需要使用别名
        needs_alias = field_name in CONFLICTING_FIELD_NAMES
        # 使用安全的内部字段名（添加下划线后缀）
        internal_name = f"{field_name}_" if needs_alias else field_name

        def make_field(py_type, is_required, alias=None):
            """
            创建字段定义元组
            
            根据是否为必填字段以及是否需要别名，
            返回不同的字段定义格式。
            """
            if is_required:
                # 必填字段使用 ... 表示必须提供
                if alias:
                    return (py_type, Field(alias=alias))
                return (py_type, ...)
            else:
                # 可选字段使用 None 作为默认值
                if alias:
                    return (Optional[py_type], Field(default=None, alias=alias))
                return (Optional[py_type], None)

        # 判断当前字段是否为必填字段
        is_required = field_name in required

        # 根据 JSON Schema 类型映射到 Python 类型
        if json_type == "string":
            # 处理字符串枚举类型
            if "enum" in field_schema:
                from enum import Enum

                # 创建枚举类，值为字符串
                enum_values = {v: v for v in field_schema["enum"]}
                enum_cls = Enum(f"{model_name}_{field_name}_enum", enum_values)
                field_definitions[internal_name] = make_field(
                    enum_cls, is_required, field_name if needs_alias else None
                )
            else:
                # 普通字符串类型
                field_definitions[internal_name] = make_field(
                    str, is_required, field_name if needs_alias else None
                )
        # 处理数值类型（浮点数和整数）
        elif json_type == "number" or json_type == "integer":
            py_type = float if json_type == "number" else int
            field_definitions[internal_name] = make_field(
                py_type, is_required, field_name if needs_alias else None
            )
        # 处理布尔类型
        elif json_type == "boolean":
            if is_required:
                field_definitions[internal_name] = (
                    bool, Field(alias=field_name) if needs_alias else ...
                )
            else:
                field_definitions[internal_name] = (
                    bool, Field(default=False, alias=field_name) if needs_alias else False
                )
        # 处理数组类型
        elif json_type == "array":
            field_definitions[internal_name] = make_field(
                list, is_required, field_name if needs_alias else None
            )
        # 处理对象类型
        elif json_type == "object":
            # 有 properties 定义时创建嵌套模型
            if "properties" in field_schema:
                nested_model = json_schema_to_pydantic_model(
                    field_schema, f"{model_name}_{field_name}"
                )
                field_definitions[internal_name] = make_field(
                    nested_model, is_required, field_name if needs_alias else None
                )
            else:
                # 无 properties 时使用通用字典类型
                field_definitions[internal_name] = make_field(
                    dict, is_required, field_name if needs_alias else None
                )
        # 处理联合类型（anyOf 或 oneOf）
        elif json_type is None and (
            "anyOf" in field_schema or "oneOf" in field_schema
        ):
            # 获取子 schema 列表
            sub_schemas = field_schema.get("anyOf") or field_schema.get("oneOf")
            types = []
            # 遍历子 schema 收集可能的类型
            for sub in sub_schemas:
                sub_type = sub.get("type", "string")
                if sub_type == "string":
                    types.append(str)
                elif sub_type == "number":
                    types.append(float)
                elif sub_type == "integer":
                    types.append(int)
                elif sub_type == "boolean":
                    types.append(bool)
                elif sub_type == "array":
                    types.append(list)
                elif sub_type == "object":
                    types.append(dict)
                else:
                    # 未知类型默认为字符串
                    types.append(str)
            from typing import Union

            # 单类型直接使用，多类型使用 Union
            union_type = Union[tuple(types)] if len(types) > 1 else types[0]
            field_definitions[internal_name] = make_field(
                union_type, is_required, field_name if needs_alias else None
            )
        # 兜底策略：未知类型默认为字符串
        else:
            field_definitions[internal_name] = make_field(
                str, is_required, field_name if needs_alias else None
            )

    # 创建 Pydantic 模型
    model = create_model(
        model_name,
        __base__=_NormalizedSchemaModel,
        __config__=ConfigDict(extra="allow", populate_by_name=True),
        **field_definitions,
    )
    # 缓存规范化后的 schema 到模型类
    model._normalized_schema = normalized_schema

    return model


class MCPToolConfig:
    """
    MCP 工具配置类
    
    用于配置 MCP 工具适配器的运行时参数注入行为。
    支持从配置或运行时上下文自动注入参数到工具调用。
    """
    
    def __init__(
        self, 
        enable_injection: bool = True, 
        default_param_keys: list[str] | None = None,
        unwrap_result: bool = False
    ):
        """
        初始化工具配置
        
        Args:
            enable_injection: 是否启用运行时参数注入
            default_param_keys: 需要自动注入的参数键列表
            unwrap_result: 是否解析工具返回结果，当为True时解析JSON格式{"content": ..., "result": ...}
        """
        self.enable_injection = enable_injection
        self.default_param_keys = default_param_keys or []
        self.unwrap_result = unwrap_result


class MCPToolToLangChainAdapter(BaseTool):
    """
    MCP 工具到 LangChain BaseTool 的适配器
    
    核心功能：
    - 将 MCP Tool 对象适配为 LangChain BaseTool
    - 自动处理工具的输入模式（args_schema）
    - 支持异步和同步两种执行模式
    - 支持运行时参数注入
    
    适配策略：
    - 优先使用 args_schema（BaseTool 风格）
    - 其次使用 inputSchema（MCP SDK 风格）
    - 两者都不可用时，args_schema 为 None
    """
    # 工具名称
    name: str = ""
    # 工具描述
    description: str = ""

    # 原始 MCP 工具对象
    mcp_tool: Any = None
    # MCP 服务器名称
    mcp_server_name: str = ""
    # MCP 客户端实例
    mcp_client: Any = None
    # 工具配置
    tool_config: Any = None

    def __init__(
        self,
        mcp_tool: Any,
        mcp_server_name: str = "",
        mcp_client: Any = None,
        tool_config: MCPToolConfig | None = None,
        **kwargs,
    ):
        """
        初始化适配器
        
        从原始 MCP 工具提取名称、描述和输入模式，
        并将输入模式转换为 Pydantic 模型。
        
        Args:
            mcp_tool: 原始 MCP 工具对象
            mcp_server_name: MCP 服务器名称
            mcp_client: MCP 客户端实例
            tool_config: 工具配置对象
            **kwargs: 传递给 BaseTool 的额外参数
        """
        # 处理已适配的 BaseTool 的 response_format
        if isinstance(mcp_tool, BaseTool):
            if (
                getattr(mcp_tool, "response_format", None)
                and "response_format" not in kwargs
            ):
                kwargs["response_format"] = mcp_tool.response_format

        # 调用父类初始化
        super().__init__(**kwargs)

        # 保存原始工具和配置信息
        self.mcp_tool = mcp_tool
        self.mcp_server_name = mcp_server_name
        self.mcp_client = mcp_client
        self.tool_config = tool_config

        # 从原始工具提取名称和描述
        tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        tool_description = getattr(mcp_tool, "description", "")

        self.name = tool_name
        self.description = tool_description

        # 根据工具类型选择合适的模式提取策略
        if (
            isinstance(mcp_tool, BaseTool)
            and getattr(mcp_tool, "args_schema", None) is not None
        ):
            # 策略1：BaseTool 风格的 args_schema
            original_schema = mcp_tool.args_schema
            if isinstance(original_schema, type) and issubclass(original_schema, BaseModel):
                # 已是 Pydantic 模型，直接使用
                self.args_schema = original_schema
            elif isinstance(original_schema, dict):
                # 字典格式的 schema，转换为 Pydantic 模型
                self.args_schema = json_schema_to_pydantic_model(
                    original_schema, f"{tool_name}Args"
                )
            else:
                # 不支持的 schema 类型，记录警告
                logger.warning(
                    f"Unexpected args_schema type for tool '{tool_name}': {type(original_schema)}"
                )
                self.args_schema = None
        else:
            # 策略2：MCP SDK 风格的 inputSchema
            input_schema = getattr(mcp_tool, "inputSchema", {})
            if (
                input_schema
                and isinstance(input_schema, dict)
                and input_schema.get("properties")
            ):
                # 存在属性定义，转换为 Pydantic 模型
                self.args_schema = json_schema_to_pydantic_model(
                    input_schema, f"{tool_name}Args"
                )
            else:
                # 无有效 schema
                self.args_schema = None

    def _get_tool_call_id(self, config) -> str:
        """
        从配置中提取工具调用ID
        
        用于事件追踪和日志记录，每个工具调用应有唯一ID。
        
        Args:
            config: 运行配置对象
            
        Returns:
            工具调用ID，未找到时返回 "unknown"
        """
        # 尝试从配置中获取 tool_call_id
        if config and "configurable" in config:
            return config["configurable"].get("tool_call_id", "unknown")
        return "unknown"

    def _get_writer(self):
        """
        获取流写入器
        
        用于将工具执行事件写入流。
        
        Returns:
            流写入器实例，获取失败时返回 None
        """
        try:
            return get_stream_writer()
        except (ImportError, RuntimeError):
            # 导入错误或运行时错误时返回 None
            return None

    def _merge_args_kwargs(self, args: tuple, kwargs: dict) -> dict:
        """
        合并位置参数和关键字参数
        
        处理多种参数传递方式的统一化：
        - 仅关键字参数
        - 单个字典作为位置参数
        - 单个字符串作为位置参数（映射到第一个字段或 input）
        - 多个位置参数
        
        Args:
            args: 位置参数元组
            kwargs: 关键字参数字典
            
        Returns:
            合并后的参数字典
        """
        # 以 kwargs 为基础创建合并字典
        merged = dict(kwargs)
        
        # 无位置参数时直接返回 kwargs
        if not args:
            return merged
        
        # 单个字典参数：直接合并到 kwargs
        if len(args) == 1 and isinstance(args[0], dict):
            merged.update(args[0])
        # 单个字符串参数：尝试映射到 schema 的第一个字段
        elif len(args) == 1 and isinstance(args[0], str):
            if self.args_schema and hasattr(self.args_schema, "model_fields"):
                fields = self.args_schema.model_fields
                if fields:
                    # 获取第一个字段名作为目标
                    first_field = next(iter(fields))
                    merged[first_field] = args[0]
                else:
                    # 无字段定义时使用 input
                    merged["input"] = args[0]
            else:
                merged["input"] = args[0]
        # 多个位置参数：为每个参数生成唯一键名
        else:
            for i, arg in enumerate(args):
                merged[f"arg_{i}"] = arg
        return merged

    def _inject_runtime_params(self, tool_kwargs: dict, config: Any) -> dict:
        """
        注入运行时参数到工具调用
        
        从两个来源提取运行时参数并注入到工具调用中：
        1. config.configurable 中的参数
        2. __pregel_runtime.context 中的参数
        
        这允许在调用工具时自动注入上下文相关的参数，
        如用户ID、会话ID等。
        
        Args:
            tool_kwargs: 原始工具参数字典
            config: 运行配置对象
            
        Returns:
            合并后的参数字典
        """
        print(f"[DEBUG] _inject_runtime_params called")
        print(f"[DEBUG] config: {config}")
        print(f"[DEBUG] config keys: {config.keys() if config else 'None'}")

        # 检查是否启用参数注入
        if self.tool_config is None or not self.tool_config.enable_injection:
            print("[DEBUG] injection disabled, returning tool_kwargs as-is")
            return tool_kwargs

        # 收集运行时参数
        runtime_params = {}
        # 从配置中获取可配置项
        configurable = config.get("configurable", {}) if config else {}
        print(f"[DEBUG] configurable: {configurable}")
        print(
            f"[DEBUG] configurable keys: {configurable.keys() if configurable else 'None'}"
        )

        # 从 configurable 中提取默认参数
        for key in self.tool_config.default_param_keys:
            if key in configurable:
                runtime_params[key] = configurable[key]
                print(
                    f"[DEBUG] extracted from configurable: {key} = {configurable[key]}"
                )

        # 获取运行时上下文
        runtime = configurable.get("__pregel_runtime")
        print(f"[DEBUG] __pregel_runtime: {runtime}")

        # 从运行时上下文中提取参数（优先级低于 configurable）
        if runtime and hasattr(runtime, "context"):
            context = runtime.context
            print(f"[DEBUG] runtime.context: {context}")
            for key in self.tool_config.default_param_keys:
                # 仅在 configurable 中不存在时使用 context
                if key in context and key not in runtime_params:
                    runtime_params[key] = context[key]
                    print(
                        f"[DEBUG] extracted from runtime.context: {key} = {context[key]}"
                    )
        else:
            print("[DEBUG] runtime is None or has no context")

        print(f"[DEBUG] runtime_params: {runtime_params}")
        # 合并参数：工具参数优先，运行时参数作为补充
        merged = {**tool_kwargs, **runtime_params}
        print(f"[DEBUG] merged tool_kwargs: {merged}")
        return merged

    async def _execute_tool(self, kwargs: dict, config: Any = None) -> Any:
        """
        执行 MCP 工具（异步）
        
        支持多种工具调用方式的优先级：
        1. _arun 方法（异步专用）
        2. invoke 方法（支持异步/同步）
        3. __call__ 方法（可调用对象）
        4. MCP 客户端远程调用
        
        Args:
            kwargs: 工具参数字典
            config: 运行配置对象
            
        Returns:
            工具执行结果
            
        Raises:
            NotImplementedError: 工具不支持异步执行
        """
        # 优先级1：检查 _arun 方法（异步执行）
        if hasattr(self.mcp_tool, "_arun"):
            arun_sig = inspect.signature(self.mcp_tool._arun)
            arun_params = arun_sig.parameters
            call_kwargs = dict(kwargs)
            # 如果方法签名包含 config 参数，则传递
            if "config" in arun_params:
                call_kwargs["config"] = config
            return await self.mcp_tool._arun(**call_kwargs)
        
        # 优先级2：检查 invoke 方法
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            invoke_sig = inspect.signature(invoke_method)
            
            # 判断是否为异步方法
            if inspect.iscoroutinefunction(invoke_method):
                # 异步 invoke 方法
                if "config" in invoke_sig.parameters:
                    return await invoke_method(kwargs, config=config)
                return await invoke_method(kwargs)
            else:
                # 同步 invoke 方法，需要在线程中执行
                if "config" in invoke_sig.parameters:
                    return await asyncio.to_thread(invoke_method, kwargs, config)
                return await asyncio.to_thread(invoke_method, kwargs)
        
        # 优先级3：检查是否可调用
        elif callable(self.mcp_tool):
            call_method = getattr(self.mcp_tool, "__call__", None)
            # 判断是否为异步可调用
            if call_method and (
                inspect.iscoroutinefunction(call_method)
                or inspect.iscoroutinefunction(self.mcp_tool)
            ):
                return await self.mcp_tool(**kwargs)
            else:
                return await asyncio.to_thread(self.mcp_tool, **kwargs)
        
        # 优先级4：通过 MCP 客户端远程调用
        else:
            if self.mcp_client and self.mcp_server_name:
                try:
                    # 使用 MCP 客户端远程调用工具
                    result = await self.mcp_client.call_tool(
                        self.mcp_server_name, self.name, kwargs
                    )
                    # 返回内容属性（如果有）
                    if hasattr(result, "content"):
                        return result.content
                    return result
                except Exception as e:
                    logger.error(
                        "Failed to call MCP tool '%s' on server '%s': %s",
                        self.name,
                        self.mcp_server_name,
                        e,
                    )
                    raise

            # 没有任何可用的执行方法
            logger.error(
                "MCP tool '%s' has no supported execution method. Type: %s",
                self.name,
                type(self.mcp_tool).__name__,
            )
            raise NotImplementedError(
                f"MCP tool {self.name} does not support async execution"
            )

    async def _arun(self, *args, config: RunnableConfig = None, **kwargs) -> Any:
        """
        异步执行工具
        
        LangChain BaseTool 的标准异步执行入口。
        负责参数合并、运行时注入、事件记录和结果处理。
        
        事件流程：
        1. 记录开始事件
        2. 执行工具
        3. 记录成功/失败事件
        4. 返回结果
        
        Args:
            *args: 位置参数
            config: 运行配置对象
            **kwargs: 关键字参数
            
        Returns:
            工具执行结果
        """
        print(f"[DEBUG _arun] config={config}, kwargs={kwargs}")
        print(f"[DEBUG _arun] args={args}")

        # 提取工具调用ID和流写入器
        tool_call_id = self._get_tool_call_id(config)
        writer = self._get_writer()
        # 记录开始时间用于计算执行时长
        start_time = datetime.now()

        # 合并参数并注入运行时参数
        tool_kwargs = self._merge_args_kwargs(args, kwargs)
        tool_kwargs = self._inject_runtime_params(tool_kwargs, config)

        logger.debug(
            "MCPToolAdapter._arun: tool=%s, args=%s, kwargs=%s, merged=%s",
            self.name,
            args,
            kwargs,
            tool_kwargs,
        )

        # 发布工具开始事件
        if writer:
            start_event = create_tool_event(
                event_type="tool_start",
                tool=self.name,
                tool_call_id=tool_call_id,
                data={"args": tool_kwargs, "description": f"开始执行工具: {self.name}"},
            )
            writer(dict(start_event))

        try:
            result = await self._execute_tool(tool_kwargs, config=config)

            if self.tool_config and self.tool_config.unwrap_result:
                if isinstance(result, str):
                    parsed_result = json.loads(result)
                else:
                    parsed_result = result
                event_result = parsed_result.get("content", parsed_result)
                return_result = parsed_result.get("result", parsed_result)
            else:
                event_result = result
                return_result = result

            if writer:
                stop_event = create_tool_event(
                    event_type="tool_stop",
                    tool=self.name,
                    tool_call_id=tool_call_id,
                    data={
                        "status": "success",
                        "result": event_result,
                        "duration_ms": int(
                            (datetime.now() - start_time).total_seconds() * 1000
                        ),
                    },
                )
                writer(dict(stop_event))

            return return_result

        except Exception as e:
            # 捕获异常，记录错误并发布错误事件
            error_msg = f"工具调用失败: {self.name}, 错误: {str(e)}"
            logger.error(error_msg)

            if writer:
                error_event = create_tool_event(
                    event_type="tool_error",
                    tool=self.name,
                    tool_call_id=tool_call_id,
                    data={
                        "status": "error",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "result": None,
                        "duration_ms": int(
                            (datetime.now() - start_time).total_seconds() * 1000
                        ),
                    },
                )
                writer(dict(error_event))

            # 根据响应格式返回不同类型的结果
            if self.response_format == "content_and_artifact":
                return (error_msg, None)
            return error_msg

    def _run(self, *args, config: RunnableConfig = None, **kwargs) -> Any:
        """
        同步执行工具
        
        LangChain BaseTool 的标准同步执行入口。
        如果底层工具只支持异步执行，会抛出 RuntimeError。
        
        支持的执行方式：
        1. _run 方法（同步执行）
        2. invoke 方法（同步）
        3. __call__ 方法（可调用对象）
        4. MCP 客户端远程调用（在事件循环中）
        
        Args:
            *args: 位置参数
            config: 运行配置对象
            **kwargs: 关键字参数
            
        Returns:
            工具执行结果
            
        Raises:
            RuntimeError: 工具只支持异步执行
            NotImplementedError: 工具不支持同步执行
        """
        # 合并参数并注入运行时参数
        tool_kwargs = self._merge_args_kwargs(args, kwargs)
        tool_kwargs = self._inject_runtime_params(tool_kwargs, kwargs.get("config"))

        # 优先级1：检查 _run 方法（同步执行）
        if hasattr(self.mcp_tool, "_run"):
            run_sig = inspect.signature(self.mcp_tool._run)
            call_kwargs = dict(tool_kwargs)
            # 如果方法签名包含 config 参数，则传递
            if "config" in run_sig.parameters:
                call_kwargs["config"] = kwargs.get("config")
            return self.mcp_tool._run(**call_kwargs)
        
        # 优先级2：检查 invoke 方法
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            # 如果是异步方法，抛出错误
            if inspect.iscoroutinefunction(invoke_method):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            invoke_sig = inspect.signature(invoke_method)
            if "config" in invoke_sig.parameters:
                return invoke_method(tool_kwargs, config=kwargs.get("config"))
            return invoke_method(tool_kwargs)
        
        # 优先级3：检查是否可调用
        elif callable(self.mcp_tool):
            call_method = getattr(self.mcp_tool, "__call__", None)
            # 如果是异步可调用，抛出错误
            if call_method and (
                inspect.iscoroutinefunction(call_method)
                or inspect.iscoroutinefunction(self.mcp_tool)
            ):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            return self.mcp_tool(**tool_kwargs)
        
        # 优先级4：通过 MCP 客户端远程调用
        elif self.mcp_client and self.mcp_server_name:
            try:
                # 获取事件循环
                loop = asyncio.get_event_loop()
                # 检查事件循环是否正在运行
                if loop.is_running():
                    raise RuntimeError(
                        f"MCP tool {self.name} requires async execution in async context"
                    )
                # 在事件循环中执行异步调用
                result = loop.run_until_complete(
                    self.mcp_client.call_tool(
                        self.mcp_server_name, self.name, tool_kwargs
                    )
                )
                # 返回内容属性（如果有）
                if hasattr(result, "content"):
                    return result.content
                return result
            except Exception as e:
                logger.error(
                    "Failed to call MCP tool '%s' on server '%s': %s",
                    self.name,
                    self.mcp_server_name,
                    e,
                )
                raise
        
        # 没有任何可用的执行方法
        else:
            raise NotImplementedError(
                f"MCP tool {self.name} does not support sync execution"
            )


def adapt_mcp_tool(
    mcp_tool: Any,
    mcp_server_name: str = "",
    mcp_client: Any = None,
    tool_config: MCPToolConfig | None = None,
) -> BaseTool:
    """
    将单个 MCP 工具适配为 LangChain BaseTool
    
    提取工具名称并创建适配器实例。
    适配失败时会记录警告并重新抛出异常。
    
    Args:
        mcp_tool: 原始 MCP 工具对象
        mcp_server_name: MCP 服务器名称
        mcp_client: MCP 客户端实例
        tool_config: 工具配置对象
        
    Returns:
        适配后的 LangChain BaseTool
        
    Raises:
        适配过程中的异常
    """
    try:
        # 提取工具名称，优先使用 name 属性
        tool_name = getattr(mcp_tool, "name", None) or str(mcp_tool)
        return MCPToolToLangChainAdapter(
            mcp_tool=mcp_tool,
            mcp_server_name=mcp_server_name,
            mcp_client=mcp_client,
            tool_config=tool_config,
            name=tool_name,
        )
    except Exception as e:
        logger.warning(
            f"Failed to adapt MCP tool {getattr(mcp_tool, 'name', 'unknown')}: {e}"
        )
        raise


def adapt_mcp_tools(
    mcp_tools: List[Any],
    mcp_server_name: str = "",
    mcp_client: Any = None,
    tool_config: MCPToolConfig | None = None,
) -> List[BaseTool]:
    """
    批量将 MCP 工具适配为 LangChain BaseTool
    
    遍历工具列表，逐个适配并收集成功结果。
    适配失败的工具会被记录，但不会阻止其他工具的适配。
    
    Args:
        mcp_tools: MCP 工具列表
        mcp_server_name: MCP 服务器名称
        mcp_client: MCP 客户端实例
        tool_config: 工具配置对象
        
    Returns:
        适配后的 BaseTool 列表
    """
    # 存储成功适配的工具
    adapted_tools = []
    # 统计失败数量
    failed_count = 0

    # 遍历每个工具进行适配
    for mcp_tool in mcp_tools:
        try:
            adapted_tool = adapt_mcp_tool(
                mcp_tool,
                mcp_server_name=mcp_server_name,
                mcp_client=mcp_client,
                tool_config=tool_config,
            )
            adapted_tools.append(adapted_tool)
        except Exception as e:
            # 适配失败，计数器加一并记录警告
            failed_count += 1
            logger.warning(f"Failed to adapt MCP tool: {e}")

    # 有失败时记录汇总信息
    if failed_count > 0:
        logger.warning(f"Adapted {len(adapted_tools)} tools, {failed_count} failed")

    return adapted_tools


def is_mcp_tool(obj: Any) -> bool:
    """
    检查对象是否为 MCP 工具
    
    通过检查是否同时具有 inputSchema 和 name 属性来判断。
    
    Args:
        obj: 待检查的对象
        
    Returns:
        是 MCP 工具返回 True，否则返回 False
    """
    return hasattr(obj, "inputSchema") and hasattr(obj, "name")
