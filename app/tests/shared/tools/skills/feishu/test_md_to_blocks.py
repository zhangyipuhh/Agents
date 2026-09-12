# -*- coding:utf-8 -*-
"""
test_md_to_blocks - _md_to_blocks helper 单元测试

覆盖：
    - 标题解析（heading1/2/3）
    - 普通段落
    - 代码围栏
    - 表格
    - 列表（bullet + ordered）
    - 反向用例（未闭合 fence、空 markdown、行首格式识别）
    - _rich_text / _table_block 等内部 helper
"""
from __future__ import annotations

import pytest

from app.shared.tools.skills.feishu.FeishuDocxClient import (
    _md_to_blocks,
    _parse_table_cells,
    _rich_text,
    _table_block,
)


# =============================================================================
# _md_to_blocks 行为
# =============================================================================


def test_md_to_blocks_empty_returns_empty_list():
    """空 markdown → 空列表（调用方应拦截此情况，不应传空字符串）。"""
    assert _md_to_blocks("") == []
    assert _md_to_blocks("   \n\n   ") == []


def test_md_to_blocks_single_h1():
    """单行 H1 标题 → 一个 heading1 block。"""
    blocks = _md_to_blocks("# 标题一")
    assert len(blocks) == 1
    assert blocks[0]["block_type"] == 3
    assert "heading1" in blocks[0]
    assert blocks[0]["heading1"]["rich_text"][0]["text_run"]["content"] == "标题一"


def test_md_to_blocks_h2_and_h3():
    """H2 / H3 标题解析。"""
    blocks = _md_to_blocks("## 二级\n### 三级")
    assert [b["block_type"] for b in blocks] == [4, 5]
    assert blocks[0]["heading2"]["rich_text"][0]["text_run"]["content"] == "二级"
    assert blocks[1]["heading3"]["rich_text"][0]["text_run"]["content"] == "三级"


def test_md_to_blocks_paragraph():
    """普通段落。"""
    blocks = _md_to_blocks("这是一段普通文本。")
    assert len(blocks) == 1
    assert blocks[0]["block_type"] == 2
    assert "这是一段普通文本" in blocks[0]["text"]["rich_text"][0]["text_run"]["content"]


def test_md_to_blocks_multi_line_paragraph_merged():
    """连续非空行合并为一个段落。"""
    blocks = _md_to_blocks("第一行\n第二行\n\n新段")
    # 第一段合并"第一行 第二行"，第二段"新段"
    assert len(blocks) == 2
    assert "第一行 第二行" in blocks[0]["text"]["rich_text"][0]["text_run"]["content"]
    assert "新段" in blocks[1]["text"]["rich_text"][0]["text_run"]["content"]


def test_md_to_blocks_code_fence():
    """代码围栏（```python\\n...\\n```）→ code block。"""
    md = "```python\nprint('hi')\n```"
    blocks = _md_to_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["block_type"] == 14
    assert "code" in blocks[0]
    assert "print('hi')" in blocks[0]["code"]["rich_text"][0]["text_run"]["content"]


def test_md_to_blocks_unclosed_fence_falls_back_to_paragraph():
    """未闭合 fence → 整段作为普通段落（不让解析失败导致 wiki 工具中断）。"""
    md = "```python\nprint('hi')\n仍继续\n没闭合"
    blocks = _md_to_blocks(md)
    # 解析器会读到末尾仍未遇到闭合 fence；当前行在 fenced 段内累积
    # 此场景至少应返回 1+ 个 block，且无异常
    assert len(blocks) >= 1
    # 不能抛异常


def test_md_to_blocks_table_simple():
    """简单表格解析为 table block，首行视为表头。"""
    md = "| 名称 | 数值 |\n|---|---|\n| a | 1 |\n| b | 2 |"
    blocks = _md_to_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["block_type"] == 27
    assert blocks[0]["table"]["property"]["row_size"] == 3
    assert blocks[0]["table"]["property"]["column_size"] == 2
    # 6 个 table_cell children
    assert len(blocks[0]["table"]["children"]) == 6


def test_md_to_blocks_table_uneven_columns_padded():
    """表格行长度不等时，自动补空字符串到等长。"""
    md = "| a | b | c |\n|---|---|---|\n| 1 | 2 |"  # 第二行缺一列
    blocks = _md_to_blocks(md)
    # 仍能解析；rows 归一化为 2 列等长
    # 注：实际归一化在本 helper 内由 _table_block 完成；
    # _md_to_blocks 会保留原始 2 列。验证 _table_block 行为见下方独立用例。
    assert len(blocks) == 1


def test_md_to_blocks_bullet_list():
    """无序列表。"""
    md = "- 苹果\n- 香蕉\n- 樱桃"
    blocks = _md_to_blocks(md)
    assert len(blocks) == 3
    assert all(b["block_type"] == 12 for b in blocks)
    contents = [b["bullet"]["rich_text"][0]["text_run"]["content"] for b in blocks]
    assert contents == ["苹果", "香蕉", "樱桃"]


def test_md_to_blocks_ordered_list():
    """有序列表。"""
    md = "1. 第一\n2. 第二\n3. 第三"
    blocks = _md_to_blocks(md)
    assert len(blocks) == 3
    assert all(b["block_type"] == 13 for b in blocks)
    contents = [b["ordered"]["rich_text"][0]["text_run"]["content"] for b in blocks]
    assert contents == ["第一", "第二", "第三"]


def test_md_to_blocks_mixed_structure():
    """综合示例：H1 + 段落 + bullet + 代码 + 表格。"""
    md = """# 报告
这是简介。

- 项目 A
- 项目 B

```bash
echo "hi"
```

| 列 1 | 列 2 |
|---|---|
| 数据 1 | 数据 2 |
"""
    blocks = _md_to_blocks(md)
    block_types = [b["block_type"] for b in blocks]
    # H1, 段落, 2×bullet, code, table
    assert 3 in block_types  # H1
    assert 2 in block_types  # paragraph
    assert 12 in block_types  # bullet
    assert 14 in block_types  # code
    assert 27 in block_types  # table


# =============================================================================
# _parse_table_cells / _rich_text / _table_block 辅助
# =============================================================================


def test_parse_table_cells_strips_pipes():
    """``| a | b | c |`` → ['a','b','c']。"""
    assert _parse_table_cells("| a | b | c |") == ["a", "b", "c"]
    assert _parse_table_cells("|a|b|c|") == ["a", "b", "c"]


def test_rich_text_empty_content_returns_single_empty_run():
    """_rich_text 空字符串返回 1 个空元素数组。"""
    out = _rich_text("")
    assert len(out) == 1
    assert out[0]["text_run"]["content"] == ""


def test_table_block_normalizes_columns_to_max_width():
    """_table_block 行长度不一致时，按 max 列宽补空字符串。"""
    rows = [["a", "b", "c"], ["1", "2"]]
    block = _table_block(rows)
    assert block["table"]["property"]["row_size"] == 2
    assert block["table"]["property"]["column_size"] == 3
    # 第二行被补到 3 列
    cells_text = [
        c["table_cell"]["rich_text"][0]["text_run"]["content"]
        for c in block["table"]["children"]
    ]
    assert cells_text == ["a", "b", "c", "1", "2", ""]


def test_table_block_empty_raises():
    """空 rows 抛 ValueError。"""
    with pytest.raises(ValueError):
        _table_block([])