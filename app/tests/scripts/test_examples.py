# -*- coding:utf-8 -*-
"""
示例脚本 ``hello_script`` 测试。

覆盖点:
    * 模块可正常导入
    * 导入后自动注册到全局 registry
    * ``run(context)`` 返回 ``tuple[str, str]`` 元组,
      内部通过 ``WordReportGenerator`` 生成 Word 报告并保存到附件目录
    * ``run`` 锁定为 ``async def run(context: ScriptContext) -> tuple[str, str]``
"""
import asyncio
import importlib
import inspect
import logging
import typing
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.scripts.base import ScriptContext
from app.scripts.registry import clear_registry
from app.shared.utils.report.word import ReportConfig


@pytest.fixture(autouse=True)
def _isolate_script_registry():
    """隔离全局脚本注册表,避免测试间相互污染。

    导入 ``app.scripts.examples.hello_script`` 会触发 ``@register_script``
    装饰器把 ``hello_script`` 写入全局 ``_SCRIPT_REGISTRY``。其他测试用例
    此前可能已经导入过该模块,导致重新加载时报 ``ValueError: 脚本名
    'hello_script' 已被注册``。本 fixture 在用例执行前清空注册表,执行后
    再清空,确保互不干扰。

    返回: 无。
    异常: 无。
    """
    clear_registry()
    yield
    clear_registry()


def test_hello_script_importable():
    """``hello_script`` 模块应可正常导入且含 ``run`` 函数。

    参数: 无。
    返回: 无。
    异常: 若模块缺失或 ``run`` 不存在,pytest 断言失败。
    """
    from app.scripts.examples import hello_script  # noqa: F401

    assert hasattr(hello_script, "run")
    assert callable(hello_script.run)


def test_hello_script_registered_in_registry():
    """导入后 ``hello_script`` 应出现在 registry 且展示名为 ``示例 Word 附件脚本``。

    为避免 ``@register_script`` 装饰器重复注册触发 ``ValueError``,本测试
    在 importlib.reload 之前显式调用 ``clear_registry()`` 清空注册表,然后
    重新加载模块以触发真实装饰器重新执行注册流程。

    参数: 无。
    返回: 无。
    异常: 若注册缺失或展示名不符,pytest 断言失败。
    """
    clear_registry()

    from app.scripts.examples import hello_script  # noqa: F401
    importlib.reload(hello_script)

    s = hello_script_registry_entry(hello_script)
    assert s is not None
    assert s.display_name == "示例 Word 附件脚本"
    assert s.name == "hello_script"


def hello_script_registry_entry(hello_script):
    """根据重新加载后的 ``hello_script`` 模块查找注册条目。

    参数:
        hello_script: 已通过 ``importlib.reload`` 重新加载的模块对象。

    返回:
        RegisteredScript: 注册表中的条目。若未找到则返回 None。
    """
    from app.scripts.registry import get_registered_script

    return get_registered_script("hello_script")


def test_hello_script_run_signature_is_tuple_str_str():
    """``hello_script.run`` 签名应严格为 ``async def run(context) -> tuple[str, str]``。

    使用 ``typing.get_type_hints`` 解析前向引用得到真实 ``ScriptContext``
    类对象与 ``tuple[str, str]`` 标注,精确断言:
        * 参数名列表仅包含 ``["context"]``
        * ``context`` 标注为 ``ScriptContext``(同一对象)
        * 返回值标注解析后等于 ``tuple[str, str]``

    参数: 无。
    返回: 无。
    异常: 若签名不符,pytest 断言失败。
    """
    from app.scripts.examples import hello_script

    sig = inspect.signature(hello_script.run)
    # 1) 参数名列表必须严格为 ["context"],无 *args/**kwargs/其他额外参数
    assert list(sig.parameters.keys()) == ["context"], (
        f"signature parameters must be exactly ['context'], "
        f"got {list(sig.parameters.keys())!r}"
    )

    # 2) 使用 typing.get_type_hints 解析所有前向引用为真实对象
    hints = typing.get_type_hints(hello_script.run)
    assert "context" in hints, (
        f"type hints missing 'context' annotation, got {sorted(hints.keys())!r}"
    )
    assert "return" in hints, (
        f"type hints missing 'return' annotation, got {sorted(hints.keys())!r}"
    )

    # 3) context 参数类型必须精确为 ScriptContext(同一类型对象)
    assert hints["context"] is ScriptContext, (
        f"hints['context'] must be ScriptContext, got {hints['context']!r}"
    )

    # 4) 返回值类型必须精确为 tuple[str, str](解析后 equals)
    assert hints["return"] == tuple[str, str], (
        f"hints['return'] must be tuple[str, str], got {hints['return']!r}"
    )
    # 额外断言 typing 模块层面的 tuple[str, str] 也等于 hints["return"],
    # 确保不是 tuple[X, Y] 或其他元组变体
    assert typing.get_type_hints(hello_script.run)["return"] == tuple[str, str]


@pytest.mark.asyncio
async def test_hello_script_generates_word_attachment(monkeypatch, tmp_path):
    """``run(context)`` 应通过 ``WordReportGenerator`` 生成 Word 附件。

    锁定精确契约:
        * ``report_data`` 精确为 ``任务名称/执行记录/触发方式/开始时间/问候内容``
        * ``cover.title.text == '{{任务名称}}定时任务执行报告'``
        * ``cover.date.text == '生成日期：{{开始时间}}'``
        * ``cover.title.space_before == 3`` 且 ``space_after == 1``
        * ``cover.date.space_before == 2``
        * ``toc is None``
        * sections 顺序: ``heading / paragraph / heading / 4*paragraph``
        * 两个 heading 的 ``in_toc == False`` 且 ``level == 1``
        * 正文模板精确对应批准计划
        * ``FooterConfig(format='第{page}页', start_from='content')``
        * ``fake_generator.save`` side_effect 写 ``b'fake-docx'`` 到 ``path``
        * 附件文件名 ``20260719_103045_100.docx``,父目录精确为 ``tmp_path/测试任务``
        * ``Path(saved_path).resolve() == Path(attachment_path)``
        * ``asyncio.to_thread`` 调用次数严格等于 2,顺序锁定:
          ``generate()`` 无参 + ``save(<attachment_path>)``

    参数:
        monkeypatch: pytest 替换工具,用于隔离生成器与附件目录。
        tmp_path: pytest 临时目录。

    返回: 无。

    异常:
        AssertionError: 任一契约不满足时失败。
    """
    from app.scripts.examples import hello_script

    fake_attachment_dir = tmp_path / "Task"
    fake_attachment_dir.mkdir(parents=True, exist_ok=True)

    fake_generator = MagicMock(name="WordReportGenerator")
    fake_doc = MagicMock(name="Document")
    fake_generator.generate.return_value = fake_doc

    def save_document(path):
        Path(path).write_bytes(b"fake-docx")

    fake_generator.save.side_effect = save_document

    captured_config: dict = {}

    def _capture_config(config):
        captured_config["config"] = config
        return fake_generator

    # to_thread spy: 记录调用并执行 func(*args)
    to_thread_calls = []

    async def fake_to_thread(func, *args, **kwargs):
        to_thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    context = ScriptContext(
        schedule_id=1,
        run_id=100,
        session_id="task-1-abc",
        schedule_name="测试任务",
        script_args={"greeting": "Hello"},
        log_logger=logging.getLogger("test_hello_script"),
        started_at=datetime(2026, 7, 19, 10, 30, 45),
        trigger_type="manual",
    )

    monkeypatch.setattr(hello_script, "TASK_ATTACHMENT_DIR", str(fake_attachment_dir))
    monkeypatch.setattr(hello_script, "WordReportGenerator", _capture_config)
    monkeypatch.setattr(hello_script.asyncio, "to_thread", fake_to_thread)

    result = await hello_script.run(context)

    # 返回值必须是 (body, attachment_path) 元组
    assert isinstance(result, tuple) and len(result) == 2
    body, attachment_path = result

    # to_thread 调用次数严格等于 2,顺序锁定
    assert len(to_thread_calls) == 2, (
        f"expected exactly 2 to_thread calls, got {len(to_thread_calls)}: "
        f"{[f.__name__ for f, _, _ in to_thread_calls]!r}"
    )
    # 第 1 次: generator.generate 无参数
    func1, args1, kwargs1 = to_thread_calls[0]
    assert func1 is fake_generator.generate, (
        f"first to_thread must be fake_generator.generate, got {func1!r}"
    )
    assert args1 == () and kwargs1 == {}, (
        f"first to_thread args/kwargs must be empty, got args={args1!r} kwargs={kwargs1!r}"
    )
    # 第 2 次: generator.save(attachment_path)
    func2, args2, kwargs2 = to_thread_calls[1]
    assert func2 is fake_generator.save, (
        f"second to_thread must be fake_generator.save, got {func2!r}"
    )
    assert kwargs2 == {}, f"second to_thread kwargs must be empty, got {kwargs2!r}"
    saved_path = args2[0]
    assert saved_path == attachment_path, (
        f"to_thread save path {saved_path!r} must match attachment_path {attachment_path!r}"
    )

    # body 内容锁定
    assert body == (
        f"Hello from schedule 测试任务 "
        f"(run_id=100, trigger=manual)"
    ), f"unexpected body: {body!r}"

    # attachment 文件名/路径锁定
    attachment = Path(attachment_path)
    assert attachment.name == "20260719_103045_100.docx", (
        f"attachment name must be 20260719_103045_100.docx, got {attachment.name!r}"
    )
    assert attachment.parent == (fake_attachment_dir / "测试任务"), (
        f"attachment parent must be {fake_attachment_dir / '测试任务'!s}, "
        f"got {attachment.parent!s}"
    )
    assert Path(saved_path).resolve() == Path(attachment_path), (
        f"Path(saved_path).resolve() {Path(saved_path).resolve()!s} "
        f"must == Path(attachment_path) {Path(attachment_path)!s}"
    )
    assert attachment.is_file()
    assert attachment.read_bytes() == b"fake-docx"

    # ReportConfig 契约
    config: ReportConfig = captured_config["config"]
    assert isinstance(config, ReportConfig)
    # data 精确键与值
    assert set(config.data.keys()) == {
        "任务名称",
        "执行记录",
        "触发方式",
        "开始时间",
        "问候内容",
    }, f"data keys mismatch: {sorted(config.data.keys())!r}"
    assert config.data["任务名称"] == "测试任务"
    assert config.data["执行记录"] == "100"
    assert config.data["触发方式"] == "manual"
    assert config.data["开始时间"] == "2026-07-19 10:30:45"
    assert config.data["问候内容"] == body

    # cover 契约(含标题/日期 space_before / space_after 精确值)
    assert config.cover is not None
    assert config.cover.title.text == "{{任务名称}}定时任务执行报告", (
        f"cover.title.text must be '{{{{任务名称}}}}定时任务执行报告', "
        f"got {config.cover.title.text!r}"
    )
    assert config.cover.title.space_before == 3, (
        f"cover.title.space_before must be 3, got {config.cover.title.space_before!r}"
    )
    assert config.cover.title.space_after == 1, (
        f"cover.title.space_after must be 1, got {config.cover.title.space_after!r}"
    )
    assert config.cover.date.text == "生成日期：{{开始时间}}", (
        f"cover.date.text must be '生成日期：{{{{开始时间}}}}', "
        f"got {config.cover.date.text!r}"
    )
    assert config.cover.date.space_before == 2, (
        f"cover.date.space_before must be 2, got {config.cover.date.space_before!r}"
    )

    # toc 必须为 None
    assert config.toc is None

    # sections 序列与正文模板
    section_types = [s.section_type for s in config.sections]
    assert section_types == [
        "heading",
        "paragraph",
        "heading",
        "paragraph",
        "paragraph",
        "paragraph",
        "paragraph",
    ], f"section_types mismatch: {section_types!r}"

    headings = [s for s in config.sections if s.section_type == "heading"]
    assert len(headings) == 2
    assert headings[0].in_toc is False, "first heading in_toc must be False"
    assert headings[1].in_toc is False, "second heading in_toc must be False"
    assert headings[0].level == 1, f"first heading level must be 1, got {headings[0].level!r}"
    assert headings[1].level == 1, f"second heading level must be 1, got {headings[1].level!r}"
    assert headings[0].content == "一、执行结果"
    assert headings[1].content == "二、任务信息"

    paragraphs = [s for s in config.sections if s.section_type == "paragraph"]
    assert paragraphs[0].content == "{{问候内容}}"
    assert paragraphs[1].content == "任务名称：{{任务名称}}"
    assert paragraphs[2].content == "执行记录：{{执行记录}}"
    assert paragraphs[3].content == "触发方式：{{触发方式}}"
    assert paragraphs[4].content == "开始时间：{{开始时间}}"

    # footer 契约
    assert config.footer.format == "第{page}页"
    assert config.footer.start_from == "content"

    # generate/save 真实调用次数
    fake_generator.generate.assert_called_once_with()
    fake_generator.save.assert_called_once_with(str(attachment))


@pytest.mark.asyncio
async def test_hello_script_uses_default_greeting_and_returns_attachment(monkeypatch, tmp_path):
    """``script_args`` 为空时应使用默认问候语 ``Hello`` 且仍返回附件路径。

    参数:
        monkeypatch: pytest 替换工具。
        tmp_path: pytest 临时目录。

    返回: 无。
    异常: AssertionError 当默认问候语未生效或返回结构不符合契约时。
    """
    from app.scripts.examples import hello_script

    fake_attachment_dir = tmp_path / "Task"
    fake_attachment_dir.mkdir(parents=True, exist_ok=True)

    fake_generator = MagicMock(name="WordReportGenerator")
    fake_generator.generate.return_value = MagicMock(name="Document")

    def save_document(path):
        Path(path).write_bytes(b"fake-docx")

    fake_generator.save.side_effect = save_document

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    context = ScriptContext(
        schedule_id=2,
        run_id=200,
        session_id="task-2-def",
        schedule_name="默认任务",
        script_args={},
        log_logger=logging.getLogger("test_hello_script_default"),
        started_at=datetime(2026, 7, 19, 11, 0, 0),
        trigger_type="scheduled",
    )

    monkeypatch.setattr(hello_script, "TASK_ATTACHMENT_DIR", str(fake_attachment_dir))
    monkeypatch.setattr(
        hello_script, "WordReportGenerator", lambda *a, **kw: fake_generator
    )
    monkeypatch.setattr(hello_script.asyncio, "to_thread", fake_to_thread)

    result = await hello_script.run(context)

    assert isinstance(result, tuple) and len(result) == 2
    body, attachment_path = result
    assert body.startswith("Hello "), f"default greeting must be 'Hello', got body={body!r}"
    assert isinstance(attachment_path, str)
    assert Path(attachment_path).is_absolute()
    assert Path(attachment_path).is_file()
    fake_generator.generate.assert_called_once_with()
    fake_generator.save.assert_called_once()


@pytest.mark.asyncio
async def test_hello_script_propagates_generator_runtime_error(monkeypatch, tmp_path):
    """当 ``WordReportGenerator.generate`` 抛 ``RuntimeError`` 时应向上透出,且 ``save`` 不被调用。

    参数:
        monkeypatch: pytest 替换工具。
        tmp_path: pytest 临时目录。

    返回: 无。
    异常:
        RuntimeError: 预期从 ``run`` 透传。
    """
    from app.scripts.examples import hello_script

    fake_attachment_dir = tmp_path / "Task"
    fake_attachment_dir.mkdir(parents=True, exist_ok=True)

    fake_generator = MagicMock(name="WordReportGenerator")
    fake_generator.generate.side_effect = RuntimeError("生成失败")

    async def fake_to_thread(func, *args, **kwargs):
        # 让被调用的 generate 抛 RuntimeError,与真实行为一致
        return func(*args, **kwargs)

    context = ScriptContext(
        schedule_id=3,
        run_id=300,
        session_id="task-3-error",
        schedule_name="失败任务",
        script_args={"greeting": "Hi"},
        log_logger=logging.getLogger("test_hello_script_error"),
        started_at=datetime(2026, 7, 19, 12, 0, 0),
        trigger_type="manual",
    )

    monkeypatch.setattr(hello_script, "TASK_ATTACHMENT_DIR", str(fake_attachment_dir))
    monkeypatch.setattr(
        hello_script, "WordReportGenerator", lambda *a, **kw: fake_generator
    )
    monkeypatch.setattr(hello_script.asyncio, "to_thread", fake_to_thread)

    with pytest.raises(RuntimeError, match="生成失败"):
        await hello_script.run(context)

    fake_generator.generate.assert_called_once()
    fake_generator.save.assert_not_called()


@pytest.mark.asyncio
async def test_hello_script_propagates_save_runtime_error(monkeypatch, tmp_path):
    """当 ``WordReportGenerator.save`` 抛 ``RuntimeError`` 时应向上透出,且 ``generate`` 已正常调用。

    参数:
        monkeypatch: pytest 替换工具。
        tmp_path: pytest 临时目录。

    返回: 无。

    异常:
        RuntimeError: 预期从 ``run`` 透传,消息为 ``"保存失败"``。
    """
    from app.scripts.examples import hello_script

    fake_attachment_dir = tmp_path / "Task"
    fake_attachment_dir.mkdir(parents=True, exist_ok=True)

    fake_generator = MagicMock(name="WordReportGenerator")
    fake_generator.generate.return_value = MagicMock(name="Document")
    fake_generator.save.side_effect = RuntimeError("保存失败")

    # fake_to_thread 真实执行被调函数,以便 save 触发 side_effect
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    context = ScriptContext(
        schedule_id=4,
        run_id=400,
        session_id="task-4-save-error",
        schedule_name="保存失败任务",
        script_args={"greeting": "Hey"},
        log_logger=logging.getLogger("test_hello_script_save_error"),
        started_at=datetime(2026, 7, 19, 13, 0, 0),
        trigger_type="manual",
    )

    monkeypatch.setattr(hello_script, "TASK_ATTACHMENT_DIR", str(fake_attachment_dir))
    monkeypatch.setattr(
        hello_script, "WordReportGenerator", lambda *a, **kw: fake_generator
    )
    monkeypatch.setattr(hello_script.asyncio, "to_thread", fake_to_thread)

    with pytest.raises(RuntimeError, match="保存失败"):
        await hello_script.run(context)

    # generate 在 save 之前正常调用一次;save 也被调用一次但抛 RuntimeError
    fake_generator.generate.assert_called_once_with()
    fake_generator.save.assert_called_once()