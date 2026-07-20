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
"""
import importlib
import inspect
import logging
import typing
from datetime import datetime
from pathlib import Path

import pytest

from app.scripts.base import ScriptContext, ScriptExecutionError
from app.scripts.registry import clear_registry


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
