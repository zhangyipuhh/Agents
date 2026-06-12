# -*- coding:utf-8 -*-
"""
SandboxTools 模块测试

测试范围:
- 辅助函数导入与存在性验证
- 沙盒步骤常量定义
- 代码块提取、语言检测、摘要生成等工具函数
"""

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
