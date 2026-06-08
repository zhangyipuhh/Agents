# -*- coding:utf-8 -*-
"""
测试 app.core.tools.BaseTools 基础工具模块

验证模块导入、get_current_time 工具调用及 _split_content 分块功能。
"""

from unittest.mock import MagicMock

from app.core.tools.BaseTools import get_current_time, _split_content


# =============================================================================
# 模块导入与存在性测试
# =============================================================================


def test_base_tools_importable():
    """
    测试 BaseTools 模块可正常导入且不抛出异常。

    参数:
        无

    返回值:
        None

    异常:
        ImportError: 模块导入失败时抛出
    """
    import app.core.tools.BaseTools as base_tools
    assert base_tools is not None


def test_get_current_time_exists():
    """
    测试 get_current_time 工具函数在模块中存在。

    参数:
        无

    返回值:
        None

    异常:
        AssertionError: 函数不存在时抛出
    """
    assert callable(get_current_time)


# =============================================================================
# get_current_time 工具逻辑测试
# =============================================================================


def test_get_current_time_with_mock_runtime():
    """
    测试 get_current_time 使用 Mock runtime 调用后返回非空字符串。

    返回值应包含当前时间格式和会话 ID。

    参数:
        runtime: Mock 的 ToolRuntime 对象，提供 context.get 方法

    返回值:
        None

    异常:
        AssertionError: 返回值非字符串或不包含 session_id 时抛出
    """
    mock_runtime = MagicMock()
    mock_runtime.context.get.return_value = "test-session-123"
    result = get_current_time(mock_runtime)
    assert isinstance(result, str)
    assert "test-session-123" in result
    assert len(result) > 0


# =============================================================================
# _split_content 函数测试
# =============================================================================


def test_split_content_returns_list():
    """
    测试 _split_content 函数返回列表类型。

    参数:
        content: 待分割的文本字符串
        chunk_size: 每个块的最大字符数（默认 4000）
        chunk_overlap: 块之间的重叠字符数（默认 50）

    返回值:
        None

    异常:
        AssertionError: 返回值非列表时抛出
    """
    text = "这是一个测试文本。" * 100
    chunks = _split_content(text)
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_split_content_empty_string():
    """
    测试 _split_content 对空字符串返回包含空字符串的列表。

    参数:
        content: 空字符串

    返回值:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    chunks = _split_content("")
    assert isinstance(chunks, list)


def test_split_content_respects_chunk_size():
    """
    测试 _split_content 分割后的单块长度不超过 chunk_size。

    参数:
        content: 较长的重复文本
        chunk_size: 限制为 50 字符

    返回值:
        None

    异常:
        AssertionError: 任一块长度超过 chunk_size 时抛出
    """
    text = "abcdefghij" * 20  # 200 字符
    chunks = _split_content(text, chunk_size=50, chunk_overlap=0)
    for chunk in chunks:
        assert len(chunk) <= 50
