# -*- coding:utf-8 -*-
"""
generate_report 工具测试

覆盖：
- 导入/存在性
- ToolRegistry 注册
- 三步 progress 事件流（有审查数据时）
- store 中无 report_data 时走早退守卫并提示模型

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


def _make_fake_runtime(tool_call_id="call_report", process_data=None):
    """
    构造一个最小可用的 ToolRuntime 替身。

    Args:
        tool_call_id: 工具调用 ID。
        process_data: 模拟 runtime.store 中 process_data 的值；
            - None（默认）：store.get 返回 None，模拟「无 process_data」
            - dict：构造一个带 .value 属性的对象，模拟「有 process_data」

    Returns:
        拥有 tool_call_id / context / state / store 属性的对象。
    """
    class _FakeRuntime:
        pass

    rt = _FakeRuntime()
    rt.tool_call_id = tool_call_id
    rt.context = {"session_id": "test_session", "store_id": "default"}
    rt.state = {}
    rt.store = MagicMock()
    if process_data is None:
        rt.store.get.return_value = None  # 无 process_data
    else:
        # 模拟 store 返回的对象：有 .value 属性，值为传入的 process_data
        store_result = MagicMock()
        store_result.value = process_data
        rt.store.get.return_value = store_result
    return rt


def test_generate_report_emits_three_progress_events_when_has_review_data():
    """
    P1: 有审查数据时，generate_report 发送 3 步 progress 事件（33% / 66% / 100%）。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        generate_report,
        GenerateReportInput,
    )
    from app.shared.tools.skills.map_agent.config.config import (
        ProjectSiteSelectionCollection,
    )

    written = []
    fake_writer = lambda event: written.append(event)

    review_collection_dict = {
        "collection_id": "batch_001",
        "collection_name": "测试批次",
        "projects": [],
    }

    with patch("app.shared.tools.skills.map_agent.MapTools.get_stream_writer") as mock_gsw, \
         patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator"):
        mock_gsw.return_value = fake_writer
        rt = _make_fake_runtime(process_data={"report_data": review_collection_dict})
        data = GenerateReportInput(project_name="测试", project_type="类型")
        generate_report(data, rt)

    progress_events = [
        e for e in written
        if isinstance(e, dict) and e.get("type") == "tool_progress"
    ]
    assert len(progress_events) >= 3, (
        f"期望至少 3 个 progress 事件，实际 {len(progress_events)} 个"
    )
    percentages = [e["data"]["percentage"] for e in progress_events]
    assert 33 in percentages
    assert 66 in percentages
    assert 100 in percentages


# ============================================================
# P1: 守卫路径（无审查结果数据时早退）
# ============================================================


def test_generate_report_returns_no_review_data_when_empty():
    """
    P1: store 中无 report_data 时，generate_report 走早退守卫：
    - 返回 Command，map_report.status == "no_review_data"
    - message 提示「当前无审查结果数据，需要先做审查才能生成报告」
    - download_url / file_name 均为空
    - messages[0] 为 ToolMessage 且 tool_call_id 与入参一致

    注意：测试环境下 ToolMessage 已被 conftest 替换为 Mock，
    调用 ToolMessage(...) 返回的 Mock 不会保留构造参数为属性；
    故改为 patch 目标模块里的 ToolMessage 引用，并断言其调用参数。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        generate_report,
        GenerateReportInput,
    )
    from langgraph.types import Command

    fake_tool_message = MagicMock()

    with patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator") as MockGen, \
         patch("app.shared.tools.skills.map_agent.MapTools.ToolMessage", fake_tool_message):
        instance = MagicMock()
        MockGen.return_value = instance

        rt = _make_fake_runtime(tool_call_id="call_empty")
        data = GenerateReportInput(
            project_name="测试项目",
            project_type="测试类型",
        )
        result = generate_report(data, rt)

    assert isinstance(result, Command)
    assert "map_report" in result.update
    report_data = result.update["map_report"]
    assert report_data["status"] == "no_review_data"
    assert report_data["download_url"] == ""
    assert report_data["file_name"] == ""
    assert "当前无审查结果数据" in report_data["message"]
    assert "需要先做审查才能生成报告" in report_data["message"]

    messages = result.update["messages"]
    assert len(messages) == 1
    # ToolMessage 应被以 tool_call_id="call_empty" 调用一次
    assert fake_tool_message.call_count == 1
    call_kwargs = fake_tool_message.call_args.kwargs
    assert call_kwargs.get("tool_call_id") == "call_empty"

    # content 应为 JSON 字符串，解析后字段符合守卫语义
    payload = json.loads(call_kwargs.get("content"))
    assert payload["status"] == "no_review_data"
    assert payload["result"] == "当前无审查结果数据，需要先做审查才能生成报告"
    assert "duration_ms" in payload


def test_generate_report_no_review_data_emits_tool_stop_event():
    """
    P1: 早退守卫会发出 tool_stop 事件（type=guard, status=no_review_data）。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        generate_report,
        GenerateReportInput,
    )

    written = []
    fake_writer = lambda event: written.append(event)

    with patch("app.shared.tools.skills.map_agent.MapTools.get_stream_writer") as mock_gsw, \
         patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator"):
        mock_gsw.return_value = fake_writer
        rt = _make_fake_runtime()  # 默认无 process_data
        data = GenerateReportInput(project_name="x", project_type="y")
        generate_report(data, rt)

    stop_events = [
        e for e in written
        if isinstance(e, dict) and e.get("type") == "tool_stop"
    ]
    assert len(stop_events) >= 1, "守卫路径应至少发出 1 个 tool_stop 事件"
    guard_event = stop_events[-1]
    assert guard_event["data"]["status"] == "no_review_data"
    assert guard_event["data"]["type"] == "guard"


def test_generate_report_no_review_data_skips_word_generator_io():
    """
    P1: 守卫路径不应触发 WordReportGenerator.generate / .save，
    防止后续维护误改回归到「生成空 Word 报告」。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        generate_report,
        GenerateReportInput,
    )

    with patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator") as MockGen:
        instance = MagicMock()
        MockGen.return_value = instance

        rt = _make_fake_runtime()
        data = GenerateReportInput(project_name="x", project_type="y")
        generate_report(data, rt)

    instance.generate.assert_not_called()
    instance.save.assert_not_called()


def test_generate_report_emits_only_first_progress_when_no_review_data():
    """
    P1: 无审查数据时，progress 事件流不会再发出 100%（完成阶段）的 progress 事件。

    说明：原始代码中 progress_event_1（33%）与 progress_event_2（66%）
    均在 try 块之前就已经 writer 出去；只有 progress_event_3（100%）
    在成功生成后才发出。因此守卫路径应发出 33% 与 66%，但**不会**发出 100%。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        generate_report,
        GenerateReportInput,
    )

    written = []
    fake_writer = lambda event: written.append(event)

    with patch("app.shared.tools.skills.map_agent.MapTools.get_stream_writer") as mock_gsw, \
         patch("app.shared.tools.skills.map_agent.MapTools.WordReportGenerator"):
        mock_gsw.return_value = fake_writer
        rt = _make_fake_runtime()  # 默认无 process_data
        data = GenerateReportInput(project_name="x", project_type="y")
        generate_report(data, rt)

    progress_events = [
        e for e in written
        if isinstance(e, dict) and e.get("type") == "tool_progress"
    ]
    percentages = [e["data"]["percentage"] for e in progress_events]
    # 守卫路径应发出 33% 与 66%（在 try 块之前的早退），但不应发出 100%
    assert 33 in percentages
    assert 66 in percentages
    assert 100 not in percentages, (
        f"守卫路径不应发出 100%（报告生成完成）阶段，实际 progress 序列：{percentages}"
    )
