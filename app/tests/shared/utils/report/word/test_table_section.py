# -*- coding:utf-8 -*-
"""表格 SectionConfig 单元测试。"""
from pathlib import Path

from app.shared.utils.report.word.config import (
    PageSetup,
    ReportConfig,
    SectionConfig,
    TableSectionConfig,
)
from app.shared.utils.report.word.generator import WordReportGenerator


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

    from docx import Document

    doc = Document(str(output))
    tables = doc.tables
    assert len(tables) == 1
    assert [cell.text for cell in tables[0].rows[0].cells] == ["指标", "状态"]
    assert [cell.text for cell in tables[0].rows[1].cells] == ["CPU 使用率", "WARN"]
