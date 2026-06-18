# -*- coding:utf-8 -*-
"""
SandboxTools 模块测试

测试范围:
- 辅助函数导入与存在性验证
- 沙盒步骤常量定义
- 代码块提取、语言检测、摘要生成等工具函数
"""

import json

import pytest
from datetime import datetime


def test_sandbox_tools_importable():
    """验证 SandboxTools 模块可导入"""
    from app.core.tools import SandboxTools
    assert SandboxTools is not None


def test_sandbox_steps_defined():
    """验证 SANDBOX_STEPS 常量已正确定义"""
    from app.core.tools.SandboxTools import SANDBOX_STEPS
    assert isinstance(SANDBOX_STEPS, list)
    assert len(SANDBOX_STEPS) == 5
    assert SANDBOX_STEPS[0]["name"] == "code_generation"
    assert SANDBOX_STEPS[4]["name"] == "result_analysis"


def test_detect_language_python():
    """验证 Python 代码语言检测"""
    from app.core.tools.SandboxTools import _detect_language
    code = "def hello():\n    print('Hello World')"
    assert _detect_language(code) == "python"


def test_detect_language_bash():
    """验证 Bash 代码语言检测"""
    from app.core.tools.SandboxTools import _detect_language
    code = "#!/bin/bash\necho 'Hello'"
    assert _detect_language(code) == "bash"


def test_detect_language_empty():
    """验证空代码返回 text"""
    from app.core.tools.SandboxTools import _detect_language
    assert _detect_language("") == "text"
    assert _detect_language(None) == "text"


def test_extract_code_blocks():
    """验证从 Markdown 文本中提取代码块"""
    from app.core.tools.SandboxTools import _extract_code_blocks
    text = "Some text\n```python\nprint(1)\n```\nMore text"
    blocks = _extract_code_blocks(text)
    assert len(blocks) == 1
    assert "print(1)" in blocks[0]


def test_extract_code_blocks_no_blocks():
    """验证无代码块时返回空列表"""
    from app.core.tools.SandboxTools import _extract_code_blocks
    assert _extract_code_blocks("No code here") == []
    assert _extract_code_blocks("") == []


def test_extract_tool_call_with_json_string():
    """验证从 ToolMessage 内容中提取 JSON 工具调用"""
    from app.core.tools.SandboxTools import _extract_tool_call

    class FakeMsg:
        content = '{"tool": "execute", "command": "ls -la"}'

    result = _extract_tool_call(FakeMsg())
    assert result is not None
    assert result["tool"] == "execute"


def test_extract_tool_call_invalid():
    """验证无法解析的内容返回 None"""
    from app.core.tools.SandboxTools import _extract_tool_call

    class FakeMsg:
        content = "not json"

    assert _extract_tool_call(FakeMsg()) is None


def test_convert_tool_call_to_event_command():
    """验证命令类工具调用转换为事件"""
    from app.core.tools.SandboxTools import _convert_tool_call_to_event
    tool_call = {"command": "python script.py", "tool": "execute"}
    event = _convert_tool_call_to_event(tool_call, 3)
    assert event["type"] == "command_execute"
    assert event["step"] == 3
    assert event["command"] == "python script.py"
    assert event["status"] == "completed"


def test_convert_tool_call_to_event_file_write():
    """验证文件写入类工具调用转换为事件"""
    from app.core.tools.SandboxTools import _convert_tool_call_to_event
    tool_call = {"file_path": "/tmp/test.py", "content": "x = 1", "tool": "write_file"}
    event = _convert_tool_call_to_event(tool_call, 2)
    assert event["type"] == "file_write"
    assert event["file_path"] == "/tmp/test.py"


def test_get_status_icon():
    """验证状态图标获取"""
    from app.core.tools.SandboxTools import _get_status_icon, SANDBOX_STEPS
    assert _get_status_icon(1, 0) == SANDBOX_STEPS[0]["icon"]
    assert _get_status_icon(5, 10) == SANDBOX_STEPS[4]["icon"]
    assert _get_status_icon(10, 0) == "⏳"


def test_extract_sandbox_summary_and_events_empty():
    """验证空消息列表返回默认摘要"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events
    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([], start)
    assert events == []
    assert summary["current_step"] == 1
    assert summary["total_steps"] == 5
    assert summary["progress_pct"] == 20


def test_extract_sandbox_summary_and_events_with_ai_message():
    """验证包含代码的 AI 消息被识别为 code_generation 事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeAIMessage:
        content = "```python\nprint('hello')\n```"

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeAIMessage()], start)
    assert len(events) == 1
    assert events[0]["type"] == "code_generation"
    assert summary["current_step"] == 2


def test_extract_sandbox_summary_and_events_with_tool_message():
    """验证 ToolMessage 被识别为工具事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeToolMessage:
        content = '{"command": "ls", "tool": "execute"}'

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeToolMessage()], start)
    assert len(events) == 1
    assert events[0]["type"] == "command_execute"
    assert summary["current_step"] == 2


def test_extract_sandbox_summary_and_events_with_standard_tool_message():
    """验证标准 LangChain ToolMessage（content 为纯文本）不抛 AttributeError，且能生成正确事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class ToolMessage:
        content = "Hello World"
        name = "execute"

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([ToolMessage()], start)
    assert len(events) == 1
    assert events[0]["type"] == "command_execute"
    assert events[0]["title"] == "执行命令"
    assert events[0]["content"] == "Hello World"
    assert summary["current_step"] == 2


def test_extract_sandbox_summary_and_events_with_tool_message_write_file():
    """验证标准 ToolMessage name 包含 write 时生成 file_write 事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class ToolMessage:
        content = "file written"
        name = "write_file"

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([ToolMessage()], start)
    assert len(events) == 1
    assert events[0]["type"] == "file_write"
    assert events[0]["title"] == "写入文件"
    assert events[0]["content"] == "file written"


def test_extract_sandbox_summary_and_events_with_tool_message_no_name():
    """验证标准 ToolMessage 无 name 时不抛异常，降级为默认执行操作事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class ToolMessage:
        content = "some output"
        # 没有 name 属性

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([ToolMessage()], start)
    assert len(events) == 1
    assert events[0]["type"] == "command_execute"
    assert events[0]["title"] == "执行操作"
    assert events[0]["content"] == "some output"


def test_sandbox_runtime_context_none():
    """验证 runtime.context 为 None 时不会在入口处触发 AttributeError"""
    from unittest.mock import patch
    from app.core.tools.SandboxTools import sandbox

    class FakeRuntime:
        tool_call_id = "call_test_001"
        context = None

    with patch("app.core.tools.SandboxTools.get_stream_writer"), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch("app.core.tools.SandboxTools.DockerSandboxMiddleware"), \
         patch("app.core.tools.SandboxTools.create_deep_agent") as mock_create_agent:

        mock_create_agent.side_effect = RuntimeError("expected_error")

        try:
            sandbox("test prompt", FakeRuntime())
        except AttributeError as e:
            pytest.fail(f"不应触发 AttributeError: {e}")
        except RuntimeError as e:
            assert str(e) == "expected_error"


# ---------------------------------------------------------------------------
# AIMessage 多类型 content 解析（2026-06-12 回归用例）
# ---------------------------------------------------------------------------


def test_extract_text_from_message_content_str():
    """str 类型 content 应被原样 strip 返回"""
    from app.core.tools.SandboxTools import _extract_text_from_message_content
    assert _extract_text_from_message_content("  hello world  ") == "hello world"
    assert _extract_text_from_message_content("") == ""


def test_extract_text_from_message_content_none():
    """None 类型 content 应返回空字符串"""
    from app.core.tools.SandboxTools import _extract_text_from_message_content
    assert _extract_text_from_message_content(None) == ""


def test_extract_text_from_message_content_list_text_blocks():
    """list[ContentBlock] 中多个 text 块应被拼接"""
    from app.core.tools.SandboxTools import _extract_text_from_message_content
    content = [
        {"type": "text", "text": "第一段"},
        {"type": "text", "text": "第二段"},
    ]
    assert _extract_text_from_message_content(content) == "第一段\n第二段"


def test_extract_text_from_message_content_list_mixed():
    """list 中混有 text + tool_use 时只取 text 块（Anthropic 风格）"""
    from app.core.tools.SandboxTools import _extract_text_from_message_content
    content = [
        {"type": "text", "text": "下面是代码："},
        {"type": "tool_use", "id": "tu1", "name": "write_file", "input": {"file_path": "/x.py"}},
        {"type": "text", "text": "再补充一点"},
    ]
    assert _extract_text_from_message_content(content) == "下面是代码：\n再补充一点"


def test_extract_text_from_message_content_dict():
    """dict 类型 content 应取 text/content 字段"""
    from app.core.tools.SandboxTools import _extract_text_from_message_content
    assert _extract_text_from_message_content({"text": "abc"}) == "abc"
    assert _extract_text_from_message_content({"content": "def"}) == "def"


def test_get_message_text_uses_text_attr():
    """当 msg 有 .text 属性时优先使用（模拟 langchain AIMessage）"""
    from app.core.tools.SandboxTools import _get_message_text

    class FakeMsg:
        content = [{"type": "text", "text": "from content"}]
        text = "from .text attr"

    assert _get_message_text(FakeMsg()) == "from .text attr"


def test_get_message_text_fallback_to_content():
    """当 msg 没有 .text 属性时回退到 content 字段"""
    from app.core.tools.SandboxTools import _get_message_text

    class FakeMsg:
        content = "raw content string"

    # 没有 .text 属性
    assert _get_message_text(FakeMsg()) == "raw content string"


def test_is_probable_code_line_python():
    """Python 关键字行应被识别为 python 代码"""
    from app.core.tools.SandboxTools import _is_probable_code_line
    is_code, lang = _is_probable_code_line("def hello():")
    assert is_code is True
    assert lang == "python"
    is_code, lang = _is_probable_code_line("import os")
    assert is_code is True and lang == "python"
    is_code, lang = _is_probable_code_line("    return x + 1")
    assert is_code is True and lang == "python"


def test_is_probable_code_line_bash():
    """Bash 关键字行应被识别为 bash 代码"""
    from app.core.tools.SandboxTools import _is_probable_code_line
    is_code, lang = _is_probable_code_line("echo hello")
    assert is_code is True and lang == "bash"
    is_code, lang = _is_probable_code_line("if [ -f /tmp/x ]; then")
    assert is_code is True and lang == "bash"


def test_is_probable_code_line_text():
    """普通文本行应被识别为 text（非代码）"""
    from app.core.tools.SandboxTools import _is_probable_code_line
    is_code, lang = _is_probable_code_line("下面是一些说明文字")
    assert is_code is False
    assert lang == "text"


def test_extract_code_blocks_heuristic_python():
    """无 markdown ``` 包裹的多行 Python 代码应被启发式识别"""
    from app.core.tools.SandboxTools import _extract_code_blocks_heuristic
    text = (
        "我会写一个 hello.py：\n"
        "def main():\n"
        "    print('hello')\n"
        "    return 0\n"
        "\n"
        "这段代码做了一件事。"
    )
    blocks = _extract_code_blocks_heuristic(text)
    assert len(blocks) >= 1
    code, lang = blocks[0]
    assert "def main():" in code
    assert "print('hello')" in code
    assert lang == "python"


def test_extract_code_blocks_heuristic_bash():
    """无 markdown ``` 包裹的多行 Shell 代码应被启发式识别"""
    from app.core.tools.SandboxTools import _extract_code_blocks_heuristic
    text = (
        "执行命令：\n"
        "echo start\n"
        "if [ -f /tmp/x ]; then\n"
        "    echo found\n"
        "fi\n"
        "完成"
    )
    blocks = _extract_code_blocks_heuristic(text)
    assert len(blocks) >= 1
    code, lang = blocks[0]
    assert "echo start" in code
    assert "fi" in code
    assert lang == "bash"


def test_extract_code_blocks_heuristic_too_short():
    """单行代码不应被识别（min_lines=2）"""
    from app.core.tools.SandboxTools import _extract_code_blocks_heuristic
    text = "def foo():\n只是一段说明文字"
    blocks = _extract_code_blocks_heuristic(text)
    assert blocks == []


def test_extract_ai_tool_calls_empty():
    """没有 tool_calls 属性时返回空列表"""
    from app.core.tools.SandboxTools import _extract_ai_tool_calls

    class FakeMsg:
        content = "text only"

    assert _extract_ai_tool_calls(FakeMsg()) == []
    assert _extract_ai_tool_calls(None) == []


def test_extract_ai_tool_calls_openai_style():
    """OpenAI 风格 tool_calls 应被提取"""
    from app.core.tools.SandboxTools import _extract_ai_tool_calls

    class FakeMsg:
        tool_calls = [
            {"id": "t1", "name": "write_file", "args": {"file_path": "/x.py", "content": "..."}},
        ]
        content_blocks = [
            {"type": "tool_call", "id": "t1", "name": "write_file", "args": {"file_path": "/x.py"}},
        ]

    calls = _extract_ai_tool_calls(FakeMsg())
    assert len(calls) == 2  # OpenAI tool_calls + content_blocks tool_call
    names = {c["name"] for c in calls}
    assert names == {"write_file"}


def test_extract_ai_tool_calls_anthropic_style():
    """Anthropic 风格 tool_use（嵌套在 content_blocks 的 non_standard 中）应被提取"""
    from app.core.tools.SandboxTools import _extract_ai_tool_calls

    class FakeMsg:
        tool_calls = []  # OpenAI 字段为空
        content_blocks = [
            {"type": "text", "text": "说明"},
            {
                "type": "non_standard",
                "value": {"type": "tool_use", "id": "tu1", "name": "write_file", "input": {"file_path": "/a.py"}},
            },
        ]

    calls = _extract_ai_tool_calls(FakeMsg())
    assert len(calls) == 1
    assert calls[0]["name"] == "write_file"
    assert calls[0]["args"] == {"file_path": "/a.py"}
    assert calls[0]["id"] == "tu1"


def test_ai_tool_call_to_event_write():
    """write_file 工具调用应转为 file_write 事件"""
    from app.core.tools.SandboxTools import _ai_tool_call_to_event
    tc = {"name": "write_file", "args": {"file_path": "/x.py", "content": "..."}, "id": "t1"}
    event = _ai_tool_call_to_event(tc, 1)
    assert event["type"] == "file_write"
    assert event["file_path"] == "/x.py"
    assert event["title"] == "决策：写入文件"


def test_ai_tool_call_to_event_execute():
    """execute 工具调用应转为 command_execute 事件"""
    from app.core.tools.SandboxTools import _ai_tool_call_to_event
    tc = {"name": "execute", "args": {"command": "ls -la"}, "id": "t1"}
    event = _ai_tool_call_to_event(tc, 3)
    assert event["type"] == "command_execute"
    assert event["command"] == "ls -la"
    assert event["title"] == "决策：执行命令"
    assert event["step"] == 3


def test_ai_tool_call_to_event_read():
    """read_file 工具调用应转为 file_read 事件"""
    from app.core.tools.SandboxTools import _ai_tool_call_to_event
    tc = {"name": "read_file", "args": {"file_path": "/y.py"}, "id": "t1"}
    event = _ai_tool_call_to_event(tc, 1)
    assert event["type"] == "file_read"
    assert event["file_path"] == "/y.py"
    assert event["title"] == "决策：读取文件"


def test_ai_message_list_content_generates_codegen_event():
    """AIMessage.content 是 list[ContentBlock] 时也能生成 code_generation 事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeAIMessage:
        # 模拟 Anthropic 风格：content 是 list，含 text 块包裹的 markdown 代码
        content = [
            {"type": "text", "text": "下面是代码：\n```python\nprint('hello from list')\n```\n"},
            {"type": "tool_use", "id": "tu1", "name": "write_file", "input": {"file_path": "/h.py"}},
        ]
        # 模拟 langchain AIMessage 的 .text 属性（自动从 text 块拼接）
        text = "下面是代码：\n```python\nprint('hello from list')\n```\n"
        tool_calls = []
        content_blocks = [
            {"type": "text", "text": "下面是代码：\n```python\nprint('hello from list')\n```\n"},
            {"type": "non_standard", "value": {"type": "tool_use", "id": "tu1", "name": "write_file", "input": {"file_path": "/h.py"}}},
        ]

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeAIMessage()], start)
    types = [e["type"] for e in events]
    assert "code_generation" in types
    assert "file_write" in types
    codegen = next(e for e in events if e["type"] == "code_generation")
    assert "print('hello from list')" in codegen["content"]
    assert summary["current_step"] >= 2


def test_ai_message_heuristic_codegen_no_markdown():
    """AIMessage 文本中无 markdown ``` 包裹时，启发式提取也能生成 code_generation 事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeAIMessage:
        content = (
            "我先写一个函数：\n"
            "def greet(name):\n"
            "    print(f'Hi, {name}')\n"
            "    return name\n"
            "好的，函数已经写好。"
        )
        text = None  # 不依赖 .text 属性，强制走 content 解析
        tool_calls = []
        content_blocks = []

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeAIMessage()], start)
    types = [e["type"] for e in events]
    assert "code_generation" in types
    codegen = next(e for e in events if e["type"] == "code_generation")
    assert "def greet(name):" in codegen["content"]


def test_ai_message_tool_calls_only():
    """AIMessage 只有 tool_calls 无文本时，应生成对应的工具事件但不生成 code_generation"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeAIMessage:
        content = ""
        text = ""
        tool_calls = [
            {"id": "t1", "name": "execute", "args": {"command": "ls -la"}},
        ]
        content_blocks = [
            {"type": "tool_call", "id": "t1", "name": "execute", "args": {"command": "ls -la"}},
        ]

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeAIMessage()], start)
    types = [e["type"] for e in events]
    assert "code_generation" not in types
    assert "command_execute" in types
    cmd_evt = next(e for e in events if e["type"] == "command_execute")
    assert cmd_evt["command"] == "ls -la"
    assert "决策" in cmd_evt["title"]


def test_ai_message_empty_content_no_event():
    """AIMessage.content 和 text 都为空时不生成任何事件"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeAIMessage:
        content = ""
        text = ""
        tool_calls = []
        content_blocks = []

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeAIMessage()], start)
    assert events == []


def test_extract_sandbox_summary_ai_step_advance():
    """code_generation + tool_calls 后 current_step 正确推进到至少 3"""
    from app.core.tools.SandboxTools import _extract_sandbox_summary_and_events

    class FakeAIMessage:
        content = [
            {"type": "text", "text": "```python\nprint(1)\n```"},
        ]
        text = "```python\nprint(1)\n```"
        tool_calls = [
            {"id": "t1", "name": "write_file", "args": {"file_path": "/a.py"}},
        ]
        content_blocks = [
            {"type": "text", "text": "```python\nprint(1)\n```"},
            {"type": "tool_call", "id": "t1", "name": "write_file", "args": {"file_path": "/a.py"}},
        ]

    start = datetime.now()
    summary, events = _extract_sandbox_summary_and_events([FakeAIMessage()], start)
    assert len(events) >= 2
    assert summary["current_step"] >= 3


def test_sandbox_runtime_context_missing_attr():
    """验证 runtime 无 context 属性时不会在入口处触发 AttributeError"""
    from unittest.mock import patch
    from app.core.tools.SandboxTools import sandbox

    class FakeRuntime:
        tool_call_id = "call_test_002"
        # 没有 context 属性

    with patch("app.core.tools.SandboxTools.get_stream_writer"), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch("app.core.tools.SandboxTools.DockerSandboxMiddleware"), \
         patch("app.core.tools.SandboxTools.create_deep_agent") as mock_create_agent:

        mock_create_agent.side_effect = RuntimeError("expected_error")

        try:
            sandbox("test prompt", FakeRuntime())
        except AttributeError as e:
            pytest.fail(f"不应触发 AttributeError: {e}")
        except RuntimeError as e:
            assert str(e) == "expected_error"


# ---------------------------------------------------------------------------
# Docker 不可用降级处理（2026-06-18 新增）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_docker_unavailable_returns_clean_error():
    """P1: Docker 不可用且 fallback_to_local=false 时，返回清晰错误 Command。"""
    from unittest.mock import patch, MagicMock
    from app.core.tools.SandboxTools import sandbox

    class FakeRuntime:
        tool_call_id = "call_docker_err_001"
        context = {"session_id": "session-docker-err"}

    mock_writer = MagicMock()

    from langchain_core.messages import ToolMessage

    mock_settings = MagicMock()
    mock_settings.get_sandbox_config.return_value = {
        "image": "python:3.12-alpine",
        "max_memory_mb": 512,
        "max_cpu_percent": 100,
        "network_enabled": False,
        "default_timeout": 60,
        "docker_mode": "local",
        "docker_host": "",
        "host_workspace_prefix": "",
        "container_workspace": "/workspace",
        "fallback_to_local": False,
    }

    with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch("app.core.tools.SandboxTools.settings", mock_settings), \
         patch("app.core.tools.SandboxTools.DockerSandboxMiddleware") as mock_middleware:

        mock_middleware.side_effect = RuntimeError("Docker daemon 未运行或未安装")

        result = await sandbox("test prompt", FakeRuntime())

        assert isinstance(result.update, dict)
        messages = result.update.get("messages", [])
        assert len(messages) == 1
        # ToolMessage 在测试环境中被 Mock，验证调用参数即可
        call_kwargs = ToolMessage.call_args.kwargs
        content = json.loads(call_kwargs["content"])
        assert "Docker daemon 未运行或未安装" in content["subagent"]
        assert "SANDBOX_FALLBACK_TO_LOCAL" in content["subagent"]
        assert call_kwargs["tool_call_id"] == "call_docker_err_001"
