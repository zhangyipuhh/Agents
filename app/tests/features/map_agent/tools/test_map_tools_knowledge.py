# -*- coding:utf-8 -*-
"""
MapTools query_knowledge 测试

覆盖：
- query_knowledge 工具可导入
- query_knowledge 使用 app.core.config.paths.KNOWLEDGE_DIR 作为 root_path
- query_knowledge 调用 BaseFilesystemTool.arun 一次并透传参数

Date: 2026-06-29
Author: AI Assistant
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_query_knowledge_importable():
    """
    P0: query_knowledge 工具可导入且为 async 函数。
    """
    from app.shared.tools.skills.map_agent.MapTools import query_knowledge

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


def test_query_knowledge_uses_knowledge_dir(tmp_path, monkeypatch):
    """
    P1: query_knowledge 使用 app.core.config.paths.KNOWLEDGE_DIR 作为 root_path。

    通过 monkeypatch 覆盖 KNOWLEDGE_DIR 为 tmp_path，验证子智能体 base 工具
    接收到的 root_path 与该常量一致。
    """
    from app.core.config import paths as paths_module
    from app.shared.tools.skills.map_agent import MapTools
    from app.shared.tools.skills.map_agent.MapTools import query_knowledge

    fake_root = tmp_path / "knowledge"
    fake_root.mkdir()
    (fake_root / "doc.txt").write_text("doc")

    # 同时 patch 模块源（paths.KNOWLEDGE_DIR）与 MapTools 的本地 import 绑定
    monkeypatch.setattr(paths_module, "KNOWLEDGE_DIR", str(fake_root))
    monkeypatch.setattr(MapTools, "KNOWLEDGE_DIR", str(fake_root))

    arun_called = {}

    async def fake_arun(self, prompt, runtime, root_path):
        arun_called["tool_name"] = self.tool_name
        arun_called["prompt"] = prompt
        arun_called["root_path"] = root_path
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

    with patch("app.shared.tools.skills.map_agent.MapTools.BaseFilesystemTool.arun", fake_arun):
        rt = _make_fake_runtime()
        result = asyncio.run(query_knowledge("search knowledge", rt))

    # 验证 arun 被调用且参数正确
    assert arun_called["tool_name"] == "query_knowledge"
    assert arun_called["prompt"] == "search knowledge"
    # root_path 应为 Path(KNOWLEDGE_DIR)，Path 在不同 OS 上表示等价即可
    assert Path(arun_called["root_path"]) == Path(str(fake_root))
    assert result is not None


def test_query_knowledge_default_knowledge_dir():
    """
    P1: 未注入 monkeypatch 时，query_knowledge 默认使用 app.core.config.paths.KNOWLEDGE_DIR。

    验证默认值来自共享路径常量模块（与 knowledge_router 使用的同一个值）。
    """
    from app.core.config.paths import KNOWLEDGE_DIR
    from app.shared.tools.skills.map_agent.MapTools import query_knowledge

    received = {}

    async def fake_arun(self, prompt, runtime, root_path):
        received["root_path"] = root_path
        from langgraph.types import Command
        from langchain_core.messages import ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"ok": True}, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    with patch("app.shared.tools.skills.map_agent.MapTools.BaseFilesystemTool.arun", fake_arun):
        rt = _make_fake_runtime()
        asyncio.run(query_knowledge("p", rt))

    assert Path(received["root_path"]) == Path(KNOWLEDGE_DIR)
