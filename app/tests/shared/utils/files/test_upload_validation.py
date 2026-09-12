# -*- coding:utf-8 -*-
"""upload_validation 测试：上传扩展名白名单 + 魔数校验（渗透报告观察项整改）。"""
import pytest


def test_upload_validation_importable():
    """模块与白名单常量可导入。"""
    from app.shared.utils.files.upload_validation import (
        ALLOWED_UPLOAD_EXTENSIONS,
        validate_upload_content,
        validate_upload_extension,
    )
    assert ".pdf" in ALLOWED_UPLOAD_EXTENSIONS
    assert ".php" not in ALLOWED_UPLOAD_EXTENSIONS


@pytest.mark.parametrize("filename", [
    "报告.pdf", "a.doc", "a.docx", "a.txt", "a.md", "a.markdown", "a.csv", "a.json",
    "A.PDF",  # 大小写不敏感
])
def test_validate_upload_extension_allows_whitelist(filename):
    """白名单内扩展名通过（与前端 accept 属性对齐）。"""
    from app.shared.utils.files.upload_validation import validate_upload_extension
    validate_upload_extension(filename)  # 不抛异常即通过


@pytest.mark.parametrize("filename", [
    "shell.php", "x.svg", "x.py", "x.sh", "x.exe", "x.html", "x.htm",
    "x.js", "x.jsp", "x.bat", "x.ps1", "noext",
])
def test_validate_upload_extension_rejects_dangerous(filename):
    """危险/未知扩展名拒绝（ValueError）。"""
    from app.shared.utils.files.upload_validation import validate_upload_extension
    with pytest.raises(ValueError):
        validate_upload_extension(filename)


def test_validate_upload_content_pdf_magic_ok():
    """真实 PDF 魔数通过。"""
    from app.shared.utils.files.upload_validation import validate_upload_content
    validate_upload_content("a.pdf", b"%PDF-1.7 ...")


def test_validate_upload_content_pdf_spoofed_rejected():
    """伪装 .pdf 的脚本内容拒绝（魔数不符）。"""
    from app.shared.utils.files.upload_validation import validate_upload_content
    with pytest.raises(ValueError):
        validate_upload_content("a.pdf", b"<?php echo 1; ?>")


def test_validate_upload_content_docx_magic_ok():
    """真实 DOCX（ZIP 容器）魔数通过。"""
    from app.shared.utils.files.upload_validation import validate_upload_content
    validate_upload_content("a.docx", b"PK\x03\x04" + b"\x00" * 64)


def test_validate_upload_content_doc_magic_ok():
    """真实 DOC（OLE2）魔数通过。"""
    from app.shared.utils.files.upload_validation import validate_upload_content
    validate_upload_content("a.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)


def test_validate_upload_content_text_types_skip_magic():
    """文本类型（md/txt/csv/json/markdown）豁免魔数校验。"""
    from app.shared.utils.files.upload_validation import validate_upload_content
    validate_upload_content("a.md", b"# hello <script>still-ok-here</script>")
    validate_upload_content("a.csv", b"a,b,c")
    validate_upload_content("a.json", b"{}")
    validate_upload_content("a.txt", b"plain")
    validate_upload_content("a.markdown", b"# t")
