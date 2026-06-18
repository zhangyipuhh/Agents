# -*- coding:utf-8 -*-
"""
BaseFilesystemTool 单元测试

覆盖：
- BaseFilesystemTool 可导入、可实例化
- arun 成功路径返回 Command
- arun 客户端断开时推送 stopped_by_user
- arun 对非法 root_path 抛出预期异常
- 空目录校验失败
- tool_stop 事件保留 subagent 字段

Date: 2026-06-18
Author: AI Assistant
"""

import asyncio
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.tools.base import BaseFilesystemTool


# ============================================================
# 公共 helper
# ============================================================


class _FakeResult:
    """模拟结构化输出模型"""
    def __init__(self, answer=""):
        self.answer = answer


class _RecordingToolMessage:
    """记录 ToolMessage 构造时的 content 与 tool_call_id"""
    last_call = None

    def __init__(self, content="", tool_call_id=None, **kwargs):
        self.content = content
        self.tool_call_id = tool_call_id
        _RecordingToolMessage.last_call = {"content": content, "tool_call_id": tool_call_id}


def _make_fake_runtime(tool_call_id="call_test"):
    """构造模拟 ToolRuntime"""

    class _FakeRuntime:
        pass

    rt = _FakeRuntime()
    rt.tool_call_id = tool_call_id
    rt.context = {"session_id": "default"}
    return rt


def _make_fake_request(disconnect_sequence):
    """构造模拟 FastAPI Request，按序列返回 is_disconnected()"""
    fake = MagicMock(name="fake_request")
    call_count = {"n": 0}
    disconnect_sequence = list(disconnect_sequence)

    async def _is_disconnected():
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(disconnect_sequence):
            return disconnect_sequence[idx]
        return False

    fake.is_disconnected = _is_disconnected
    fake._call_count = call_count
    return fake


def _count_writer_events(writer_mock):
    """统计 writer 调用的事件类型与 tool_stop data"""
    counts = {"tool_start": 0, "tool_progress": 0, "tool_stop": 0, "tool_error": 0}
    stop_data_list = []
    for call in writer_mock.call_args_list:
        if not call.args:
            continue
        event = call.args[0]
        if not isinstance(event, dict):
            continue
        et = event.get("type")
        if et in counts:
            counts[et] += 1
        if et == "tool_stop":
            stop_data_list.append(event.get("data", {}))
    return counts, stop_data_list


def _default_patches(fake_astream, fake_request=None):
    """返回一组常用 patch，用于驱动 BaseFilesystemTool.arun"""
    mock_agent = MagicMock()
    mock_agent.astream = fake_astream
    mock_writer = MagicMock()
    mock_checkpointer = MagicMock()

    async def mock_create_child_agent(self, root_path, model):
        return mock_agent

    patches = [
        patch("app.core.tools.base.BaseFilesystemTool.get_stream_writer", return_value=mock_writer),
        patch("app.core.tools.base.BaseFilesystemTool.ModelFactory.create_model"),
        patch.object(BaseFilesystemTool, "create_child_agent", mock_create_child_agent),
        patch("app.core.tools.base.BaseFilesystemTool.get_async_checkpointer", return_value=mock_checkpointer),
        patch("app.core.tools.base.BaseFilesystemTool.get_current_request", return_value=fake_request),
        patch("app.core.tools.base.BaseFilesystemTool.extract_structured_messages", return_value=[]),
    ]
    return patches, mock_writer


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_base_filesystem_tool_importable():
    """
    P0: BaseFilesystemTool 可以从 base 包导入。
    """
    assert BaseFilesystemTool is not None


def test_base_filesystem_tool_init():
    """
    P0: BaseFilesystemTool 可以按预期参数实例化。
    """
    tool = BaseFilesystemTool(
        tool_name="test_tool",
        system_prompt="You are a test assistant.",
        response_format=_FakeResult,
        max_file_size_mb=5,
    )
    assert tool.tool_name == "test_tool"
    assert tool.system_prompt == "You are a test assistant."
    assert tool.response_format is _FakeResult
    assert tool.max_file_size_mb == 5


# ============================================================
# P1: 成功路径
# ============================================================


def test_arun_returns_command_on_success(tmp_path):
    """
    P1: 子智能体正常完成时，arun 返回包含 ToolMessage 的 Command。
    """
    root_path = tmp_path / "workspace"
    root_path.mkdir()
    (root_path / "test.txt").write_text("hello")

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"model": {"messages": [MagicMock(content="file found")]}})
        yield ("values", {"structured_response": {"answer": "final answer"}})

    fake_request = _make_fake_request([False])
    patches, mock_writer = _default_patches(fake_astream, fake_request)

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch("app.core.tools.base.BaseFilesystemTool.ToolMessage", _RecordingToolMessage)
        )
        tool = BaseFilesystemTool(
            tool_name="test_tool",
            system_prompt="test prompt",
            response_format=_FakeResult,
        )
        result = asyncio.run(tool.arun("search files", _make_fake_runtime(), root_path))

    assert result is not None
    messages = result.update.get("messages", [])
    assert len(messages) == 1
    msg = messages[0]
    assert isinstance(msg, _RecordingToolMessage)
    parsed = json.loads(msg.content)
    assert "subagent" in parsed
    assert "final answer" in parsed["subagent"]

    counts, stop_data_list = _count_writer_events(mock_writer)
    assert counts["tool_start"] == 1
    assert counts["tool_stop"] == 1
    success_event = next(
        (d for d in stop_data_list if d.get("status") == "success"), None
    )
    assert success_event is not None
    assert success_event.get("result", {}).get("answer") == "final answer"


# ============================================================
# P1: 失败路径
# ============================================================


def test_arun_raises_file_not_found():
    """
    P1: root_path 不存在时，arun 抛出 FileNotFoundError。
    """
    tool = BaseFilesystemTool(tool_name="test_tool", system_prompt="test")
    with pytest.raises(FileNotFoundError):
        asyncio.run(tool.arun("search", _make_fake_runtime(), "/not/exist/path"))


def test_arun_raises_not_a_directory(tmp_path):
    """
    P1: root_path 是文件而非目录时，arun 抛出 NotADirectoryError。
    """
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a dir")

    tool = BaseFilesystemTool(tool_name="test_tool", system_prompt="test")
    with pytest.raises(NotADirectoryError):
        asyncio.run(tool.arun("search", _make_fake_runtime(), file_path))


def test_arun_raises_empty_directory(tmp_path):
    """
    P1: root_path 是空目录时，arun 抛出 ValueError。
    """
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    tool = BaseFilesystemTool(tool_name="test_tool", system_prompt="test")
    with pytest.raises(ValueError):
        asyncio.run(tool.arun("search", _make_fake_runtime(), empty_dir))


# ============================================================
# P2: 边界条件
# ============================================================


def test_arun_stopped_by_user(tmp_path):
    """
    P2: 客户端断开时，arun 立即推送 status='stopped_by_user' 的 tool_stop 事件。
    """
    root_path = tmp_path / "workspace"
    root_path.mkdir()
    (root_path / "test.txt").write_text("hello")

    async def fake_astream(*args, **kwargs):
        # 使用空 messages 列表，避免 extract_structured_messages 处理 MagicMock 时的边界异常
        yield ("updates", {"model": {"messages": []}})
        yield ("updates", {"model": {"messages": []}})

    fake_request = _make_fake_request([True])
    patches, mock_writer = _default_patches(fake_astream, fake_request)

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        stack.enter_context(
            patch("app.core.tools.base.BaseFilesystemTool.ToolMessage", _RecordingToolMessage)
        )
        tool = BaseFilesystemTool(tool_name="test_tool", system_prompt="test")
        result = asyncio.run(tool.arun("search files", _make_fake_runtime(), root_path))

    assert result is not None
    assert _RecordingToolMessage.last_call is not None
    parsed = json.loads(_RecordingToolMessage.last_call["content"])
    assert "已被用户中止" in parsed["subagent"]

    counts, stop_data_list = _count_writer_events(mock_writer)
    stopped_event = next(
        (d for d in stop_data_list if d.get("status") == "stopped_by_user"), None
    )
    assert stopped_event is not None
    assert stopped_event.get("thread_id") == "call_test"
    assert "final_messages" in stopped_event
