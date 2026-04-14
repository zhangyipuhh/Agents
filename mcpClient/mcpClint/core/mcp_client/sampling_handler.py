#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Sampling Handler 模块

处理 MCP Server 发起的 LLM 回传请求 (sampling/createMessage)。
借鉴 hermes-agent tools/mcp_tool.py SamplingHandler 实现。

Date: 2026-04-14
"""

import asyncio
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 尝试导入 MCP 类型
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _safe_numeric(
    value: Any, default: float, coerce: type = float, minimum: float = 1
) -> float:
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
# SamplingHandler
# ---------------------------------------------------------------------------


class SamplingHandler:
    """
    处理 MCP Server 的 sampling/createMessage 请求

    每个启用了 sampling 的 MCPServerTask 创建一个 SamplingHandler 实例。
    处理程序是可调用的，直接传递给 ClientSession 作为 sampling_callback。
    所有状态（速率限制时间戳、metrics、工具循环计数器）都在实例上。

    Attributes:
        server_name: 服务器名称
        max_rpm: 每分钟最大请求数
        timeout: LLM 调用超时时间
        max_tokens_cap: 最大 token 上限
        max_tool_rounds: 工具循环上限
        model_override: 模型覆盖
        allowed_models: 允许的模型列表
        audit_level: 审计日志级别
        metrics: 指标字典

    Args:
        server_name: 服务器名称
        config: Sampling 配置字典
    """

    _STOP_REASON_MAP = {
        "stop": "endTurn",
        "length": "maxTokens",
        "tool_calls": "toolUse",
    }

    def __init__(self, server_name: str, config: dict) -> None:
        """
        初始化 SamplingHandler

        Args:
            server_name: 服务器名称
            config: Sampling 配置字典
        """
        self.server_name = server_name
        self.max_rpm = _safe_numeric(config.get("max_rpm", 10), 10, int)
        self.timeout = _safe_numeric(config.get("timeout", 30), 30, float)
        self.max_tokens_cap = _safe_numeric(
            config.get("max_tokens_cap", 4096), 4096, int
        )
        self.max_tool_rounds = _safe_numeric(
            config.get("max_tool_rounds", 5),
            5,
            int,
            minimum=0,
        )
        self.model_override = config.get("model")
        self.allowed_models = config.get("allowed_models", [])

        _log_levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
        }
        self.audit_level = _log_levels.get(
            str(config.get("log_level", "info")).lower(),
            logging.INFO,
        )

        self._rate_timestamps: List[float] = []
        self._tool_loop_count = 0
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "tokens_used": 0,
            "tool_use_count": 0,
        }

    def _check_rate_limit(self) -> bool:
        """
        滑动窗口速率限制检查

        Returns:
            True if request is allowed, False otherwise
        """
        now = time.time()
        window = now - 60
        self._rate_timestamps[:] = [t for t in self._rate_timestamps if t > window]
        if len(self._rate_timestamps) >= self.max_rpm:
            return False
        self._rate_timestamps.append(now)
        return True

    def _resolve_model(self, preferences) -> Optional[str]:
        """
        解析模型偏好

        配置覆盖 > 服务器提示 > None (使用默认)

        Args:
            preferences: 模型偏好对象

        Returns:
            模型名称或 None
        """
        if self.model_override:
            return self.model_override
        if preferences and hasattr(preferences, "hints") and preferences.hints:
            for hint in preferences.hints:
                if hasattr(hint, "name") and hint.name:
                    return hint.name
        return None

    @staticmethod
    def _extract_tool_result_text(block) -> str:
        """
        从 ToolResultContent 块提取文本

        Args:
            block: 结果块对象

        Returns:
            提取的文本内容
        """
        if not hasattr(block, "content") or block.content is None:
            return ""
        items = block.content if isinstance(block.content, list) else [block.content]
        return "\n".join(item.text for item in items if hasattr(item, "text"))

    def _convert_messages(self, params) -> List[dict]:
        """
        将 MCP SamplingMessages 转换为 OpenAI 格式

        Args:
            params: Sampling 参数

        Returns:
            OpenAI 格式的消息列表
        """
        messages: List[dict] = []
        for msg in params.messages:
            blocks = (
                msg.content_as_list
                if hasattr(msg, "content_as_list")
                else (msg.content if isinstance(msg.content, list) else [msg.content])
            )

            tool_results = [b for b in blocks if hasattr(b, "toolUseId")]
            tool_uses = [
                b
                for b in blocks
                if hasattr(b, "name")
                and hasattr(b, "input")
                and not hasattr(b, "toolUseId")
            ]
            content_blocks = [
                b
                for b in blocks
                if not hasattr(b, "toolUseId")
                and not (hasattr(b, "name") and hasattr(b, "input"))
            ]

            for tr in tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tr.toolUseId,
                        "content": self._extract_tool_result_text(tr),
                    }
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
                                "arguments": json.dumps(tu.input)
                                if isinstance(tu.input, dict)
                                else str(tu.input),
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
                    messages.append(
                        {"role": msg.role, "content": content_blocks[0].text}
                    )
                else:
                    parts = []
                    for block in content_blocks:
                        if hasattr(block, "text"):
                            parts.append({"type": "text", "text": block.text})
                        elif hasattr(block, "data") and hasattr(block, "mimeType"):
                            parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{block.mimeType};base64,{block.data}"
                                    },
                                }
                            )
                        else:
                            logger.warning(
                                "Unsupported sampling content block type: %s (skipped)",
                                type(block).__name__,
                            )
                    if parts:
                        messages.append({"role": msg.role, "content": parts})

        return messages

    @staticmethod
    def _error(message: str, code: int = -1):
        """
        返回 ErrorData

        Args:
            message: 错误消息
            code: 错误码

        Returns:
            ErrorData 对象或抛出异常
        """
        if _MCP_SAMPLING_TYPES:
            return ErrorData(code=code, message=message)
        raise Exception(message)

    def _build_tool_use_result(self, choice, response) -> CreateMessageResultWithTools:
        """
        从 LLM tool_calls 响应构建 CreateMessageResultWithTools

        Args:
            choice: LLM 响应选择
            response: 完整响应

        Returns:
            CreateMessageResultWithTools 对象
        """
        self.metrics["tool_use_count"] += 1

        if self.max_tool_rounds == 0:
            self._tool_loop_count = 0
            return self._error(
                f"Tool loops disabled for server '{self.server_name}' (max_tool_rounds=0)"
            )

        self._tool_loop_count += 1
        if self._tool_loop_count > self.max_tool_rounds:
            self._tool_loop_count = 0
            return self._error(
                f"Tool loop limit exceeded for server '{self.server_name}' "
                f"(max {self.max_tool_rounds} rounds)"
            )

        content_blocks = []
        for tc in choice.message.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    logger.warning(
                        "MCP server '%s': malformed tool_calls arguments (wrapping as raw)",
                        self.server_name,
                    )
                    parsed = {"_raw": args}
            else:
                parsed = args if isinstance(args, dict) else {"_raw": str(args)}

            content_blocks.append(
                ToolUseContent(
                    type="tool_use",
                    id=tc.id,
                    name=tc.function.name,
                    input=parsed,
                )
            )

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

    def _build_text_result(self, choice, response) -> CreateMessageResult:
        """
        从普通文本响应构建 CreateMessageResult

        Args:
            choice: LLM 响应选择
            response: 完整响应

        Returns:
            CreateMessageResult 对象
        """
        from mcpClient.core.mcp_client.security import _sanitize_error

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

    def session_kwargs(self) -> dict:
        """
        返回传递给 ClientSession 的 kwargs

        Returns:
            包含 sampling_callback 和 sampling_capabilities 的字典
        """
        return {
            "sampling_callback": self,
            "sampling_capabilities": SamplingCapability(
                tools=SamplingToolsCapability(),
            ),
        }

    async def __call__(self, context, params) -> Any:
        """
        Sampling 回调，被 MCP SDK 调用

        Args:
            context: MCP SDK context
            params: Sampling 请求参数

        Returns:
            CreateMessageResult, CreateMessageResultWithTools, 或 ErrorData
        """
        if not self._check_rate_limit():
            logger.warning(
                "MCP server '%s' sampling rate limit exceeded (%d/min)",
                self.server_name,
                self.max_rpm,
            )
            self.metrics["errors"] += 1
            return self._error(
                f"Sampling rate limit exceeded for server '{self.server_name}' "
                f"({self.max_rpm} requests/minute)"
            )

        model = self._resolve_model(getattr(params, "modelPreferences", None))

        resolved_model = model or self.model_override or ""

        if (
            self.allowed_models
            and resolved_model
            and resolved_model not in self.allowed_models
        ):
            logger.warning(
                "MCP server '%s' requested model '%s' not in allowed_models",
                self.server_name,
                resolved_model,
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
            from app.core.llmcalls import ModelFactory
            from app.core.config.settings import settings

            llm_config = settings.get_llm_config()

            llm = ModelFactory.create_model(
                model_type=llm_config["model_type"],
                model_name=resolved_model or llm_config["model_name"],
                api_key=llm_config["api_key"],
                temperature=call_temperature
                if call_temperature is not None
                else llm_config["temperature"],
                base_url=llm_config.get("base_url"),
            )

            return llm.invoke(messages)

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_sync_call),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            self.metrics["errors"] += 1
            return self._error(
                f"Sampling LLM call timed out after {self.timeout}s "
                f"for server '{self.server_name}'"
            )
        except Exception as exc:
            self.metrics["errors"] += 1
            from mcpClient.core.mcp_client.security import _sanitize_error

            return self._error(f"Sampling LLM call failed: {_sanitize_error(str(exc))}")

        if not getattr(response, "choices", None):
            self.metrics["errors"] += 1
            return self._error(
                f"LLM returned empty response (no choices) for server '{self.server_name}'"
            )

        choice = response.choices[0]
        self.metrics["requests"] += 1
        total_tokens = getattr(getattr(response, "usage", None), "total_tokens", 0)
        if isinstance(total_tokens, int):
            self.metrics["tokens_used"] += total_tokens

        if (
            choice.finish_reason == "tool_calls"
            and hasattr(choice.message, "tool_calls")
            and choice.message.tool_calls
        ):
            return self._build_tool_use_result(choice, response)

        return self._build_text_result(choice, response)
