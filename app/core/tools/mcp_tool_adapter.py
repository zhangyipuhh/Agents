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
from pydantic import BaseModel, create_model

from langchain_core.tools import BaseTool

from app.core.tools.events import create_tool_event

logger = logging.getLogger(__name__)


def json_schema_to_pydantic_model(
    schema: dict[str, Any], model_name: str = "ToolArgs"
) -> Type[BaseModel]:
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    field_definitions = {}
    for field_name, field_schema in properties.items():
        field_type = field_schema.get("type", "string")

        if field_type == "string":
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
            default = ... if field_name in required else dict
            field_definitions[field_name] = (dict, default)
        else:
            default = ... if field_name in required else None
            field_definitions[field_name] = (str, default)

    if not field_definitions:
        return create_model(model_name)

    return create_model(model_name, **field_definitions)


class MCPToolToLangChainAdapter(BaseTool):
    name: str = ""
    description: str = ""

    mcp_tool: Any = None
    mcp_server_name: str = ""
    mcp_client: Any = None

    def __init__(
        self, mcp_tool: Any, mcp_server_name: str = "", mcp_client: Any = None, **kwargs
    ):
        super().__init__(**kwargs)

        self.mcp_tool = mcp_tool
        self.mcp_server_name = mcp_server_name
        self.mcp_client = mcp_client

        tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        tool_description = getattr(mcp_tool, "description", "")

        self.name = tool_name
        self.description = tool_description

        input_schema = getattr(mcp_tool, "inputSchema", {})
        if input_schema:
            self.args_schema = json_schema_to_pydantic_model(
                input_schema, f"{tool_name}Args"
            )
        else:
            self.args_schema = create_model(f"{tool_name}Args")

    def _get_tool_call_id(self, config) -> str:
        if config and "configurable" in config:
            return config["configurable"].get("tool_call_id", "unknown")
        return "unknown"

    def _get_writer(self):
        try:
            return get_stream_writer()
        except (ImportError, RuntimeError):
            return None

    async def _execute_tool(self, kwargs: dict, config: Any = None) -> Any:
        if hasattr(self.mcp_tool, "_arun"):
            return await self.mcp_tool._arun(**kwargs, config=config)
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            if inspect.iscoroutinefunction(invoke_method):
                return await invoke_method(kwargs)
            else:
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

        if writer:
            start_event = create_tool_event(
                event_type="tool_start",
                tool=self.name,
                tool_call_id=tool_call_id,
                data={"args": kwargs, "description": f"开始执行工具: {self.name}"}
            )
            writer(dict(start_event))

        try:
            result = await self._execute_tool(kwargs, config=config)

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

            if writer:
                error_event = create_tool_event(
                    event_type="tool_error",
                    tool=self.name,
                    tool_call_id=tool_call_id,
                    data={"error_type": type(e).__name__, "error_message": str(e), "args": kwargs}
                )
                writer(dict(error_event))

            raise

    def _run(self, *args, **kwargs) -> Any:
        if hasattr(self.mcp_tool, "_run"):
            return self.mcp_tool._run(*args, **kwargs)
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            if inspect.iscoroutinefunction(invoke_method):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            return invoke_method(kwargs)
        elif callable(self.mcp_tool):
            call_method = getattr(self.mcp_tool, "__call__", None)
            if call_method and (
                inspect.iscoroutinefunction(call_method)
                or inspect.iscoroutinefunction(self.mcp_tool)
            ):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            return self.mcp_tool(**kwargs)
        elif self.mcp_client and self.mcp_server_name:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    raise RuntimeError(
                        f"MCP tool {self.name} requires async execution in async context"
                    )
                result = loop.run_until_complete(
                    self.mcp_client.call_tool(self.mcp_server_name, self.name, kwargs)
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
