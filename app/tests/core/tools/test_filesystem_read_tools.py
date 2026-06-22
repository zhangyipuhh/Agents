# -*- coding:utf-8 -*-
"""
FilesystemReadTools 重构回归测试

覆盖：
- explore 工具可导入
- explore 使用 session 上传目录作为 root_path
- explore 通过 BaseFilesystemTool 执行
- explore 目录自动创建

Date: 2026-06-18
Author: AI Assistant
"""

import asyncio
import inspect
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.shared.utils.files import session_path_manager as spm


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


def test_explore_uses_session_upload_root(tmp_path, monkeypatch):
    """
    P1: explore 使用日期化 session 上传目录作为 root_path。
    实际读取时由 FilesystemBackend.read 猴补丁映射到 data/tmp/upload/... 下的 .md 文件。
    """
    from app.core.tools import FilesystemReadTools

    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)

    session_id = "test_session"
    spm.register_session_upload_date(session_id)
    today = date.today()
    root_path = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/{session_id}"
    root_path.mkdir(parents=True, exist_ok=True)
    (root_path / "test.txt").write_text("hello")

    arun_called = {}

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

    with patch("app.core.tools.FilesystemReadTools.BaseFilesystemTool.arun", fake_arun):
        asyncio.run(FilesystemReadTools.explore("search", _make_fake_runtime(session_id=session_id)))

    assert arun_called["tool_name"] == "explore"
    assert arun_called["root_path"] == str(root_path)


def test_explore_ignores_knowledge_root(tmp_path, monkeypatch):
    """
    P1: explore 即使 context 中存在 knowledge_root，也仍然使用日期化 session 上传目录。
    """
    from app.core.tools import FilesystemReadTools

    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)

    session_id = "test_session"
    spm.register_session_upload_date(session_id)
    today = date.today()
    upload_path = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/{session_id}"
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

    with patch("app.core.tools.FilesystemReadTools.BaseFilesystemTool.arun", fake_arun):
        rt = _make_fake_runtime(session_id=session_id)
        rt.context["knowledge_root"] = str(tmp_path / "data" / "Knowledge")
        asyncio.run(FilesystemReadTools.explore("search", rt))

    assert arun_called["root_path"] == str(upload_path)


# ============================================================
# P2: 目录自动创建
# ============================================================


def test_explore_creates_session_upload_root_when_missing(tmp_path, monkeypatch):
    """
    P2: 当 session 上传目录不存在时，explore 会自动创建它。
    """
    from app.core.tools import FilesystemReadTools

    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)

    session_id = "missing_upload_session"
    today = date.today()
    expected_root = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/{session_id}"

    async def fake_arun(self, prompt, runtime, root_path):
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

    with patch("app.core.tools.FilesystemReadTools.BaseFilesystemTool.arun", fake_arun):
        asyncio.run(FilesystemReadTools.explore("search", _make_fake_runtime(session_id=session_id)))

    assert expected_root.exists()


# ============================================================
# P1: 空目录静默处理
# ============================================================


def test_explore_empty_workspace_returns_not_found(tmp_path, monkeypatch):
    """
    P1: 当 session 上传目录为空时，explore 不启动子智能体，直接返回"未找到文件"。
    """
    from app.core.tools import FilesystemReadTools
    from langgraph.types import Command

    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)

    session_id = "empty_session"
    spm.register_session_upload_date(session_id)
    today = date.today()
    root_path = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/{session_id}"
    root_path.mkdir(parents=True, exist_ok=True)

    arun_called = False

    async def fake_arun(self, prompt, runtime, root_path):
        nonlocal arun_called
        arun_called = True
        return Command(update={"messages": [{"type": "tool", "content": '{"subagent": "done"}', "tool_call_id": runtime.tool_call_id}]})

    class _RealToolMessage:
        def __init__(self, content, tool_call_id):
            self.content = content
            self.tool_call_id = tool_call_id

    with patch("app.core.tools.FilesystemReadTools.BaseFilesystemTool.arun", fake_arun), \
         patch("app.core.tools.FilesystemReadTools.ToolMessage", _RealToolMessage):
        result = asyncio.run(FilesystemReadTools.explore("search", _make_fake_runtime(session_id=session_id)))

    assert not arun_called
    assert isinstance(result, Command)
    messages = result.update["messages"]
    assert len(messages) == 1
    assert "未找到文件" in messages[0].content
