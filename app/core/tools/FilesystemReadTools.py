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


@tool(description="""
【只读文件系统查询】在用户上传的工作空间中搜索和读取文件内容，仅支持只读操作。

调用时机：
- 需要搜索文件内容、列出目录结构时
- 需要比对文档与代码差异时
- 任何不修改文件的文件系统只读查询场景

参数：
- query: 查询要求，用自然语言描述需要查找的内容。例如：
  "列出所有 .md 文件"
  "搜索所有包含 'AgentState' 的 Python 文件"
  "逐一比对 docs/ 中的文档和实际代码，找出所有不一致之处"

注意：该工具仅搜索 {cwd}/app/data/upload/{session_id} 工作空间内的文件，不能访问工作空间外的路径。
""")
def filesystem_read(
    query: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    只读文件系统查询工具

    在指定的工作空间中创建一个只读子智能体，使用 FilesystemFileSearchMiddleware
    提供 glob_search 和 grep_search 能力。子智能体执行过程通过 get_stream_writer()
    以 tool_progress 事件流式推送。

    Args:
        query: 查询要求，自然语言描述。子智能体会根据此描述自行决定使用 glob_search 还是 grep_search。
        runtime: 工具运行时上下文，包含 session_id、tool_call_id、context 等。

    Returns:
        Command: 包含 ToolMessage 的查询结果，通过 Command.update.messages 返回。
    """
    tool_name = "filesystem_read"
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
                "你是只读文件系统助手。你只能使用 glob_search 和 grep_search 工具。"
                "不能创建、修改或删除任何文件。"
                "根据用户的查询要求，选择合适的工具完成任务，返回清晰的结果。"
                "如果 glob_search 或 grep_search 返回空结果，直接说明未找到匹配内容。"
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
