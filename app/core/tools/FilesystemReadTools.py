#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FilesystemReadTools - 文件系统只读子智能体工具模块

该模块定义了 filesystem_read 工具，基于 LangChain Agent + FilesystemFileSearchMiddleware。
工具内部创建一个只读的子智能体，提供 glob_search 和 grep_search 能力，
不包含任何文件写入操作。

工作空间:
    通过 Path.cwd() 反向定位项目根目录，拼接 app/data/upload/{session_id} 作为 root_path。
    root_path 限定子智能体的搜索范围，确保只读安全。

流式事件:
    使用 get_stream_writer() + create_tool_event() 向前端推送 tool_start / tool_progress / tool_stop 事件。
    子智能体内部每步执行结果通过 tool_progress 事件转发给父图。

Date: 2026-04-28
Author: AI Assistant
"""

import json
from datetime import datetime
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import FilesystemFileSearchMiddleware, TodoListMiddleware
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools.events import create_tool_event


def _extract_chunk_content(chunk):
    """从 chunk 中提取 thinking 和 text 内容，去掉 tool_use 等冗余数据。

    chunk 格式: (stream_mode, data) 元组（LangGraph v2 streaming）
    """
    if not (isinstance(chunk, tuple) and len(chunk) == 2):
        return chunk

    stream_mode, data = chunk

    if stream_mode == "custom":
        return data

    if stream_mode == "messages":
        return data

    if stream_mode == "updates" and isinstance(data, dict):
        clean = {}
        for key, update in data.items():
            if update is None:
                continue
            msgs = update.get("messages", [])
            if not msgs:
                clean[key] = update
                continue
            clean_msgs = []
            for msg in msgs:
                if hasattr(msg, "type") and msg.type == "ai":
                    content = msg.content
                    if isinstance(content, list):
                        filtered_blocks = [
                            block for block in content
                            if isinstance(block, dict) and block.get("type") in ("thinking", "text")
                        ]
                        msg.content = filtered_blocks
                    clean_msgs.append(msg)
                else:
                    clean_msgs.append(msg)
            clean[key] = {**update, "messages": clean_msgs}
        return clean

    return chunk


@tool(description="文件系统查询工具，在用户上传的工作空间中搜索和列出文件路径。")
def search_agent(
    query: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    在用户上传的工作空间中搜索和列出文件路径。

    重要：调用此工具前，必须将用户的自然语言问题扩展为具体的结构化查询。
    不要直接将用户的简短问题（如"变更"、"配置在哪里"）原样传入，请先扩展为具体搜索指令。

    转换规则：
        - 用户问"是否有XXX文件/记录" → 扩展为"搜索包含'XXX'及相关关键词的文件"
        - 用户问"XXX在哪里" → 扩展为"搜索包含'XXX'的文件"
        - 用户问"列出XXX" → 扩展为"列出包含'XXX'的文件"
        - 模糊词汇应扩展同义词：变更(更新/changelog)、配置(config/settings)、日志(log/record)

    Args:
        query: 结构化查询要求，必须是扩展后的具体指令，格式如下：
            - 搜索文件: "搜索包含 '[关键词]' 的文件" 或 "搜索 [文件类型] 文件中包含 '[关键词]' 的内容"
            - 列出文件: "列出 [目录] 下所有 [文件类型] 文件"

            正确示例（已扩展）：
            - 用户问："有变更记录吗？"
              → 扩展为："搜索包含'变更'、'更新'、'changelog'关键词的文件"
            - 用户问："配置在哪里？"
              → 扩展为："搜索包含'config'、'配置'、'settings'关键词的文件"
            - 用户问："列出所有测试文件"
              → 扩展为："列出所有 .test.ts 和 .spec.ts 文件"

            错误示例（不要这样做）：
            - 直接传入："变更" ❌
            - 直接传入："配置" ❌

    Returns:
        查询结果，包含搜索到的文件路径列表或含有查询内容的文件路径。

    Note:
        - 仅搜索 {cwd}/app/data/upload/{session_id} 工作空间内的文件
        - query 必须是具体的搜索指令，不能直接将用户的模糊问题原样传入
    """
    tool_name = "search_agent"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    session_id = runtime.context.get("session_id", "default")

    project_root = Path.cwd()
    root_path = project_root / "app" / "data" / "upload" / session_id

    try:
        if not root_path.exists():
            raise FileNotFoundError(f"工作空间文件夹不存在: {root_path}")
        if not root_path.is_dir():
            raise NotADirectoryError(f"路径不是文件夹: {root_path}")
        if not any(root_path.iterdir()):
            raise ValueError(f"工作空间文件夹为空: {root_path}")

        start_event = create_tool_event(
            event_type="tool_start",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "args": {"query": query},
                "root_path": str(root_path),
                "description": f"开始文件系统查询: {query[:100]}",
            },
        )
        writer(dict(start_event))
        model = ModelFactory.create_model(
            model_type=LLM_CONFIG["model_type"],
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            temperature=LLM_CONFIG["temperature"],
            base_url=LLM_CONFIG["base_url"],
        )

        child_agent = create_agent(
            model=model,
            middleware=[
                TodoListMiddleware(
                    system_prompt=(
                        "## `write_todos`\n"
                        "你是文件搜索执行器。使用 `write_todos` 规划搜索步骤。\n"
                        "每次搜索任务都应使用此工具规划步骤。\n"
                        "计划模式示例：\n"
                        "1. glob_search 搜索文件名匹配\n"
                        "2. grep_search 搜索文件内容匹配\n"
                        "3. 汇总返回结果\n"
                        "开始执行后立即将第一个任务标记为 in_progress。\n"
                        "完成任务后立即标记为 completed。"
                    ),
                    tool_description=(
                        "创建搜索任务清单。每次文件搜索都应使用此工具规划步骤：\n"
                        "glob_search 搜文件名，grep_search 搜文件内容。\n"
                        "任务完成后立即更新状态。"
                    ),
                ),
                FilesystemFileSearchMiddleware(
                    root_path=str(root_path),
                    use_ripgrep=False,
                    max_file_size_mb=10,
                ),
            ],
            system_prompt=(
                "你是文件搜索执行器。\n"
                "流程：接收查询 → 写搜索计划 → 执行搜索 → 返回结果。\n"
                "你只能使用 write_todos、glob_search、grep_search 工具。\n"
                "glob_search 搜文件名，grep_search 搜文件内容（含全文匹配）。\n"
                "无论用什么方式搜索，最终结果只输出文件路径列表，不要返回文件内容。\n"
                "绝对禁止：与用户对话、反问、询问确认、问候。\n"
                "直接返回搜索到的文件路径列表即可。"
            ),
        )

        final_answer = ""
        for chunk in child_agent.stream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode=["updates"],
            version="v2",
        ):
            writer(dict(create_tool_event(
                event_type="tool_progress",
                tool=tool_name,
                tool_call_id=tool_call_id,
                data={
                    "child_stream": _extract_chunk_content(chunk),
                    "message": "子智能体执行中",
                },
            )))

            if isinstance(chunk, tuple) and len(chunk) == 2:
                stream_mode, data = chunk
                if stream_mode == "updates" and data is not None:
                    for update in data.values():
                        msgs = update.get("messages", [])
                        if msgs:
                            for msg in msgs:
                                if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                                    content = msg.content
                                    if isinstance(content, list):
                                        parts = []
                                        for block in content:
                                            if isinstance(block, dict) and block.get("type") == "text":
                                                parts.append(block.get("text", ""))
                                        final_answer = "".join(parts)
                                    else:
                                        final_answer = content

        if not final_answer:
            final_answer = "子智能体执行完成，但未获取到文本回复。"

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        stop_event = create_tool_event(
            event_type="tool_stop",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "status": "success",
                "result": {
                    "query": query,
                    "answer": final_answer[:500],
                },
                "duration_ms": duration_ms,
            },
        )
        writer(dict(stop_event))

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {"subagent": final_answer},
                            ensure_ascii=False,
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    except Exception as e:
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        error_event = create_tool_event(
            event_type="tool_error",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "args": {"query": query},
                "duration_ms": duration_ms,
            },
        )
        writer(dict(error_event))

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {"subagent": str(e)},
                            ensure_ascii=False,
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

