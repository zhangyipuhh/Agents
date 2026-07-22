# -*- coding:utf-8 -*-
"""表格 SectionConfig 单元测试。"""
import importlib
import sys
from pathlib import Path

import pytest

from app.shared.utils.report.word.config import (
    PageSetup,
    ReportConfig,
    SectionConfig,
    TableSectionConfig,
)


def test_section_config_accepts_table_type():
    cfg = SectionConfig(
        section_type="table",
        table=TableSectionConfig(
            headers=["指标", "当前值"],
            rows=[["CPU 使用率", "75%"]],
            status_column=1,
        ),
    )
    assert cfg.section_type == "table"
    assert cfg.table.headers == ["指标", "当前值"]
    assert cfg.table.status_column == 1


def test_table_section_config_defaults():
    cfg = TableSectionConfig(headers=["a"], rows=[["b"]])
    assert cfg.column_widths is None
    assert cfg.header_fill == "D9E1F2"
    assert cfg.cell_align == "left"
    assert cfg.status_column is None


def test_render_table_section_produces_docx(tmp_path: Path):
    """验证表格配置可生成包含预期内容的 DOCX 文件。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None。

    Raises:
        AssertionError: 生成文件或表格内容不符合预期时抛出。
    """
    pytest.importorskip("docx")
    mocked_docx_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name == "docx" or module_name.startswith("docx.")
    }
    generator_module_name = "app.shared.utils.report.word.generator"
    word_package_name = "app.shared.utils.report.word"
    original_generator_module = sys.modules[generator_module_name]
    word_package = sys.modules[word_package_name]
    original_package_generator = word_package.generator
    original_logger_info = original_generator_module.logger.info
    original_logger_debug = original_generator_module.logger.debug

    try:
        for module_name in list(sys.modules):
            if module_name == "docx" or module_name.startswith("docx."):
                del sys.modules[module_name]
        sys.modules.pop(generator_module_name, None)

        pytest.importorskip("docx")
        from docx import Document

        importlib.import_module(generator_module_name)
        from app.shared.utils.report.word.generator import WordReportGenerator

        cfg = ReportConfig(
            page_setup=PageSetup(),
            cover=None,
            toc=None,
            sections=[
                SectionConfig(section_type="heading", content="测试"),
                SectionConfig(
                    section_type="table",
                    table=TableSectionConfig(
                        headers=["指标", "状态"],
                        rows=[
                            ["CPU 使用率", "WARN"],
                            ["磁盘使用率", "CRIT"],
                        ],
                        status_column=1,
                    ),
                ),
            ],
        )
        output = tmp_path / "report.docx"
        generator = WordReportGenerator(cfg)
        generator.generate()
        generator.save(str(output))
        assert output.exists()
        assert output.stat().st_size > 1000

        doc = Document(str(output))
        tables = doc.tables
        assert len(tables) == 1
        assert [cell.text for cell in tables[0].rows[0].cells] == ["指标", "状态"]
        assert [cell.text for cell in tables[0].rows[1].cells] == ["CPU 使用率", "WARN"]
    finally:
        sys.modules.pop(generator_module_name, None)
        sys.modules[generator_module_name] = original_generator_module
        word_package.generator = original_package_generator
        original_generator_module.logger.info = original_logger_info
        original_generator_module.logger.debug = original_logger_debug
        for module_name in list(sys.modules):
            if module_name == "docx" or module_name.startswith("docx."):
                del sys.modules[module_name]
        sys.modules.update(mocked_docx_modules)
