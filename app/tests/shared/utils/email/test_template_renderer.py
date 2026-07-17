# -*- coding:utf-8 -*-
"""
EmailTemplateRenderer 单元测试模块。

覆盖：
- 基础占位符替换（白名单变量）
- 未匹配变量保留原样
- 非白名单变量忽略（防注入）
- datetime / list / None 等值规范化为字符串
- 空模板返回空串
- 占位符内允许空白
"""
from datetime import datetime

from app.shared.utils.email import EmailTemplateRenderer
from app.shared.utils.email.template_renderer import build_render_context


# =============================================================================
# P0: 导入与构造
# =============================================================================

def test_template_renderer_importable():
    """测试 EmailTemplateRenderer 模块可导入。"""
    from app.shared.utils.email import template_renderer

    assert hasattr(template_renderer, "EmailTemplateRenderer")
    assert hasattr(template_renderer, "build_render_context")
    assert hasattr(EmailTemplateRenderer, "SUPPORTED_VARS")
    assert "schedule_name" in EmailTemplateRenderer.SUPPORTED_VARS
    assert "script_output" in EmailTemplateRenderer.SUPPORTED_VARS


# =============================================================================
# P1: 基础渲染
# =============================================================================

def test_render_replaces_whitelisted_variable():
    """白名单变量应被正确替换。"""
    out = EmailTemplateRenderer.render(
        "Hello {{schedule_name}}", {"schedule_name": "每日巡检"}
    )
    assert out == "Hello 每日巡检"


def test_render_replaces_multiple_variables():
    """同一模板中的多个占位符应全部替换。"""
    out = EmailTemplateRenderer.render(
        "schedule={{schedule_name}}, run={{run_id}}",
        {"schedule_name": "cron-job", "run_id": 42},
    )
    assert out == "schedule=cron-job, run=42"


def test_render_keeps_unknown_variable_intact():
    """未匹配的占位符应保留原样，方便调试。"""
    out = EmailTemplateRenderer.render(
        "foo {{unknown_var}} bar {{schedule_name}}",
        {"schedule_name": "ok"},
    )
    assert out == "foo {{unknown_var}} bar ok"


def test_render_ignores_non_whitelisted_keys():
    """非白名单变量应被忽略；模板里若提到该占位符则保留原样。"""
    # ctx 含 eval / import 等敏感键
    ctx = {
        "schedule_name": "ok",
        "eval": "1+1",
        "__import__": "os",
        "code": "<script>",
    }
    out = EmailTemplateRenderer.render(
        "{{schedule_name}}-{{eval}}-{{__import__}}",
        ctx,
    )
    # 只有 schedule_name 被替换；其他占位符保留原样
    assert out == "ok-{{eval}}-{{__import__}}"


def test_render_allows_spaces_around_variable_name():
    """占位符允许 ``{{ var }}`` 含任意空白。"""
    out = EmailTemplateRenderer.render(
        "[{{ schedule_name }}]", {"schedule_name": "x"}
    )
    assert out == "[x]"


def test_render_empty_template_returns_empty_string():
    """空模板返回空字符串。"""
    assert EmailTemplateRenderer.render("", {"schedule_name": "x"}) == ""


def test_render_no_placeholder_returns_template_unchanged():
    """模板不含占位符时原样返回。"""
    assert EmailTemplateRenderer.render(
        "no placeholders here", {"schedule_name": "x"}
    ) == "no placeholders here"


def test_render_stringifies_datetime():
    """datetime 值应规范化为 ``YYYY-MM-DD HH:MM:SS``。"""
    dt = datetime(2026, 7, 17, 9, 0, 0)
    out = EmailTemplateRenderer.render(
        "started={{started_at}}", {"started_at": dt}
    )
    assert out == "started=2026-07-17 09:00:00"


def test_render_stringifies_list_with_comma_join():
    """list 值应使用逗号拼接为字符串。"""
    out = EmailTemplateRenderer.render(
        "files={{attachment_paths}}",
        {"attachment_paths": ["/a.pdf", "/b.docx"]},
    )
    assert out == "files=/a.pdf, /b.docx"


def test_render_stringifies_none_as_empty_string():
    """None 应规范化为空串。"""
    out = EmailTemplateRenderer.render(
        "[{{script_name}}]", {"script_name": None}
    )
    assert out == "[]"


def test_render_stringifies_non_string_scalar():
    """其他标量走 str(value)。"""
    out = EmailTemplateRenderer.render(
        "{{run_id}}", {"run_id": 12345}
    )
    assert out == "12345"


def test_render_handles_context_none():
    """context=None 时不应抛异常。"""
    out = EmailTemplateRenderer.render("hello {{schedule_name}}", None)
    assert out == "hello {{schedule_name}}"


# =============================================================================
# P1: build_render_context
# =============================================================================

def test_build_render_context_collects_all_supported_vars():
    """build_render_context 应填齐 SUPPORTED_VARS 中的所有变量。"""
    started = datetime(2026, 7, 17, 9, 0, 0)
    finished = datetime(2026, 7, 17, 9, 1, 30)
    ctx = build_render_context(
        schedule={"id": 7, "name": "daily"},
        run_id=99,
        script_output="hello",
        attachments=["/tmp/a.pdf"],
        started_at=started,
        finished_at=finished,
        trigger_type="scheduled",
        script_name="hello_script",
    )
    expected_keys = {
        "schedule_name", "schedule_id", "run_id",
        "started_at", "finished_at", "trigger_type",
        "script_name", "script_output", "attachment_paths",
    }
    assert set(ctx.keys()) == expected_keys
    assert ctx["schedule_name"] == "daily"
    assert ctx["schedule_id"] == 7
    assert ctx["run_id"] == 99
    assert ctx["trigger_type"] == "scheduled"
    assert ctx["script_name"] == "hello_script"
    assert ctx["script_output"] == "hello"
    assert ctx["attachment_paths"] == ["/tmp/a.pdf"]


def test_build_render_context_handles_missing_fields():
    """schedule 字段缺失时使用默认值（避免 KeyError）。"""
    ctx = build_render_context(
        schedule={},
        run_id=1,
        script_output="",
        attachments=None,
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        finished_at=datetime(2026, 1, 1, 0, 0, 1),
        trigger_type="manual",
        script_name=None,
    )
    assert ctx["schedule_name"] == ""
    assert ctx["schedule_id"] is None
    assert ctx["script_name"] == ""
    assert ctx["script_output"] == ""
    assert ctx["attachment_paths"] == []


def test_end_to_end_build_then_render():
    """build_render_context 生成的 context 喂给 render 能完整渲染。"""
    ctx = build_render_context(
        schedule={"id": 1, "name": "cron"},
        run_id=2,
        script_output="ok",
        attachments=None,
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        finished_at=datetime(2026, 1, 1, 0, 0, 5),
        trigger_type="scheduled",
        script_name="hello_script",
    )
    out = EmailTemplateRenderer.render(
        "[{{schedule_name}}#{{run_id}}] {{script_output}}",
        ctx,
    )
    assert out == "[cron#2] ok"
