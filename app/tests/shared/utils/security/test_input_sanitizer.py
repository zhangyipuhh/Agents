# -*- coding:utf-8 -*-
"""input_sanitizer 模块测试：纯文本字段 HTML 消毒（渗透报告 vuln-0004 整改）。"""


def test_sanitize_plain_text_importable():
    """模块与标准类型可导入。"""
    from app.shared.utils.security.input_sanitizer import (
        OptionalPlainText,
        PlainText,
        sanitize_optional_text,
        sanitize_plain_text,
    )
    assert callable(sanitize_plain_text)
    assert callable(sanitize_optional_text)
    assert PlainText is not None
    assert OptionalPlainText is not None


def test_sanitize_strips_script_tags():
    """script 标签被剥离,innerText 保留。"""
    from app.shared.utils.security.input_sanitizer import sanitize_plain_text
    assert sanitize_plain_text("<script>alert(1)</script>") == "alert(1)"


def test_sanitize_strips_img_onerror_payload():
    """img/onerror 载荷整标签剥离,无残留。"""
    from app.shared.utils.security.input_sanitizer import sanitize_plain_text
    assert sanitize_plain_text('<img src=x onerror=alert(1)>') == ""


def test_sanitize_strips_nested_and_malformed_tags():
    """嵌套/畸形标签全部剥离。"""
    from app.shared.utils.security.input_sanitizer import sanitize_plain_text
    assert sanitize_plain_text("研发<b>部</b>门") == "研发部门"
    assert sanitize_plain_text("a</b>b<i>c") == "abc"
    assert sanitize_plain_text("<svg><script>alert(1)</script></svg>") == "alert(1)"


def test_sanitize_preserves_literal_angle_brackets():
    """字面小于号保留(非标签),避免双重转义显示异常。"""
    from app.shared.utils.security.input_sanitizer import sanitize_plain_text
    assert sanitize_plain_text("a < b") == "a < b"
    assert sanitize_plain_text("1 < 2 > 0") == "1 < 2 > 0"


def test_sanitize_empty_and_plain_passthrough():
    """空串与纯文本原样透传。"""
    from app.shared.utils.security.input_sanitizer import sanitize_plain_text
    assert sanitize_plain_text("") == ""
    assert sanitize_plain_text("张三") == "张三"
    assert sanitize_plain_text("研发一部") == "研发一部"


def test_sanitize_optional_none_passthrough():
    """Optional 版本 None 透传。"""
    from app.shared.utils.security.input_sanitizer import sanitize_optional_text
    assert sanitize_optional_text(None) is None
    assert sanitize_optional_text("<b>x</b>") == "x"


def test_plaintext_annotated_type_sanitizes_in_model():
    """PlainText 注解在 Pydantic 模型中自动消毒。"""
    from pydantic import BaseModel
    from app.shared.utils.security.input_sanitizer import PlainText

    class _M(BaseModel):
        name: PlainText = ""

    assert _M(name="<script>alert(1)</script>").name == "alert(1)"
    assert _M().name == ""


def test_optional_plaintext_annotated_type_in_model():
    """OptionalPlainText 注解在 Pydantic 模型中自动消毒且 None 透传。"""
    from typing import Optional
    from pydantic import BaseModel
    from app.shared.utils.security.input_sanitizer import OptionalPlainText

    class _M(BaseModel):
        title: OptionalPlainText = None

    assert _M(title="<i>t</i>").title == "t"
    assert _M().title is None
