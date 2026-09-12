#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
用户输入 HTML 消毒模块（等保三级入侵防范 + 渗透报告 vuln-0004 整改）。

设计决策：
- ``bleach.clean(tags=frozenset(), strip=True)`` 剥离全部 HTML 标签；
- ``html.unescape`` 还原 bleach 序列化时产生的实体转义，保证「研发 <部>」
  这类字面输入落库后按原样显示（前端 Vue ``{{ }}`` 插值自带转义，安全）；
- 本模块只服务「不预期 HTML 的纯文本字段」（名称/标题/部门/职位等）。
  富文本/Markdown 内容（聊天消息、知识库）不走本模块——由前端
  ``safeMarkdown`` + DOMPurify 防线负责（2026-08-07 已落地）。

新功能标准：所有用户可控纯文本字段必须使用 ``PlainText`` /
``OptionalPlainText`` 注解类型声明（见 AGENTS.md 安全开发强制标准）。
"""
import html
from typing import Annotated, Optional

import bleach
from pydantic import AfterValidator


def sanitize_plain_text(value: str) -> str:
    """剥离字符串中的全部 HTML 标签,返回纯文本。

    参数:
        value: 原始用户输入字符串。

    返回:
        str: 无标签纯文本；空输入原样返回。

    异常:
        TypeError: value 非字符串时由 bleach/Pydantic 上游抛出（正常不触发）。
    """
    if not value:
        return value
    cleaned = bleach.clean(
        value,
        tags=frozenset(),
        attributes={},
        strip=True,
        strip_comments=True,
    )
    return html.unescape(cleaned)


def sanitize_optional_text(value: Optional[str]) -> Optional[str]:
    """对 Optional[str] 字段消毒；None 透传。

    参数:
        value: 原始输入或 None。

    返回:
        Optional[str]: 消毒后文本或 None。
    """
    return sanitize_plain_text(value) if isinstance(value, str) else value


# 标准注解类型：新功能所有用户可控纯文本字段必须使用
PlainText = Annotated[str, AfterValidator(sanitize_plain_text)]
OptionalPlainText = Annotated[Optional[str], AfterValidator(sanitize_optional_text)]
