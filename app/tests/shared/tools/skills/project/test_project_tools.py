# -*- coding:utf-8 -*-
"""
ProjectTools 测试：覆盖 project 智能体的 8 个 @tool 工具的基础行为。

Date: 2026-07-02
"""
import asyncio
import json
import sys
import types
from unittest.mock import MagicMock, patch


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_project_tools_importable():
    """P0: ProjectTools 模块可导入。"""
    from app.shared.tools.skills.project import ProjectTools

    assert ProjectTools is not None
    for name in [
        "intent_clarification",
        "project_doc_query",
        "project_doc_outline",
        "project_doc_write",
        "project_doc_workflow",
        "manage_project_log",
        "append_change_log",
        "generate_project_docx",
    ]:
        assert hasattr(ProjectTools, name), f"缺少工具函数: {name}"


def test_project_tools_input_models_importable():
    """P0: 所有 Pydantic 入参模型可导入。"""
    from app.shared.tools.skills.project.ProjectTools import (
        AppendChangeLogInput,
        GenerateProjectDocxInput,
        IntentClarificationInput,
        ManageProjectLogInput,
        ProjectDocOutlineInput,
        ProjectDocQueryInput,
        ProjectDocWorkflowInput,
        ProjectDocWriteInput,
        Question,
        QuestionOption,
    )

    assert all(
        cls is not None
        for cls in (
            IntentClarificationInput,
            ProjectDocQueryInput,
            ProjectDocOutlineInput,
            ProjectDocWriteInput,
            ProjectDocWorkflowInput,
            ManageProjectLogInput,
            AppendChangeLogInput,
            GenerateProjectDocxInput,
            Question,
            QuestionOption,
        )
    )


def test_project_tools_registered_in_registry():
    """P0: 8 个工具经 ToolRegistry 注册到 project 智能体。

    测试策略：AST 静态解析源码，确认每个工具均带 @tool 装饰器。
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[5] / "shared" / "tools" / "skills" / "project" / "ProjectTools.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    expected = {
        "intent_clarification",
        "project_doc_query",
        "project_doc_outline",
        "project_doc_write",
        "project_doc_workflow",
        "manage_project_log",
        "append_change_log",
        "generate_project_docx",
    }

    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in expected:
            for dec in node.decorator_list:
                func_name = None
                if isinstance(dec, ast.Call):
                    if isinstance(dec.func, ast.Name):
                        func_name = dec.func.id
                    elif isinstance(dec.func, ast.Attribute):
                        func_name = dec.func.attr
                if func_name == "tool":
                    found.add(node.name)
                    break

    missing = expected - found
    assert not missing, f"以下工具缺少 @tool 装饰器: {missing}"


# ============================================================
# P1: IntentClarificationInput 校验
# ============================================================


def test_intent_clarification_input_accepts_questions():
    """P1: IntentClarificationInput 接收 1-4 个 Question（options 至少 2 个或空）。"""
    from app.shared.tools.skills.project.ProjectTools import (
        IntentClarificationInput,
        Question,
        QuestionOption,
    )

    q = Question(
        question="请选择文档类型",
        header="doc_type",
        options=[
            QuestionOption(label="需求规格", description="标准需求文档"),
            QuestionOption(label="概要设计", description="概要设计文档"),
        ],
    )
    data = IntentClarificationInput(questions=[q])
    assert len(data.questions) == 1
    assert data.questions[0].header == "doc_type"


def test_intent_clarification_input_rejects_empty_questions():
    """P1: questions 为空时抛 Pydantic ValidationError。"""
    from pydantic import ValidationError

    from app.shared.tools.skills.project.ProjectTools import IntentClarificationInput

    try:
        IntentClarificationInput(questions=[])
    except ValidationError:
        return
    raise AssertionError("questions=[] 应抛 ValidationError")


def test_intent_clarification_input_rejects_too_many_questions():
    """P1: questions > 4 时抛 Pydantic ValidationError。"""
    from pydantic import ValidationError

    from app.shared.tools.skills.project.ProjectTools import (
        IntentClarificationInput,
        Question,
    )

    questions = [
        Question(question=f"q{i}", header=f"h{i}", options=[])
        for i in range(5)
    ]
    try:
        IntentClarificationInput(questions=questions)
    except ValidationError:
        return
    raise AssertionError("questions=5 个应抛 ValidationError")


# ============================================================
# P1: intent_clarification 行为
# ============================================================


def _make_runtime(tool_call_id="call-ic"):
    """构造最小可用的 ToolRuntime 替身。"""
    rt = MagicMock()
    rt.tool_call_id = tool_call_id
    return rt


def _resolve_func(tool_wrapper):
    """在测试 env 下从 wrapped 工具或函数本身取得可调用对象。

    - 生产环境：`tool_wrapper` 是 `StructuredTool`，取其 `func` 即可。
    - 测试环境：`@tool` 被 conftest 替换为 identity，`register_tool` 也返回原函数，
      所以 `tool_wrapper` 本身就是可调用函数。
    """
    if callable(tool_wrapper) and hasattr(tool_wrapper, "func"):
        return tool_wrapper.func
    return tool_wrapper


def test_intent_clarification_returns_command_with_pending():
    """P1: intent_clarification 返回 Command，含 pending_question 与 messages。"""
    from langgraph.types import Command

    from app.shared.tools.skills.project.ProjectTools import (
        Question,
        QuestionOption,
        intent_clarification,
    )

    q = Question(
        question="doc type?",
        header="doc_type",
        options=[
            QuestionOption(label="需求", description="需求规格"),
            QuestionOption(label="设计", description="设计文档"),
        ],
    )
    rt = _make_runtime(tool_call_id="call-001")
    func = _resolve_func(intent_clarification)

    with patch("app.shared.tools.skills.project.ProjectTools.get_stream_writer") as mock_gsw:
        mock_gsw.return_value = lambda event: None
        result = func([q], rt)

    assert isinstance(result, Command)
    assert "pending_question" in result.update
    assert result.update["pending_question"]["status"] == "pending"
    assert result.update["pending_question"]["tool_call_id"] == "call-001"
    assert len(result.update["pending_question"]["questions"]) == 1
    assert "messages" in result.update


# ============================================================
# P1: manage_project_log / append_change_log 行为
# ============================================================


def test_manage_project_log_append_creates_file(tmp_path, monkeypatch):
    """P1: manage_project_log(append) 写入 .project/project_log.md。"""
    from app.shared.tools.skills.project import ProjectTools

    project_id = "2026/07/02/test-uuid"

    def _fake_resolve(rel: str):
        if not rel:
            raise ValueError("empty")
        return tmp_path / rel

    monkeypatch.setattr(ProjectTools, "resolve_project_dir", _fake_resolve)
    func = _resolve_func(ProjectTools.manage_project_log)

    fake_tm = MagicMock()
    with patch.object(ProjectTools, "get_stream_writer") as mock_gsw, \
         patch.object(ProjectTools, "ToolMessage", fake_tm):
        mock_gsw.return_value = lambda event: None
        rt = _make_runtime()
        result = func(project_id, "append", "测试记录内容", rt)

    assert hasattr(result, "update")
    assert fake_tm.call_count == 1
    payload_text = fake_tm.call_args.kwargs.get("content")
    payload = json.loads(payload_text)
    assert payload["status"] == "success"
    log_file = tmp_path / "data/project" / project_id / ".project" / "project_log.md"
    assert log_file.exists()
    text = log_file.read_text(encoding="utf-8")
    assert "测试记录内容" in text


def test_manage_project_log_read_returns_empty_when_no_file(tmp_path, monkeypatch):
    """P1: manage_project_log(read) 在文件不存在时返回 error_command。"""
    from app.shared.tools.skills.project import ProjectTools

    project_id = "2026/07/02/missing-uuid"

    def _fake_resolve(rel: str):
        if not rel:
            raise ValueError("empty")
        return tmp_path / rel

    monkeypatch.setattr(ProjectTools, "resolve_project_dir", _fake_resolve)
    func = _resolve_func(ProjectTools.manage_project_log)

    fake_tm = MagicMock()
    with patch.object(ProjectTools, "get_stream_writer") as mock_gsw, \
         patch.object(ProjectTools, "ToolMessage", fake_tm):
        mock_gsw.return_value = lambda event: None
        rt = _make_runtime(tool_call_id="call-read")
        result = func(project_id, "read", "", rt)

    assert hasattr(result, "update")
    assert fake_tm.call_count == 1
    payload_text = fake_tm.call_args.kwargs.get("content")
    payload = json.loads(payload_text)
    assert payload["status"] == "error"
    assert "日志文件不存在" in payload["message"]


def test_append_change_log_creates_file(tmp_path, monkeypatch):
    """P1: append_change_log 写入 .project/变更记录.md。"""
    from app.shared.tools.skills.project import ProjectTools

    project_id = "2026/07/02/changelog-uuid"

    def _fake_resolve(rel: str):
        if not rel:
            raise ValueError("empty")
        return tmp_path / rel

    monkeypatch.setattr(ProjectTools, "resolve_project_dir", _fake_resolve)
    func = _resolve_func(ProjectTools.append_change_log)

    fake_tm = MagicMock()
    with patch.object(ProjectTools, "get_stream_writer") as mock_gsw, \
         patch.object(ProjectTools, "ToolMessage", fake_tm):
        mock_gsw.return_value = lambda event: None
        rt = _make_runtime()
        result = func(project_id, "初始化变更记录", rt)

    assert hasattr(result, "update")
    assert fake_tm.call_count == 1
    payload_text = fake_tm.call_args.kwargs.get("content")
    payload = json.loads(payload_text)
    assert payload["status"] == "success"
    change_file = tmp_path / "data/project" / project_id / ".project" / "变更记录.md"
    assert change_file.exists()
    text = change_file.read_text(encoding="utf-8")
    assert "初始化变更记录" in text
    assert "# 变更记录" in text


# ============================================================
# P1: generate_project_docx 落盘
# ============================================================


def test_generate_project_docx_writes_file(tmp_path, monkeypatch):
    """P1: generate_project_docx 写入 data/download/{session_id}/。"""
    from app.shared.tools.skills.project import ProjectTools

    # 切换工作目录到 tmp_path，避免污染真实 data/download
    monkeypatch.chdir(tmp_path)
    func = _resolve_func(ProjectTools.generate_project_docx)

    # 构造带 session_id 的 runtime
    rt = MagicMock()
    rt.tool_call_id = "docx-call"
    rt.context = {"session_id": "session-001"}

    fake_tm = MagicMock()
    with patch.object(ProjectTools, "get_stream_writer") as mock_gsw, \
         patch.object(ProjectTools, "WordReportGenerator") as MockGen, \
         patch.object(ProjectTools, "ToolMessage", fake_tm):
        mock_gsw.return_value = lambda event: None
        instance = MagicMock()
        MockGen.return_value = instance

        result = func("p-001", "# 测试标题\n\n正文", "测试文档", rt)

    assert hasattr(result, "update")
    assert fake_tm.call_count == 1
    payload_text = fake_tm.call_args.kwargs.get("content")
    payload = json.loads(payload_text)
    assert payload["status"] == "success"
    assert payload["file_name"].endswith(".docx")
    assert payload["download_url"].endswith(".docx")
    instance.generate.assert_called_once()
    instance.save.assert_called_once()
    # 验证 save 收到正确路径
    save_args = instance.save.call_args
    saved_path = save_args.args[0] if save_args.args else save_args.kwargs.get("file_path")
    assert saved_path is not None
    saved_path_str = str(saved_path).replace("\\", "/")
    assert saved_path_str.endswith(".docx")
    assert "data/download" in saved_path_str
    assert "session-001" in saved_path_str
