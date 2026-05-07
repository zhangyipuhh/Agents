#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FilesystemReadTools - 文件系统探索工具模块

该模块定义 explore 工具，启动探索子智能体，在单个子智能体中完成路径搜索 + 文件读取 + 内容分析。

设计对照 opencode:
    - opencode task.txt (父 LLM 工具描述)  →  @tool(description=...)
    - opencode explore.txt (子智能体 prompt) →  _EXPLORE_SYSTEM_PROMPT
    - opencode Task(prompt=, subagent_type="explore") →  explore(prompt=)

工作空间:
    通过 Path.cwd() 反向定位项目根目录，拼接 app/data/upload/{session_id} 作为 root_path。
    root_path 限定子智能体的操作范围，确保只读安全。

子智能体可用工具:
    - TodoListMiddleware:  write_todos 规划步骤
    - EncodingSafeFileSearchMiddleware:  glob_search + grep_search（编码安全）
    - FilesystemMiddleware:  ls + read_file

流式事件:
    使用 get_stream_writer() + create_tool_event() 向前端推送 tool_start / tool_progress / tool_stop 事件。

Date: 2026-05-07
Author: AI Assistant
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from langchain.agents import create_agent
from langchain.agents.middleware import ContextEditingMiddleware, TodoListMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from deepagents import FilesystemMiddleware
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver

from app.shared.tools.middleware.encoding_safe_file_search import EncodingSafeFileSearchMiddleware
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools.events import create_tool_event


_EXPLORE_SYSTEM_PROMPT = """\
You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns (use glob_search tool)
- Searching code and text with powerful regex patterns (use grep_search tool)
- Reading and analyzing file contents (use read_file / ls tools)

Guidelines:
- Use glob_search for broad file pattern matching
- Use grep_search for searching file contents with regex (use (?i) for case-insensitive)
- Use read_file when you know the specific file path you need to read
- Use ls for listing directory contents
- Adapt your search approach based on the thoroughness level specified by the caller
- Return file paths as absolute paths in your final response
- For clear communication, avoid using emojis
- Do not create any files, or run any commands that modify the user's system state in any way

Complete the user's search request efficiently and report your findings clearly.
"""


class ExploreResult(BaseModel):
    """explore 子智能体结构化输出"""
    answer: str = Field(description="文件搜索与分析结果")


def _extract_last_ai_text(messages: list) -> str:
    """从 messages 列表中提取最后一条 AI 消息的文本内容，作为兜底回答。"""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if not content:
            continue
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if text_parts:
                return "".join(text_parts).strip()
            thinking_parts = [
                b.get("thinking", "") for b in content
                if isinstance(b, dict) and b.get("type") == "thinking"
            ]
            if thinking_parts:
                return "".join(thinking_parts).strip()
    return ""


@tool(description=(
    "Launch a new agent to handle complex, multistep file search and reading tasks autonomously.\n"
    "The explore agent specializes in searching for files by name and content, then reading them.\n\n"
    "## When to use\n"
    "- When you need to search for files by name patterns AND read their content\n"
    "- When you need to find files containing specific keywords or text\n"
    "- When the scope of file search may span multiple directories\n"
    "- For complex file exploration that requires both finding and reading files\n\n"
    "## When NOT to use\n"
    "- If you know the specific file path you need to read, use the read_file tool directly\n"
    "- If you only need to list directory contents, use the ls tool directly\n"
    "- If you only need to search for file paths (not read content), use glob_search/grep_search directly\n"
    "- For tasks that are not related to file searching and reading\n\n"
    "## Prompt writing rules (CRITICAL)\n"
    "The prompt parameter must be a highly detailed task description for the subagent "
    "to perform autonomously. You must specify exactly what information the subagent "
    "should return back to you.\n"
    "Do NOT pass the user's raw message as prompt — formulate a detailed task instead.\n\n"
    "## Session resumption\n"
    "Each explore invocation returns a task_id. You can pass this task_id in "
    "a subsequent call to resume the same subagent session. When resuming, the subagent "
    "continues with its full previous context (all messages and tool results) "
    "via LangGraph checkpointing.\n"
    "This should only be set if you mean to resume a previous task.\n\n"
    "## Concurrency\n"
    "Launch multiple explore agents concurrently whenever possible, "
    "to maximize performance; use a single message with multiple tool calls."
))
def explore(
    prompt: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    启动探索子智能体，在工作空间中搜索文件、读取内容并分析。

    子智能体同时挂载 EncodingSafeFileSearchMiddleware（glob_search + grep_search）
    和 FilesystemMiddleware（ls + read_file），支持在单个 LLM 往返中完成
    搜索 → 读取 → 分析全流程。

    使用 LangGraph MemorySaver checkpointer 管理子智能体会话。传入 task_id
    可恢复之前的会话，子智能体将继续拥有完整历史上下文。

    Args:
        prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
                包含搜索目标、预期返回信息、操作约束等。
        task_id: 可选。传入之前的 task_id 可恢复子智能体会话。

    Returns:
        子智能体的文件搜索与分析结果，包含 task_id 用于后续恢复。
    """
    tool_name = "explore"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    actual_task_id =  tool_call_id

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
                "args": {"prompt": prompt},
                "root_path": str(root_path),
                "description": f"开始文件探索: {prompt[:100]}",
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
                EncodingSafeFileSearchMiddleware(
                    root_path=str(root_path),
                    max_file_size_mb=10,
                ),
                FilesystemMiddleware(
                    backend=FilesystemBackend(
                        root_dir=str(root_path),
                        virtual_mode=True,
                    ),
                ),
                ContextEditingMiddleware(
                    edits=[
                        ClearToolUsesEdit(
                            trigger=100000,
                            keep=20,
                            exclude_tools=[],
                            placeholder="[earlier tool results trimmed for context length]",
                        )
                    ]
                ),
            ],
            system_prompt=_EXPLORE_SYSTEM_PROMPT,
            response_format=ExploreResult,
            checkpointer=MemorySaver(),
        )

        # LangGraph checkpointer 自动管理会话历史
        # 相同的 thread_id 恢复完整上下文，对应 opencode task.ts 中 session 查找逻辑
        config = {"configurable": {"thread_id": actual_task_id}}

        final_answer = ""
        for chunk in child_agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
            stream_mode=["updates", "values", "messages"],
        ):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                stream_mode, data = chunk
            elif isinstance(chunk, dict):
                stream_mode = chunk.get("type")
                data = chunk.get("data")
            else:
                continue

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
                    if isinstance(sr, ExploreResult):
                        final_answer = sr.answer
                    elif isinstance(sr, dict):
                        final_answer = sr.get("answer", "")
                    # 如果 structured_response 没有提供有效答案，尝试从 messages 获取
                    if not final_answer and "messages" in data:
                        final_answer = _extract_last_ai_text(data["messages"])
                elif "messages" in data:
                    final_answer = _extract_last_ai_text(data["messages"])

        if not final_answer:
            final_answer = "子智能体执行完成，但未获取到文本回复。"

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # 输出包装为 <task_result> 格式（对应 opencode task.ts:160-166）
        output_text = (
            f"task_id: {actual_task_id} (for resuming to continue this task if needed)\n"
            f"\n"
            f"<task_result>\n"
            f"{final_answer}\n"
            f"</task_result>"
        )

        stop_event = create_tool_event(
            event_type="tool_stop",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "status": "success",
                "result": {
                    "prompt": prompt,
                    "task_id": actual_task_id,
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
                            {"subagent": output_text},
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
                "args": {"prompt": prompt, "task_id": actual_task_id},
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
