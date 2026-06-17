#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
subagent_message_extractor - 子智能体消息结构化提取器

将 LangChain BaseMessage 列表转换为前端可消费的结构化 dict 列表。
为后端 subagent 工具（sandbox / explore）的事件填充 child_messages / final_messages 字段。

设计目标：
    1. 与 SandboxTools._extract_ai_tool_calls 兼容（OpenAI/Anthropic 两种风格）
    2. 测试环境使用 Mock 对象时通过 type(msg).__name__ 兼容判断
    3. content 字段保留原始结构（str / list[ContentBlock]），不强行 stringify
    4. 失败消息（无 type / 异常）降级为 {"type": "Unknown", "content": str(msg)}

新结构化字段约定（与 create_tool_event 配合使用）：
    data.child_messages = [
        {
            "type": "HumanMessage" | "AIMessage" | "ToolMessage" | "Unknown",
            "role": "user" | "ai" | "tool",
            "content": str | list[dict],
            "tool_calls": [{"name", "args", "id"}],   # 仅 AIMessage
            "tool_call_id": "str",                      # 仅 ToolMessage
            "name": "str"                               # 仅 ToolMessage: 工具名
        },
        ...
    ]

Date: 2026-06-13
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping

logger = logging.getLogger(__name__)


# 测试环境中 langchain_core 可能被 mock，类型检查退化为字符串名匹配
_HUMAN_TYPE_NAMES = {"HumanMessage", "MockHumanMessage", "_MockHumanMessage"}
_AI_TYPE_NAMES = {"AIMessage", "MockAIMessage", "_MockAIMessage", "AIMessageChunk"}
_TOOL_TYPE_NAMES = {"ToolMessage", "MockToolMessage", "_MockToolMessage", "ToolCall"}
_SYSTEM_TYPE_NAMES = {"SystemMessage", "MockSystemMessage", "_MockSystemMessage"}


def _classify_role(type_name: str) -> str:
    """
    根据消息类型名返回角色字符串

    Args:
        type_name: 消息对象的类名（兼容 Mock 后缀）

    Returns:
        str: "user" | "ai" | "tool" | "system" | "unknown"
    """
    if type_name in _HUMAN_TYPE_NAMES:
        return "user"
    if type_name in _AI_TYPE_NAMES:
        return "ai"
    if type_name in _TOOL_TYPE_NAMES:
        return "tool"
    if type_name in _SYSTEM_TYPE_NAMES:
        return "system"
    return "unknown"


def _normalize_content(content: Any) -> Any:
    """
    归一化消息 content 字段：
    - str 原样返回
    - list 保留结构（不强制 join），便于前端按 ContentBlock 渲染
    - None 转为空字符串
    - dict 保留原结构
    - 其他类型调用 str() 兜底

    Args:
        content: 任意类型的消息 content 字段

    Returns:
        归一化后的 content；str 或 list[dict] 或 dict
    """
    if content is None:
        return ""
    if isinstance(content, (str, list, dict)):
        return content
    return str(content)


def _extract_tool_calls_from_ai(msg: Any) -> List[dict]:
    """
    从 AIMessage 派生对象提取 LLM 决策的工具调用列表

    兼容三种来源：
    1. OpenAI 风格：`msg.tool_calls` 字段（list[dict]，含 name/args/id）
    2. Anthropic 风格：`msg.content` 是 list，其中 type='tool_use' 块
    3. langchain-core 1.x 归一化：`msg.content_blocks` 中 type='tool_call'/'non_standard' 块

    Args:
        msg: AIMessage 或 MockAIMessage 或含 tool_calls 字段的对象

    Returns:
        list[dict]: 工具调用列表，每项统一为 {name, args, id}
    """
    results: List[dict] = []

    # 1) OpenAI 风格：msg.tool_calls
    tool_calls = getattr(msg, "tool_calls", None) or []
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name") or ""
                args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                results.append({"name": name, "args": args, "id": tc.get("id")})
            elif isinstance(tc, Mapping):
                # 兼容 Mapping 协议
                name = tc.get("name", "") if hasattr(tc, "get") else ""
                results.append({"name": str(name), "args": {}, "id": None})

    # 2) Anthropic 风格：msg.content 是 list
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name") or ""
                args = block.get("input")
                if not isinstance(args, dict):
                    args = {}
                results.append({"name": name, "args": args, "id": block.get("id")})

    # 3) langchain-core 1.x content_blocks
    content_blocks = getattr(msg, "content_blocks", None)
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_call":
                name = block.get("name") or ""
                args = block.get("args") if isinstance(block.get("args"), dict) else {}
                results.append({"name": name, "args": args, "id": block.get("id")})
            elif btype == "non_standard":
                value = block.get("value")
                if isinstance(value, dict) and value.get("type") == "tool_use":
                    name = value.get("name") or ""
                    args = value.get("input")
                    if not isinstance(args, dict):
                        args = {}
                    results.append({"name": name, "args": args, "id": value.get("id")})

    return results


def _extract_message(msg: Any) -> dict:
    """
    把单个消息对象转为结构化 dict

    Args:
        msg: LangChain BaseMessage 或其 Mock 对象

    Returns:
        dict: {type, role, content, tool_calls?, tool_call_id?, name?}
    """
    type_name = type(msg).__name__
    role = _classify_role(type_name)

    # 默认字段
    result: dict = {
        "type": type_name,
        "role": role,
        "content": _normalize_content(getattr(msg, "content", None)),
    }

    # AIMessage 提取 tool_calls
    if role == "ai":
        tool_calls = _extract_tool_calls_from_ai(msg)
        if tool_calls:
            result["tool_calls"] = tool_calls

    # ToolMessage 提取 tool_call_id 和 name
    if role == "tool":
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id is not None:
            result["tool_call_id"] = tool_call_id
        name = getattr(msg, "name", None)
        if name:
            result["name"] = name

    return result


def extract_structured_messages(messages: Iterable[Any]) -> List[dict]:
    """
    把 LangChain BaseMessage 列表转换为前端可消费的结构化 dict 列表

    Args:
        messages: 任意含 LangChain BaseMessage 派生对象的可迭代对象

    Returns:
        list[dict]: 每项为 {type, role, content, tool_calls?, tool_call_id?, name?}
        异常输入（如 None、空、非可迭代）会返回空列表
    """
    if not messages:
        return []

    result: List[dict] = []
    for msg in messages:
        if msg is None:
            continue
        try:
            result.append(_extract_message(msg))
        except Exception as exc:
            # 单条消息解析失败时降级为 Unknown 条目，不影响其他消息
            logger.warning("[subagent_message_extractor] 解析消息失败: %s", exc)
            try:
                result.append({
                    "type": "Unknown",
                    "role": "unknown",
                    "content": str(msg),
                })
            except Exception:
                # str(msg) 仍失败时彻底跳过
                continue
    return result
