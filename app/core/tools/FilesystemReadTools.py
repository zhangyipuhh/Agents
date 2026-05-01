#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FilesystemReadTools - 文件系统搜索与读取工具模块

该模块定义了两个文件系统工具：
    1. get_file_paths - 搜索文件并返回路径列表（基于 EncodingSafeFileSearchMiddleware）
    2. search_agent  - 读取指定路径文件并分析内容（基于 deepagents FilesystemMiddleware）

工具闭环流程：
    用户问题 → search_agent(paths=?, query) → 路径为空，先调用 get_file_paths(query)
    → 返回路径列表 → search_agent(paths=[...], query) → 读取并分析

工作空间:
    通过 Path.cwd() 反向定位项目根目录，拼接 app/data/upload/{session_id} 作为 root_path。
    root_path 限定子智能体的操作范围，确保只读安全。

流式事件:
    使用 get_stream_writer() + create_tool_event() 向前端推送 tool_start / tool_progress / tool_stop 事件。

Date: 2026-04-28
Author: AI Assistant
"""

import json
from datetime import datetime
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ContextEditingMiddleware, TodoListMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from deepagents import FilesystemMiddleware
from deepagents.backends import FilesystemBackend

from app.shared.tools.middleware.encoding_safe_file_search import EncodingSafeFileSearchMiddleware
from app.shared.utils.search.query_transformer import transform_query
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools.events import create_tool_event




class GetFilePathsResult(BaseModel):
    """get_file_paths 子智能体结构化输出"""
    paths: list[str] = Field(description="搜索到的文件路径列表")


class SearchAgentResult(BaseModel):
    """search_agent 子智能体结构化输出"""
    answer: str = Field(description="文件内容分析结果")


@tool(description=(
    "文件路径搜索工具。搜索文件名和文件内容，返回匹配的文件路径列表。\n"
    "本工具只返回文件路径，不读取文件内容。需要读取文件时请使用 search_agent 工具。\n"
    "直接传入用户原始问题即可，不要自己改写、扩展或自作聪明。\n"
    "正确：'如何实现的mcp集成'、'查找含langchain的文件'\n"
    "错误：'读取unified_mcp_client详细设计完整内容'、'列出所有mcp_adapter模块文件'\n"
    "后端会自动拆词和模糊搜索，不需要你预处理。"
))
def get_file_paths(
    query: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    在用户上传的工作空间中搜索文件路径（支持按文件名和文件内容搜索）。

    只返回匹配的文件路径列表，不读取文件内容。

    Args:
        query: 搜索指令。应为用户的完整搜索意图，包含：
            - 搜索目标（文件名 / 文件内容 / 两者）
            - 关键词
            - 格式如："用户要找文件内容包含'需求'的文件"

    Returns:
        查询结果，包含搜索到的文件路径列表。
    """
    tool_name = "get_file_paths"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    query = transform_query(query)

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
                EncodingSafeFileSearchMiddleware(
                    root_path=str(root_path),
                    max_file_size_mb=10,
                ),
                ContextEditingMiddleware(
                    edits=[
                        ClearToolUsesEdit(
                            trigger=1000,
                            keep=2,
                            exclude_tools=[],
                            placeholder="[earlier tool results trimmed for context length]",
                        )
                    ]
                ),
            ],
            system_prompt=(
                "你是文件搜索执行器，只负责搜索并返回文件路径列表。\n"
                "流程：\n"
                "1. 理解查询意图，提取关键词。若查询过于简短（如单个词），应扩展到同义词和英文对应词\n"
                "2. glob_search 按文件名搜索关键词\n"
                "3. grep_search 按文件内容搜索关键词（英文用 (?i) 忽略大小写）\n"
                "4. 返回文件路径列表，格式如：- /path/to/file1.py\\n- /path/to/file2.md\n"
                "绝对禁止：读取文件内容、分析文件、回答用户问题、与用户对话、反问、询问确认、问候。\n"
                "你的唯一职责是返回文件路径列表，文件内容的读取和分析由 search_agent 工具完成。\n"
                "你只能使用 write_todos、glob_search、grep_search 工具。"
            ),
            response_format=GetFilePathsResult,
        )

        final_answer = ""
        for chunk in child_agent.stream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode=["updates", "values"],
            version="v2",
        ):
            if not isinstance(chunk, dict):
                continue
            stream_mode = chunk.get("type")
            data = chunk.get("data")

            if stream_mode == "updates":
                writer(dict(create_tool_event(
                    event_type="tool_progress",
                    tool=tool_name,
                    tool_call_id=tool_call_id,
                    data={
                        "child_stream": data,
                        "message": "子智能体执行中",
                    },
                )))

            if stream_mode == "values" and isinstance(data, dict):
                if "structured_response" in data:
                    sr = data["structured_response"]
                    if isinstance(sr, GetFilePathsResult):
                        final_answer = "\n".join(f"- {p}" for p in sr.paths)

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
                    "answer": final_answer,
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


@tool(description=(
    "文件读取与分析工具。读取指定路径的文件内容并按用户问题进行分析。\n"
    "参数 paths: 文件路径列表（必须通过 get_file_paths 工具获取，不能自己猜测或推断路径）\n"
    "参数 query: 用户原始问题或分析意图\n"
    "重要：paths 参数必填且必须来自 get_file_paths 的返回结果。\n"
    "如果路径未知，必须先调用 get_file_paths 获取文件路径列表。"
))
def search_agent(
    paths: list[str],
    query: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    读取指定路径的文件内容并按用户问题进行分析。

    这是文件系统的读取入口，必须传入从 get_file_paths 获取的路径列表。
    工具内部基于 deepagents FilesystemMiddleware 提供 ls 和 read_file 能力。

    Args:
        paths: 文件路径列表，必须来自 get_file_paths 的返回结果。
        query: 用户原始问题或分析意图。

    Returns:
        文件内容分析结果。
    """
    tool_name = "search_agent"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    session_id = runtime.context.get("session_id", "default")

    project_root = Path.cwd()
    root_path = project_root / "app" / "data" / "upload" / session_id

    try:
        if not paths:
            raise ValueError(
                "paths 参数为空。请先调用 get_file_paths 获取文件路径列表。"
            )

        start_event = create_tool_event(
            event_type="tool_start",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "args": {"paths": paths, "query": query},
                "root_path": str(root_path),
                "description": f"开始读取文件并分析: {query[:100]}",
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

        root_str = str(root_path).replace("\\", "/")
        relative_paths = []
        for p in paths:
            p_norm = p.replace("\\", "/")
            if p_norm.startswith(root_str):
                rel = p_norm[len(root_str):].lstrip("/")
            else:
                rel = p_norm.lstrip("/")
            relative_paths.append(rel)

        child_agent = create_agent(
            model=model,
            middleware=[
                FilesystemMiddleware(
                    backend=FilesystemBackend(
                        root_dir=str(root_path),
                        virtual_mode=False,
                    ),
                ),
                ContextEditingMiddleware(
                    edits=[
                        ClearToolUsesEdit(
                            trigger=2000,
                            keep=3,
                            exclude_tools=[],
                            placeholder="[earlier file content trimmed for context length]",
                        )
                    ]
                ),
            ],
            system_prompt=(
                "你是文件读取与分析执行器。\n"
                "目标文件列表（相对于工作空间）：\n"
                "{paths}\n\n"
                "流程：\n"
                "1. 使用 ls 确认目标文件存在\n"
                "2. 使用 read_file 逐个读取文件内容\n"
                "   - read_file 的 path 参数使用上述相对路径\n"
                "   - 默认 limit=200 行，如需查看全文可增大 limit 值\n"
                "3. 根据用户问题分析文件内容并返回答案\n\n"
                "用户问题: {query}\n\n"
                "只能使用 ls、read_file 工具。\n"
                "绝对禁止：与用户对话、反问、询问确认、问候。"
            ).format(
                paths="\n".join(f"- {p}" for p in relative_paths),
                query=query,
            ),
            response_format=SearchAgentResult,
        )

        first_message = (
            f"请读取以下文件并根据用户问题进行分析：\n\n"
            f"文件列表：\n" + "\n".join(f"- {p}" for p in relative_paths) +
            f"\n\n用户问题：{query}"
        )

        final_answer = ""
        for chunk in child_agent.stream(
            {"messages": [{"role": "user", "content": first_message}]},
            stream_mode=["updates", "values"],
            version="v2",
        ):
            if not isinstance(chunk, dict):
                continue
            stream_mode = chunk.get("type")
            data = chunk.get("data")

            if stream_mode == "updates":
                writer(dict(create_tool_event(
                    event_type="tool_progress",
                    tool=tool_name,
                    tool_call_id=tool_call_id,
                    data={
                        "child_stream": data,
                        "message": "子智能体执行中",
                    },
                )))

            if stream_mode == "values" and isinstance(data, dict):
                if "structured_response" in data:
                    sr = data["structured_response"]
                    if isinstance(sr, SearchAgentResult):
                        final_answer = sr.answer

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
                    "answer": final_answer,
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
                "args": {"paths": paths, "query": query},
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

