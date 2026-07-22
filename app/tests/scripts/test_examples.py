# -*- coding:utf-8 -*-
"""
脚本开发样板 ``hello_script`` 测试。

覆盖点:
    * 模块可正常导入
    * 导入后自动注册到全局 registry
    * ``run(context)`` 在不同 ``mode`` 下分别返回 ``str`` 或
      ``tuple[str, list[str]]``
    * 单附件 / 多附件模式正确生成文件并返回绝对路径
    * ``mode=error`` 抛出 ``ScriptExecutionError``
    * 默认参数行为符合预期
    * ``params_schema`` 声明 ``server_list`` 字段及 UI 扩展元数据,
      ``run`` 在 ``mode=text`` 下消费 ``server_list`` 字符串数组并在缺省或为空时
      保持既有摘要。
"""
import importlib
import inspect
import logging
import typing
from datetime import datetime
from pathlib import Path

import pytest

from app.scripts.base import ScriptContext, ScriptExecutionError
from app.scripts.registry import clear_registry, get_registered_script


@pytest.fixture(autouse=True)
def _isolate_script_registry():
    """隔离全局脚本注册表，避免测试间相互污染。

    导入 ``app.scripts.examples.hello_script`` 会触发 ``@register_script``
    装饰器把 ``hello_script`` 写入全局 ``_SCRIPT_REGISTRY``。本 fixture
    在每个用例前后清空注册表，确保互不干扰。

    返回: 无。
    异常: 无。
    """
    clear_registry()
    yield
    clear_registry()


def test_hello_script_importable():
    """``hello_script`` 模块应可正常导入且含 ``run`` 函数。"""
    from app.scripts.examples import hello_script  # noqa: F401

    assert hasattr(hello_script, "run")
    assert callable(hello_script.run)


def test_hello_script_registered_in_registry():
    """导入后 ``hello_script`` 应出现在 registry 且展示名为 ``脚本开发样板``。"""
    from app.scripts.examples import hello_script  # noqa: F401
    importlib.reload(hello_script)

    from app.scripts.registry import get_registered_script

    s = get_registered_script("hello_script")
    assert s is not None
    assert s.display_name == "脚本开发样板"
    assert s.name == "hello_script"


def test_hello_script_run_signature():
    """``hello_script.run`` 签名应为 ``async def run(context: ScriptContext) -> str | tuple[str, list[str]]``。"""
    from app.scripts.examples import hello_script

    sig = inspect.signature(hello_script.run)
    assert list(sig.parameters.keys()) == ["context"]

    hints = typing.get_type_hints(hello_script.run)
    assert hints["context"] is ScriptContext
    assert hints["return"] == str | tuple[str, list[str]]


def _make_context(
    monkeypatch,
    tmp_path,
    *,
    script_args=None,
    schedule_name="测试任务",
    run_id=100,
    started_at=None,
    trigger_type="manual",
):
    """构造一个隔离的 ``ScriptContext`` 测试对象。

    参数:
        monkeypatch: pytest 替换工具。
        tmp_path: pytest 临时目录。
        script_args: 脚本参数字典。
        schedule_name: 任务名称。
        run_id: 执行记录 ID。
        started_at: 开始时间，默认 2026-07-19 10:30:45。
        trigger_type: 触发方式。

    返回:
        ScriptContext: 用于测试的上下文对象。
    """
    from app.scripts.examples import hello_script

    fake_attachment_dir = tmp_path / "Task"
    fake_attachment_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hello_script, "TASK_ATTACHMENT_DIR", str(fake_attachment_dir))

    return ScriptContext(
        schedule_id=1,
        run_id=run_id,
        session_id=f"task-{run_id}-abc",
        schedule_name=schedule_name,
        script_args=script_args or {},
        log_logger=logging.getLogger(f"test_hello_script_{run_id}"),
        started_at=started_at or datetime(2026, 7, 19, 10, 30, 45),
        trigger_type=trigger_type,
    )


@pytest.mark.asyncio
async def test_hello_script_mode_text_returns_str(monkeypatch, tmp_path):
    """``mode=text`` 时应返回纯文本字符串。"""
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "text", "content": "Hello"},
    )
    result = await hello_script.run(context)

    assert isinstance(result, str)
    assert "Hello" in result
    assert "run_id=100" in result
    assert "trigger=manual" in result


@pytest.mark.asyncio
async def test_hello_script_mode_single_returns_one_attachment(monkeypatch, tmp_path):
    """``mode=single`` 时应返回 ``(body, [path])`` 并生成一个 ``.txt`` 附件。"""
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "single", "content": "Single"},
    )
    result = await hello_script.run(context)

    assert isinstance(result, tuple) and len(result) == 2
    body, attachments = result
    assert isinstance(body, str)
    assert "Single" in body
    assert isinstance(attachments, list) and len(attachments) == 1

    attachment = Path(attachments[0])
    assert attachment.is_absolute()
    assert attachment.is_file()
    assert attachment.suffix == ".txt"
    assert attachment.name == "20260719_103045_100.txt"
    assert "Single" in attachment.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_hello_script_mode_multi_returns_two_attachments(monkeypatch, tmp_path):
    """``mode=multi`` 时应返回 ``(body, [path1, path2])`` 并生成 ``.txt`` 与 ``.md`` 附件。"""
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "multi", "content": "Multi"},
    )
    result = await hello_script.run(context)

    assert isinstance(result, tuple) and len(result) == 2
    body, attachments = result
    assert isinstance(body, str)
    assert "Multi" in body
    assert isinstance(attachments, list) and len(attachments) == 2

    suffixes = []
    for path in attachments:
        attachment = Path(path)
        assert attachment.is_absolute()
        assert attachment.is_file()
        suffixes.append(attachment.suffix)
        assert "Multi" in attachment.read_text(encoding="utf-8")

    assert set(suffixes) == {".txt", ".md"}


@pytest.mark.asyncio
async def test_hello_script_mode_error_raises_script_execution_error(monkeypatch, tmp_path):
    """``mode=error`` 时应抛出 ``ScriptExecutionError``。"""
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "error"},
    )
    with pytest.raises(ScriptExecutionError, match="mode=error"):
        await hello_script.run(context)


@pytest.mark.asyncio
async def test_hello_script_default_mode_and_content(monkeypatch, tmp_path):
    """``script_args`` 为空时应使用默认值 ``mode=text`` 与 ``content=定时任务执行成功``。"""
    from app.scripts.examples import hello_script

    context = _make_context(monkeypatch, tmp_path, script_args={})
    result = await hello_script.run(context)

    assert isinstance(result, str)
    assert "定时任务执行成功" in result
    assert "run_id=100" in result
    assert "trigger=manual" in result


# ----------------------------------------------------------------------------
# 脚本样板的 server_list 参数契约（schema + 行为）
# ----------------------------------------------------------------------------


def test_hello_script_params_schema_declares_server_list():
    """``params_schema`` 应声明 ``server_list`` 字段，类型与 UI 扩展精确匹配。

    沿用 ``test_hello_script_registered_in_registry`` 的 reload+registry 风格，
    避免不同用例之间注册表状态相互污染。
    """
    from app.scripts.examples import hello_script  # noqa: F401
    importlib.reload(hello_script)

    s = get_registered_script("hello_script")
    assert s is not None, "hello_script 应已注册到 registry"

    schema = s.params_schema
    assert isinstance(schema, dict)
    properties = schema.get("properties", {})
    assert "server_list" in properties, (
        "params_schema.properties 必须包含 server_list"
    )

    server_list = properties["server_list"]
    assert server_list["type"] == "array"
    # items 仅断言元素类型为字符串，允许未来增加 description 等描述字段
    assert server_list["items"]["type"] == "string"
    assert server_list["uniqueItems"] is True
    assert server_list["default"] == []
    assert server_list["x-control"] == "server-multiselect"
    assert server_list["x-source"] == "devops-servers"
    assert server_list["x-value-field"] == "business_name"


@pytest.mark.asyncio
async def test_hello_script_text_mode_returns_servers(monkeypatch, tmp_path):
    """``mode=text`` + ``server_list`` 含两个业务名时，结果应保留原 summary 且包含两个业务名。"""
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={
            "mode": "text",
            "server_list": ["业务A-生产", "业务B-测试"],
        },
    )
    result = await hello_script.run(context)

    assert isinstance(result, str), "mode=text 必须返回纯文本"
    # 既有 summary 字段必须保留，避免破坏现有契约
    assert "run_id=100" in result
    assert "trigger=manual" in result
    # 新参数的业务名应出现在返回文本中
    assert "业务A-生产" in result
    assert "业务B-测试" in result


@pytest.mark.asyncio
async def test_hello_script_server_list_missing_or_empty_keeps_default_summary(
    monkeypatch, tmp_path
):
    """``server_list`` 缺失或为空数组时，结果应与原默认摘要完全一致。

    验证:
        * 默认参数 ``script_args={}`` 与 ``script_args={"server_list": []}`` 的
          返回字符串完全相等，说明空数组与缺失键在 ``run`` 内部行为等价
        * 自定义 ``content`` 配合空数组时，结果保留自定义 ``content``，且不追加
          空服务器列表相关文案
    """
    from app.scripts.examples import hello_script

    # 1) 默认 args={} 与 args={"server_list": []} 两次执行结果完全相等
    default_context = _make_context(monkeypatch, tmp_path, script_args={})
    default_result = await hello_script.run(default_context)

    empty_server_list_context = _make_context(
        monkeypatch, tmp_path, script_args={"server_list": []}
    )
    empty_server_list_result = await hello_script.run(empty_server_list_context)

    assert isinstance(default_result, str)
    assert isinstance(empty_server_list_result, str)
    assert default_result == empty_server_list_result, (
        "server_list 缺失与为空数组时输出必须完全相等，"
        f"default={default_result!r} empty={empty_server_list_result!r}"
    )

    # 2) 自定义 content + 空数组：保留自定义 content，不追加空列表文案
    custom_context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "text", "content": "Hello", "server_list": []},
    )
    custom_result = await hello_script.run(custom_context)

    assert isinstance(custom_result, str)
    assert "Hello" in custom_result
    # 不附加空服务器列表文案，避免破坏既有契约
    assert "服务器列表" not in custom_result
    assert "[]" not in custom_result


@pytest.mark.parametrize(
    "bad_server_list",
    [
        "业务A-生产",  # 字符串而非数组
        ["业务A-生产", 123],  # 含数字
        ["业务A-生产", None],  # 含 null
        ["业务A-生产", ""],  # 含空字符串
    ],
    ids=["string", "with-int", "with-null", "with-empty-string"],
)
@pytest.mark.asyncio
async def test_hello_script_invalid_server_list_raises(
    monkeypatch, tmp_path, bad_server_list
):
    """``server_list`` 不合法（字符串 / 含数字 / 含 null / 含空字符串）时应抛 ``ScriptExecutionError``。

    错误消息需包含 ``server_list`` 字段名，便于调度器日志定位。
    """
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "text", "server_list": bad_server_list},
    )
    with pytest.raises(ScriptExecutionError, match="server_list"):
        await hello_script.run(context)


# ----------------------------------------------------------------------------
# 脚本样板的 api_list 参数契约（schema + 行为）
# ----------------------------------------------------------------------------


def test_hello_script_params_schema_declares_api_list():
    """``params_schema`` 应声明 ``api_list`` 字段，类型与 UI 扩展精确匹配。

    契约：
        x-control=api-multiselect / x-source=api-configs / x-value-field=id；
        元素类型为字符串；uniqueItems=True；默认空数组。
    """
    from app.scripts.examples import hello_script  # noqa: F401
    importlib.reload(hello_script)

    s = get_registered_script("hello_script")
    assert s is not None, "hello_script 应已注册到 registry"

    schema = s.params_schema
    properties = schema.get("properties", {})
    assert "api_list" in properties, "params_schema.properties 必须包含 api_list"

    api_list = properties["api_list"]
    assert api_list["type"] == "array"
    assert api_list["items"]["type"] == "string"
    assert api_list["uniqueItems"] is True
    assert api_list["default"] == []
    assert api_list["x-control"] == "api-multiselect"
    assert api_list["x-source"] == "api-configs"
    assert api_list["x-value-field"] == "id"


@pytest.mark.asyncio
async def test_hello_script_api_list_present_appends_check_summary(monkeypatch, tmp_path):
    """``api_list`` 非空时正文摘要应追加 ``api_check=...`` 行（来自 ``run_api_checks`` stub）。"""
    from app.scripts.examples import hello_script

    # 用 stub 替换 run_api_checks，断言 hello_script 真的在 run 内调用并把 summary 拼到正文
    captured_ctx: dict = {}
    async def stub_run_api_checks(context):
        captured_ctx["args"] = dict(context.script_args)
        from app.scripts.api_check import ApiCheckItem, ApiCheckReport
        report = ApiCheckReport(items=[
            ApiCheckItem(node_id=10, name="查询接口", path="业务系统",
                         check_passed=True, http_status=200, duration_ms=12),
            ApiCheckItem(node_id=11, name="上报接口", path="",
                         check_passed=False, http_status=500, duration_ms=8,
                         error_message="服务端错误"),
        ])
        return report
    monkeypatch.setattr(hello_script, "run_api_checks", stub_run_api_checks)

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "text", "api_list": ["10", "11"]},
    )
    result = await hello_script.run(context)

    assert captured_ctx["args"]["api_list"] == ["10", "11"]
    assert isinstance(result, str)
    assert "api_check=1/2 passed" in result
    assert "id=10 OK 200/12ms" in result
    assert "id=11 FAIL 500/8ms" in result


@pytest.mark.asyncio
async def test_hello_script_api_list_empty_keeps_default_summary(monkeypatch, tmp_path):
    """``api_list`` 缺失 / 空数组时与原默认摘要完全一致。

    ``run_api_checks`` 仍会被调用一次（脚本入口固定调用），其内部对空 ids
    短路返回空 report；因此两次执行结果完全相等，且均不含 ``api_check=`` 行。
    """
    from app.scripts.examples import hello_script
    from app.scripts.api_check import ApiCheckReport

    calls: list = []
    async def stub_empty_report(context):
        calls.append(list(context.script_args.get("api_list") or []))
        return ApiCheckReport(items=[])
    monkeypatch.setattr(hello_script, "run_api_checks", stub_empty_report)

    ctx_missing = _make_context(monkeypatch, tmp_path, script_args={})
    out_missing = await hello_script.run(ctx_missing)
    ctx_empty = _make_context(monkeypatch, tmp_path, script_args={"api_list": []})
    out_empty = await hello_script.run(ctx_empty)

    assert out_missing == out_empty
    assert "api_check=" not in out_missing
    assert calls == [[], []], "两次 run 都会调用 run_api_checks，传入空数组"


@pytest.mark.asyncio
async def test_hello_script_api_list_md_attachment_includes_table(monkeypatch, tmp_path):
    """``mode=multi`` + ``api_list`` 非空时，``.md`` 附件应包含接口健康检查表格。"""
    from app.scripts.examples import hello_script
    from app.scripts.api_check import ApiCheckItem, ApiCheckReport

    async def stub(context):
        return ApiCheckReport(items=[
            ApiCheckItem(node_id=10, name="查询接口", path="业务系统",
                         check_passed=True, http_status=200, duration_ms=15),
        ])

    monkeypatch.setattr(hello_script, "run_api_checks", stub)

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "multi", "content": "Demo", "api_list": ["10"]},
    )
    result = await hello_script.run(context)
    assert isinstance(result, tuple) and len(result) == 2
    _, attachments = result
    md_path = next(p for p in attachments if p.endswith(".md"))
    md_text = Path(md_path).read_text(encoding="utf-8")
    assert "## 接口健康检查" in md_text
    assert "| 查询接口 | 业务系统 | 200 | 15 | 通过 |" in md_text


@pytest.mark.parametrize(
    "bad_api_list",
    [
        "10",  # 字符串而非数组
        ["10", 123],  # 含数字
        ["10", None],  # 含 null
        ["10", ""],  # 含空字符串
    ],
    ids=["string", "with-int", "with-null", "with-empty-string"],
)
@pytest.mark.asyncio
async def test_hello_script_invalid_api_list_raises(
    monkeypatch, tmp_path, bad_api_list
):
    """``api_list`` 不合法（字符串 / 含数字 / 含 null / 含空字符串）时应抛 ``ScriptExecutionError``。

    api_config_service 在脚本内被 run_api_checks 解析；api_list 非空时先校验。
    本测试不预装 service，因此一旦校验通过才会去取 service；这里直接覆盖校验阶段。
    """
    from app.scripts.examples import hello_script

    context = _make_context(
        monkeypatch,
        tmp_path,
        script_args={"mode": "text", "api_list": bad_api_list},
    )
    with pytest.raises(ScriptExecutionError, match="api_list"):
        await hello_script.run(context)


@pytest.mark.asyncio
async def test_hello_script_api_list_non_integer_id_raises_when_service_called(
    monkeypatch, tmp_path
):
    """``api_list`` 含非整数字符串时，``run_api_checks`` -> ``resolve_api_list`` 抛错。

    为触发 ``service.send_request`` 之前的 ``resolve_api_list`` 分支，需先把 service 注入；
    本用例直接构造 stub service 并预置 args，确认脚本侧确实抛 ScriptExecutionError。
    """
    from app.scripts.examples import hello_script

    class _S:
        async def get_tree(self): return []
        async def send_request(self, _id):  # 不应到达
            raise AssertionError("send_request 不应在解析阶段之前被调用")

    ctx = _make_context(
        monkeypatch, tmp_path,
        script_args={"mode": "text", "api_list": ["bad"]},
    )
    ctx.api_config_service = _S()
    with pytest.raises(ScriptExecutionError, match="api_list"):
        await hello_script.run(ctx)
