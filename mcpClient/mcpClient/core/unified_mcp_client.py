#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
统一 MCP 客户端模块

整合 MultiServerMCPClient、Sampling 回调、流式输出包装。

Date: 2026-04-20
"""

import asyncio
import json
import logging
import math
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

_MCP_SAMPLING_TYPES = False
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

_CREDENTIAL_PATTERN = re.compile(
    r"(?:"
    r"ghp_[A-Za-z0-9_]{1,255}"
    r"|sk-[A-Za-z0-9_]{1,255}"
    r"|Bearer\s+\S+"
    r"|token=[^\s&,;\"']{1,255}"
    r"|key=[^\s&,;\"']{1,255}"
    r"|API_KEY=[^\s&,;\"']{1,255}"
    r"|password=[^\s&,;\"']{1,255}"
    r"|secret=[^\s&,;\"']{1,255}"
    r")",
    re.IGNORECASE,
)


def _sanitize_error(text: str) -> str:
    return _CREDENTIAL_PATTERN.sub("[REDACTED]", text)


def _safe_numeric(value: Any, default: float, coerce: type = float, minimum: float = 1) -> float:
    try:
        result = coerce(value)
        if isinstance(result, float) and not math.isfinite(result):
            return default
        return max(result, minimum)
    except (TypeError, ValueError, OverflowError):
        return default


def _convert_server_config(name: str, config: dict) -> dict:
    adapted = dict(config)

    if "transport" not in adapted:
        type_val = adapted.pop("type", "").lower()
        if type_val == "sse":
            adapted["transport"] = "sse"
        elif type_val in ("http", "streamable_http"):
            adapted["transport"] = "http"
        elif "command" in adapted:
            adapted["transport"] = "stdio"
        elif "url" in adapted:
            url = adapted["url"].lower()
            if "/sse" in url:
                adapted["transport"] = "sse"
            else:
                adapted["transport"] = "http"
        else:
            logger.warning("MCP server '%s': cannot determine transport, skipping", name)
            return {}

    for key in ("tags", "sampling", "timeout", "connect_timeout", "read_timeout", "env"):
        adapted.pop(key, None)

    logger.info("MCP server '%s' adapted config: %s", name, adapted)
    return adapted


class SamplingCallback:
    _STOP_REASON_MAP = {
        "stop": "endTurn",
        "length": "maxTokens",
        "tool_calls": "toolUse",
    }

    def __init__(self, server_name: str, config: dict, llm_config: dict) -> None:
        self.server_name = server_name
        self.max_rpm = _safe_numeric(config.get("max_rpm", 10), 10, int)
        self.timeout = _safe_numeric(config.get("timeout", 30), 30, float)
        self.max_tokens_cap = _safe_numeric(config.get("max_tokens_cap", 4096), 4096, int)
        self.max_tool_rounds = _safe_numeric(config.get("max_tool_rounds", 5), 5, int, minimum=0)
        self.model_override = config.get("model")
        self.allowed_models = config.get("allowed_models", [])
        self.llm_config = llm_config

        _log_levels = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}
        self.audit_level = _log_levels.get(str(config.get("log_level", "info")).lower(), logging.INFO)

        self._rate_timestamps: List[float] = []
        self._tool_loop_count = 0
        self.metrics = {"requests": 0, "errors": 0, "tokens_used": 0, "tool_use_count": 0}

    def _check_rate_limit(self) -> bool:
        now = time.time()
        window = now - 60
        self._rate_timestamps[:] = [t for t in self._rate_timestamps if t > window]
        if len(self._rate_timestamps) >= self.max_rpm:
            return False
        self._rate_timestamps.append(now)
        return True

    def _resolve_model(self, preferences) -> Optional[str]:
        if self.model_override:
            return self.model_override
        if preferences and hasattr(preferences, "hints") and preferences.hints:
            for hint in preferences.hints:
                if hasattr(hint, "name") and hint.name:
                    return hint.name
        return None

    @staticmethod
    def _extract_tool_result_text(block) -> str:
        if not hasattr(block, "content") or block.content is None:
            return ""
        items = block.content if isinstance(block.content, list) else [block.content]
        return "\n".join(item.text for item in items if hasattr(item, "text"))

    def _convert_messages(self, params) -> List[dict]:
        messages: List[dict] = []
        for msg in params.messages:
            blocks = (
                msg.content_as_list
                if hasattr(msg, "content_as_list")
                else (msg.content if isinstance(msg.content, list) else [msg.content])
            )

            tool_results = [b for b in blocks if hasattr(b, "toolUseId")]
            tool_uses = [
                b for b in blocks if hasattr(b, "name") and hasattr(b, "input") and not hasattr(b, "toolUseId")
            ]
            content_blocks = [
                b for b in blocks if not hasattr(b, "toolUseId") and not (hasattr(b, "name") and hasattr(b, "input"))
            ]

            for tr in tool_results:
                messages.append(
                    {"role": "tool", "tool_call_id": tr.toolUseId, "content": self._extract_tool_result_text(tr)}
                )

            if tool_uses:
                tc_list = []
                for tu in tool_uses:
                    tc_list.append(
                        {
                            "id": getattr(tu, "id", f"call_{len(tc_list)}"),
                            "type": "function",
                            "function": {
                                "name": tu.name,
                                "arguments": json.dumps(tu.input) if isinstance(tu.input, dict) else str(tu.input),
                            },
                        }
                    )
                msg_dict: dict = {"role": msg.role, "tool_calls": tc_list}
                text_parts = [b.text for b in content_blocks if hasattr(b, "text")]
                if text_parts:
                    msg_dict["content"] = "\n".join(text_parts)
                messages.append(msg_dict)
            elif content_blocks:
                if len(content_blocks) == 1 and hasattr(content_blocks[0], "text"):
                    messages.append({"role": msg.role, "content": content_blocks[0].text})
                else:
                    parts = []
                    for block in content_blocks:
                        if hasattr(block, "text"):
                            parts.append({"type": "text", "text": block.text})
                        elif hasattr(block, "data") and hasattr(block, "mimeType"):
                            parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{block.mimeType};base64,{block.data}"},
                                }
                            )
                        else:
                            logger.warning(
                                "Unsupported sampling content block type: %s (skipped)", type(block).__name__
                            )
                    if parts:
                        messages.append({"role": msg.role, "content": parts})

        return messages

    @staticmethod
    def _error(message: str, code: int = -1):
        if _MCP_SAMPLING_TYPES:
            return ErrorData(code=code, message=message)
        raise Exception(message)

    def _build_tool_use_result(self, choice, response) -> Any:
        self.metrics["tool_use_count"] += 1

        if self.max_tool_rounds == 0:
            self._tool_loop_count = 0
            return self._error(f"Tool loops disabled for server '{self.server_name}' (max_tool_rounds=0)")

        self._tool_loop_count += 1
        if self._tool_loop_count > self.max_tool_rounds:
            self._tool_loop_count = 0
            return self._error(
                f"Tool loop limit exceeded for server '{self.server_name}' (max {self.max_tool_rounds} rounds)"
            )

        content_blocks = []
        for tc in choice.message.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "MCP server '%s': malformed tool_calls arguments (wrapping as raw)", self.server_name
                    )
                    parsed = {"_raw": args}
            else:
                parsed = args if isinstance(args, dict) else {"_raw": str(args)}

            content_blocks.append(ToolUseContent(type="tool_use", id=tc.id, name=tc.function.name, input=parsed))

        logger.log(
            self.audit_level,
            "MCP server '%s' sampling response: model=%s, tool_calls=%d",
            self.server_name,
            response.model,
            len(content_blocks),
        )

        return CreateMessageResultWithTools(
            role="assistant",
            content=content_blocks,
            model=response.model,
            stopReason="toolUse",
        )

    def _build_text_result(self, choice, response) -> Any:
        self._tool_loop_count = 0
        response_text = choice.message.content or ""

        logger.log(
            self.audit_level,
            "MCP server '%s' sampling response: model=%s",
            self.server_name,
            response.model,
        )

        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text=_sanitize_error(response_text)),
            model=response.model,
            stopReason=self._STOP_REASON_MAP.get(choice.finish_reason, "endTurn"),
        )

    async def __call__(self, context, params) -> Any:
        if not _MCP_SAMPLING_TYPES:
            return self._error("MCP sampling types not available")

        if not self._check_rate_limit():
            logger.warning("MCP server '%s' sampling rate limit exceeded (%d/min)", self.server_name, self.max_rpm)
            self.metrics["errors"] += 1
            return self._error(
                f"Sampling rate limit exceeded for server '{self.server_name}' ({self.max_rpm} requests/minute)"
            )

        model = self._resolve_model(getattr(params, "modelPreferences", None))
        resolved_model = model or self.model_override or ""

        if self.allowed_models and resolved_model and resolved_model not in self.allowed_models:
            logger.warning(
                "MCP server '%s' requested model '%s' not in allowed_models", self.server_name, resolved_model
            )
            self.metrics["errors"] += 1
            return self._error(
                f"Model '{resolved_model}' not allowed for server '{self.server_name}'. "
                f"Allowed: {', '.join(self.allowed_models)}"
            )

        messages = self._convert_messages(params)
        if hasattr(params, "systemPrompt") and params.systemPrompt:
            messages.insert(0, {"role": "system", "content": params.systemPrompt})

        max_tokens = min(params.maxTokens, self.max_tokens_cap)
        call_temperature = None
        if hasattr(params, "temperature") and params.temperature is not None:
            call_temperature = params.temperature

        def _sync_call():
            from app.core.llmcalls.model_factory import ModelFactory

            llm = ModelFactory.create_model(
                model_type=self.llm_config["model_type"],
                model_name=resolved_model or self.llm_config["model_name"],
                api_key=self.llm_config["api_key"],
                temperature=call_temperature if call_temperature is not None else self.llm_config["temperature"],
                base_url=self.llm_config.get("base_url"),
            )
            return llm.invoke(messages)

        try:
            response = await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=self.timeout)
        except asyncio.TimeoutError:
            self.metrics["errors"] += 1
            return self._error(f"Sampling LLM call timed out after {self.timeout}s for server '{self.server_name}'")
        except Exception as exc:
            self.metrics["errors"] += 1
            return self._error(f"Sampling LLM call failed: {_sanitize_error(str(exc))}")

        if not getattr(response, "choices", None):
            self.metrics["errors"] += 1
            return self._error(f"LLM returned empty response (no choices) for server '{self.server_name}'")

        choice = response.choices[0]
        self.metrics["requests"] += 1
        total_tokens = getattr(getattr(response, "usage", None), "total_tokens", 0)
        if isinstance(total_tokens, int):
            self.metrics["tokens_used"] += total_tokens

        if choice.finish_reason == "tool_calls" and hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            return self._build_tool_use_result(choice, response)

        return self._build_text_result(choice, response)


class StreamOutputWrapper(BaseTool):
    name: str = ""
    description: str = ""

    def __init__(self, original_tool: BaseTool, max_content_length: int = 500, **kwargs):
        super().__init__(**kwargs)
        self.original_tool = original_tool
        self.max_content_length = max_content_length
        self.name = original_tool.name
        self.description = original_tool.description
        self.args_schema = original_tool.args_schema

    def _run(self, *args, config=None, **kwargs) -> str:
        result = self.original_tool._run(*args, config=config, **kwargs)
        return self._process_result(result)

    async def _arun(self, *args, config=None, **kwargs) -> str:
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
        except (ImportError, RuntimeError):
            result = await self.original_tool._arun(*args, config=config, **kwargs)
            return self._process_result(result)

        tool_call_id = self._get_tool_call_id(config)

        try:
            writer(
                {
                    "header": {
                        "tool_name": self.name,
                        "tool_call_id": tool_call_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "start",
                        "version": "1.0",
                    },
                    "body": {"data": None, "metadata": {"tool_type": "mcp", "args": kwargs}},
                    "footer": None,
                }
            )

            result = await self.original_tool._arun(*args, config=config, **kwargs)

            result_str = str(result)
            result_length = len(result_str)

            if result_length <= self.max_content_length:
                writer(
                    {
                        "header": {
                            "tool_name": self.name,
                            "tool_call_id": tool_call_id,
                            "timestamp": datetime.now().isoformat(),
                            "status": "complete",
                            "version": "1.0",
                        },
                        "body": {
                            "data": result,
                            "metadata": {"tool_type": "mcp", "data_size": "small", "result_length": result_length},
                        },
                        "footer": {
                            "success": True,
                            "message": "执行成功",
                            "stats": {"total": 1, "processed": 1, "failed": 0},
                        },
                    }
                )
                return result_str
            else:
                writer(
                    {
                        "header": {
                            "tool_name": self.name,
                            "tool_call_id": tool_call_id,
                            "timestamp": datetime.now().isoformat(),
                            "status": "progress",
                            "version": "1.0",
                        },
                        "body": {
                            "data": result,
                            "metadata": {"tool_type": "mcp", "data_size": "large", "result_length": result_length},
                        },
                        "footer": None,
                    }
                )

                writer(
                    {
                        "header": {
                            "tool_name": self.name,
                            "tool_call_id": tool_call_id,
                            "timestamp": datetime.now().isoformat(),
                            "status": "complete",
                            "version": "1.0",
                        },
                        "body": {
                            "data": None,
                            "metadata": {"tool_type": "mcp", "data_size": "large"},
                        },
                        "footer": {
                            "success": True,
                            "message": f"执行成功，返回 {result_length} 字符数据",
                            "stats": {"total": 1, "processed": 1, "failed": 0},
                        },
                    }
                )

                summary = f"执行成功，返回 {result_length} 字符数据"
                if isinstance(result, (dict, list)):
                    summary = f"执行成功，返回 {type(result).__name__}，大小: {result_length} 字符"
                return summary

        except Exception as e:
            error_msg = f"工具调用失败: {self.name}, 错误: {str(e)}"
            writer(
                {
                    "header": {
                        "tool_name": self.name,
                        "tool_call_id": tool_call_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "error",
                        "version": "1.0",
                    },
                    "body": {"data": None, "metadata": {"tool_type": "mcp", "error": error_msg}},
                    "footer": {
                        "success": False,
                        "message": error_msg,
                        "stats": {"total": 1, "processed": 0, "failed": 1},
                    },
                }
            )
            return f"错误：{error_msg}"

    def _process_result(self, result: Any) -> str:
        result_str = str(result)
        result_length = len(result_str)
        if result_length <= self.max_content_length:
            return result_str
        summary = f"执行成功，返回 {result_length} 字符数据"
        if isinstance(result, (dict, list)):
            summary = f"执行成功，返回 {type(result).__name__}，大小: {result_length} 字符"
        return summary

    def _get_tool_call_id(self, config) -> str:
        if config and "configurable" in config:
            return config["configurable"].get("tool_call_id", "unknown")
        return "unknown"


class UnifiedMCPClient:
    def __init__(
        self,
        server_configs: dict,
        sampling_llm_config: dict = None,
        max_content_length: int = 500,
    ) -> None:
        self._server_configs = server_configs
        self._sampling_llm_config = sampling_llm_config
        self._max_content_length = max_content_length

        self._adapted_configs = self._adapt_all_configs(server_configs)
        self._sampling_callbacks = self._create_sampling_callbacks(sampling_llm_config)

        if self._adapted_configs:
            logger.info("Creating MultiServerMCPClient with %d server configs", len(self._adapted_configs))
            self._client = MultiServerMCPClient(self._adapted_configs)
            logger.info("MultiServerMCPClient created successfully")
        else:
            self._client = None
            logger.warning("No valid MCP server configurations provided")

    def _adapt_all_configs(self, server_configs: dict) -> dict:
        adapted = {}
        for name, config in server_configs.items():
            converted = _convert_server_config(name, config)
            if converted:
                adapted[name] = converted
        return adapted

    def _create_sampling_callbacks(self, llm_config: dict = None) -> Dict[str, SamplingCallback]:
        if not _MCP_SAMPLING_TYPES:
            return {}

        callbacks = {}
        effective_llm_config = llm_config

        if effective_llm_config is None:
            try:
                from app.core.config.settings import settings

                effective_llm_config = settings.get_llm_config()
            except ImportError:
                logger.debug("Cannot load LLM config from settings, sampling disabled")
                return {}

        for name, config in self._server_configs.items():
            sampling_config = config.get("sampling", {})
            if sampling_config.get("enabled", False):
                callbacks[name] = SamplingCallback(name, sampling_config, effective_llm_config)
                logger.info("Sampling callback created for server '%s'", name)

        return callbacks

    async def get_tools(self) -> list[BaseTool]:
        if self._client is None:
            logger.warning("get_tools called but _client is None")
            return []

        try:
            logger.info("Fetching tools from %d servers", len(self._adapted_configs))
            tools = await self._client.get_tools()
            logger.info("Successfully fetched %d tools", len(tools))
            return [StreamOutputWrapper(tool, self._max_content_length) for tool in tools]
        except Exception as e:
            logger.error("Failed to get tools: %s", e, exc_info=True)
            return []

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        if self._client is None:
            raise RuntimeError("MCP client is not initialized")

        async with self._client.session(server_name) as session:
            result = await session.call_tool(tool_name, arguments=arguments)
            return result

    async def get_server_tools(self, server_name: str) -> Optional[dict]:
        if server_name not in self._server_configs:
            return None

        if self._client is None:
            return None

        try:
            tools = await self._client.get_tools(server_name=server_name)
        except Exception:
            tools = []

        tags = self._server_configs[server_name].get("tags", [])
        return {"tools": tools, "tags": tags}

    async def shutdown(self) -> None:
        if self._client is not None:
            try:
                if hasattr(self._client, "cleanup"):
                    await self._client.cleanup()
                elif hasattr(self._client, "close"):
                    await self._client.close()
            except Exception as exc:
                logger.error("Error during MCP client cleanup: %s", exc)
            self._client = None

    def get_server_names(self) -> List[str]:
        return list(self._adapted_configs.keys())

    def get_sampling_callback(self, server_name: str) -> Optional[SamplingCallback]:
        return self._sampling_callbacks.get(server_name)
