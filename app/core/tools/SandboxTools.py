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
    通过 session_path_manager 获取日期化上传目录 data/upload/{yyyy}/{mm}/{dd}/{session_id} 作为 workspace。
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
import traceback
from datetime import datetime
from pathlib import Path

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from deepagents import create_deep_agent

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.config.settings import settings
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools._stop_signal import get_current_request
from app.core.tools.events import create_tool_event
from app.core.tools.subagent_message_extractor import extract_structured_messages
from app.core.tools.subagent_registry import get_subagent_meta
from app.shared.tools.middleware.docker_sandbox_backend import DockerSandboxMiddleware
from docker.errors import DockerException
from app.shared.utils.files.session_path_manager import get_session_upload_dir
from app.shared.utils.memory.checkpoint import get_async_checkpointer

# 2026-06-15 新增：停止信号检测间隔（每 N 个 chunk 检测一次 is_disconnected）
# 5 个 chunk 检测一次足够在 200-500ms 内响应停止（LLM token 生成约 40-100ms/个），
# 避免每 chunk await 引入额外延迟。
_STOP_CHECK_INTERVAL = 5

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


# Python / Shell 关键字集合，用于在缺少 markdown ``` 包裹时启发式识别代码块
_PY_KEYWORDS = (
    "def ", "import ", "from ", "class ", "print(", "if __name__",
    "return ", "pass", "raise ", "yield ", "with ", "as ", "global ",
    "elif ", "else:", "except ", "finally:", "try:", "lambda ",
)
_PY_LINE_STARTERS = (
    "def ", "class ", "import ", "from ", "return ", "if ", "for ",
    "while ", "try:", "except ", "with ", "lambda ", "pass", "break",
    "continue", "raise ", "yield ", "global ", "nonlocal ", "del ",
)
_SH_KEYWORDS = ("echo ", "if [", "then", "fi", "for ", "do", "done", "case ", "esac")


def _is_probable_code_line(line: str) -> tuple[bool, str]:
    """
    启发式判断单行文本是否像代码

    Args:
        line: 单行文本（已 strip）

    Returns:
        tuple[bool, str]: (是否像代码, 语言标识 python/bash/text)
    """
    stripped = line.strip()
    if not stripped:
        return False, "text"
    # Shell 优先（防止 `if [` 被 Python 的 if 误判）
    if any(stripped.startswith(kw) or kw in stripped for kw in _SH_KEYWORDS):
        return True, "bash"
    if stripped.startswith(("#!/bin/", "#!/usr/bin/")):
        return True, "bash"
    # 缩进开头的多行结构（Python 缩进语法特征）
    if line.startswith(("    ", "\t", "        ")):
        if (
            any(kw in stripped for kw in _PY_KEYWORDS)
            or "=" in stripped
            or stripped.endswith(":")
            or "(" in stripped
        ):
            return True, "python"
    if any(stripped.startswith(kw) for kw in _PY_LINE_STARTERS):
        return True, "python"
    if any(kw in stripped for kw in _PY_KEYWORDS):
        return True, "python"
    return False, "text"


def _extract_code_blocks_heuristic(content: str, min_lines: int = 2) -> list:
    """
    在缺少 markdown ``` 包裹时，启发式提取连续的多行代码块

    策略：从文本中找到所有"像代码"的连续行（至少 min_lines 行），
    将其作为一个代码块返回。主要用于 LLM 在 AIMessage 中**不**用 markdown
    包裹代码的场景（Anthropic Claude 倾向）。

    Args:
        content: 消息文本内容
        min_lines: 最少连续多少行算一个代码块，默认 2

    Returns:
        list: 提取到的代码块列表（每个元素是连续的多行代码）
    """
    if not content:
        return []
    lines = content.splitlines()
    blocks = []
    buf: list[str] = []
    buf_lang = "text"

    def flush() -> None:
        nonlocal buf, buf_lang
        if len(buf) >= min_lines:
            code = "\n".join(buf).strip("\n")
            if code:
                blocks.append((code, buf_lang))
        buf = []
        buf_lang = "text"

    for line in lines:
        ok, lang = _is_probable_code_line(line)
        if ok:
            # 同一代码块内的语言推断取最频繁出现的
            if buf and lang != "text" and buf_lang == "text":
                buf_lang = lang
            elif lang != "text":
                buf_lang = lang
            buf.append(line)
        else:
            flush()
    flush()
    return blocks


def _extract_text_from_message_content(content) -> str:
    """
    从 langchain Message 的 content 字段提取纯文本（防御性 fallback）

    langchain-core 1.x 中 AIMessage 已经提供 `.text` 属性自动处理 str / list[ContentBlock]
    两种格式；本函数用于以下场景：
    - 非 langchain Message 对象（如测试中的 Mock、str/int/None 等）
    - 自定义消息类型未实现 `.text` 属性时的兜底

    Args:
        content: 任意类型的 content 字段

    Returns:
        str: 提取出的纯文本（strip 后）；空内容返回 ""
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in ("text", None) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                # Anthropic 风格的 tool_use 等其它 block 不参与文本拼接
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"].strip()
        if isinstance(content.get("content"), str):
            return content["content"].strip()
        return str(content).strip()
    return str(content).strip()


def _get_message_text(msg) -> str:
    """
    统一从 langchain BaseMessage 派生对象获取纯文本

    优先使用 langchain 内置的 `.text` 属性（langchain-core 1.x 自动处理 str /
    list[ContentBlock] 两种格式），仅在缺失时回退到 `_extract_text_from_message_content`。

    Args:
        msg: langchain BaseMessage 派生的消息对象

    Returns:
        str: 提取出的纯文本（strip 后）
    """
    if msg is None:
        return ""
    text_attr = getattr(msg, "text", None)
    if isinstance(text_attr, str):
        return text_attr.strip()
    return _extract_text_from_message_content(getattr(msg, "content", None))


def _extract_ai_tool_calls(msg) -> list[dict]:
    """
    从 AIMessage 中提取 LLM 决策的工具调用

    兼容两种来源：
    1. **OpenAI 风格**：`msg.tool_calls` 字段（非空 list）
    2. **Anthropic 风格**：`msg.content` 是 list，包含 `type == 'tool_use'` 的块
       （langchain-core 1.x 会在 `msg.content_blocks` 中归一化为 `type == 'non_standard'`）

    返回的字典统一使用 `name` / `args` 字段，便于下游统一处理。

    Args:
        msg: langchain AIMessage 或类似对象

    Returns:
        list[dict]: 工具调用列表，每项为 `{"name": str, "args": dict, "id": str|None}`
    """
    results: list[dict] = []
    if msg is None:
        return results

    # 1) OpenAI 风格：独立 tool_calls 字段
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("name") or ""
            args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
            results.append({"name": name, "args": args, "id": tc.get("id")})

    # 2) Anthropic 风格 / 通用风格：从 content_blocks 中提取
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
                    # Anthropic 用 "input" 字段，OpenAI 用 "args"，归一化为 "args"
                    args = value.get("input")
                    if not isinstance(args, dict):
                        args = {}
                    results.append({"name": name, "args": args, "id": value.get("id")})

    return results


def _ai_tool_call_to_event(tool_call: dict, current_step: int) -> dict:
    """
    将 AIMessage 中的单个 tool_call 转换为沙盒事件

    判断优先级：
    1. 工具名（最权威，write_file 永远视为写文件，即使 input 中无 content 字段）
    2. args.command → command_execute
    3. args.file_path + 工具名含 write/edit → file_write
    4. args.file_path → file_read（兜底：仅有路径但工具名不明确）

    Args:
        tool_call: 来自 `_extract_ai_tool_calls` 的统一格式 dict
        current_step: 当前步骤序号

    Returns:
        dict: 沙盒事件字典
    """
    name = (tool_call.get("name") or "").lower()
    args = tool_call.get("args") or {}
    command = args.get("command") if isinstance(args, dict) else None
    file_path = args.get("file_path") or args.get("path") if isinstance(args, dict) else None

    # 工具名优先判断（最权威的语义信号）
    if "write" in name or "edit" in name:
        event_type = "file_write"
        title = "决策：写入文件"
    elif "read" in name or "ls" in name or "glob" in name or "grep" in name:
        event_type = "file_read"
        title = "决策：读取文件"
    elif "execute" in name or "run" in name:
        event_type = "command_execute"
        title = "决策：执行命令"
    elif command:
        event_type = "command_execute"
        title = "决策：执行命令"
    elif file_path:
        # 工具名不明确但有 file_path，兜底为读取（更安全，避免误判写入）
        event_type = "file_read"
        title = "决策：读取文件"
    else:
        event_type = "command_execute"
        title = "决策：执行操作"

    event: dict = {
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
    return event


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
            if tool_call:
                # JSON 格式的 ToolMessage（兼容现有测试与部分手动构造的消息）
                event = _convert_tool_call_to_event(tool_call, current_step)
            else:
                # 标准 LangChain ToolMessage：content 为执行结果，name 为工具名
                tool_name = getattr(msg, "name", "") or ""
                raw_content = getattr(msg, "content", "")
                content_str = raw_content if isinstance(raw_content, str) else str(raw_content)

                if "write" in tool_name.lower():
                    event_type = "file_write"
                    title = "写入文件"
                elif "read" in tool_name.lower():
                    event_type = "file_read"
                    title = "读取文件"
                elif "execute" in tool_name.lower() or "run" in tool_name.lower():
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
                if content_str and len(content_str) < 5000:
                    event["content"] = content_str

            events.append(event)
            current_step = min(current_step + 1, 5)
            continue

        # 识别 AI 生成的代码（优先按类型名匹配，否则按内容启发式匹配）
        is_ai_message = msg_type_name in ("AIMessage", "MockAIMessage", "_MockAIMessage")
        if not is_ai_message and hasattr(msg, "content") and not hasattr(msg, "tool_call_id"):
            # 对未知类型对象，若包含字符串 content 且无 tool_call_id，视为 AI 消息
            is_ai_message = True

        if is_ai_message:
            # 兼容 AIMessage.content 为 str / list[ContentBlock] / None 的情况
            # 优先用 langchain 内置 .text 属性（langchain-core 1.x 自动归一化）
            text = _get_message_text(msg)
            if text:
                code_blocks = _extract_code_blocks(text)
                if not code_blocks:
                    # markdown ``` 包裹缺失时降级用启发式提取（Anthropic 场景）
                    heuristic_blocks = _extract_code_blocks_heuristic(text)
                    if heuristic_blocks:
                        code_blocks = [
                            code for code, _lang in heuristic_blocks
                        ]
                        heuristic_langs = [lang for _code, lang in heuristic_blocks]
                    else:
                        heuristic_langs = []
                else:
                    heuristic_langs = []
                if code_blocks:
                    # 取首块的语言标识（启发式时使用启发式结果，否则用 _detect_language）
                    lang = (
                        heuristic_langs[0]
                        if heuristic_langs
                        else _detect_language(code_blocks[0])
                    )
                    events.append({
                        "timestamp": int(time.time() * 1000),
                        "step": 1,
                        "type": "code_generation",
                        "title": "生成执行代码",
                        "content": code_blocks[0],
                        "language": lang,
                        "status": "completed",
                    })
                    current_step = max(current_step, 2)

            # 提取 LLM 决策的工具调用（前置事件），覆盖 OpenAI/Anthropic 两种风格
            ai_tool_calls = _extract_ai_tool_calls(msg)
            for tc in ai_tool_calls:
                events.append(_ai_tool_call_to_event(tc, current_step))
                current_step = min(current_step + 1, 5)

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
async def sandbox(  # 2026-06-15: 改 async，支持子智能体停止信号感知
    prompt: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    启动沙箱子智能体，在隔离的 Docker 容器中执行代码和文件操作。

    子智能体挂载 DockerSandboxMiddleware（继承 FilesystemMiddleware），
    提供完整的沙箱工具集：ls, read_file, write_file, edit_file, glob, grep, execute。

    使用 LangGraph MemorySaver checkpointer 管理子智能体会话。

    ## 2026-06-15 新增：用户停止信号感知

    通过 ``app.core.tools._stop_signal`` 取出当前请求的 FastAPI Request，
    在 ``child_agent.astream()`` 循环中每 ``_STOP_CHECK_INTERVAL`` 个 chunk 检测一次
    ``request.is_disconnected()``，发现客户端断开（停止按钮触发）时立即：

    1. 跳出 astream 循环
    2. 推送 ``tool_stop`` 事件，``data.status = "stopped_by_user"``（前端可识别）
    3. 清理 Docker 容器资源（``middleware.cleanup()``）
    4. 返回 ``Command`` 包含「子智能体已被用户中止」文本，让父 LLM 知道该子任务被中断

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

    # 2026-06-15 新增：从 ContextVar 取出当前 FastAPI Request（可能为 None）
    # None 场景：非 HTTP 上下文（如直接调用工具函数做测试）
    # 此时跳过 is_disconnected 检测，正常跑完子智能体
    request = get_current_request()

    # 增加 runtime.context 全链路日志与空值保护
    logger.info(
        "[sandbox] tool_call_id=%s, runtime_type=%s, has_context=%s, context_type=%s, context=%s",
        tool_call_id,
        type(runtime).__name__,
        hasattr(runtime, "context"),
        type(getattr(runtime, "context", None)).__name__,
        getattr(runtime, "context", None),
    )
    context = getattr(runtime, "context", None)
    if not isinstance(context, dict):
        logger.warning(
            "[sandbox] runtime.context is missing or not a dict! "
            "runtime=%s, context=%s. Falling back to 'default'.",
            runtime,
            context,
        )
        context = {}
    session_id = context.get("session_id", "default")
    project_id = context.get("project_id")  # 2026-06-30 新增：项目目录路由

    # 构建工作目录路径
    # 注意：这是沙箱 workspace 的统一创建入口。
    # DockerSandboxBackend / DockerSandboxMiddleware 不再自行创建工作目录，
    # 必须由调用方提前创建并传入。
    # 工作空间指向原文件上传目录；实际读取时由 FilesystemBackend.read 猴补丁映射到 .md 缓存文件。
    # 2026-06-30 改造：有 project_id 时走项目独立目录，否则走 session 目录
    workspace = get_session_upload_dir(session_id, create=True, project_id=project_id)

    try:
        # workspace 已由 get_session_upload_dir 创建

        # 发送工具开始事件
        start_event = create_tool_event(
            event_type="tool_start",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "args": {"prompt": prompt},
                "workspace": str(workspace),
                "description": f"启动沙箱子智能体: {prompt[:100]}",
                # ===== 2026-06-13 新增 subagent 字段（向前兼容，老客户端忽略） =====
                "thread_id": tool_call_id,
                "parent_prompt": prompt,
                # 2026-06-18 新增：展示元信息由后端统一提供，降低前端耦合
                "meta": get_subagent_meta(tool_name),
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

        # 读取沙箱容器化部署配置（2026-06-12 重构：从 Pydantic Settings 注入）
        sandbox_cfg = settings.get_sandbox_config()

        # 创建 Docker 沙箱中间件
        middleware = DockerSandboxMiddleware(
            session_id=session_id,
            workspace=str(workspace),
            image=sandbox_cfg["image"],
            max_memory_mb=sandbox_cfg["max_memory_mb"],
            max_cpu_percent=sandbox_cfg["max_cpu_percent"],
            network_enabled=sandbox_cfg["network_enabled"],
            default_timeout=sandbox_cfg["default_timeout"],
            docker_mode=sandbox_cfg["docker_mode"],
            docker_host=sandbox_cfg["docker_host"],
            host_workspace_prefix=sandbox_cfg["host_workspace_prefix"],
            container_workspace=sandbox_cfg["container_workspace"],
            fallback_to_local=sandbox_cfg["fallback_to_local"],
        )

        # 2026-06-16 改造：使用全局共享 checkpointer（PostgreSQL/Memory）持久化子智能体消息
        # 原 MemorySaver() 是进程内临时实例，子智能体返回后 messages 全部丢失，
        # 导致 GET /api/session/{id}/messages 无法恢复 sandbox 轨迹。
        # 改为全局 checkpointer 后，子智能体 messages 按 thread_id=tool_call_id 落库，
        # 切会话重新加载时可通过 CheckpointHistoryService.get_subagent_history 反查。
        child_checkpointer = await get_async_checkpointer()

        # 创建 deep agent 子智能体
        child_agent = create_deep_agent(
            model=model,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            middleware=[middleware],
            checkpointer=child_checkpointer,
            name="sandbox",
        )

        # 使用 tool_call_id 作为 thread_id 支持会话恢复（与全局 checkpointer 共享同一张表）
        config = {"configurable": {"thread_id": tool_call_id}}

        final_answer = ""
        all_messages = []
        # 2026-06-15 新增：用户主动停止标志（与正常完成 / 异常分支并列）
        stopped_by_user = False

        # 2026-06-15 改造：sync stream → async astream
        # 原因：需要在每次 __anext__ 之间 await request.is_disconnected() 检测停止信号
        async for chunk in child_agent.astream(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
            stream_mode=["updates", "values", "messages"],
        ):
            # 2026-06-15 新增：客户端断开检测（每 N 个 chunk 检测一次）
            if request is not None and len(all_messages) % _STOP_CHECK_INTERVAL == 0:
                try:
                    if await request.is_disconnected():
                        logger.info(
                            "[sandbox] 客户端已断开，停止子智能体。tool_call_id=%s",
                            tool_call_id,
                        )
                        stopped_by_user = True
                        break
                except Exception as e:
                    logger.warning(f"[sandbox] is_disconnected 检测异常: {e}")

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
                        # ===== 2026-06-13 新增 subagent 字段 =====
                        "thread_id": tool_call_id,
                        "child_messages": extract_structured_messages(all_messages),
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

        # ===== 2026-06-15 新增：用户停止分支（与正常完成并列）=====
        if stopped_by_user:
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            final_answer = "子智能体已被用户中止"

            # 推送 tool_stop 事件，status='stopped_by_user' 供前端识别
            stopped_summary = {
                "current_step": 0,
                "total_steps": len(SANDBOX_STEPS),
                "progress_pct": 0,
                "status_message": "已被用户中止",
                "status_icon": "⏹️",
                "elapsed_ms": duration_ms,
                "completed_steps": 0,
                "final_status": "已被用户中止",
                "result_preview": final_answer,
            }
            stop_event = create_tool_event(
                event_type="tool_stop",
                tool=tool_name,
                tool_call_id=tool_call_id,
                data={
                    "status": "stopped_by_user",  # 区别于 'success' / 'failure'
                    "result": {
                        "prompt": prompt,
                        "answer": final_answer,
                    },
                    "duration_ms": duration_ms,
                    "final_summary": stopped_summary,
                    # ===== 2026-06-13 新增 subagent 字段 =====
                    "thread_id": tool_call_id,
                    "parent_prompt": prompt,
                    "final_messages": extract_structured_messages(all_messages),
                },
            )
            writer(dict(stop_event))

            # 关键：清理 Docker 容器资源（断开时必须执行，避免容器残留）
            try:
                middleware.cleanup()
                logger.info("[sandbox] 子智能体停止后 Docker 容器已清理")
            except Exception as e:
                logger.warning(f"[sandbox] 清理 Docker 容器异常: {e}")

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

        # ===== 原有正常结束逻辑 =====
        # 如果还没有获取到有效答案，从循环内累计的 all_messages 中提取最后一条 AI 文本。
        # 不能用 data["messages"]：data 是最后一个流块的数据，当最后一块是 updates 模式时
        # data = {node_name: {state_delta}}，没有顶层 messages 键（修复前 bug 现场）。
        if not final_answer and all_messages:
            final_answer = _extract_last_ai_text(all_messages)

        # 兜底：仅在确实没有任何 AI 文本产出时才使用；同时记录 warning 便于排查
        if not final_answer:
            logger.warning(
                "[sandbox] 兜底触发：未从 all_messages 中取到 AI 文本。"
                "tool_call_id=%s, all_messages_count=%d, last_stream_mode=%s",
                tool_call_id,
                len(all_messages),
                stream_mode,
            )
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
                # ===== 2026-06-13 新增 subagent 字段 =====
                "thread_id": tool_call_id,
                "parent_prompt": prompt,
                "final_messages": extract_structured_messages(all_messages),
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

    except (RuntimeError, DockerException) as e:
        # Docker 初始化失败且未开启 fallback_to_local 时的干净降级路径
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        error_message = str(e)
        logger.warning(
            "[sandbox] Docker 不可用且未开启 fallback_to_local，工具拒绝执行。"
            "tool_call_id=%s, error=%s",
            tool_call_id,
            error_message,
        )

        user_message = (
            "沙箱执行失败：Docker daemon 未运行或未安装。"
            "如需在本地环境继续运行，可设置 SANDBOX_FALLBACK_TO_LOCAL=true（注意：会失去 Docker 隔离）。"
        )
        error_event = create_tool_event(
            event_type="tool_error",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "error_type": type(e).__name__,
                "error_message": error_message,
                "args": {"prompt": prompt},
                "duration_ms": duration_ms,
                "thread_id": tool_call_id,
                "parent_prompt": prompt,
            },
        )
        writer(dict(error_event))

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {"subagent": user_message},
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

        logger.error("sandbox 工具执行失败: %s\n%s", e, traceback.format_exc())

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
                # ===== 2026-06-13 新增 subagent 字段 =====
                "thread_id": tool_call_id,
                "parent_prompt": prompt,
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
