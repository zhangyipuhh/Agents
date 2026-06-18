# -*- coding:utf-8 -*-
"""
FilesystemReadTools 重构回归测试

覆盖：
- explore 工具可导入
- explore 仅读取当前 session 上传目录，不再使用 knowledge_root
- explore 通过 BaseFilesystemTool 执行
- explore 异常转发

Date: 2026-06-18
Author: AI Assistant
"""

import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_explore_importable():
    """
    P0: explore 工具可导入且为 async 函数。
    """
    from app.core.tools import FilesystemReadTools
    from langgraph.types import Command

    assert hasattr(FilesystemReadTools, "explore")
    assert inspect.iscoroutinefunction(FilesystemReadTools.explore)
    assert inspect.signature(FilesystemReadTools.explore).return_annotation is Command


# ============================================================
# P1: 路径选择
# ============================================================


def _make_fake_runtime(tool_call_id="call_explore", session_id="default"):
    class _FakeRuntime:
        pass

    rt = _FakeRuntime()
    rt.tool_call_id = tool_call_id
    rt.context = {"session_id": session_id}
    return rt


def test_explore_uses_session_upload_root(tmp_path):
    """
    P1: explore 使用 data/upload/{session_id} 作为 root_path。
    """
    from app.core.tools import FilesystemReadTools

    session_id = "test_session"
    root_path = tmp_path / "data" / "upload" / session_id
    root_path.mkdir(parents=True, exist_ok=True)
    (root_path / "test.txt").write_text("hello")

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"model": {"messages": [MagicMock(content="file found")]}})
        yield ("values", {"structured_response": {"answer": "done"}})

    mock_agent = MagicMock()
    mock_agent.astream = fake_astream
    mock_writer = MagicMock()
    mock_checkpointer = MagicMock()
    arun_called = {}

    original_arun = FilesystemReadTools.BaseFilesystemTool.arun

    async def fake_arun(self, prompt, runtime, root_path):
        arun_called["root_path"] = str(root_path)
        arun_called["tool_name"] = self.tool_name
        # 返回一个最小 Command 模拟
        from langgraph.types import Command
        from langchain_core.messages import ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content='{"subagent": "done"}',
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    with patch("pathlib.Path.cwd", return_value=tmp_path), \
         patch("app.core.tools.FilesystemReadTools.BaseFilesystemTool.arun", fake_arun):

        asyncio.run(FilesystemReadTools.explore("search", _make_fake_runtime(session_id=session_id)))

    assert arun_called["tool_name"] == "explore"
    assert arun_called["root_path"] == str(root_path)


def test_explore_ignores_knowledge_root(tmp_path):
    """
    P1: explore 即使 context 中存在 knowledge_root，也仍然使用 session 上传目录。
    """
    from app.core.tools import FilesystemReadTools

    session_id = "test_session"
    upload_path = tmp_path / "data" / "upload" / session_id
    upload_path.mkdir(parents=True, exist_ok=True)
    (upload_path / "upload.txt").write_text("upload file")

    arun_called = {}

    async def fake_arun(self, prompt, runtime, root_path):
        arun_called["root_path"] = str(root_path)
        from langgraph.types import Command
        from langchain_core.messages import ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content='{"subagent": "done"}',
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    with patch("pathlib.Path.cwd", return_value=tmp_path), \
         patch("app.core.tools.FilesystemReadTools.BaseFilesystemTool.arun", fake_arun):

        rt = _make_fake_runtime(session_id=session_id)
        rt.context["knowledge_root"] = str(tmp_path / "data" / "Knowledge")
        asyncio.run(FilesystemReadTools.explore("search", rt))

    assert arun_called["root_path"] == str(upload_path)


# ============================================================
# P2: 异常转发
# ============================================================


def test_explore_raises_when_session_root_missing(tmp_path):
    """
    P2: 当 session 上传目录不存在时，explore 抛出 FileNotFoundError。
    """
    from app.core.tools import FilesystemReadTools

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                FilesystemReadTools.explore("search", _make_fake_runtime(session_id="missing"))
            )
