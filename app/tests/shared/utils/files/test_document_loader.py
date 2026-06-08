# -*- coding:utf-8 -*-
"""
DocumentLoader 测试模块

测试 app.shared.utils.files.DocumentLoader 的模块导入和类实例化。
"""
from pathlib import Path


def test_import_document_loader():
    """
    测试 DocumentLoader 模块可正常导入。

    Returns:
        None

    Raises:
        AssertionError: 导入失败或类未定义时抛出。
    """
    from app.shared.utils.files.DocumentLoader import DocumentLoader

    assert DocumentLoader is not None


def test_document_loader_instantiation():
    """
    测试 DocumentLoader 类可实例化（使用不存在的路径仅验证构造器不抛异常）。

    Returns:
        None

    Raises:
        AssertionError: 实例化失败或属性不正确时抛出。
    """
    from app.shared.utils.files.DocumentLoader import DocumentLoader

    loader = DocumentLoader("fake/path.txt")
    assert loader is not None
    assert loader.path == Path("fake/path.txt")
    assert loader.glob == "**/*"
    assert loader.silent_errors is True
