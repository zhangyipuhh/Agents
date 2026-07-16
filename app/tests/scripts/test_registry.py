# -*- coding:utf-8 -*-
"""
``@register_script`` 装饰器与全局 registry 测试。

覆盖点：
    * 装饰器可正常导入与调用
    * 注册后元数据可从 ``get_registered_script`` 取回
    * 同名重复注册抛 ``ValueError``
    * 装饰非协程函数抛 ``TypeError``
    * 装饰签名不合法的函数抛 ``ValueError``
    * ``clear_registry`` 能清空注册表
"""
import pytest

from app.scripts.base import ScriptContext
from app.scripts.registry import (
    clear_registry,
    get_registered_script,
    get_registered_scripts,
    register_script,
)


def test_register_script_importable():
    """``register_script`` 应可正常导入且可调用。"""
    assert callable(register_script)


def test_register_script_stores_metadata():
    """装饰后元数据应可从 ``get_registered_script`` 取回。"""
    clear_registry()

    @register_script(name="test_meta", display_name="测试", description="d")
    async def run(context: ScriptContext) -> str:
        return "ok"

    s = get_registered_script("test_meta")
    assert s is not None
    assert s.name == "test_meta"
    assert s.display_name == "测试"
    assert s.description == "d"
    assert s.module_path.endswith(".run")
    assert callable(s.func)
    clear_registry()


def test_register_script_rejects_duplicate_name():
    """同名注册应抛 ``ValueError``。"""
    clear_registry()

    @register_script(name="dup", display_name="d1", description="")
    async def run1(context):  # noqa: ANN001
        return ""

    with pytest.raises(ValueError):
        @register_script(name="dup", display_name="d2", description="")
        async def run2(context):  # noqa: ANN001
            return ""

    clear_registry()


def test_register_script_rejects_sync_function():
    """装饰非协程函数应抛 ``TypeError``。"""
    clear_registry()
    with pytest.raises(TypeError):
        @register_script(name="sync", display_name="s", description="")
        def run(context):  # noqa: ANN001
            return ""
    clear_registry()


def test_register_script_rejects_invalid_signature():
    """函数签名不接受单个位置参数时应抛 ``ValueError``。"""
    clear_registry()
    with pytest.raises(ValueError):
        @register_script(name="bad_sig", display_name="b", description="")
        async def run(context, extra):  # noqa: ANN001
            return ""
    clear_registry()


def test_register_script_rejects_empty_name():
    """``name`` 为空字符串应抛 ``ValueError``。"""
    clear_registry()
    with pytest.raises(ValueError):
        @register_script(name="", display_name="x", description="")
        async def run(context):  # noqa: ANN001
            return ""
    clear_registry()


def test_register_script_rejects_empty_display_name():
    """``display_name`` 为空字符串应抛 ``ValueError``。"""
    clear_registry()
    with pytest.raises(ValueError):
        @register_script(name="x", display_name="", description="")
        async def run(context):  # noqa: ANN001
            return ""
    clear_registry()


def test_clear_registry():
    """``clear_registry`` 后注册表应为空。"""
    clear_registry()

    @register_script(name="tmp", display_name="t", description="")
    async def run(context):  # noqa: ANN001
        return ""

    assert "tmp" in get_registered_scripts()
    clear_registry()
    assert get_registered_scripts() == {}


def test_get_registered_script_returns_none_for_unknown():
    """查询未知名应返回 ``None``。"""
    clear_registry()
    assert get_registered_script("nonexistent") is None
    clear_registry()


def test_get_registered_scripts_returns_copy():
    """``get_registered_scripts`` 应返回浅拷贝，修改不影响原注册表。"""
    clear_registry()

    @register_script(name="copy_test", display_name="c", description="")
    async def run(context):  # noqa: ANN001
        return ""

    snapshot = get_registered_scripts()
    snapshot.clear()
    # 原注册表不受影响
    assert "copy_test" in get_registered_scripts()
    clear_registry()
