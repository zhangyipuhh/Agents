# -*- coding:utf-8 -*-
"""
示例脚本 ``hello_script`` 测试。

覆盖点：
    * 模块可正常导入
    * 导入后自动注册到全局 registry
    * ``run(context)`` 返回含问候语的字符串
"""
import logging
from datetime import datetime

import pytest

from app.scripts.base import ScriptContext
from app.scripts.registry import clear_registry, get_registered_script


def test_hello_script_importable():
    """``hello_script`` 模块应可正常导入且含 ``run`` 函数。"""
    from app.scripts.examples import hello_script  # noqa: F401

    assert hasattr(hello_script, "run")
    assert callable(hello_script.run)


def test_hello_script_registered_in_registry():
    """导入后 ``hello_script`` 应出现在 registry。"""
    from app.scripts.examples import hello_script  # noqa: F401

    s = get_registered_script("hello_script")
    assert s is not None
    assert s.display_name == "示例问候脚本"
    assert s.name == "hello_script"


@pytest.mark.asyncio
async def test_hello_script_runs_and_returns_message():
    """``run(context)`` 应返回含问候语的字符串。"""
    from app.scripts.examples import hello_script

    context = ScriptContext(
        schedule_id=1,
        run_id=100,
        session_id="task-1-abc",
        schedule_name="测试任务",
        script_args={"greeting": "Hello"},
        log_logger=logging.getLogger("test_hello_script"),
        started_at=datetime.now(),
        trigger_type="manual",
    )
    result = await hello_script.run(context)
    assert "Hello" in result
    assert "测试任务" in result
    assert "100" in result


@pytest.mark.asyncio
async def test_hello_script_uses_default_greeting_when_args_empty():
    """``script_args`` 为空时应使用默认问候语 ``Hello``。"""
    from app.scripts.examples import hello_script

    context = ScriptContext(
        schedule_id=2,
        run_id=200,
        session_id="task-2-def",
        schedule_name="默认任务",
        script_args={},
        log_logger=logging.getLogger("test_hello_script_default"),
        started_at=datetime.now(),
        trigger_type="scheduled",
    )
    result = await hello_script.run(context)
    assert "Hello" in result
