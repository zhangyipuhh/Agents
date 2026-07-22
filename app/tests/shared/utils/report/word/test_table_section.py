# -*- coding:utf-8 -*-
"""表格 SectionConfig 单元测试。"""
from app.shared.utils.report.word.config import SectionConfig, TableSectionConfig


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
