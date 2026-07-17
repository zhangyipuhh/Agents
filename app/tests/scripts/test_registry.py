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

from app.scripts.base import ScriptContext, ScriptExecutionError, normalize_script_result
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


# =============================================================================
# normalize_script_result 兼容测试（2026-07-17 新约定）
# =============================================================================

def test_normalize_script_result_str_returns_pair_none():
    """str 输入应归一化为 ``(str, None)``（向后兼容旧契约）。"""
    assert normalize_script_result("hello") == ("hello", None)


def test_normalize_script_result_tuple_with_none_attachments():
    """``(body, None)`` 应归一化为 ``(body, None)``。"""
    assert normalize_script_result(("hi", None)) == ("hi", None)


def test_normalize_script_result_tuple_with_single_str_attachment():
    """``(body, "path")`` 应归一化为 ``(body, ["path"])``。"""
    assert normalize_script_result(("hi", "/tmp/a.pdf")) == ("hi", ["/tmp/a.pdf"])


def test_normalize_script_result_tuple_with_list_attachments():
    """``(body, list[str])`` 应归一化为 ``(body, list[str])``。"""
    assert normalize_script_result(("hi", ["/a.pdf", "/b.docx"])) == (
        "hi",
        ["/a.pdf", "/b.docx"],
    )


def test_normalize_script_result_empty_list_treated_as_none():
    """``(body, [])`` 应归一化为 ``(body, None)``（无附件场景）。"""
    assert normalize_script_result(("hi", [])) == ("hi", None)


def test_normalize_script_result_rejects_non_string_body():
    """tuple[0] 非 str 应抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError):
        normalize_script_result((123, None))


def test_normalize_script_result_rejects_non_str_non_tuple():
    """非 str / 非 tuple 类型应抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError):
        normalize_script_result(123)
    with pytest.raises(ScriptExecutionError):
        normalize_script_result(["body", None])


def test_normalize_script_result_rejects_invalid_attachment_type():
    """tuple[1] 非 str / list[str] / None 应抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError):
        normalize_script_result(("hi", 123))
    with pytest.raises(ScriptExecutionError):
        normalize_script_result(("hi", {"a": 1}))


def test_normalize_script_result_rejects_list_with_non_str_items():
    """attachments list 含非 str 元素应抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError):
        normalize_script_result(("hi", ["/a.pdf", 123]))


def test_normalize_script_result_rejects_wrong_tuple_length():
    """长度非 2 的 tuple 应抛 ``ScriptExecutionError``。"""
    with pytest.raises(ScriptExecutionError):
        normalize_script_result(("hi", "/a.pdf", "extra"))
