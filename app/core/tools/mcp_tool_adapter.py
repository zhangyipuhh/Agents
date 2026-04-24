#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP 工具转换器模块

提供将 MCP Tool 对象转换为 LangChain BaseTool 的功能，
解决 MCP Python SDK v1.27.0 的 Tool 对象与 LangChain bind_tools() 不兼容的问题。

Date: 2026-04-20
Author: AI Assistant
"""

import asyncio
import inspect
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

    Args:
        ref: $ref 字符串，格式如 "#/$defs/Feature"
        defs: $defs 定义的字典（已扁平化，不包含 $defs 键）

    Returns:
        解析后的 schema 字典
    """
    if not ref.startswith("#/"):
        raise ValueError(f"Only local references are supported, got: {ref}")

    path_parts = ref[2:].split("/")
    current = defs

    for part in path_parts:
        if part == "$defs":
            continue
        if part not in current:
            raise KeyError(f"Reference '{ref}' not found in defs")
        current = current[part]

    return copy.deepcopy(current)


def _collect_defs(schema: dict[str, Any], defs: dict = None) -> dict:
    """
    递归收集 JSON Schema 中所有的 $defs 定义

    Args:
        schema: JSON Schema 字典
        defs: 已收集的 $defs 定义（用于递归）

    Returns:
        收集到的所有 $defs 定义
    """
    if defs is None:
        defs = {}
    
    if not isinstance(schema, dict):
        return defs
    
    if "$defs" in schema:
        defs.update(copy.deepcopy(schema["$defs"]))
    
    for key, value in schema.items():
        if key == "$defs":
            continue
        elif isinstance(value, dict):
            _collect_defs(value, defs)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _collect_defs(item, defs)
    
    return defs


def _normalize_schema(schema: dict[str, Any], all_defs: dict = None) -> dict[str, Any]:
    """
    规范化 JSON Schema，解析所有 $ref 引用

    这个函数递归处理 schema，首先收集所有的 $defs 定义，
    然后解析所有 $ref 引用。

    Args:
        schema: 原始 JSON Schema
        all_defs: 所有 $defs 定义（用于递归）

    Returns:
        规范化后的 JSON Schema
    """
    if not isinstance(schema, dict):
        return schema

    if all_defs is None:
        all_defs = _collect_defs(schema)

    result = {}

    for key, value in schema.items():
        if key == "$defs":
            continue
        elif key == "$ref":
            if isinstance(value, str):
                try:
                    resolved = _resolve_ref(value, all_defs)
                    resolved = _normalize_schema(resolved, all_defs)
                    result.update(resolved)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to resolve $ref '{value}': {e}")
                    result[key] = value
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = _normalize_schema(value, all_defs)
        elif isinstance(value, list):
            result[key] = [
                _normalize_schema(item, all_defs) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


class _NormalizedSchemaModel(BaseModel):
    """
    自定义 Pydantic 模型基类，存储已经解析好 $ref 引用的 schema
    
    当 LangChain 的 bind_tools() 调用 model_json_schema() 时，
    返回已经解析好的 schema，避免 $ref 引用解析错误。
    """
    _normalized_schema: ClassVar[dict] = {}
    
    @classmethod
    def model_json_schema(cls, **kwargs) -> dict:
        if cls._normalized_schema:
            return cls._normalized_schema
        return super().model_json_schema(**kwargs)


def json_schema_to_pydantic_model(
    schema: dict[str, Any], model_name: str = "ToolArgs"
) -> Type[BaseModel]:
    """
    将 JSON Schema 转换为 Pydantic 模型

    支持 $ref 和 $defs 引用解析。

    Args:
        schema: JSON Schema 字典
        model_name: 生成的模型名称

    Returns:
        Pydantic 模型类
    """
    normalized_schema = _normalize_schema(schema)
    properties = normalized_schema.get("properties", {})
    required = normalized_schema.get("required", [])

    # 与 Pydantic 类型注解可能冲突的字段名
    CONFLICTING_FIELD_NAMES = {"type", "default", "title", "description", "examples"}

    field_definitions = {}
    for field_name, field_schema in properties.items():
        json_type = field_schema.get("type")

        # 检查字段名称是否与类型注解冲突
        needs_alias = field_name in CONFLICTING_FIELD_NAMES
        # 使用安全的内部字段名
        internal_name = f"{field_name}_" if needs_alias else field_name

        def make_field(py_type, is_required, alias=None):
            if is_required:
                if alias:
                    return (py_type, Field(alias=alias))
                return (py_type, ...)
            else:
                if alias:
                    return (Optional[py_type], Field(default=None, alias=alias))
                return (Optional[py_type], None)

        is_required = field_name in required

        if json_type == "string":
            if "enum" in field_schema:
                from enum import Enum

                enum_values = {v: v for v in field_schema["enum"]}
                enum_cls = Enum(f"{model_name}_{field_name}_enum", enum_values)
                field_definitions[internal_name] = make_field(
                    enum_cls, is_required, field_name if needs_alias else None
                )
            else:
                field_definitions[internal_name] = make_field(
                    str, is_required, field_name if needs_alias else None
                )
        elif json_type == "number" or json_type == "integer":
            py_type = float if json_type == "number" else int
            field_definitions[internal_name] = make_field(
                py_type, is_required, field_name if needs_alias else None
            )
        elif json_type == "boolean":
            if is_required:
                field_definitions[internal_name] = (
                    bool, Field(alias=field_name) if needs_alias else ...
                )
            else:
                field_definitions[internal_name] = (
                    bool, Field(default=False, alias=field_name) if needs_alias else False
                )
        elif json_type == "array":
            field_definitions[internal_name] = make_field(
                list, is_required, field_name if needs_alias else None
            )
        elif json_type == "object":
            if "properties" in field_schema:
                nested_model = json_schema_to_pydantic_model(
                    field_schema, f"{model_name}_{field_name}"
                )
                field_definitions[internal_name] = make_field(
                    nested_model, is_required, field_name if needs_alias else None
                )
            else:
                field_definitions[internal_name] = make_field(
                    dict, is_required, field_name if needs_alias else None
                )
        elif json_type is None and (
            "anyOf" in field_schema or "oneOf" in field_schema
        ):
            sub_schemas = field_schema.get("anyOf") or field_schema.get("oneOf")
            types = []
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
                    types.append(str)
            from typing import Union

            union_type = Union[tuple(types)] if len(types) > 1 else types[0]
            field_definitions[internal_name] = make_field(
                union_type, is_required, field_name if needs_alias else None
            )
        else:
            field_definitions[internal_name] = make_field(
                str, is_required, field_name if needs_alias else None
            )

    model = create_model(
        model_name,
        __base__=_NormalizedSchemaModel,
        __config__=ConfigDict(extra="allow", populate_by_name=True),
        **field_definitions,
    )
    model._normalized_schema = normalized_schema

    return model


class MCPToolConfig:
    def __init__(
        self, enable_injection: bool = True, default_param_keys: list[str] | None = None
    ):
        self.enable_injection = enable_injection
        self.default_param_keys = default_param_keys or []


class MCPToolToLangChainAdapter(BaseTool):
    name: str = ""
    description: str = ""

    mcp_tool: Any = None
    mcp_server_name: str = ""
    mcp_client: Any = None
    tool_config: Any = None

    def __init__(
        self,
        mcp_tool: Any,
        mcp_server_name: str = "",
        mcp_client: Any = None,
        tool_config: MCPToolConfig | None = None,
        **kwargs,
    ):
        if isinstance(mcp_tool, BaseTool):
            if (
                getattr(mcp_tool, "response_format", None)
                and "response_format" not in kwargs
            ):
                kwargs["response_format"] = mcp_tool.response_format

        super().__init__(**kwargs)

        self.mcp_tool = mcp_tool
        self.mcp_server_name = mcp_server_name
        self.mcp_client = mcp_client
        self.tool_config = tool_config

        tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        tool_description = getattr(mcp_tool, "description", "")

        self.name = tool_name
        self.description = tool_description

        if (
            isinstance(mcp_tool, BaseTool)
            and getattr(mcp_tool, "args_schema", None) is not None
        ):
            original_schema = mcp_tool.args_schema
            if isinstance(original_schema, type) and issubclass(original_schema, BaseModel):
                self.args_schema = original_schema
            elif isinstance(original_schema, dict):
                self.args_schema = json_schema_to_pydantic_model(
                    original_schema, f"{tool_name}Args"
                )
            else:
                logger.warning(
                    f"Unexpected args_schema type for tool '{tool_name}': {type(original_schema)}"
                )
                self.args_schema = None
        else:
            input_schema = getattr(mcp_tool, "inputSchema", {})
            if (
                input_schema
                and isinstance(input_schema, dict)
                and input_schema.get("properties")
            ):
                self.args_schema = json_schema_to_pydantic_model(
                    input_schema, f"{tool_name}Args"
                )
            else:
                self.args_schema = None

    def _get_tool_call_id(self, config) -> str:
        if config and "configurable" in config:
            return config["configurable"].get("tool_call_id", "unknown")
        return "unknown"

    def _get_writer(self):
        try:
            return get_stream_writer()
        except (ImportError, RuntimeError):
            return None

    def _merge_args_kwargs(self, args: tuple, kwargs: dict) -> dict:
        merged = dict(kwargs)
        if not args:
            return merged
        if len(args) == 1 and isinstance(args[0], dict):
            merged.update(args[0])
        elif len(args) == 1 and isinstance(args[0], str):
            if self.args_schema and hasattr(self.args_schema, "model_fields"):
                fields = self.args_schema.model_fields
                if fields:
                    first_field = next(iter(fields))
                    merged[first_field] = args[0]
                else:
                    merged["input"] = args[0]
            else:
                merged["input"] = args[0]
        else:
            for i, arg in enumerate(args):
                merged[f"arg_{i}"] = arg
        return merged

    def _inject_runtime_params(self, tool_kwargs: dict, config: Any) -> dict:
        print(f"[DEBUG] _inject_runtime_params called")
        print(f"[DEBUG] config: {config}")
        print(f"[DEBUG] config keys: {config.keys() if config else 'None'}")

        if self.tool_config is None or not self.tool_config.enable_injection:
            print("[DEBUG] injection disabled, returning tool_kwargs as-is")
            return tool_kwargs

        runtime_params = {}
        configurable = config.get("configurable", {}) if config else {}
        print(f"[DEBUG] configurable: {configurable}")
        print(
            f"[DEBUG] configurable keys: {configurable.keys() if configurable else 'None'}"
        )

        for key in self.tool_config.default_param_keys:
            if key in configurable:
                runtime_params[key] = configurable[key]
                print(
                    f"[DEBUG] extracted from configurable: {key} = {configurable[key]}"
                )

        runtime = configurable.get("__pregel_runtime")
        print(f"[DEBUG] __pregel_runtime: {runtime}")

        if runtime and hasattr(runtime, "context"):
            context = runtime.context
            print(f"[DEBUG] runtime.context: {context}")
            for key in self.tool_config.default_param_keys:
                if key in context and key not in runtime_params:
                    runtime_params[key] = context[key]
                    print(
                        f"[DEBUG] extracted from runtime.context: {key} = {context[key]}"
                    )
        else:
            print("[DEBUG] runtime is None or has no context")

        print(f"[DEBUG] runtime_params: {runtime_params}")
        merged = {**tool_kwargs, **runtime_params}
        print(f"[DEBUG] merged tool_kwargs: {merged}")
        return merged

    async def _execute_tool(self, kwargs: dict, config: Any = None) -> Any:
        if hasattr(self.mcp_tool, "_arun"):
            arun_sig = inspect.signature(self.mcp_tool._arun)
            arun_params = arun_sig.parameters
            call_kwargs = dict(kwargs)
            if "config" in arun_params:
                call_kwargs["config"] = config
            return await self.mcp_tool._arun(**call_kwargs)
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            invoke_sig = inspect.signature(invoke_method)
            if inspect.iscoroutinefunction(invoke_method):
                if "config" in invoke_sig.parameters:
                    return await invoke_method(kwargs, config=config)
                return await invoke_method(kwargs)
            else:
                if "config" in invoke_sig.parameters:
                    return await asyncio.to_thread(invoke_method, kwargs, config)
                return await asyncio.to_thread(invoke_method, kwargs)
        elif callable(self.mcp_tool):
            call_method = getattr(self.mcp_tool, "__call__", None)
            if call_method and (
                inspect.iscoroutinefunction(call_method)
                or inspect.iscoroutinefunction(self.mcp_tool)
            ):
                return await self.mcp_tool(**kwargs)
            else:
                return await asyncio.to_thread(self.mcp_tool, **kwargs)
        else:
            if self.mcp_client and self.mcp_server_name:
                try:
                    result = await self.mcp_client.call_tool(
                        self.mcp_server_name, self.name, kwargs
                    )
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

            logger.error(
                "MCP tool '%s' has no supported execution method. Type: %s",
                self.name,
                type(self.mcp_tool).__name__,
            )
            raise NotImplementedError(
                f"MCP tool {self.name} does not support async execution"
            )

    async def _arun(self, *args, config: RunnableConfig = None, **kwargs) -> Any:
        print(f"[DEBUG _arun] config={config}, kwargs={kwargs}")
        print(f"[DEBUG _arun] args={args}")

        tool_call_id = self._get_tool_call_id(config)
        writer = self._get_writer()
        start_time = datetime.now()

        tool_kwargs = self._merge_args_kwargs(args, kwargs)
        tool_kwargs = self._inject_runtime_params(tool_kwargs, config)

        logger.debug(
            "MCPToolAdapter._arun: tool=%s, args=%s, kwargs=%s, merged=%s",
            self.name,
            args,
            kwargs,
            tool_kwargs,
        )

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

            if writer:
                stop_event = create_tool_event(
                    event_type="tool_stop",
                    tool=self.name,
                    tool_call_id=tool_call_id,
                    data={
                        "status": "success",
                        "result": result,
                        "duration_ms": int(
                            (datetime.now() - start_time).total_seconds() * 1000
                        ),
                    },
                )
                writer(dict(stop_event))

            return result

        except Exception as e:
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

            if self.response_format == "content_and_artifact":
                return (error_msg, None)
            return error_msg

    def _run(self, *args, config: RunnableConfig = None, **kwargs) -> Any:
        tool_kwargs = self._merge_args_kwargs(args, kwargs)
        tool_kwargs = self._inject_runtime_params(tool_kwargs, kwargs.get("config"))

        if hasattr(self.mcp_tool, "_run"):
            run_sig = inspect.signature(self.mcp_tool._run)
            call_kwargs = dict(tool_kwargs)
            if "config" in run_sig.parameters:
                call_kwargs["config"] = kwargs.get("config")
            return self.mcp_tool._run(**call_kwargs)
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            if inspect.iscoroutinefunction(invoke_method):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            invoke_sig = inspect.signature(invoke_method)
            if "config" in invoke_sig.parameters:
                return invoke_method(tool_kwargs, config=kwargs.get("config"))
            return invoke_method(tool_kwargs)
        elif callable(self.mcp_tool):
            call_method = getattr(self.mcp_tool, "__call__", None)
            if call_method and (
                inspect.iscoroutinefunction(call_method)
                or inspect.iscoroutinefunction(self.mcp_tool)
            ):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            return self.mcp_tool(**tool_kwargs)
        elif self.mcp_client and self.mcp_server_name:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    raise RuntimeError(
                        f"MCP tool {self.name} requires async execution in async context"
                    )
                result = loop.run_until_complete(
                    self.mcp_client.call_tool(
                        self.mcp_server_name, self.name, tool_kwargs
                    )
                )
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
    try:
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
    adapted_tools = []
    failed_count = 0

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
            failed_count += 1
            logger.warning(f"Failed to adapt MCP tool: {e}")

    if failed_count > 0:
        logger.warning(f"Adapted {len(adapted_tools)} tools, {failed_count} failed")

    return adapted_tools


def is_mcp_tool(obj: Any) -> bool:
    return hasattr(obj, "inputSchema") and hasattr(obj, "name")
