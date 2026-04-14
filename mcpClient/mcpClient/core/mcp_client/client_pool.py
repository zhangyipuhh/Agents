#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP Client 连接池模块

管理 MCP 服务器连接的生命周期，支持 stdio 和 HTTP 两种传输方式。
借鉴 hermes-agent tools/mcp_tool.py 实现。

Date: 2026-04-14
"""

import asyncio
import inspect
import json
import logging
import math
import os
import threading
from typing import Any, Awaitable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP SDK 导入
# ---------------------------------------------------------------------------

_MCP_AVAILABLE = False
_MCP_HTTP_AVAILABLE = False
_MCP_SSE_AVAILABLE = False
_MCP_SAMPLING_TYPES = False
_MCP_NOTIFICATION_TYPES = False
_MCP_MESSAGE_HANDLER_SUPPORTED = False

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    _MCP_AVAILABLE = True
    try:
        from mcp.client.streamable_http import streamablehttp_client

        _MCP_HTTP_AVAILABLE = True
    except ImportError:
        _MCP_HTTP_AVAILABLE = False
    try:
        from mcp.client.sse import sse_client

        _MCP_SSE_AVAILABLE = True
    except ImportError:
        _MCP_SSE_AVAILABLE = False
    try:
        from mcp.client.streamable_http import streamable_http_client

        _MCP_NEW_HTTP = True
    except ImportError:
        _MCP_NEW_HTTP = False
    try:
        from mcp.types import (
            CreateMessageResult,
            CreateMessageResultWithTools,
            ErrorData,
            SamplingCapability,
            SamplingToolsCapability,
            TextContent,
            ToolUseContent,
        )

        _MCP_SAMPLING_TYPES = True
    except ImportError:
        logger.debug("MCP sampling types not available -- sampling disabled")
    try:
        from mcp.types import (
            ServerNotification,
            ToolListChangedNotification,
            PromptListChangedNotification,
            ResourceListChangedNotification,
        )

        _MCP_NOTIFICATION_TYPES = True
    except ImportError:
        logger.debug("MCP notification types not available -- dynamic tool discovery disabled")
except ImportError:
    logger.debug("mcp package not installed -- MCP tool support disabled")


def _check_message_handler_support() -> bool:
    """
    检查 ClientSession 是否支持 message_handler 参数

    Args:
        无

    Returns:
        True if message_handler is supported, False otherwise
    """
    if not _MCP_AVAILABLE:
        return False
    try:
        return "message_handler" in inspect.signature(ClientSession).parameters
    except (TypeError, ValueError):
        return False


_MCP_MESSAGE_HANDLER_SUPPORTED = _check_message_handler_support()
if _MCP_AVAILABLE and not _MCP_MESSAGE_HANDLER_SUPPORTED:
    logger.debug("MCP SDK does not support message_handler -- dynamic tool discovery disabled")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_DEFAULT_TOOL_TIMEOUT = 120.0
_DEFAULT_CONNECT_TIMEOUT = 60.0
_MAX_RECONNECT_RETRIES = 5
_MAX_INITIAL_CONNECT_RETRIES = 3
_MAX_BACKOFF_SECONDS = 60.0

# ---------------------------------------------------------------------------
# 错误格式化
# ---------------------------------------------------------------------------


def _format_connect_error(exc: BaseException) -> str:
    """
    格式化连接错误为可读消息

    Args:
        exc: 原始异常

    Returns:
        格式化的错误消息
    """

    def _find_missing(current: BaseException) -> Optional[str]:
        nested = getattr(current, "exceptions", None)
        if nested:
            for child in nested:
                missing = _find_missing(child)
                if missing:
                    return missing
            return None
        if isinstance(current, FileNotFoundError):
            if getattr(current, "filename", None):
                return str(current.filename)
            match = __import__("re").search(r"No such file or directory: '([^']+)'", str(current))
            if match:
                return match.group(1)
        for attr in ("__cause__", "__context__"):
            nested_exc = getattr(current, attr, None)
            if isinstance(nested_exc, BaseException):
                missing = _find_missing(nested_exc)
                if missing:
                    return missing
        return None

    def _flatten_messages(current: BaseException) -> List[str]:
        nested = getattr(current, "exceptions", None)
        if nested:
            flattened: List[str] = []
            for child in nested:
                flattened.extend(_flatten_messages(child))
            return flattened
        messages = []
        text = str(current).strip()
        if text:
            messages.append(text)
        for attr in ("__cause__", "__context__"):
            nested_exc = getattr(current, attr, None)
            if isinstance(nested_exc, BaseException):
                messages.extend(_flatten_messages(nested_exc))
        return messages or [current.__class__.__name__]

    from mcpClient.core.mcp_client.security import _sanitize_error

    missing = _find_missing(exc)
    if missing:
        message = f"missing executable '{missing}'"
        if os.path.basename(missing) in {"npx", "npm", "node"}:
            message += (
                " (ensure Node.js is installed and PATH includes its bin directory, "
                "or set mcp_servers.<name>.command to an absolute path)"
            )
        return _sanitize_error(message)

    deduped: List[str] = []
    for item in _flatten_messages(exc):
        if item not in deduped:
            deduped.append(item)
    return _sanitize_error("; ".join(deduped[:3]))


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _safe_numeric(value: Any, default: float, coerce: type = float, minimum: float = 1) -> float:
    """
    安全地转换数值的辅助函数

    Args:
        value: 要转换的值
        default: 转换失败时的默认值
        coerce: 转换类型 (int 或 float)
        minimum: 最小值

    Returns:
        转换后的数值，如果转换失败则返回默认值
    """
    try:
        result = coerce(value)
        if isinstance(result, float) and not math.isfinite(result):
            return default
        return max(result, minimum)
    except (TypeError, ValueError, OverflowError):
        return default


# ---------------------------------------------------------------------------
# MCPServerTask
# ---------------------------------------------------------------------------


class MCPServerTask:
    """
    管理单个 MCP 服务器连接的生命周期

    整个连接生命周期（连接、发现工具、服务、断开）在一个 asyncio Task 中运行，
    保持传输上下文活跃。工具调用通过 run_coroutine_threadsafe() 调度到事件循环。

    Attributes:
        name: 服务器名称
        session: MCP ClientSession 实例
        tool_timeout: 工具调用超时时间（秒）
        _task: asyncio Task
        _ready: 连接就绪事件
        _shutdown_event: 关闭事件
        _tools: 工具列表
        _config: 服务器配置
        _sampling: SamplingHandler 实例

    Args:
        name: 服务器名称
    """

    __slots__ = (
        "name",
        "session",
        "tool_timeout",
        "_task",
        "_ready",
        "_shutdown_event",
        "_tools",
        "_error",
        "_config",
        "_sampling",
        "_registered_tool_names",
        "_auth_type",
        "_refresh_lock",
    )

    def __init__(self, name: str) -> None:
        """
        初始化 MCPServerTask

        Args:
            name: 服务器名称
        """
        self.name = name
        self.session: Optional[Any] = None
        self.tool_timeout: float = _DEFAULT_TOOL_TIMEOUT
        self._task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._tools: list = []
        self._error: Optional[Exception] = None
        self._config: dict = {}
        self._sampling: Optional["SamplingHandler"] = None
        self._registered_tool_names: List[str] = []
        self._auth_type: str = ""
        self._refresh_lock = asyncio.Lock()

    def _is_http(self) -> bool:
        """
        检查是否使用 HTTP 传输

        Returns:
            True if using HTTP transport, False otherwise
        """
        return "url" in self._config

    def _is_sse(self) -> bool:
        """
        检查是否使用 SSE 传输

        Returns:
            True if using SSE transport, False otherwise
        """
        config_type = self._config.get("type", "").lower()
        if config_type == "sse":
            return True
        url = self._config.get("url", "")
        return bool(url and "/sse" in url)

    async def _make_message_handler(self):
        """
        创建消息处理器回调

        Returns:
            消息处理协程
        """

        async def _handler(message: Any) -> None:
            try:
                if isinstance(message, Exception):
                    logger.debug("MCP message handler (%s): exception: %s", self.name, message)
                    return
                if _MCP_NOTIFICATION_TYPES and isinstance(message, ServerNotification):
                    match message.root:
                        case ToolListChangedNotification():
                            logger.info(
                                "MCP server '%s': received tools/list_changed notification",
                                self.name,
                            )
                            await self._refresh_tools()
                        case PromptListChangedNotification():
                            logger.debug(
                                "MCP server '%s': prompts/list_changed (ignored)",
                                self.name,
                            )
                        case ResourceListChangedNotification():
                            logger.debug(
                                "MCP server '%s': resources/list_changed (ignored)",
                                self.name,
                            )
                        case _:
                            pass
            except Exception:
                logger.exception("Error in MCP message handler for '%s'", self.name)

        return _handler

    async def _refresh_tools(self) -> None:
        """
        重新获取并刷新工具列表

        当服务器发送 notifications/tools/list_changed 时调用。
        """
        if self.session is None:
            return

        async with self._refresh_lock:
            tools_result = await self.session.list_tools()
            new_mcp_tools = tools_result.tools if hasattr(tools_result, "tools") else []
            self._tools = new_mcp_tools
            logger.info(
                "MCP server '%s': dynamically refreshed %d tool(s)",
                self.name,
                len(self._registered_tool_names),
            )

    async def _run_stdio(self, config: dict) -> None:
        """
        使用 stdio 传输运行服务器

        Args:
            config: 服务器配置

        Raises:
            ValueError: 配置无效时
        """
        if not _MCP_AVAILABLE:
            raise ImportError("mcp package is required for stdio transport")

        command = config.get("command")
        args = config.get("args", [])
        user_env = config.get("env")

        if not command:
            raise ValueError(f"MCP server '{self.name}' has no 'command' in config")

        from mcpClient.core.mcp_client.security import (
            _build_safe_env,
            _resolve_stdio_command,
        )

        safe_env = _build_safe_env(user_env)
        command, safe_env = _resolve_stdio_command(command, safe_env)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=safe_env if safe_env else None,
        )

        sampling_kwargs = self._sampling.session_kwargs() if self._sampling else {}
        if _MCP_NOTIFICATION_TYPES and _MCP_MESSAGE_HANDLER_SUPPORTED:
            sampling_kwargs["message_handler"] = await self._make_message_handler()

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, **sampling_kwargs) as session:
                await session.initialize()
                self.session = session
                await self._discover_tools()
                self._ready.set()
                await self._shutdown_event.wait()

    async def _run_http(self, config: dict) -> None:
        """
        使用 HTTP/StreamableHTTP 传输运行服务器

        Args:
            config: 服务器配置

        Raises:
            ImportError: HTTP 传输不可用时
        """
        if not _MCP_HTTP_AVAILABLE:
            raise ImportError(
                f"MCP server '{self.name}' requires HTTP transport but mcp.client.streamable_http is not available."
            )

        url = config["url"]
        headers = dict(config.get("headers") or {})
        connect_timeout = config.get("connect_timeout", _DEFAULT_CONNECT_TIMEOUT)

        sampling_kwargs = self._sampling.session_kwargs() if self._sampling else {}
        if _MCP_NOTIFICATION_TYPES and _MCP_MESSAGE_HANDLER_SUPPORTED:
            sampling_kwargs["message_handler"] = await self._make_message_handler()

        if _MCP_NEW_HTTP:
            import httpx

            client_kwargs: dict = {
                "follow_redirects": True,
                "timeout": httpx.Timeout(float(connect_timeout), read=300.0),
            }
            if headers:
                client_kwargs["headers"] = headers

            async with httpx.AsyncClient(**client_kwargs) as http_client:
                async with streamable_http_client(url, http_client=http_client) as (
                    read_stream,
                    write_stream,
                    _get_session_id,
                ):
                    async with ClientSession(read_stream, write_stream, **sampling_kwargs) as session:
                        await session.initialize()
                        self.session = session
                        await self._discover_tools()
                        self._ready.set()
                        await self._shutdown_event.wait()
        else:
            _http_kwargs: dict = {
                "headers": headers,
                "timeout": float(connect_timeout),
            }
            async with streamablehttp_client(url, **_http_kwargs) as (
                read_stream,
                write_stream,
                _get_session_id,
            ):
                async with ClientSession(read_stream, write_stream, **sampling_kwargs) as session:
                    await session.initialize()
                    self.session = session
                    await self._discover_tools()
                    self._ready.set()
                    await self._shutdown_event.wait()

    async def _run_sse(self, config: dict) -> None:
        """
        使用 SSE/Server-Sent Events 传输运行服务器

        Args:
            config: 服务器配置

        Raises:
            ImportError: SSE 传输不可用时
        """
        if not _MCP_SSE_AVAILABLE:
            raise ImportError(f"MCP server '{self.name}' requires SSE transport but mcp.client.sse is not available.")

        url = config["url"]
        headers = dict(config.get("headers") or {})
        timeout = config.get("connect_timeout", _DEFAULT_CONNECT_TIMEOUT)

        sampling_kwargs = self._sampling.session_kwargs() if self._sampling else {}
        if _MCP_NOTIFICATION_TYPES and _MCP_MESSAGE_HANDLER_SUPPORTED:
            sampling_kwargs["message_handler"] = await self._make_message_handler()

        async with sse_client(url, headers=headers, timeout=timeout) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream, **sampling_kwargs) as session:
                await session.initialize()
                self.session = session
                await self._discover_tools()
                self._ready.set()
                await self._shutdown_event.wait()

    async def _discover_tools(self) -> None:
        """
        从连接的会话中发现工具
        """
        if self.session is None:
            return
        tools_result = await self.session.list_tools()
        self._tools = tools_result.tools if hasattr(tools_result, "tools") else []

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """
        调用 MCP 工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用结果

        Raises:
            RuntimeError: 服务器未连接时
        """
        if self.session is None:
            raise RuntimeError(f"MCP server '{self.name}' is not connected")

        result = await self.session.call_tool(tool_name, arguments=arguments)
        return result

    async def run(self, config: dict) -> None:
        """
        长期运行的协程：连接、发现工具、等待、断开

        包含自动重连机制。

        Args:
            config: 服务器配置
        """
        self._config = config
        self.tool_timeout = config.get("timeout", _DEFAULT_TOOL_TIMEOUT)
        self._auth_type = (config.get("auth") or "").lower().strip()

        if "url" in config and "command" in config:
            logger.warning(
                "MCP server '%s' has both 'url' and 'command' in config. Using URL-based transport.",
                self.name,
            )

        retries = 0
        initial_retries = 0
        backoff = 1.0

        while True:
            try:
                if self._is_sse():
                    await self._run_sse(config)
                elif self._is_http():
                    await self._run_http(config)
                else:
                    await self._run_stdio(config)
                break
            except Exception as exc:
                self.session = None

                if not self._ready.is_set():
                    initial_retries += 1
                    if initial_retries > _MAX_INITIAL_CONNECT_RETRIES:
                        logger.warning(
                            "MCP server '%s' failed initial connection after %d attempts, giving up: %s",
                            self.name,
                            _MAX_INITIAL_CONNECT_RETRIES,
                            exc,
                        )
                        self._error = exc
                        self._ready.set()
                        return

                    logger.warning(
                        "MCP server '%s' initial connection failed (attempt %d/%d), retrying in %.0fs: %s",
                        self.name,
                        initial_retries,
                        _MAX_INITIAL_CONNECT_RETRIES,
                        backoff,
                        exc,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

                    if self._shutdown_event.is_set():
                        self._error = exc
                        self._ready.set()
                        return
                    continue

                if self._shutdown_event.is_set():
                    logger.debug(
                        "MCP server '%s' disconnected during shutdown: %s",
                        self.name,
                        exc,
                    )
                    return

                retries += 1
                if retries > _MAX_RECONNECT_RETRIES:
                    logger.warning(
                        "MCP server '%s' failed after %d reconnection attempts, giving up: %s",
                        self.name,
                        _MAX_RECONNECT_RETRIES,
                        exc,
                    )
                    return

                logger.warning(
                    "MCP server '%s' connection lost (attempt %d/%d), reconnecting in %.0fs: %s",
                    self.name,
                    retries,
                    _MAX_RECONNECT_RETRIES,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

                if self._shutdown_event.is_set():
                    return
            finally:
                self.session = None

    async def start(self, config: dict) -> None:
        """
        创建后台 Task 并等待就绪或失败

        Args:
            config: 服务器配置

        Raises:
            Exception: 连接或初始化失败时
        """
        from mcpClient.core.mcp_client.sampling_handler import SamplingHandler

        sampling_config = config.get("sampling", {})
        if sampling_config.get("enabled", True) and _MCP_SAMPLING_TYPES:
            self._sampling = SamplingHandler(self.name, sampling_config)
        else:
            self._sampling = None

        self._task = asyncio.ensure_future(self.run(config))
        await self._ready.wait()
        if self._error:
            raise self._error

    async def shutdown(self) -> None:
        """
        信号 Task 退出并等待干净的资源清理
        """
        self._shutdown_event.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning(
                    "MCP server '%s' shutdown timed out, cancelling task",
                    self.name,
                )
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        self.session = None


# ---------------------------------------------------------------------------
# MCPClientPool
# ---------------------------------------------------------------------------


_MCP_LOOP: Optional[asyncio.AbstractEventLoop] = None
_MCP_THREAD: Optional[threading.Thread] = None
_POOL_LOCK = threading.Lock()


def _ensure_mcp_loop() -> None:
    """
    确保 MCP 事件循环正在运行（启动后台线程）
    """
    global _MCP_LOOP, _MCP_THREAD

    if _MCP_LOOP is not None and _MCP_THREAD is not None:
        return

    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_forever()
        finally:
            loop.close()

    with _POOL_LOCK:
        if _MCP_LOOP is None:
            _MCP_LOOP = asyncio.new_event_loop()
            _MCP_THREAD = threading.Thread(target=_run_loop, args=(_MCP_LOOP,), daemon=True)
            _MCP_THREAD.start()
            logger.info("MCP event loop started in background thread")


def _run_on_mcp_loop(coro: Awaitable, timeout: Optional[float] = None) -> Any:
    """
    在 MCP 事件循环上调度协程并返回结果（线程安全）

    Args:
        coro: 要执行的协程
        timeout: 超时时间（秒）

    Returns:
        协程的结果

    Raises:
        RuntimeError: 事件循环未启动时
        TimeoutError: 操作超时时
    """
    if _MCP_LOOP is None:
        raise RuntimeError("MCP event loop is not running. Call _ensure_mcp_loop() first.")

    future = asyncio.run_coroutine_threadsafe(coro, _MCP_LOOP)

    if timeout is not None:
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout}s")
    else:
        return future.result()


class MCPClientPool:
    """
    MCP 服务器连接池管理器

    管理多个 MCP 服务器连接的生命周期，提供线程安全的工具调用接口。

    Attributes:
        _servers: 服务器名称到 MCPServerTask 的映射
    """

    def __init__(self) -> None:
        """
        初始化连接池
        """
        self._servers: Dict[str, MCPServerTask] = {}

    async def connect(self, name: str, config: dict) -> None:
        """
        连接一个 MCP 服务器

        Args:
            name: 服务器名称
            config: 服务器配置
        """
        if name in self._servers:
            logger.warning("MCP server '%s' is already connected", name)
            return

        await self._do_connect(name, config)

    async def _do_connect(self, name: str, config: dict) -> None:
        """
        实际执行连接（协程）

        Args:
            name: 服务器名称
            config: 服务器配置
        """
        server = MCPServerTask(name)
        self._servers[name] = server
        await server.start(config)
        logger.info("MCP server '%s' connected", name)

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """
        调用 MCP 服务器工具（线程安全）

        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            args: 工具参数

        Returns:
            工具调用结果

        Raises:
            RuntimeError: 服务器未连接或工具调用失败时
        """
        with _POOL_LOCK:
            server = self._servers.get(server_name)

        if not server:
            raise RuntimeError(f"MCP server '{server_name}' is not connected")

        return await server.call_tool(tool_name, args)

    async def shutdown(self) -> None:
        """
        关闭所有 MCP 服务器连接
        """
        if not self._servers:
            return

        logger.info("Shutting down %d MCP server(s)...", len(self._servers))

        for name, server in list(self._servers.items()):
            try:
                await server.shutdown()
                logger.info("MCP server '%s' shutdown complete", name)
            except Exception as exc:
                logger.error("Error shutting down MCP server '%s': %s", name, exc)

        self._servers.clear()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------


client_pool = MCPClientPool()
