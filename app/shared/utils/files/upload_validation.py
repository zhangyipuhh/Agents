#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
上传文件校验模块（2026-09-12 渗透报告观察项整改）。

两道防线：
1. 扩展名白名单（与前端 InputBox/KnowledgeChat/ProfileInputBox 的
   accept 属性对齐）：.pdf/.doc/.docx/.txt/.md/.markdown/.csv/.json；
2. 魔数嗅探（defense-in-depth）：二进制类型 .pdf/.doc/.docx 校验文件头,
   防止「shell.php 改名 shell.pdf」伪装上传。文本类型豁免魔数
   （其内容经转 md + 前端 DOMPurify 防线处理）。

新上传入口标准：必须先过本模块校验（见 AGENTS.md 安全开发强制标准）。
"""
from pathlib import Path


ALLOWED_UPLOAD_EXTENSIONS = frozenset({
    ".pdf", ".doc", ".docx",
    ".txt", ".md", ".markdown", ".csv", ".json",
})

# 二进制类型魔数签名（文本类型不校验）
_MAGIC_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}


def validate_upload_extension(filename: str) -> str:
    """校验文件扩展名是否在白名单内。

    参数:
        filename: 原始文件名（含扩展名）。

    返回:
        str: 归一化（小写）的扩展名。

    异常:
        ValueError: 扩展名缺失或不在白名单时抛出。
    """
    suffix = (Path(filename or "").suffix or "").lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"不支持的文件类型: {suffix or '(无扩展名)'}，"
            f"允许: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
        )
    return suffix


def validate_upload_content(filename: str, content: bytes) -> None:
    """魔数嗅探：二进制类型的文件头必须与扩展名匹配。

    参数:
        filename: 原始文件名（取扩展名）。
        content: 文件内容字节。

    返回:
        None

    异常:
        ValueError: 扩展名不在白名单，或魔数与扩展名不符时抛出。
    """
    suffix = validate_upload_extension(filename)
    signatures = _MAGIC_SIGNATURES.get(suffix)
    if not signatures:
        return  # 文本类型豁免魔数
    head = content[:8]
    if not any(head.startswith(sig) for sig in signatures):
        raise ValueError(
            f"文件内容与扩展名 {suffix} 不符（魔数校验失败）"
        )
