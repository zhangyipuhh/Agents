#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FilesystemReadTools - 文件系统探索工具模块

该模块定义 `explore` 工具，启动探索子智能体，在单个子智能体中完成路径搜索 +
文件读取 + 内容分析。

设计对照 opencode:
    - opencode task.txt (父 LLM 工具描述)  →  @tool(description=...)
    - opencode explore.txt (子智能体 prompt) → _EXPLORE_SYSTEM_PROMPT
    - opencode Task(prompt=, subagent_type="explore") → explore(prompt=)

工作空间:
    通过 Path.cwd() 反向定位项目根目录，拼接 data/upload/{session_id} 作为 root_path。
    root_path 限定子智能体的操作范围，确保只读安全。

子智能体可用工具:
    - TodoListMiddleware:  write_todos 规划步骤
    - EncodingSafeFileSearchMiddleware:  glob_search + grep_search（编码安全）
    - FilesystemMiddleware:  ls + read_file

流式事件:
    使用 get_stream_writer() + create_tool_event() 向前端推送 tool_start / tool_progress /
    tool_stop 事件。通用执行逻辑已下沉到 `app.core.tools.base.BaseFilesystemTool`。

Date: 2026-05-07
Author: AI Assistant
"""

from pathlib import Path

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.core.agent.AgentContext import AgentContext
from app.core.tools.base import BaseFilesystemTool


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
async def explore(
    prompt: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    启动探索子智能体，读取当前 session 上传目录中的文件并分析。

    该工具仅面向当前会话上传目录 `data/upload/{session_id}`，知识库检索请使用
    `query_knowledge` 工具。

    Args:
        prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
                包含搜索目标、预期返回信息、操作约束等。
        runtime: 工具运行时上下文，包含 session_id 与 tool_call_id。

    Returns:
        Command: 子智能体的文件搜索与分析结果。
    """
    session_id = runtime.context.get("session_id", "default")
    root_path = Path.cwd() / "data" / "upload" / session_id

    tool = BaseFilesystemTool(
        tool_name="explore",
        system_prompt=_EXPLORE_SYSTEM_PROMPT,
        response_format=ExploreResult,
    )
    return await tool.arun(prompt, runtime, root_path)
