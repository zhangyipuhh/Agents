#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP 工具转换器模块

提供将 MCP Tool 对象转换为 LangChain BaseTool 的功能，
解决 MCP Python SDK v1.27.0 的 Tool 对象与 LangChain bind_tools() 不兼容的问题。

问题原因：
- MCP Python SDK v1.27.0 的 Tool 对象不是有效的装饰器函数
- LangChain 的 bind_tools() 要求工具必须是带 __name__ 属性的可调用对象
- 错误信息: "The first argument must be a string or a callable with a __name__ for tool decorator"

解决方案：
- 将 MCP Tool 对象转换为 langchain_core.tools 的 BaseTool 子类
- 保持工具的 name、description 和 inputSchema 信息

Date: 2026-04-20
Author: AI Assistant
"""

import asyncio
import inspect
import logging
from typing import Any, List, Optional, Type
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool

try:
    import anyio
    ANYIO_AVAILABLE = True
except ImportError:
    ANYIO_AVAILABLE = False

logger = logging.getLogger(__name__)


def json_schema_to_pydantic_model(
    schema: dict[str, Any],
    model_name: str = "ToolArgs"
) -> Type[BaseModel]:
    """
    将 JSON Schema 转换为 Pydantic 模型

    Args:
        schema: JSON Schema 字典
        model_name: 模型名称

    Returns:
        Type[BaseModel]: Pydantic 模型类
    """
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
            field_definitions[field_name] = (float, default) if field_type == "number" else (int, default)
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
    """
    MCP Tool 到 LangChain BaseTool 的适配器

    包装 MCP Tool 对象，转换为 LangChain 可用的 BaseTool 格式。
    支持同步和异步执行。
    """

    name: str = ""
    description: str = ""

    mcp_tool: Any = None
    mcp_server_name: str = ""
    mcp_pool: Any = None

    def __init__(
        self,
        mcp_tool: Any,
        mcp_server_name: str = "",
        mcp_pool: Any = None,
        **kwargs
    ):
        """
        初始化适配器

        Args:
            mcp_tool: MCP Tool 对象
            mcp_server_name: MCP 服务器名称
            mcp_pool: MCPClientPool 实例，用于调用工具
            **kwargs: 传递给 BaseTool 的其他参数
        """
        super().__init__(**kwargs)

        self.mcp_tool = mcp_tool
        self.mcp_server_name = mcp_server_name
        self.mcp_pool = mcp_pool

        tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        tool_description = getattr(mcp_tool, "description", "")

        self.name = tool_name
        self.description = tool_description

        input_schema = getattr(mcp_tool, "inputSchema", {})
        if input_schema:
            self.args_schema = json_schema_to_pydantic_model(input_schema, f"{tool_name}Args")
        else:
            self.args_schema = create_model(f"{tool_name}Args")

    async def _arun(
        self,
        *args,
        **kwargs
    ) -> Any:
        """
        异步执行 MCP 工具

        Args:
            *args: 位置参数
            **kwargs: 关键字参数（工具参数）

        Returns:
            Any: 工具执行结果
        """
        logger.debug(
            "Attempting to execute MCP tool '%s'. Attributes: _arun=%s, invoke=%s, callable=%s, type=%s",
            self.name,
            hasattr(self.mcp_tool, "_arun"),
            hasattr(self.mcp_tool, "invoke"),
            callable(self.mcp_tool),
            type(self.mcp_tool).__name__
        )
        
        if self.mcp_pool and self.mcp_server_name:
            server = self.mcp_pool._servers.get(self.mcp_server_name)
            if server and server.session is None:
                logger.info(
                    "MCP tool '%s': session is None, attempting to reconnect to '%s'",
                    self.name,
                    self.mcp_server_name
                )
                try:
                    config = server._config if hasattr(server, '_config') else {}
                    await self.mcp_pool.connect(self.mcp_server_name, config)
                    logger.info(
                        "MCP tool '%s': reconnected to '%s'",
                        self.name,
                        self.mcp_server_name
                    )
                except Exception as e:
                    logger.warning(
                        "MCP tool '%s': failed to reconnect to '%s': %s",
                        self.name,
                        self.mcp_server_name,
                        e
                    )
        
        if hasattr(self.mcp_tool, "_arun"):
            return await self.mcp_tool._arun(*args, **kwargs)
        elif hasattr(self.mcp_tool, "invoke"):
            invoke_method = self.mcp_tool.invoke
            if inspect.iscoroutinefunction(invoke_method):
                return await invoke_method(kwargs)
            else:
                return await asyncio.to_thread(invoke_method, kwargs)
        elif callable(self.mcp_tool):
            call_method = getattr(self.mcp_tool, "__call__", None)
            if call_method and (inspect.iscoroutinefunction(call_method) or inspect.iscoroutinefunction(self.mcp_tool)):
                return await self.mcp_tool(**kwargs)
            else:
                return await asyncio.to_thread(self.mcp_tool, **kwargs)
        else:
            if self.mcp_pool and self.mcp_server_name:
                max_retries = 2
                last_error = None
                
                for attempt in range(max_retries):
                    try:
                        result = await self.mcp_pool.call_tool(self.mcp_server_name, self.name, kwargs)
                        if hasattr(result, 'content'):
                            return result.content
                        return result
                    except Exception as e:
                        error_str = str(e).lower()
                        error_type = type(e).__name__
                        
                        should_retry = (
                            "not connected" in error_str or 
                            "closed" in error_str or
                            error_type == "ClosedResourceError" or
                            error_type == "McpError" or
                            isinstance(e, (RuntimeError, ConnectionError, OSError))
                        )
                        
                        if should_retry:
                            logger.warning(
                                "MCP tool '%s' connection issue (attempt %d/%d), retrying: %s - %s",
                                self.name,
                                attempt + 1,
                                max_retries,
                                error_type,
                                e
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(0.5)
                                continue
                        last_error = e
                        break
                    except Exception as e:
                        logger.error(
                            "Failed to call MCP tool '%s' on server '%s': %s",
                            self.name,
                            self.mcp_server_name,
                            e
                        )
                        raise
                
                if last_error:
                    logger.error(
                        "MCP tool '%s' failed after %d attempts: %s",
                        self.name,
                        max_retries,
                        last_error
                    )
                    raise last_error

            logger.error(
                "MCP tool '%s' has no supported execution method. Type: %s, Dir: %s",
                self.name,
                type(self.mcp_tool).__name__,
                dir(self.mcp_tool)
            )
            raise NotImplementedError(f"MCP tool {self.name} does not support async execution")

    def _run(
        self,
        *args,
        **kwargs
    ) -> Any:
        """
        同步执行 MCP 工具

        Args:
            *args: 位置参数
            **kwargs: 关键字参数（工具参数）

        Returns:
            Any: 工具执行结果
        """
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
            if call_method and (inspect.iscoroutinefunction(call_method) or inspect.iscoroutinefunction(self.mcp_tool)):
                raise RuntimeError(
                    f"MCP tool {self.name} only supports async execution but _run was called"
                )
            return self.mcp_tool(**kwargs)
        elif self.mcp_pool and self.mcp_server_name:
            try:
                from mcpClient.core.mcp_client.client_pool import _run_on_mcp_loop
                result = _run_on_mcp_loop(
                    self.mcp_pool.call_tool(self.mcp_server_name, self.name, kwargs)
                )
                if hasattr(result, 'content'):
                    return result.content
                return result
            except Exception as e:
                logger.error(
                    "Failed to call MCP tool '%s' on server '%s': %s",
                    self.name,
                    self.mcp_server_name,
                    e
                )
                raise
        else:
            raise NotImplementedError(f"MCP tool {self.name} does not support sync execution")


def adapt_mcp_tool(
    mcp_tool: Any,
    mcp_server_name: str = "",
    mcp_pool: Any = None
) -> BaseTool:
    """
    将单个 MCP Tool 对象转换为 LangChain BaseTool

    Args:
        mcp_tool: MCP Tool 对象
        mcp_server_name: MCP 服务器名称
        mcp_pool: MCPClientPool 实例，用于调用工具

    Returns:
        BaseTool: LangChain BaseTool 对象
    """
    try:
        tool_name = getattr(mcp_tool, "name", None) or str(mcp_tool)
        return MCPToolToLangChainAdapter(
            mcp_tool=mcp_tool,
            mcp_server_name=mcp_server_name,
            mcp_pool=mcp_pool,
            name=tool_name
        )
    except Exception as e:
        logger.warning(f"Failed to adapt MCP tool {getattr(mcp_tool, 'name', 'unknown')}: {e}")
        raise


def adapt_mcp_tools(
    mcp_tools: List[Any],
    mcp_server_name: str = "",
    mcp_pool: Any = None
) -> List[BaseTool]:
    """
    将 MCP Tool 对象列表转换为 LangChain BaseTool 列表

    Args:
        mcp_tools: MCP Tool 对象列表
        mcp_server_name: MCP 服务器名称
        mcp_pool: MCPClientPool 实例，用于调用工具

    Returns:
        List[BaseTool]: LangChain BaseTool 列表
    """
    adapted_tools = []
    failed_count = 0

    for mcp_tool in mcp_tools:
        try:
            adapted_tool = adapt_mcp_tool(
                mcp_tool,
                mcp_server_name=mcp_server_name,
                mcp_pool=mcp_pool
            )
            adapted_tools.append(adapted_tool)
        except Exception as e:
            failed_count += 1
            logger.warning(f"Failed to adapt MCP tool: {e}")

    if failed_count > 0:
        logger.warning(f"Adapted {len(adapted_tools)} tools, {failed_count} failed")

    return adapted_tools


def is_mcp_tool(obj: Any) -> bool:
    """
    检查对象是否是 MCP Tool 对象

    Args:
        obj: 任意对象

    Returns:
        bool: 是否是 MCP Tool 对象
    """
    return hasattr(obj, "inputSchema") and hasattr(obj, "name")
