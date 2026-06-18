# -*- coding:utf-8 -*-
"""
MapTools query_knowledge 测试

覆盖：
- query_knowledge 工具可导入
- query_knowledge 使用 runtime.context["knowledge_root"] 作为 root_path
- 未配置 knowledge_root 时返回错误 Command
- 成功路径调用 BaseFilesystemTool.arun

Date: 2026-06-18
Author: AI Assistant
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_query_knowledge_importable():
    """
    P0: query_knowledge 工具可导入且为 async 函数。
    """
    from app.features.map_agent.tools.MapTools import query_knowledge

    assert query_knowledge is not None
    import inspect
    assert inspect.iscoroutinefunction(query_knowledge)


# ============================================================
# P1: 路径选择
# ============================================================


def _make_fake_runtime(tool_call_id="call_knowledge"):
    class _FakeRuntime:
        pass

    rt = _FakeRuntime()
    rt.tool_call_id = tool_call_id
    rt.context = {}
    return rt


def test_query_knowledge_uses_knowledge_root(tmp_path):
    """
    P1: query_knowledge 使用 runtime.context["knowledge_root"] 作为 root_path。
    """
    from app.features.map_agent.tools.MapTools import query_knowledge

    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "doc.txt").write_text("doc")

    arun_called = {}

    async def fake_arun(self, prompt, runtime, root_path):
        arun_called["tool_name"] = self.tool_name
        arun_called["root_path"] = str(root_path)
        from langgraph.types import Command
        from langchain_core.messages import ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"subagent": "knowledge result"}, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    with patch("app.features.map_agent.tools.MapTools.BaseFilesystemTool.arun", fake_arun):
        rt = _make_fake_runtime()
        rt.context["knowledge_root"] = str(knowledge_root)
        result = asyncio.run(query_knowledge("search knowledge", rt))

    assert arun_called["tool_name"] == "query_knowledge"
    assert arun_called["root_path"] == str(knowledge_root)
    assert result is not None


class _RecordingToolMessage:
    """记录 ToolMessage 构造参数"""
    def __init__(self, content="", tool_call_id=None, **kwargs):
        self.content = content
        self.tool_call_id = tool_call_id


def test_query_knowledge_returns_error_when_missing_root():
    """
    P1: 未配置 knowledge_root 时，query_knowledge 直接返回错误 Command。
    """
    from app.features.map_agent.tools.MapTools import query_knowledge
    from unittest.mock import patch

    rt = _make_fake_runtime(tool_call_id="call_no_root")
    # 确保 context 中没有 knowledge_root
    assert "knowledge_root" not in rt.context

    with patch("app.features.map_agent.tools.MapTools.ToolMessage", _RecordingToolMessage):
        result = asyncio.run(query_knowledge("search", rt))

    assert result is not None
    messages = result.update.get("messages", [])
    assert len(messages) == 1
    msg = messages[0]
    assert isinstance(msg, _RecordingToolMessage)
    parsed = json.loads(msg.content)
    assert "error" in parsed
    assert "未配置知识库路径" in parsed["error"]
