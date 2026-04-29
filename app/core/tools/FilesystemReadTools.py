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
from langchain.agents.middleware import FilesystemFileSearchMiddleware
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools.events import create_tool_event


@tool(description="文件系统查询工具，在用户上传的工作空间中搜索和列出文件路径。")
def search_agent(
    query: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    在用户上传的工作空间中搜索和列出文件路径。

    Args:
        query: 结构化查询要求，建议使用以下格式：
            - 搜索文件: "搜索 [文件类型] 文件中包含 '[关键词]' 的内容"
            - 列出文件: "列出 [目录] 下所有 [文件类型] 文件"
            示例：
            - "搜索包含 'AgentState' 的文件"
            - "列出 src 目录下所有 .ts 文件"

    Returns:
        查询结果，包含搜索到的文件路径列表或含有查询内容的文件路径。

    Note:
        仅搜索 {cwd}/app/data/upload/{session_id} 工作空间内的文件。
    """
    tool_name = "search_agent"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    session_id = runtime.context.get("session_id", "default")

    project_root = Path.cwd()
    root_path = project_root / "app" / "data" / "upload" / session_id

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

    try:
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
                FilesystemFileSearchMiddleware(
                    root_path=str(root_path),
                    use_ripgrep=True,
                    max_file_size_mb=10,
                ),
            ],
            system_prompt=(
                "你是文件系统查询助手。你只能使用 glob_search 和 grep_search 工具。"
                "返回内容:\n"
                "1. 搜索文件: 包含搜索到的文件路径列表\n"
                "2. 列出文件: 包含搜索到的文件路径列表\n"
            ),
        )

        final_answer = ""
        for chunk in child_agent.stream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode=["updates"],
            version="v2",
        ):
            progress_event = create_tool_event(
                event_type="tool_progress",
                tool=tool_name,
                tool_call_id=tool_call_id,
                data={
                    "child_stream": chunk,
                    "message": "子智能体执行中",
                },
            )
            writer(dict(progress_event))

            # chunk is a tuple: (stream_mode, data)
            if isinstance(chunk, tuple) and len(chunk) == 2:
                stream_mode, data = chunk
                if stream_mode == "updates":
                    for update in data.values():
                        msgs = update.get("messages", [])
                        for msg in msgs:
                            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                                final_answer = msg.content
            elif isinstance(chunk, dict):
                # Fallback for dict format
                if chunk.get("type") == "updates":
                    for update in chunk.get("data", {}).values():
                        msgs = update.get("messages", [])
                        for msg in msgs:
                            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                                final_answer = msg.content

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
                            {
                                "status": "success",
                                "tool": tool_name,
                                "duration_ms": duration_ms,
                                "result": {
                                    "query": query,
                                    "answer": final_answer,
                                },
                            },
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
                            {
                                "status": "error",
                                "tool": tool_name,
                                "duration_ms": duration_ms,
                                "error": {
                                    "type": type(e).__name__,
                                    "message": str(e),
                                },
                            },
                            ensure_ascii=False,
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
