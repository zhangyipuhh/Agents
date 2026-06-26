# -*- coding:utf-8 -*-
"""
generate_report 工具测试

覆盖：
- 导入/存在性
- ToolRegistry 注册
- 三步 progress 事件流
- store 中无 report_data 时降级为默认集合

Date: 2026-06-26
Author: AI Assistant
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_generate_report_importable():
    """
    P0: generate_report 工具可导入。
    """
    from app.shared.tools.skills.map_agent.MapTools import generate_report
    assert generate_report is not None


def test_generate_report_input_model_importable():
    """
    P0: GenerateReportInput Pydantic 模型可导入。
    """
    from app.shared.tools.skills.map_agent.MapTools import GenerateReportInput
    assert GenerateReportInput is not None

    # 必填字段验证
    with pytest.raises(Exception):
        GenerateReportInput()

    instance = GenerateReportInput(
        project_name="某高速公路",
        project_type="交通",
    )
    assert instance.project_name == "某高速公路"
    assert instance.project_type == "交通"


def test_generate_report_registered():
    """
    P0: generate_report 已注册到 ToolRegistry。
    """
    from app.shared.tools.skills.map_agent import MapTools  # noqa: F401
    from app.shared.tools.registry import ToolRegistry

    info = ToolRegistry._tools.get("generate_report")
    assert info is not None, "generate_report 未注册到 ToolRegistry"
    assert info["agent"] == "map_agent"


# ============================================================
# P1: 成功路径
# ============================================================


def _make_fake_runtime(tool_call_id="call_report"):
    class _FakeRuntime:
        pass

    rt = _FakeRuntime()
    rt.tool_call_id = tool_call_id
    rt.context = {"session_id": "test_session", "store_id": "default"}
    rt.state = {}
    rt.store = MagicMock()
    rt.store.get.return_value = None  # 无 process_data 时返回 None
    return rt


def test_generate_report_uses_default_collection_when_empty():
    """
    P1: store 无 report_data 时降级为默认空集合，不抛异常。
    """
    from app.shared.tools.skills.map_agent.MapTools import generate_report, GenerateReportInput
    from langgraph.types import Command
    from langchain_core.messages import ToolMessage
    from unittest.mock import MagicMock, AsyncMock, patch

    # Mock WordReportGenerator.generate / save 避免真实IO
    with patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator") as MockGen:
        instance = MagicMock()
        MockGen.return_value = instance

        rt = _make_fake_runtime()
        data = GenerateReportInput(
            project_name="测试项目",
            project_type="测试类型",
        )

        result = generate_report(data, rt)

    assert isinstance(result, Command)
    # 检查返回值
    assert "map_report" in result.update
    report_data = result.update["map_report"]
    # 演示模式可能为 saved 或 report_generated
    assert report_data["status"] in ("report_generated", "saved")


# ============================================================
# P1: 失败路径
# ============================================================


def test_generate_report_emits_three_progress_events():
    """
    P1: generate_report 发送 3 步 progress 事件（33% / 66% / 100%）。
    """
    from app.shared.tools.skills.map_agent.MapTools import generate_report, GenerateReportInput
    from langgraph.config import get_stream_writer
    from unittest.mock import MagicMock, patch

    written = []

    # Mock get_stream_writer 直接捕获
    fake_writer = lambda event: written.append(event)

    with patch("app.shared.tools.skills.map_agent.MapTools.get_stream_writer") as mock_gsw, \
         patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator"):
        mock_gsw.return_value = fake_writer
        rt = _make_fake_runtime()
        data = GenerateReportInput(project_name="测试", project_type="类型")
        generate_report(data, rt)

    # 查找 tool_progress 事件
    progress_events = [
        e for e in written
        if isinstance(e, dict) and e.get("type") == "tool_progress"
    ]
    assert len(progress_events) >= 3, f"期望至少 3 个 progress 事件，实际 {len(progress_events)} 个"

    percentages = [e["data"]["percentage"] for e in progress_events]
    assert 33 in percentages
    assert 66 in percentages
    assert 100 in percentages
