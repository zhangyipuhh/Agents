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
from datetime import datetime
from typing import Any, List, Optional, Type

from langgraph.config import get_stream_writer
from pydantic import BaseModel, ConfigDict, create_model

from langchain_core.tools import BaseTool

from app.core.tools.events import create_tool_event

try:
    import anyio
    ANYIO_AVAILABLE = True
except ImportError:
    ANYIO_AVAILABLE = False

logger = logging.getLogger(__name__)


def json_schema_to_pydantic_model(
    schema: dict[str, Any], model_name: str = "ToolArgs"
) -> Type[BaseModel]:
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    field_definitions = {}
    for field_name, field_schema in properties.items():
        field_type = field_schema.get("type")

        if field_type == "string":
            if "enum" in field_schema:
                from enum import Enum
                enum_values = {v: v for v in field_schema["enum"]}
                enum_cls = Enum(f"{model_name}_{field_name}_enum", enum_values)
                default = ... if field_name in required else None
                field_definitions[field_name] = (enum_cls, default)
            else:
                default = ... if field_name in required else None
                field_definitions[field_name] = (str, default)
        elif field_type == "number" or field_type == "integer":
            default = ... if field_name in required else None
            field_definitions[field_name] = (
                (float, default) if field_type == "number" else (int, default)
            )
        elif field_type == "boolean":
            default = ... if field_name in required else False
            field_definitions[field_name] = (bool, default)
        elif field_type == "array":
            default = ... if field_name in required else list
            field_definitions[field_name] = (list, default)
        elif field_type == "object":
            if "properties" in field_schema:
                nested_model = json_schema_to_pydantic_model(
                    field_schema, f"{model_name}_{field_name}"
                )
                default = ... if field_name in required else None
                field_definitions[field_name] = (nested_model, default)
            else:
                default = ... if field_name in required else dict
                field_definitions[field_name] = (dict, default)
        elif field_type is None and ("anyOf" in field_schema or "oneOf" in field_schema):
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
            default = ... if field_name in required else None
            field_definitions[field_name] = (union_type, default)
        else:
            default = ... if field_name in required else None
            field_definitions[field_name] = (str, default)

    model = create_model(
        model_name,
        __config__=ConfigDict(extra="allow"),
        **field_definitions,
    )

    return model


class MCPToolToLangChainAdapter(BaseTool):
    name: str = ""
    description: str = ""

    mcp_tool: Any = None
    mcp_server_name: str = ""
    mcp_client: Any = None

    def __init__(
        self, mcp_tool: Any, mcp_server_name: str = "", mcp_client: Any = None, **kwargs
    ):
        if isinstance(mcp_tool, BaseTool):
            if getattr(mcp_tool, "response_format", None) and "response_format" not in kwargs:
                kwargs["response_format"] = mcp_tool.response_format

        super().__init__(**kwargs)

        self.mcp_tool = mcp_tool
        self.mcp_server_name = mcp_server_name
        self.mcp_client = mcp_client

        tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        tool_description = getattr(mcp_tool, "description", "")

        self.name = tool_name
        self.description = tool_description

        if isinstance(mcp_tool, BaseTool) and getattr(mcp_tool, "args_schema", None) is not None:
            self.args_schema = mcp_tool.args_schema
        else:
            input_schema = getattr(mcp_tool, "inputSchema", {})
            if input_schema and isinstance(input_schema, dict) and input_schema.get("properties"):
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

    async def _arun(self, *args, config=None, **kwargs) -> Any:
        tool_call_id = self._get_tool_call_id(config)
        writer = self._get_writer()
        start_time = datetime.now()

        tool_kwargs = self._merge_args_kwargs(args, kwargs)

        logger.debug(
            "MCPToolAdapter._arun: tool=%s, args=%s, kwargs=%s, merged=%s",
            self.name, args, kwargs, tool_kwargs,
        )

        if writer:
            start_event = create_tool_event(
                event_type="tool_start",
                tool=self.name,
                tool_call_id=tool_call_id,
                data={"args": tool_kwargs, "description": f"开始执行工具: {self.name}"}
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
                        "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000)
                    }
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
                        "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000)
                    }
                )
                writer(dict(error_event))

            if self.response_format == "content_and_artifact":
                return (error_msg, None)
            return error_msg

    def _run(self, *args, **kwargs) -> Any:
        tool_kwargs = self._merge_args_kwargs(args, kwargs)

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
                    self.mcp_client.call_tool(self.mcp_server_name, self.name, tool_kwargs)
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
    mcp_tool: Any, mcp_server_name: str = "", mcp_client: Any = None
) -> BaseTool:
    try:
        tool_name = getattr(mcp_tool, "name", None) or str(mcp_tool)
        return MCPToolToLangChainAdapter(
            mcp_tool=mcp_tool,
            mcp_server_name=mcp_server_name,
            mcp_client=mcp_client,
            name=tool_name,
        )
    except Exception as e:
        logger.warning(
            f"Failed to adapt MCP tool {getattr(mcp_tool, 'name', 'unknown')}: {e}"
        )
        raise


def adapt_mcp_tools(
    mcp_tools: List[Any], mcp_server_name: str = "", mcp_client: Any = None
) -> List[BaseTool]:
    adapted_tools = []
    failed_count = 0

    for mcp_tool in mcp_tools:
        try:
            adapted_tool = adapt_mcp_tool(
                mcp_tool, mcp_server_name=mcp_server_name, mcp_client=mcp_client
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
