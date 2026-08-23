#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MarkdownToCardConverter - Markdown 文本 → 飞书交互式卡片 JSON 转换器

职责：
    - 把 agent 回复的 Markdown 文本转成飞书卡片 JSON（msg_type="interactive"）
    - 自动检测文本是否含 Markdown 特征，决定走"纯文本"还是"卡片"渲染
    - 卡片 API 任何失败 → 调用方应降级回纯文本发送

支持的 Markdown 语法：
    - # / ## / ###  → 飞书 ``tag="markdown"`` + heading 文本（飞书 markdown 元素内嵌原生支持）
    - **粗体** / *斜体* / `code`  → 同上（飞书 markdown 元素支持）
    - - xxx / * xxx 列表项  →  同行拼接为 tag="markdown" 段落
    - 1. xxx / 1) xxx 有序列表项 →  保留"1."原前缀，每个独立 tag="markdown" 元素
    - > 引用  → ``tag="markdown"`` 内嵌引用语法
    - --- 分隔线  → ``tag="hr"``
    - ``` ... ``` 代码围栏  → ``tag="code_block"``
    - 纯文本段落  → ``tag="markdown"``

依据：[飞书消息卡片文档](https://open.feishu.cn/document/develop-a-card-interactive-bot/card-building-steps)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# 飞书单卡片约 30KB 总上限；保守字符阈值为 4000，避免序列化超限。
_MAX_CARD_TEXT_LEN = 4000
_TRUNCATE_HINT = "...（内容过长已截断）"

# 流式卡片主文本元素 ID，供 CardKit 元素级更新 API 定位
_STREAMING_ELEMENT_ID = "markdown_main"

# Markdown 特征检测正则（任一命中即视为 markdown）
_RE_BOLD = re.compile(r"\*\*[^*\n]+\*\*")
_RE_ITALIC = re.compile(r"(?<![*\w])\*[^*\n]+\*(?![*\w])")
_RE_INLINE_CODE = re.compile(r"`[^`\n]+`")
_RE_HEADING = re.compile(r"(?m)^#{1,6}\s+\S")
_RE_LIST = re.compile(r"(?m)^\s{0,3}[-*+]\s+\S")
# 有序列表项: 行首 1. / 2. / …… / 99. + 空格 + 非空白字符
# 允许 0~3 个前导空格（与无序列表一致）；编号限定 1~2 位避免误吞带年份等的长数字
_RE_ORDERED_LIST = re.compile(r"(?m)^\s{0,3}\d{1,2}[.)]\s+\S")
# 行内编号项的拆分锚（2026-07-17 新增）: 数字 +（. 或 )）+ 空格 的**前一个字符**
# 必须是 CJK 字符 / CJK 标点 / 半角中英标点 —— 即"前一个 item 末尾 + 编号前缀"
# 的边界位置。LLM 输出"1. xxx2. xxx3. xxx"(编号挤在同一行)时,前一个 item
# 末尾几乎不跟空白,只能靠 CJK 终止字符作为锚。仅靠 CJK 单字符锚可避免把
# "今天是 2026 年 7 月 17 日" / "苹果 20 元一斤" 等含数字的非编号文本误拆。
# re.split 在捕获组（数字）位置切开,捕获到的数字单独成 entry,便于 walk 重组。
_RE_INLINE_ORDERED_SPLIT = re.compile(
    r"(?<=[一-鿿。,，;:；、！？」】）)])\s*(\d{1,2})[.)]\s+"
)
_RE_BLOCKQUOTE = re.compile(r"(?m)^\s*>\s+\S")
_RE_HR = re.compile(r"(?m)^\s*---\s*$")
_RE_FENCE = re.compile(r"```")

# Markdown 表格检测（2026-08-23 新增）。
#
# 触发条件：连续两行都「像表格行」——
#   - 表格行：行首 `|` 或包含至少 2 个 `|`，典型 `| col | col |`
#   - 分隔行：`| --- | --- |`（纯 `-` / `:---` / `:---:` 等对齐标识，列数等于表头列数）
#
# 注意：分隔行必须紧随表头行；否则不识别。下面两个正则分别匹配「表头/数据行」
# 与「纯对齐分隔行」。
_RE_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$")
# 允许的单元格内容：飞书 markdown 元素不支持多行字符串，也不允许出现 `|`，
# 但本正则仅做行级别判别；解析单元格交给下面的 `_parse_table_cells`。
_RE_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _parse_table_row(line: str) -> List[str]:
    """把 ``"| col1 | col2 | col3 |"`` 这种行切成单元格列表。

    去除首尾的 ``|``、按 ``|`` 拆分、每格 ``strip``。空行会被丢弃。

    Args:
        line: 原始表格行

    Returns:
        list[str]: 单元格文本列表（不含空字符串）
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def _looks_like_separator_row(line: str, header_cols: int) -> bool:
    """判断当前行是否是「合法的表格分隔行」，且列数与表头一致。

    飞书 v1/v2 schema 不强制要求 ``:---:`` 对齐语法，但很多 LLM 输出会带，
    这里都接受。表格分隔行的所有单元格必须是 ``-`` / ``:---`` / ``---:`` /
    ``:---:`` 这种纯对齐标记，不允许混杂其它字符。

    Args:
        line: 原始行
        header_cols: 上一行表头的列数

    Returns:
        bool: 该行能作为表格分隔行返回 ``True``
    """
    s = line.strip()
    # 必须形如 ``| ... |``，否则直接判否
    if not _RE_TABLE_SEP.match(s):
        return False
    cells = _parse_table_row(line)
    if len(cells) != header_cols:
        return False
    for c in cells:
        cc = c.strip()
        if not re.fullmatch(r":?-{2,}:?", cc):
            return False
    return True


def _build_column_set_table(
    header: List[str],
    body_rows: List[List[str]],
) -> List[Dict[str, Any]]:
    """把表格数据转成飞书 ``column_set`` + ``column`` 多列布局列表。

    飞书 v2.0 schema 没有原生的 ``<table>`` 元素；为了让 LLM 输出的
    ``| 列 | 列 |`` 表格能在卡片里整齐展示，我们用一列一列的方式抽出
    数据：第一个 ``column_set`` 是表头（加粗居中、灰色背景），后续每个
    数据行再起一个 ``column_set``、背景 ``default`` 隔行错开。

    列宽策略：固定 ``weight=1``，由飞书侧自动均分（避免 weight 必须 <= 5 的
    硬限制）。如果列数 > 5，仍然输出（飞书会强制压缩列宽）。

    Args:
        header: 表头单元格列表
        body_rows: 数据行列表（每行是单元格列表，长度可能不一致）

    Returns:
        list[dict]: 每个元素是一个 ``column_set``（表头 + 每行一个）
    """
    col_count = len(header)
    if col_count == 0:
        return [{"tag": "markdown", "content": ""}]

    def _column(cell_text: str) -> Dict[str, Any]:
        """构造单列内容：居中对齐（表头 / 数据共用，由调用方决定加粗）。"""
        # 飞书 markdown 元素会保留 \n，但单格里换行不友好，去掉多余空格
        text = re.sub(r"\s+", " ", cell_text or "").strip()
        return {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "vertical_align": "top",
            "elements": [
                {"tag": "markdown", "content": text, "text_align": "center"}
            ],
        }

    def _header_column(cell_text: str) -> Dict[str, Any]:
        col = _column(cell_text)
        # 表头元素再嵌一个加粗的 markdown
        col["elements"][0]["content"] = f"**{col['elements'][0]['content'] or ''}**"
        return col

    header_columns = [_header_column(h) for h in header]
    elements: List[Dict[str, Any]] = [
        {
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "grey",
            "horizontal_spacing": "default",
            "columns": header_columns,
        }
    ]

    for idx, row in enumerate(body_rows):
        # 把单元格补齐到 col_count（短行补空、长行截断）
        cells = list(row)[:col_count]
        while len(cells) < col_count:
            cells.append("")
        columns = [_column(c) for c in cells]
        elements.append(
            {
                "tag": "column_set",
                "flex_mode": "none",
                "background_style": "default",
                "horizontal_spacing": "default",
                "columns": columns,
            }
        )

    return elements


class MarkdownToCardConverter:
    """Markdown → 飞书卡片 JSON 转换器（无交互按钮，纯展示）。"""

    # ------------------------------------------------------------------ #
    # 公开 API                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def looks_like_markdown(text: str) -> bool:
        """判断文本是否含 Markdown 特征。

        检测规则（任一命中即返回 True）：
            - **粗体** / *斜体* / `行内代码`
            - # / ## / ### 起始行
            - - / * 列表前缀
            - > 引用
            - --- 分隔线
            - ``` 代码围栏

        Args:
            text: 待检测文本

        Returns:
            bool: 是否包含 Markdown 特征
        """
        if not text:
            return False
        if _RE_BOLD.search(text):
            return True
        if _RE_ITALIC.search(text):
            return True
        if _RE_INLINE_CODE.search(text):
            return True
        if _RE_HEADING.search(text):
            return True
        if _RE_LIST.search(text):
            return True
        if _RE_ORDERED_LIST.search(text):
            return True
        if _RE_BLOCKQUOTE.search(text):
            return True
        if _RE_HR.search(text):
            return True
        # 代码围栏：成对出现才算
        if _RE_FENCE.search(text) and len(_RE_FENCE.findall(text)) >= 2:
            return True
        # Markdown 表格行：至少出现一对「表格行 + 分隔行」（2026-08-23 新增）
        if MarkdownToCardConverter._looks_like_markdown_table(text):
            return True
        return False

    # ------------------------------------------------------------------ #
    # Markdown 表格检测（2026-08-23 新增）                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _looks_like_markdown_table(text: str) -> bool:
        """判断文本是否包含 markdown 表格。

        触发条件：至少出现一对「表头行 + 分隔行」——
          - 表头行：``| col1 | col2 |...``（前后带 ``|``，中间有 ``|``）
          - 分隔行：``| --- | --- |...``（每个 cell 是 ``:---:`` / ``---`` 这种对齐标记）

        仅一行 ``| col |`` 没有分隔行不算表格。

        Args:
            text: 待检测文本

        Returns:
            bool: 文本里是否含 markdown 表格
        """
        if not text:
            return False
        in_table = False
        header_cols = 0
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                if in_table:
                    # 表格块内的空行视作表格结束（除非接下来还有数据行，但
                    # 标准 markdown 表格是连续成段）
                    in_table = False
                    header_cols = 0
                continue
            if _RE_TABLE_ROW.match(line):
                cells = _parse_table_row(raw)
                if in_table:
                    # 在表内：先判定是否为「合法的分隔行」——分隔行也满足
                    # ``|...|...|`` 形状，但单元格内容是 `---` / `:---:`。
                    # 仅当分隔行的列数与表头一致，且每个单元格是合法对齐标记
                    # 时，才算真正的表格分隔行。
                    if _looks_like_separator_row(raw, header_cols):
                        return True
                    # 不是分隔行但又在表格区域里——若列数与表头一致，认为
                    # 是「数据行」继续；否则视为表格假设失败，从候选表头行开始重试。
                    if len(cells) != header_cols:
                        in_table = False
                        header_cols = 0
                    continue
                # 不在表内：把当前行当作候选表头，等待下一行验证分隔行
                in_table = True
                header_cols = len(cells)
                continue
            # 非表格行 → 重置表假设
            in_table = False
            header_cols = 0
        return False

    @staticmethod
    def to_card_json(
        markdown_text: str,
        header_title: str = "🤖 AI 智能体回复",
    ) -> Dict[str, Any]:
        """把 Markdown 文本转换为飞书卡片 JSON（schema=2.0）。

        2026-07-17 升级：从 v1.0 schema（``{"card": {...}}`` 嵌套结构）
        切换到 v2.0 schema（``{"schema": "2.0", "header": {...}, "body": {...}}``），
        避免孤立加粗行（如 ``**核心原则：**``）触发飞书
        ``ErrCode: 200621; ErrMsg: parse card json err`` 导致降级为纯文本
        （降级后用户看到 ``**xxx**`` / ``- xxx`` 原始 markdown 源码）。

        Args:
            markdown_text: Markdown 文本
            header_title: 卡片头部标题

        Returns:
            dict: 飞书卡片 JSON（schema 2.0），结构形如::

                {
                    "schema": "2.0",
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "template": "blue",
                        "title": {"tag": "plain_text", "content": "..."},
                    },
                    "body": {
                        "elements": [
                            {"tag": "markdown", "content": "..."},
                            {"tag": "hr"},
                            {"tag": "code_block", "language": "python", "content": "..."},
                            ...
                        ],
                    },
                }
        """
        if markdown_text is None:
            markdown_text = ""
        # 截断
        text = markdown_text
        if len(text) > _MAX_CARD_TEXT_LEN:
            keep = _MAX_CARD_TEXT_LEN - len(_TRUNCATE_HINT)
            text = text[:keep] + _TRUNCATE_HINT

        elements = MarkdownToCardConverter._parse_block_elements(text)
        # 至少给一个占位元素，避免飞书拒绝空卡片
        if not elements:
            elements = [{"tag": "markdown", "content": ""}]

        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": header_title},
            },
            "body": {"elements": elements},
        }

    @staticmethod
    def to_streaming_card_json(
        markdown_text: str,
        header_title: str = "🤖 AI 智能体回复",
        *,
        element_id: str = _STREAMING_ELEMENT_ID,
        print_frequency_ms: int = 70,
        print_step: int = 1,
        print_strategy: str = "fast",
    ) -> Dict[str, Any]:
        """把 Markdown 文本转换为支持 CardKit 流式更新的卡片 JSON。

        与 ``to_card_json`` 的区别：
            - 给主文本 markdown 元素增加 ``element_id``，供元素级更新 API 定位
            - ``config`` 中开启 ``streaming_mode``、``update_multi`` 并填充
              ``streaming_config``（打印频率/步长/策略）

        Args:
            markdown_text: Markdown 文本
            header_title: 卡片头部标题
            element_id: 主文本元素 ID，用于元素级更新；默认 ``markdown_main``
            print_frequency_ms: streaming 打印频率（毫秒）
            print_step: streaming 打印步长（字符数）
            print_strategy: streaming 打印策略，如 ``fast``

        Returns:
            dict: 飞书卡片 JSON（schema 2.0 + streaming 配置）
        """
        card = MarkdownToCardConverter.to_card_json(
            markdown_text, header_title=header_title
        )
        # 给第一个 markdown 元素设置 element_id（作为主文本容器）
        body = card.setdefault("body", {})
        elements = body.setdefault("elements", [])
        for element in elements:
            if isinstance(element, dict) and element.get("tag") == "markdown":
                element["element_id"] = element_id
                break

        config = card.setdefault("config", {})
        config["update_multi"] = True
        config["streaming_mode"] = True
        config["streaming_config"] = {
            "print_frequency_ms": {
                "default": print_frequency_ms,
                "android": print_frequency_ms,
                "ios": print_frequency_ms,
                "pc": print_frequency_ms,
            },
            "print_step": {
                "default": print_step,
                "android": print_step,
                "ios": print_step,
                "pc": print_step,
            },
            "print_strategy": print_strategy,
        }
        return card

    # ------------------------------------------------------------------ #
    # Block-level parsing                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_block_elements(text: str) -> List[Dict[str, Any]]:
        """逐行扫描 markdown 文本，按块生成飞书卡片元素。

        支持的块类型（按顺序处理同一文本）：
            - 围栏代码块（``` ... ```）→ code_block
            - 分隔线（---）→ hr
            - 标题（#/##/###）→ markdown 元素
            - 引用（> xxx）→ markdown 元素（> 前缀）
            - 列表项（- xxx / * xxx）→ 拼成单个 markdown 段落
            - 空行 → 段落分隔
            - 其它文本 → markdown 段落

        Args:
            text: 已截断的 markdown 文本

        Returns:
            list[dict]: 飞书卡片元素列表
        """
        elements: List[Dict[str, Any]] = []
        lines = text.splitlines()
        # 预处理：剥离单独成行的 **xxx** 加粗 / *xxx* 斜体包装，
        # 清理行首/行尾的内联标记；同时给纯 emoji 行首补一个普通
        # ASCII 空格作为前缀缓冲，避免飞书 markdown 解析器对孤立
        # emoji 行触发 "parse card json err"（code=200621）。
        # 飞书 v1 schema 的 markdown 元素要求行首必须是普通字符；
        # emoji 在前会被解析器误判为非法。补一个空格视觉上几乎无感，
        # 但能保证卡片解析成功。视觉加粗由卡片整体结构承担。
        _solo_bold = re.compile(r"^\*\*([^*\n]+)\*\*\s*$")
        _solo_italic = re.compile(r"^\*([^*\n]+)\*\s*$")
        _leading_marker = re.compile(r"^\*+\s+")
        _trailing_marker = re.compile(r"\s+\*+$")
        # 匹配"行首是 emoji（一个或多个 emoji 字符）+ 可选空格 + 文本"
        _leading_emoji = re.compile(
            r"^([\U0001F300-\U0001FAFF\U00002600-\U000027BF"
            r"\U0001F000-\U0001F02F\U0001F100-\U0001F1FF"
            r"\U0001F200-\U0001F2FF]+)(\s*)(.*)$"
        )

        def _safe_leading_emoji(line: str) -> str:
            m = _leading_emoji.match(line)
            if not m:
                return line
            emoji, spaces, rest = m.group(1), m.group(2), m.group(3)
            # 行首只有 emoji（无后续文字）→ 在前补 ASCII 空格
            if not rest.strip():
                return " " + line
            # emoji + 空格 + 文本 → emoji 前补 ASCII 空格
            return " " + emoji + (spaces or " ") + rest

        lines = [_solo_bold.sub(r"\1", line) for line in lines]
        lines = [_solo_italic.sub(r"\1", line) for line in lines]
        lines = [_leading_marker.sub("", line) for line in lines]
        lines = [_trailing_marker.sub("", line) for line in lines]
        lines = [_safe_leading_emoji(line) for line in lines]
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 围栏代码块
            if stripped.startswith("```"):
                # 找到下一个 ``` 结束符
                fence_open = stripped
                lang_match = re.match(r"^```\s*([\w+-]*)\s*$", fence_open)
                lang = lang_match.group(1) if lang_match and lang_match.group(1) else ""
                code_lines: List[str] = []
                i += 1
                while i < n:
                    inner = lines[i]
                    if inner.strip().startswith("```"):
                        i += 1
                        break
                    code_lines.append(inner)
                    i += 1
                code_content = "\n".join(code_lines)
                # 飞书 code_block 元素
                cb: Dict[str, Any] = {"tag": "code_block", "content": code_content}
                if lang:
                    cb["language"] = lang
                elements.append(cb)
                continue

            # 分隔线
            if re.match(r"^\s*---\s*$", line):
                elements.append({"tag": "hr"})
                i += 1
                continue

            # Markdown 表格（2026-08-23 新增）：表头行 + 分隔行 + 0..N 数据行
            # 使用与 _looks_like_markdown_table 同样的判定；解析失败回退为普通段落。
            # 2026-08-23 增补：少列补空、多列截断（不再因列数不一致而 break）。
            # LLM 偶发输出「少一格」的表格行，整体丢弃会丢内容，故统一交给
            # _build_column_set_table 在 column_set 层做对齐。
            if _RE_TABLE_ROW.match(stripped):
                cells = _parse_table_row(line)
                if (
                    len(cells) >= 2
                    and (i + 1) < n
                    and _looks_like_separator_row(lines[i + 1], len(cells))
                ):
                    # 吃掉表头 + 分隔行；继续累积数据行直到非表格行
                    header = cells
                    i += 2
                    body_rows: List[List[str]] = []
                    while i < n and _RE_TABLE_ROW.match(lines[i].strip()):
                        row = _parse_table_row(lines[i])
                        # 单元格数与表头不一致时：少则补空、多则截断，保留整张表
                        # （LLM 偶尔会漏一格；「补空」比「整行丢失」对用户更友好）
                        if len(row) < len(header):
                            row = row + [""] * (len(header) - len(row))
                        elif len(row) > len(header):
                            row = row[: len(header)]
                        body_rows.append(row)
                        i += 1
                    elements.extend(
                        _build_column_set_table(header, body_rows)
                    )
                    continue

            # 标题
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                # 飞书 markdown 元素内嵌 # 标题语法（# / ## / ### / #### 均可）
                prefix = "#" * min(level, 4)
                elements.append(
                    {"tag": "markdown", "content": f"{prefix} {title}"}
                )
                i += 1
                continue

            # 引用：每行单独一个 markdown 元素（避免多行解析问题）
            if stripped.startswith(">"):
                while i < n and lines[i].lstrip().startswith(">"):
                    inner = lines[i].lstrip()[1:].lstrip()
                    elements.append(
                        {"tag": "markdown", "content": f"> {inner}"}
                    )
                    i += 1
                continue

            # 列表项：每项单独一个 markdown 元素（避免飞书 v1 markdown 元素
            # 多行内容解析问题）。连续项仍聚拢在一起便于阅读。
            if re.match(r"^\s*[-*+]\s+\S", line):
                while i < n and re.match(r"^\s*[-*+]\s+\S", lines[i]):
                    bullet = re.sub(r"^\s*[-*+]\s+", "- ", lines[i])
                    elements.append({"tag": "markdown", "content": bullet})
                    i += 1
                continue

            # 有序列表项：每项单独一个 markdown 元素(保留"1."原前缀，
            # 由飞书 markdown 元素原生渲染编号递增)。编号限定 1~2 位数字。
            # 同时识别 "1." 与 "1)" 两种写法。
            #
            # 2026-07-17 增补：行内多编号拆分。LLM 经常把多个编号项挤到同一行
            # (`1. xxx2. xxx3. xxx4. xxx`),仅靠行扫描会丢内容。
            # 故对每个 emit 的有序列表项内容做 `_RE_INLINE_ORDERED_SPLIT` 拆分,
            # 把同行多编号切成多个独立 markdown 元素。仅靠 CJK 字符/CJK 标点作锚
            # 避免误拆"20 元一斤""2026 年"等含数字的非编号文本。
            ordered_match = re.match(r"^\s*(\d{1,2})[.)]\s+(\S.*)$", line)
            if ordered_match:
                while i < n:
                    om = re.match(r"^\s*(\d{1,2})[.)]\s+(\S.*)$", lines[i])
                    if not om:
                        break
                    full_content = f"{om.group(1)}. {om.group(2)}"
                    # 行内编号拆分
                    inline_parts = _RE_INLINE_ORDERED_SPLIT.split(full_content)
                    if len(inline_parts) == 1:
                        elements.append(
                            {"tag": "markdown", "content": full_content}
                        )
                    else:
                        # parts[0] 是含行首 "1. xxx" 的第一个 item（行首编号已拼回）
                        # parts[1] = num, parts[2] = next_seg, parts[3] = num, ...
                        elements.append(
                            {"tag": "markdown", "content": inline_parts[0].rstrip()}
                        )
                        for k in range(1, len(inline_parts), 2):
                            num = inline_parts[k]
                            seg = (
                                inline_parts[k + 1]
                                if k + 1 < len(inline_parts)
                                else ""
                            )
                            elements.append(
                                {
                                    "tag": "markdown",
                                    "content": f"{num}. {seg.rstrip()}",
                                }
                            )
                    i += 1
                continue

            # 空行：跳过（用于段落分隔）
            if not stripped:
                i += 1
                continue

            # 普通段落：合并到下一个空行 / 块级元素之前
            para_lines: List[str] = []
            while i < n:
                cur = lines[i]
                cur_stripped = cur.strip()
                if not cur_stripped:
                    break
                if cur_stripped.startswith("```"):
                    break
                if re.match(r"^\s*---\s*$", cur):
                    break
                if re.match(r"^(#{1,6})\s+\S", cur_stripped):
                    break
                if cur_stripped.startswith(">"):
                    break
                if re.match(r"^\s*[-*+]\s+\S", cur):
                    break
                if re.match(r"^\s*\d{1,2}[.)]\s+\S", cur):
                    break
                para_lines.append(cur)
                i += 1
            # 每段拆成单独 markdown 元素（每行一个），避免飞书 v1
            # markdown 元素多行内容解析不稳定的问题
            for line in para_lines:
                elements.append({"tag": "markdown", "content": line})

        return elements