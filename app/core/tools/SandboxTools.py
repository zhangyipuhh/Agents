#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SandboxTools - 沙箱子智能体工具模块

该模块定义 sandbox 工具，启动沙箱子智能体，在隔离的 Docker 容器中执行代码和文件操作。

设计对标 FilesystemReadTools.explore:
    - 使用 create_deep_agent (deepagents) 创建子智能体
    - 使用 DockerSandboxMiddleware 提供隔离执行环境
    - 支持流式事件输出 (tool_start / tool_progress / tool_stop)

工作空间:
    通过 Path.cwd() 反向定位项目根目录，拼接 app/data/upload/{session_id}/sandbox 作为 workspace。
    每个 session 拥有独立的沙箱工作目录。

子智能体可用工具:
    - DockerSandboxMiddleware 继承 FilesystemMiddleware 提供:
        ls, read_file, write_file, edit_file, glob, grep, execute

流式事件:
    使用 get_stream_writer() + create_tool_event() 向前端推送 tool_start / tool_progress / tool_stop 事件。

Date: 2026-06-12
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.types import Command

from deepagents import create_deep_agent

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools.events import create_tool_event
from app.shared.tools.middleware.docker_sandbox_backend import DockerSandboxMiddleware

logger = logging.getLogger(__name__)

# 预定义沙盒执行的步骤模板
SANDBOX_STEPS = [
    {"step": 1, "name": "code_generation", "label": "生成代码", "icon": "📝"},
    {"step": 2, "name": "file_write", "label": "写入文件", "icon": "💾"},
    {"step": 3, "name": "command_execute", "label": "执行代码", "icon": "▶️"},
    {"step": 4, "name": "command_output", "label": "获取输出", "icon": "📤"},
    {"step": 5, "name": "result_analysis", "label": "分析结果", "icon": "✅"},
]


def _detect_language(code: str) -> str:
    """
    根据代码内容检测编程语言

    Args:
        code: 代码字符串

    Returns:
        str: 检测到的语言标识
    """
    if not code:
        return "text"
    first_line = code.strip().split("\n", 1)[0]
    if first_line.startswith("#!/bin/bash") or first_line.startswith("#!/bin/sh"):
        return "bash"
    if first_line.startswith("#!/usr/bin/env python") or first_line.startswith("#!/usr/bin/python"):
        return "python"
    # 简单启发式检测
    indicators = {
        "python": ["def ", "import ", "print(", "class ", "if __name__"],
        "javascript": ["function ", "const ", "let ", "var ", "=>", "console.log"],
        "typescript": ["interface ", "type ", ": string", ": number", ": boolean"],
        "java": ["public class", "public static", "System.out.println"],
        "go": ["package main", "func main", "fmt.Println"],
        "rust": ["fn main", "let mut", "println!"],
        "bash": ["echo ", "if [", "then", "fi", "for ", "do", "done"],
    }
    scores = {lang: 0 for lang in indicators}
    for lang, keywords in indicators.items():
        for kw in keywords:
            if kw in code:
                scores[lang] += 1
    if scores:
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return best
    return "text"


def _extract_code_blocks(content: str) -> list:
    """
    从消息文本中提取代码块

    Args:
        content: 消息文本内容

    Returns:
        list: 提取到的代码块列表
    """
    if not content:
        return []
    blocks = []
    # 匹配 ```language\ncode\n``` 格式
    import re
    pattern = r"```(?:\w+)?\n(.*?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)
    for match in matches:
        stripped = match.strip()
        if stripped:
            blocks.append(stripped)
    return blocks


def _extract_tool_call(msg) -> dict:
    """
    从 ToolMessage 中提取工具调用信息

    Args:
        msg: ToolMessage 对象

    Returns:
        dict: 工具调用信息字典，若无法提取则返回 None
    """
    if not hasattr(msg, "content"):
        return None
    content = msg.content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _convert_tool_call_to_event(tool_call: dict, current_step: int) -> dict:
    """
    将工具调用转换为沙盒事件

    Args:
        tool_call: 工具调用信息字典
        current_step: 当前步骤序号

    Returns:
        dict: 沙盒事件字典
    """
    # 根据工具调用内容推断事件类型
    tool_name = tool_call.get("tool") or tool_call.get("name") or ""
    content = tool_call.get("content") or tool_call.get("result") or ""
    command = tool_call.get("command") or ""
    file_path = tool_call.get("file_path") or tool_call.get("path") or ""

    if command:
        event_type = "command_execute"
        title = "执行命令"
    elif file_path and content:
        event_type = "file_write"
        title = "写入文件"
    elif file_path:
        event_type = "file_read"
        title = "读取文件"
    elif "write" in str(tool_name).lower():
        event_type = "file_write"
        title = "写入文件"
    elif "read" in str(tool_name).lower():
        event_type = "file_read"
        title = "读取文件"
    elif "execute" in str(tool_name).lower() or "run" in str(tool_name).lower():
        event_type = "command_execute"
        title = "执行命令"
    else:
        event_type = "command_execute"
        title = "执行操作"

    event = {
        "timestamp": int(time.time() * 1000),
        "step": current_step,
        "type": event_type,
        "title": title,
        "status": "completed",
    }
    if command:
        event["command"] = command
    if file_path:
        event["file_path"] = file_path
    if content and isinstance(content, str) and len(content) < 5000:
        event["content"] = content
    return event


def _get_status_icon(current_step: int, total_messages: int) -> str:
    """
    根据当前步骤获取状态图标

    Args:
        current_step: 当前步骤序号
        total_messages: 消息总数

    Returns:
        str: 状态图标字符串
    """
    if current_step <= len(SANDBOX_STEPS):
        return SANDBOX_STEPS[current_step - 1]["icon"]
    return "⏳"


def _extract_sandbox_summary_and_events(messages: list, start_time: datetime) -> tuple:
    """
    从子智能体消息中提取摘要信息和事件列表

    Args:
        messages: 子智能体消息列表
        start_time: 沙盒执行开始时间

    Returns:
        tuple: (summary_dict, events_list)
    """
    events = []
    current_step = 1

    for msg in messages:
        msg_type_name = type(msg).__name__
        content = getattr(msg, "content", None)
        tool_call = _extract_tool_call(msg)

        # 识别工具调用（优先按类型名匹配，否则按内容启发式匹配）
        is_tool_message = msg_type_name in ("ToolMessage", "MockToolMessage", "_MockToolMessage")
        if not is_tool_message and tool_call:
            # 若能解析出工具调用结构，视为 Tool 消息
            is_tool_message = True

        if is_tool_message:
            event = _convert_tool_call_to_event(tool_call, current_step)
            events.append(event)
            current_step = min(current_step + 1, 5)
            continue

        # 识别 AI 生成的代码（优先按类型名匹配，否则按内容启发式匹配）
        is_ai_message = msg_type_name in ("AIMessage", "MockAIMessage", "_MockAIMessage")
        if not is_ai_message and hasattr(msg, "content") and not hasattr(msg, "tool_call_id"):
            # 对未知类型对象，若包含字符串 content 且无 tool_call_id，视为 AI 消息
            is_ai_message = True

        if is_ai_message:
            if isinstance(content, str) and content.strip():
                code_blocks = _extract_code_blocks(content)
                if code_blocks:
                    events.append({
                        "timestamp": int(time.time() * 1000),
                        "step": 1,
                        "type": "code_generation",
                        "title": "生成执行代码",
                        "content": code_blocks[0],
                        "language": _detect_language(code_blocks[0]),
                        "status": "completed",
                    })
                    current_step = max(current_step, 2)

    # 生成摘要
    total_steps = len(SANDBOX_STEPS)
    progress_pct = min(int(current_step / total_steps * 100), 100)
    status_message = (
        SANDBOX_STEPS[current_step - 1]["label"]
        if current_step <= total_steps
        else "执行完成"
    )
    elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

    summary = {
        "current_step": current_step,
        "total_steps": total_steps,
        "progress_pct": progress_pct,
        "status_message": status_message,
        "status_icon": _get_status_icon(current_step, len(messages)),
        "elapsed_ms": elapsed_ms,
    }

    return summary, events


SANDBOX_SYSTEM_PROMPT = """\
你是一个安全沙箱智能体，负责在隔离的 Docker 容器中执行代码和文件操作。

## 核心职责

1. 根据用户请求，编写并执行 Python 或 Shell 代码
2. 安全地操作文件系统（创建、读取、编辑、删除文件）
3. 向用户返回执行结果，包括输出、错误和文件变更

## 安全规则

- **默认禁用网络**：容器无法访问外网，请勿尝试下载外部资源
- **资源受限**：容器有内存和 CPU 限制，避免执行高资源消耗任务
- **超时保护**：命令执行有超时限制，避免死循环
- **工作目录隔离**：所有文件操作限制在当前会话的工作目录内
- **禁止危险命令**：不要执行 `rm -rf /`、`mkfs`、`dd` 等破坏性命令

## 工具使用规范

- `execute`：执行 shell 命令，适用于运行脚本、安装包（若镜像已含）
- `write_file`：创建新文件
- `read_file`：读取文件内容
- `edit_file`：修改文件内容
- `ls`：列出目录内容
- `glob` / `grep`：搜索文件

## 输出要求

- 执行代码后，向用户说明执行结果
- 如有错误，提供清晰的错误信息和可能的解决方案
- 文件操作后，告知用户文件路径和内容摘要
- 保持简洁，禁止铺垫和总结
"""


def _extract_last_ai_text(messages: list) -> str:
    """
    从 messages 列表中提取最后一条 AI 消息的文本内容，作为兜底回答。

    Args:
        messages: 消息列表

    Returns:
        str: 最后一条 AI 消息的文本内容，如果没有则返回空字符串
    """
    for msg in reversed(messages):
        # 使用类型名称检查，避免在测试环境中 isinstance 失败
        msg_type_name = type(msg).__name__

        # 跳过 HumanMessage
        if msg_type_name in ('HumanMessage', 'MockHumanMessage', '_MockHumanMessage'):
            continue

        # 只处理 AIMessage 或带有 content 属性的消息
        if msg_type_name not in ('AIMessage', 'MockAIMessage', '_MockAIMessage') and not hasattr(msg, 'content'):
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
    "Launch a sandbox subagent to safely execute code and file operations in an isolated Docker container.\n"
    "The sandbox agent specializes in running Python/Shell code and performing file operations securely.\n\n"
    "## When to use\n"
    "- When you need to execute user-provided code safely\n"
    "- When you need to perform data analysis or processing\n"
    "- When you need to create, read, edit files in an isolated environment\n"
    "- When the task involves code execution that should not affect the host system\n\n"
    "## When NOT to use\n"
    "- If you only need to read existing files on the host, use read_file directly\n"
    "- If you only need to search files, use glob_search/grep_search directly\n"
    "- For tasks that don't require code execution or file operations\n\n"
    "## Prompt writing rules (CRITICAL)\n"
    "The prompt parameter must be a highly detailed task description for the subagent "
    "to perform autonomously. You must specify exactly what code to execute or what "
    "file operations to perform.\n"
    "Do NOT pass the user's raw message as prompt — formulate a detailed task instead.\n\n"
    "## Security\n"
    "The sandbox runs in an isolated Docker container with:\n"
    "- No network access (network_enabled=False)\n"
    "- Memory limit (default 512MB)\n"
    "- CPU limit (default 100%)\n"
    "- Timeout protection (default 60s)\n"
))
def sandbox(
    prompt: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    启动沙箱子智能体，在隔离的 Docker 容器中执行代码和文件操作。

    子智能体挂载 DockerSandboxMiddleware（继承 FilesystemMiddleware），
    提供完整的沙箱工具集：ls, read_file, write_file, edit_file, glob, grep, execute。

    使用 LangGraph MemorySaver checkpointer 管理子智能体会话。

    Args:
        prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
                包含要执行的代码、文件操作、预期返回信息等。
        runtime: 工具运行时对象（自动注入）

    Returns:
        Command: 包含子智能体执行结果的命令

    Raises:
        RuntimeError: Docker 不可用时抛出
    """
    tool_name = "sandbox"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    session_id = runtime.context.get("session_id", "default")

    # 构建工作目录路径
    project_root = Path.cwd()
    workspace = project_root / "app" / "data" / "upload" / session_id / "sandbox"

    try:
        # 确保工作目录存在
        workspace.mkdir(parents=True, exist_ok=True)

        # 发送工具开始事件
        start_event = create_tool_event(
            event_type="tool_start",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "args": {"prompt": prompt},
                "workspace": str(workspace),
                "description": f"启动沙箱子智能体: {prompt[:100]}",
            },
        )
        writer(dict(start_event))

        # 创建模型实例
        model = ModelFactory.create_model(
            model_type=LLM_CONFIG["model_type"],
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            temperature=LLM_CONFIG["temperature"],
            base_url=LLM_CONFIG["base_url"],
        )

        # 创建 Docker 沙箱中间件
        middleware = DockerSandboxMiddleware(
            session_id=session_id,
            workspace=str(workspace),
            image="python:3.12-alpine",
            max_memory_mb=512,
            max_cpu_percent=100,
            network_enabled=False,
            default_timeout=60,
        )

        # 创建 deep agent 子智能体
        child_agent = create_deep_agent(
            model=model,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            middleware=[middleware],
            checkpointer=MemorySaver(),
            name="sandbox",
        )

        # 使用 tool_call_id 作为 thread_id 支持会话恢复
        config = {"configurable": {"thread_id": tool_call_id}}

        final_answer = ""
        all_messages = []

        # 流式执行子智能体
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
                # 从 updates 数据中提取消息列表，用于生成摘要和事件
                extracted_messages = []
                if isinstance(data, dict):
                    for node_name, node_data in data.items():
                        if isinstance(node_data, dict) and "messages" in node_data:
                            extracted_messages.extend(node_data["messages"])
                if extracted_messages:
                    all_messages.extend(extracted_messages)

                # 生成沙盒摘要和事件
                sandbox_summary, sandbox_events = _extract_sandbox_summary_and_events(
                    all_messages, start_time
                )

                writer(dict(create_tool_event(
                    event_type="tool_progress",
                    tool=tool_name,
                    tool_call_id=tool_call_id,
                    data={
                        "child_stream": data,
                        "message": "沙箱子智能体执行中",
                        "sandbox_summary": sandbox_summary,
                        "sandbox_events": sandbox_events,
                    },
                )))

            if stream_mode == "values" and isinstance(data, dict):
                # 尝试从 structured_response 获取结果
                if "structured_response" in data:
                    sr = data["structured_response"]
                    if isinstance(sr, dict):
                        final_answer = sr.get("answer") or sr.get("content") or ""
                    elif isinstance(sr, str):
                        final_answer = sr

        # 如果还没有获取到有效答案，尝试从 messages 获取
        if not final_answer and "messages" in data:
            final_answer = _extract_last_ai_text(data["messages"])

        # 确保 final_answer 不为 None
        if not final_answer:
            final_answer = "沙箱子智能体执行完成，但未获取到文本回复。"

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # 构造输出文本
        output_text = (
            f"<task_result>\n"
            f"{final_answer}\n"
            f"</task_result>"
        )

        # 生成最终摘要
        final_summary, _ = _extract_sandbox_summary_and_events(all_messages, start_time)
        final_summary["completed_steps"] = final_summary["current_step"]
        final_summary["final_status"] = "执行完成"
        final_summary["result_preview"] = final_answer[:200] + "..." if len(final_answer) > 200 else final_answer

        # 发送工具停止事件
        stop_event = create_tool_event(
            event_type="tool_stop",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "status": "success",
                "result": {
                    "prompt": prompt,
                    "answer": final_answer,
                },
                "duration_ms": duration_ms,
                "final_summary": final_summary,
            },
        )
        writer(dict(stop_event))

        # 清理沙箱资源
        middleware.cleanup()

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

        logger.error("sandbox 工具执行失败: %s", e, exc_info=True)

        # 发送工具错误事件
        error_event = create_tool_event(
            event_type="tool_error",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "args": {"prompt": prompt},
                "duration_ms": duration_ms,
            },
        )
        writer(dict(error_event))

        # 异常时也要清理沙箱资源
        try:
            if 'middleware' in locals() and middleware is not None:
                middleware.cleanup()
        except Exception as cleanup_error:
            logger.warning("清理沙箱资源时出错: %s", cleanup_error)

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {"subagent": f"沙箱执行失败: {str(e)}"},
                            ensure_ascii=False,
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
