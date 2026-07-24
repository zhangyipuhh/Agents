#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
动态上下文提示词模块

负责把会话的运行时状态（用户上传附件列表、可用服务器列表）拼接到系统提示词末尾，
供两个 chat 入口（/api/agent/chat、/api/knowledge-chat）统一调用。

设计要点：
    1. 以 attachments 表为唯一事实源，每轮对话实时查询拼接，
       上传/删除附件后下一轮自动同步，不依赖前端请求体中的附件数组。
    2. 动态节点（<attachments> / <servers>）追加在系统提示词末尾，利用近因效应。
    3. 空状态显式化：没有附件时也输出 ``<attachments></attachments>``，
       显式空列表比节点缺失更能抑制模型幻觉。
    4. 路径跨平台：注入提示词的路径统一为 POSIX 风格且剥离 Windows 盘符
       （如 ``E:\\a\\b.md`` → ``/a/b.md``）；读取侧通过
       :func:`resolve_prompt_path` 反向解析回当前平台可访问的路径。
    5. <servers> 节点为后期扩展预留：本期仅注入空节点与说明文字，
       build_dynamic_context_xml 已支持 servers 参数，接入真实数据时结构不变。

Date: 2026-07-24
Author: AI Assistant
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import quoteattr

from app.core.config.paths import _PROJECT_ROOT

logger = logging.getLogger(__name__)

# Windows 盘符前缀（如 "E:" / "c:"）
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

DYNAMIC_CONTEXT_RULES = (
    "用户上传的附件列在 <attachments> 节点中。当用户询问附件内容时，"
    "必须使用该节点中列出的 path 调用 read_file 工具，禁止凭记忆或猜测编造文件名和内容。"
    "若 <attachments> 为空或其中没有用户所指的文件，直接告知用户没有该附件，不要假装读取。\n"
    "<servers> 节点列出可用服务器，用户可通过命令或拖拽引用。"
)
"""<attachments> / <servers> 节点的静态使用规则，随动态节点一起注入系统提示词末尾。"""


def normalize_attachment_path(stored_path: str) -> str:
    """把任意平台的存储路径规范化为注入提示词用的 POSIX 风格路径。

    规则：
        - 反斜杠统一替换为正斜杠；
        - 剥离 Windows 盘符（``E:\\a\\b.md`` / ``c:/a.md`` → ``/a/b.md``）；
        - Linux 绝对路径已是 ``/`` 开头，原样保留。

    参数:
        stored_path: attachments 表中的 stored_path（绝对路径，Windows 或 Linux 风格）

    返回:
        str: POSIX 风格、无盘符的绝对路径（以 ``/`` 开头）
    """
    if not stored_path:
        return ""
    normalized = str(stored_path).replace("\\", "/")
    normalized = _WINDOWS_DRIVE_RE.sub("", normalized, count=1)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def resolve_prompt_path(prompt_path: str) -> Path:
    """把提示词中的规范化路径反向解析为当前平台可访问的绝对路径。

    与 :func:`normalize_attachment_path` 互逆：
        - 已是当前平台绝对路径（Windows ``E:\\...`` / Linux ``/...``）→ 原样返回；
        - Windows 上以 ``/`` 开头的无盘符路径 → 补项目根所在盘符
          （``/a/b.md`` → ``E:\\a\\b.md``，盘符取自 ``_PROJECT_ROOT``）；
        - Linux 上以 ``/`` 开头的路径本身就是绝对路径，走第一条规则原样返回。

    参数:
        prompt_path: 提示词 <attachments> 节点中的 path 值

    返回:
        Path: 当前平台可访问的绝对路径（不保证存在，调用方自行判断）

    异常:
        ValueError: prompt_path 为空时抛出
    """
    raw = str(prompt_path or "").strip()
    if not raw:
        raise ValueError("prompt_path 不能为空字符串")
    p = Path(raw)
    if p.is_absolute():
        return p
    if os.name == "nt" and raw.startswith("/"):
        drive = Path(_PROJECT_ROOT).drive
        if drive:
            return Path(drive + raw)
    return p


def _format_size(size_bytes: Any) -> str:
    """把字节数格式化为人类可读的大小字符串。

    参数:
        size_bytes: 字节数（int 或可转 int 的值；非法值按 0 处理）

    返回:
        str: 如 ``"512B"`` / ``"560KB"`` / ``"2.3MB"``（保留 1 位小数，整数去尾零）
    """
    try:
        size = float(size_bytes or 0)
    except (TypeError, ValueError):
        size = 0.0
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            text = f"{size:.1f}".rstrip("0").rstrip(".")
            return f"{text}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _format_uploaded_at(created_at: Any) -> str:
    """把附件创建时间格式化为 ``YYYY-MM-DD`` 字符串。

    参数:
        created_at: datetime 实例或 ISO 格式字符串；空值返回空字符串

    返回:
        str: 日期字符串（如 ``"2026-07-24"``）；无法解析时返回原值前 10 位
    """
    if not created_at:
        return ""
    if isinstance(created_at, datetime):
        return created_at.strftime("%Y-%m-%d")
    return str(created_at)[:10]


def build_dynamic_context_xml(
    attachments: Optional[List[Dict[str, Any]]] = None,
    servers: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """构建 <attachments> / <servers> 动态上下文 XML 片段。

    空状态显式化：attachments / servers 为空时仍输出空的成对节点，
    而不是省略整个节点（显式空列表是更强的负向信号，抑制模型脑补附件）。

    参数:
        attachments: 附件记录列表（attachments 表行字典，需含
            file_name / stored_path / file_size / created_at 键）
        servers: 服务器列表（预留，需含 name / command 键；本期调用方传 None）

    返回:
        str: 形如::

            <attachments>
              <file name="需求文档.docx" path="/data/tmp/upload/.../x.md" size="560KB" uploaded_at="2026-07-24" />
            </attachments>

            <servers>
            </servers>
    """
    lines: List[str] = ["<attachments>"]
    for att in attachments or []:
        name = quoteattr(str(att.get("file_name") or ""))
        path = quoteattr(normalize_attachment_path(att.get("stored_path") or ""))
        size = quoteattr(_format_size(att.get("file_size")))
        uploaded_at = quoteattr(_format_uploaded_at(att.get("created_at")))
        lines.append(
            f"  <file name={name} path={path} size={size} uploaded_at={uploaded_at} />"
        )
    lines.append("</attachments>")
    lines.append("")
    lines.append("<servers>")
    for srv in servers or []:
        name = quoteattr(str(srv.get("name") or ""))
        command = quoteattr(str(srv.get("command") or ""))
        lines.append(f"  <server name={name} command={command} />")
    lines.append("</servers>")
    return "\n".join(lines)


async def build_dynamic_system_suffix(session_id: str) -> str:
    """构建追加到系统提示词末尾的动态上下文后缀（静态规则 + XML 节点）。

    以 attachments 表为唯一事实源，按 session_id 实时查询附件列表；
    数据库未启用（Memory 模式）或查询异常时降级为空附件列表，
    仍输出显式空节点，保证提示词结构稳定。

    参数:
        session_id: 会话 ID

    返回:
        str: 完整后缀文本，形如::

            用户上传的附件列在 <attachments> 节点中。...
            <servers> 节点列出可用服务器，...

            <attachments>
              ...
            </attachments>

            <servers>
            </servers>
    """
    # 延迟导入避免模块级循环依赖（attachment_db → DatabasePool）
    from app.shared.utils.files.attachment_db import AttachmentDB

    try:
        attachments = await AttachmentDB.get_session_attachments(session_id or "default")
    except Exception as e:
        logger.warning(
            "[dynamic_context] 查询会话附件失败，降级为空列表: session_id=%s, error=%s",
            session_id, e,
        )
        attachments = []

    xml_block = build_dynamic_context_xml(attachments)
    return f"{DYNAMIC_CONTEXT_RULES}\n\n{xml_block}"
