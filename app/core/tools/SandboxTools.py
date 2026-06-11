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
                writer(dict(create_tool_event(
                    event_type="tool_progress",
                    tool=tool_name,
                    tool_call_id=tool_call_id,
                    data={
                        "child_stream": data,
                        "message": "沙箱子智能体执行中",
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
