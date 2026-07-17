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
    - - xxx / * xxx 列表项  → 同行拼接为 tag="markdown" 段落
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

# Markdown 特征检测正则（任一命中即视为 markdown）
_RE_BOLD = re.compile(r"\*\*[^*\n]+\*\*")
_RE_ITALIC = re.compile(r"(?<![*\w])\*[^*\n]+\*(?![*\w])")
_RE_INLINE_CODE = re.compile(r"`[^`\n]+`")
_RE_HEADING = re.compile(r"(?m)^#{1,6}\s+\S")
_RE_LIST = re.compile(r"(?m)^\s{0,3}[-*+]\s+\S")
_RE_BLOCKQUOTE = re.compile(r"(?m)^\s*>\s+\S")
_RE_HR = re.compile(r"(?m)^\s*---\s*$")
_RE_FENCE = re.compile(r"```")


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
        if _RE_BLOCKQUOTE.search(text):
            return True
        if _RE_HR.search(text):
            return True
        # 代码围栏：成对出现才算
        if _RE_FENCE.search(text) and len(_RE_FENCE.findall(text)) >= 2:
            return True
        return False

    @staticmethod
    def to_card_json(
        markdown_text: str,
        header_title: str = "🤖 AI 智能体回复",
    ) -> Dict[str, Any]:
        """把 Markdown 文本转换为飞书卡片 JSON。

        Args:
            markdown_text: Markdown 文本
            header_title: 卡片头部标题

        Returns:
            dict: 飞书卡片 JSON，结构形如::

                {
                    "config": {"wide_screen_mode": True, "enable_forward": True},
                    "card": {
                        "header": {"title": {"tag": "plain_text", "content": "..."}},
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
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": header_title},
                },
                "elements": elements,
            },
        }

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
                para_lines.append(cur)
                i += 1
            # 每段拆成单独 markdown 元素（每行一个），避免飞书 v1
            # markdown 元素多行内容解析不稳定的问题
            for line in para_lines:
                elements.append({"tag": "markdown", "content": line})

        return elements