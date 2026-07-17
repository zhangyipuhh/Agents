# -*- coding:utf-8 -*-
"""
MarkdownToCardConverter 单元测试

覆盖：
    - 导入存在性
    - looks_like_markdown 触发（6 种）/ 否定
    - to_card_json 基本结构
    - 各类 markdown 元素的转换
    - 截断与空文本
    - Unicode / emoji
"""
import pytest

from app.shared.tools.skills.feishu.MarkdownToCardConverter import (
    MarkdownToCardConverter,
)


# ---------------------------------------------------------------------------
# P0 导入/存在性
# ---------------------------------------------------------------------------
def test_MarkdownToCardConverter_importable():
    """P0：模块可正常导入。"""
    assert MarkdownToCardConverter is not None


# ---------------------------------------------------------------------------
# P1 looks_like_markdown 触发
# ---------------------------------------------------------------------------
def test_looks_like_markdown_bold():
    """粗体 **xxx** 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("这是 **粗体** 文本") is True


def test_looks_like_markdown_italic():
    """斜体 *xxx* 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("这是 *斜体* 文本") is True


def test_looks_like_markdown_inline_code():
    """行内代码 `xxx` 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("变量是 `foo`") is True


def test_looks_like_markdown_heading_h1():
    """# 一级标题 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("# 标题") is True


def test_looks_like_markdown_heading_h2():
    """## 二级标题 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("## 子标题") is True


def test_looks_like_markdown_list():
    """- 列表项 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("- 第一项\n- 第二项") is True


def test_looks_like_markdown_blockquote():
    """> 引用 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("> 引用文字") is True


def test_looks_like_markdown_hr():
    """--- 分隔线 触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("上段\n\n---\n\n下段") is True


def test_looks_like_markdown_code_block():
    """代码围栏触发。"""
    md = "```python\nprint('hi')\n```"
    assert MarkdownToCardConverter.looks_like_markdown(md) is True


def test_looks_like_markdown_single_fence_no_match():
    """单个 ``` 不触发（不成对）。"""
    assert MarkdownToCardConverter.looks_like_markdown("```python\nonly-open") is False


# ---------------------------------------------------------------------------
# P2 looks_like_markdown 否定
# ---------------------------------------------------------------------------
def test_looks_like_markdown_plain_text_false():
    """纯文本不触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("你好世界") is False


def test_looks_like_markdown_empty():
    """空文本不触发。"""
    assert MarkdownToCardConverter.looks_like_markdown("") is False
    assert MarkdownToCardConverter.looks_like_markdown(None) is False


# ---------------------------------------------------------------------------
# P1 to_card_json 基本结构
# ---------------------------------------------------------------------------
def test_to_card_json_basic_structure():
    """P1：基本结构含 config / card.header / card.elements。"""
    card = MarkdownToCardConverter.to_card_json("# 标题\n\n正文")
    assert "config" in card
    assert card["config"]["wide_screen_mode"] is True
    assert "card" in card
    assert "header" in card["card"]
    assert card["card"]["header"]["title"]["tag"] == "plain_text"
    assert card["card"]["header"]["title"]["content"] == "🤖 AI 智能体回复"
    assert isinstance(card["card"]["elements"], list)
    assert len(card["card"]["elements"]) >= 1


def test_to_card_json_custom_header_title():
    """自定义 header_title 生效。"""
    card = MarkdownToCardConverter.to_card_json("hi", header_title="客服回复")
    assert card["card"]["header"]["title"]["content"] == "客服回复"


def test_to_card_json_empty_text_returns_one_element():
    """空文本仍产出至少 1 个占位元素。"""
    card = MarkdownToCardConverter.to_card_json("")
    assert len(card["card"]["elements"]) == 1


def test_to_card_json_none_text_returns_one_element():
    """None 文本不抛异常。"""
    card = MarkdownToCardConverter.to_card_json(None)
    assert len(card["card"]["elements"]) == 1


# ---------------------------------------------------------------------------
# P1 各 markdown 元素转换
# ---------------------------------------------------------------------------
def test_to_card_json_headings_h1_h2_h3():
    """h1 / h2 / h3 都被转为 markdown 元素。"""
    md = "# 一级\n## 二级\n### 三级"
    card = MarkdownToCardConverter.to_card_json(md)
    elements = card["card"]["elements"]
    # 应至少有 3 个 markdown 元素（每行一个）
    md_elems = [e for e in elements if e.get("tag") == "markdown"]
    assert len(md_elems) >= 3
    # 内容包含标题前缀
    joined = "\n".join(e["content"] for e in md_elems)
    assert "# 一级" in joined
    assert "## 二级" in joined
    assert "### 三级" in joined


def test_to_card_json_hr():
    """--- 分隔线转为 tag=hr。"""
    md = "上段\n\n---\n\n下段"
    card = MarkdownToCardConverter.to_card_json(md)
    hr_elems = [e for e in card["card"]["elements"] if e.get("tag") == "hr"]
    assert len(hr_elems) == 1


def test_to_card_json_list_items_merged():
    """连续列表项合并为单个 markdown 元素。"""
    md = "- 第一项\n- 第二项\n- 第三项"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["card"]["elements"] if e.get("tag") == "markdown"]
    # 列表被合并为单元素
    list_elems = [e for e in md_elems if "- 第一项" in e["content"]]
    assert len(list_elems) == 1
    # 三项都在
    assert "- 第二项" in list_elems[0]["content"]
    assert "- 第三项" in list_elems[0]["content"]


def test_to_card_json_blockquote():
    """> 引用 转为 markdown 元素。"""
    md = "> 引用文字"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["card"]["elements"] if e.get("tag") == "markdown"]
    assert any("> 引用文字" in e["content"] for e in md_elems)


def test_to_card_json_code_block_with_language():
    """带语言的代码围栏转为 tag=code_block 且含 language。"""
    md = "```python\nprint('hi')\n```"
    card = MarkdownToCardConverter.to_card_json(md)
    code_elems = [e for e in card["card"]["elements"] if e.get("tag") == "code_block"]
    assert len(code_elems) == 1
    assert code_elems[0]["language"] == "python"
    assert "print('hi')" in code_elems[0]["content"]


def test_to_card_json_code_block_without_language():
    """无语言代码围栏转为 tag=code_block，不含 language 字段。"""
    md = "```\nfoo()\n```"
    card = MarkdownToCardConverter.to_card_json(md)
    code_elems = [e for e in card["card"]["elements"] if e.get("tag") == "code_block"]
    assert len(code_elems) == 1
    assert "language" not in code_elems[0]
    assert "foo()" in code_elems[0]["content"]


def test_to_card_json_plain_paragraph():
    """纯文本段落转为单个 markdown 元素。"""
    card = MarkdownToCardConverter.to_card_json("这是普通段落。")
    md_elems = [e for e in card["card"]["elements"] if e.get("tag") == "markdown"]
    assert any("这是普通段落" in e["content"] for e in md_elems)


def test_to_card_json_bold_passes_through_markdown_element():
    """**粗体** 在 markdown 元素内保留原样（飞书原生渲染）。"""
    card = MarkdownToCardConverter.to_card_json("**强调** 文字")
    md_elems = [e for e in card["card"]["elements"] if e.get("tag") == "markdown"]
    assert any("**强调**" in e["content"] for e in md_elems)


# ---------------------------------------------------------------------------
# P2 截断
# ---------------------------------------------------------------------------
def test_to_card_json_truncate_long_text():
    """>4000 字符文本被截断并追加 hint。"""
    long_md = "# 标题\n" + ("a" * 5000)
    card = MarkdownToCardConverter.to_card_json(long_md)
    # 拼接所有 markdown 元素内容应不超过 _MAX + hint
    joined = "\n".join(
        e.get("content", "")
        for e in card["card"]["elements"]
        if isinstance(e, dict)
    )
    assert "...（内容过长已截断）" in joined
    assert len(joined) <= 4000 + len("...（内容过长已截断）")


# ---------------------------------------------------------------------------
# P2 Unicode / emoji
# ---------------------------------------------------------------------------
def test_to_card_json_unicode_emoji():
    """中文 / emoji 正常保留。"""
    md = "# 你好 🌍\n\n这是 **重要** 内容。"
    card = MarkdownToCardConverter.to_card_json(md)
    elements = card["card"]["elements"]
    joined = "\n".join(
        e.get("content", "")
        for e in elements
        if isinstance(e, dict)
    )
    assert "你好" in joined
    assert "🌍" in joined
    assert "**重要**" in joined