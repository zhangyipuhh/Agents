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
    """P1：基本结构含 schema=2.0 / header / body.elements。"""
    card = MarkdownToCardConverter.to_card_json("# 标题\n\n正文")
    assert card["schema"] == "2.0"
    assert "config" in card
    assert card["config"]["wide_screen_mode"] is True
    assert "header" in card
    assert card["header"]["template"] == "blue"
    assert card["header"]["title"]["tag"] == "plain_text"
    assert card["header"]["title"]["content"] == "🤖 AI 智能体回复"
    assert "body" in card
    assert "elements" in card["body"]
    assert isinstance(card["body"]["elements"], list)
    assert len(card["body"]["elements"]) >= 1
    # 关键：v2.0 schema 不再有外层 card 字段
    assert "card" not in card


# ---------------------------------------------------------------------------
# P1 有序列表（2026-07-17 新增，修复 MarkdownToCardConverter 不识别 1./2. 编号项）
# ---------------------------------------------------------------------------
def test_looks_like_markdown_ordered_list():
    """P1：纯数字列表 `1. xxx` 触发 markdown 判定。"""
    text = "1. 第一项\n2. 第二项\n3. 第三项"
    assert MarkdownToCardConverter.looks_like_markdown(text) is True


def test_looks_like_markdown_ordered_list_with_paren():
    """P1：`1) xxx` 写法也能触发。"""
    text = "1) 第一项\n2) 第二项"
    assert MarkdownToCardConverter.looks_like_markdown(text) is True


def test_looks_like_markdown_ordered_list_with_two_digit_number():
    """P1：两位数字 `10. xxx` 也能触发（编号限定为 1~2 位数字）。"""
    text = "10. 十号项"
    assert MarkdownToCardConverter.looks_like_markdown(text) is True


def test_to_card_json_ordered_list_single_layer():
    """单层有序列表，每项独立 markdown 元素，保留 "1." 原前缀。"""
    md = "1. 第一项\n2. 第二项\n3. 第三项"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    contents = [e["content"] for e in md_elems]
    # 每项独立成元素
    assert "1. 第一项" in contents
    assert "2. 第二项" in contents
    assert "3. 第三项" in contents
    # 不应被合并到一个元素
    assert not any("1." in c and "2." in c and "\n" in c for c in contents)


def test_to_card_json_ordered_list_with_sub_bullets():
    """有序列表 + 子项混合：每条编号项 + 每条子项各自独立成元素。"""
    md = "1. 顶层一\n   - 子项 A\n   - 子项 B\n2. 顶层二\n   - 子项 C"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    contents = [e["content"] for e in md_elems]
    # 编号项
    assert "1. 顶层一" in contents
    assert "2. 顶层二" in contents
    # 子项
    assert any(c.startswith("- ") and "A" in c for c in contents)
    assert any(c.startswith("- ") and "B" in c for c in contents)
    assert any(c.startswith("- ") and "C" in c for c in contents)


def test_to_card_json_real_user_case_numbered_list():
    """P1：复现用户截图"不动产权登记意义"源文本，编号 1~5 各自独立成元素。

    用户反馈"第4 第5第二条位置不对"的根因：编号项被当作普通段落，
    导致 `**4. 便于管理**` / `**5. 提高效率**` 被串到上一子项目末尾。
    本测试断言每个编号项独占一个 markdown 元素、与子项完全分离。
    """
    text = (
        "不动产权登记的主要意义：\n"
        "\n"
        "1. 保护产权 - 明确产权归属，防止纠纷 - 为物权变动提供法律依据\n"
        "2. 规范市场\n"
        "   - 规范不动产交易行为 - 保障交易安全与透明\n"
        "3. 保护权益\n"
        "   - 防止一房二卖、重复抵押 - 保障债权人权益\n"
        "4. 便于管理\n"
        "   - 为税收征管提供依据 - 支持宏观经济决策\n"
        "5. 提高效率\n"
        "   - 信息共享，减少重复审查 - 为其他部门提供数据支持\n"
        "有其他问题吗？\n"
    )
    card = MarkdownToCardConverter.to_card_json(text)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    contents = [e["content"] for e in md_elems]

    # 五个编号项各自独立成元素（关键修复点）
    numbered_contents = [c for c in contents if c.startswith(("1. ", "2. ", "3. ", "4. ", "5. "))]
    assert len(numbered_contents) == 5, f"应有 5 个编号项，实际 {len(numbered_contents)}: {numbered_contents}"
    assert any("保护产权" in c for c in numbered_contents)
    assert any("规范市场" in c for c in numbered_contents)
    assert any("保护权益" in c for c in numbered_contents)
    assert any("便于管理" in c for c in numbered_contents)
    assert any("提高效率" in c for c in numbered_contents)

    # 关键："4. 便于管理" 不应被串到 "3. 保护权益" 的内容里
    item_3 = next(c for c in numbered_contents if c.startswith("3. "))
    assert "便于管理" not in item_3
    item_4 = next(c for c in numbered_contents if c.startswith("4. "))
    assert "保护权益" not in item_4

    # 子项也各自独立成元素（每个一行）
    # 注：用户截图源文本中只有第 2~5 项各挂 1 条子项目，
    #    第 1 项的子内容是 inline 写法（" - 明确产权归属,..."连在同一行），
    #    因此预期子项数量为 4。
    bullets = [c for c in contents if c.startswith("- ")]
    assert len(bullets) == 4, f"应有 4 个子项（第 2~5 项各 1 条），实际 {len(bullets)}: {bullets}"

    # 段落首句独立成元素
    assert any("不动产权登记的主要意义" in c for c in contents)
    assert any("有其他问题吗" in c for c in contents)


def test_to_card_json_numbered_list_paren_form_strips_prefix():
    """P1：`1) xxx` 形式被识别为有序列表项，元素内容统一写成 "1. xxx"。"""
    md = "1) 第一项\n2) 第二项"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    contents = [e["content"] for e in md_elems]
    # 飞书原生渲染 "1." 风格更稳，这里统一写成 "1." 前缀
    assert "1. 第一项" in contents
    assert "2. 第二项" in contents


def test_to_card_json_custom_header_title():
    """自定义 header_title 生效。"""
    card = MarkdownToCardConverter.to_card_json("hi", header_title="客服回复")
    assert card["header"]["title"]["content"] == "客服回复"


def test_to_card_json_empty_text_returns_one_element():
    """空文本仍产出至少 1 个占位元素。"""
    card = MarkdownToCardConverter.to_card_json("")
    assert len(card["body"]["elements"]) == 1


def test_to_card_json_none_text_returns_one_element():
    """None 文本不抛异常。"""
    card = MarkdownToCardConverter.to_card_json(None)
    assert len(card["body"]["elements"]) == 1


# ---------------------------------------------------------------------------
# P1 各 markdown 元素转换
# ---------------------------------------------------------------------------
def test_to_card_json_headings_h1_h2_h3():
    """h1 / h2 / h3 都被转为 markdown 元素。"""
    md = "# 一级\n## 二级\n### 三级"
    card = MarkdownToCardConverter.to_card_json(md)
    elements = card["body"]["elements"]
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
    hr_elems = [e for e in card["body"]["elements"] if e.get("tag") == "hr"]
    assert len(hr_elems) == 1


def test_to_card_json_list_items_merged():
    """连续列表项每项单独一个 markdown 元素（避免飞书多行解析）。"""
    md = "- 第一项\n- 第二项\n- 第三项"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    # 三项各自独立 markdown 元素
    list_elems = [e for e in md_elems if e["content"].startswith("- ")]
    assert len(list_elems) == 3
    assert list_elems[0]["content"] == "- 第一项"
    assert list_elems[1]["content"] == "- 第二项"
    assert list_elems[2]["content"] == "- 第三项"


def test_to_card_json_blockquote():
    """> 引用 转为 markdown 元素。"""
    md = "> 引用文字"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert any("> 引用文字" in e["content"] for e in md_elems)


def test_to_card_json_code_block_with_language():
    """带语言的代码围栏转为 tag=code_block 且含 language。"""
    md = "```python\nprint('hi')\n```"
    card = MarkdownToCardConverter.to_card_json(md)
    code_elems = [e for e in card["body"]["elements"] if e.get("tag") == "code_block"]
    assert len(code_elems) == 1
    assert code_elems[0]["language"] == "python"
    assert "print('hi')" in code_elems[0]["content"]


def test_to_card_json_code_block_without_language():
    """无语言代码围栏转为 tag=code_block，不含 language 字段。"""
    md = "```\nfoo()\n```"
    card = MarkdownToCardConverter.to_card_json(md)
    code_elems = [e for e in card["body"]["elements"] if e.get("tag") == "code_block"]
    assert len(code_elems) == 1
    assert "language" not in code_elems[0]
    assert "foo()" in code_elems[0]["content"]


def test_to_card_json_plain_paragraph():
    """纯文本段落转为单个 markdown 元素。"""
    card = MarkdownToCardConverter.to_card_json("这是普通段落。")
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert any("这是普通段落" in e["content"] for e in md_elems)


def test_to_card_json_bold_passes_through_markdown_element():
    """行内粗体 **xxx 文字** 保留（飞书 markdown 元素原生渲染）。"""
    card = MarkdownToCardConverter.to_card_json("**强调** 文字")
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert any("**强调**" in e["content"] for e in md_elems)


def test_to_card_json_solo_bold_stripped():
    """单独一行的 **xxx** 包装被剥离，且行首 emoji 前补 ASCII 空格。

    飞书卡片 v2.0 schema 的 markdown 元素对独立成行的纯加粗行解析不稳定，
    故解析前预处理剥离包装；同时为防止 emoji 行首解析失败补一个 ASCII 空格。
    """
    card = MarkdownToCardConverter.to_card_json("**📝 文档工作流**")
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert len(md_elems) == 1
    # ** 剥离后剩 📝 文档工作流，再经 emoji 前缀处理 → " 📝 文档工作流"
    assert md_elems[0]["content"].strip() == "📝 文档工作流"
    assert md_elems[0]["content"].startswith(" ")


def test_to_card_json_solo_italic_stripped():
    """单独一行的 *xxx* 包装被剥离。"""
    card = MarkdownToCardConverter.to_card_json("*斜体*")
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert len(md_elems) == 1
    assert md_elems[0]["content"] == "斜体"


def test_to_card_json_blockquote_each_line_separate_element():
    """> 引用 每行单独一个 markdown 元素。"""
    md = "> 第一行\n> 第二行"
    card = MarkdownToCardConverter.to_card_json(md)
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    quote_elems = [e for e in md_elems if e["content"].startswith("> ")]
    assert len(quote_elems) == 2
    assert quote_elems[0]["content"] == "> 第一行"
    assert quote_elems[1]["content"] == "> 第二行"


def test_to_card_json_leading_emoji_gets_space_prefix():
    """行首 emoji 前补 ASCII 空格，避免飞书解析失败（code=200621）。

    飞书 v2.0 markdown 元素对"行首为孤立 emoji"的解析不稳定，
    必须在前面有普通字符（ASCII 即可）。
    """
    card = MarkdownToCardConverter.to_card_json("📝 文档工作流")
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert len(md_elems) == 1
    # emoji 前补了一个空格
    assert md_elems[0]["content"].startswith(" ")
    assert "📝" in md_elems[0]["content"]


def test_to_card_json_solo_emoji_line_gets_space_prefix():
    """行首只有 emoji 的行 → 整行前补 ASCII 空格。"""
    card = MarkdownToCardConverter.to_card_json("🔧")
    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert len(md_elems) == 1
    assert md_elems[0]["content"] == " 🔧"


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
        for e in card["body"]["elements"]
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
    elements = card["body"]["elements"]
    joined = "\n".join(
        e.get("content", "")
        for e in elements
        if isinstance(e, dict)
    )
    assert "你好" in joined
    assert "🌍" in joined
    assert "**重要**" in joined


# ---------------------------------------------------------------------------
# P1 复现 Terminal#614-628 出错文本（schema 2.0）
# ---------------------------------------------------------------------------
def test_to_card_json_real_failing_case_schema_2_0():
    """复现 Terminal#614-628 出错文本，确认 2.0 schema 下产出有效 JSON。

    飞书 v1.0 schema 下该文本触发 ``ErrCode: 200621; ErrMsg: parse card json err``
    （孤立加粗行 + 全角冒号组合在某些客户端版本解析失败），导致降级为纯文本。
    切换到 2.0 schema 后应能正常生成卡片，markdown 元素全部独立成行。
    """
    text = """民法是调整平等主体之间人身关系和财产关系的法律规范的总称。

**主要内容：**
- **人身关系**：人格权、身份权（如婚姻、家庭关系）
- **财产关系**：物权、债权、知识产权等

**核心原则：**
- 平等自愿
- 公平诚信
- 保护民事主体合法权益

**常见民法典分编：** 物权、合同、人格权、婚姻家庭、继承、侵权责任
"""
    card = MarkdownToCardConverter.to_card_json(text)
    # schema 2.0 结构断言
    assert card["schema"] == "2.0"
    assert "body" in card
    assert "card" not in card  # 关键：v2.0 不再有外层 card
    assert card["header"]["template"] == "blue"

    elements = card["body"]["elements"]
    md_elems = [e for e in elements if e.get("tag") == "markdown"]

    # 至少 8 个 markdown 元素（1 段 + 1 标题 + 2 列表 + 1 标题 + 3 列表 + 1 标题）
    assert len(md_elems) >= 8

    # 独立成行的 **xxx：** 加粗行被预处理剥离为纯文本（避免 v1 schema 的 200621）
    # 注：仅校验"独立成行"的两种标题（"主要内容：" / "核心原则："）；
    #     "**常见民法典分编：** 物权..."不是独立成行（同行有后文），
    #     _solo_bold 正则不会剥离，由飞书 v2.0 markdown 元素原生渲染。
    solo_bold_stripped = [
        el for el in md_elems
        if el["content"].strip() in ("主要内容：", "核心原则：")
    ]
    assert len(solo_bold_stripped) >= 2

    # 列表项里 "- **xxx**：" 的内联加粗仍保留（飞书原生 markdown 渲染）
    inline_bold_list = [
        el for el in md_elems
        if el["content"].startswith("- **") and "**：" in el["content"]
    ]
    assert len(inline_bold_list) >= 2

    # 顶层 schema 标识
    assert card["schema"] == "2.0"
    # config 字段保持简洁
    assert card["config"]["wide_screen_mode"] is True