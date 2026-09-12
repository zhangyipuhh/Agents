#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuDocxClient - 飞书 docx v1 服务客户端

职责：
    - 封装飞书 docx v1 Open API（创建文档 / 读取内容 / 写入 block）
    - 提供 ``create_document`` / ``get_document_raw_content`` /
      ``append_block_children`` / ``list_blocks`` 异步方法
    - 提供 ``_md_to_blocks`` 模块级 helper：把 markdown 文本转飞书 docx block JSON
    - 失败统一返回 ``{"success": False, "error": ..., "code": ...}``，
      不抛异常（与项目内全部 Client / Tool 一致）

复用：
    - ``MarkdownToCardConverter`` 的正则常量（_RE_HEADING / _RE_FENCE /
      _RE_TABLE_ROW 等），保证「md 解析语义」全项目只有一份
    - 不复用其卡片 schema 输出（卡片结构 ≠ 文档 block 结构）

约束：
    - 不直接调用 ``FeishuClient.get_lark_client()`` 旧单例路径
      （2026-09-11 已重构为 FeishuEndpointResolver 按 agent 路由）
    - 构造必须由调用方传入 ``lark.Client`` 实例（来自 ``build_lark_client(endpoint``）
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from app.shared.tools.skills.feishu.MarkdownToCardConverter import (
    _RE_HEADING,
    _RE_FENCE,
    _RE_LIST,
    _RE_ORDERED_LIST,
    _RE_TABLE_ROW,
    _RE_TABLE_SEP,
)

logger = logging.getLogger(__name__)


# 飞书 docx block_type 常量（与 Open API 协议对齐，参考 lark-oapi v3_main）。
_BLOCK_TEXT = 2            # paragraph
_BLOCK_HEADING1 = 3
_BLOCK_HEADING2 = 4
_BLOCK_HEADING3 = 5
_BLOCK_BULLET = 12
_BLOCK_ORDERED = 13
_BLOCK_CODE = 14
_BLOCK_TABLE = 27

_TABLE_HEADER_BG = "BlueBackgroundColor"


# =============================================================================
# _md_to_blocks 模块级 helper（公共，公开以便测试）
# =============================================================================


def _rich_text(content: str) -> List[Dict[str, Any]]:
    """构造飞书 block 文本片段数组。

    Args:
        content: 原始文本内容

    Returns:
        list[dict]: 飞书 rich_text 元素数组（含一个 TextRun + 基础样式）
    """
    if not content:
        return [{"text_run": {"content": ""}}]
    return [
        {
            "text_run": {
                "content": content,
            }
        }
    ]


def _heading_block(level: int, content: str) -> Dict[str, Any]:
    """构造 heading 块。

    Args:
        level: 1/2/3
        content: 文本

    Returns:
        dict: heading block JSON
    """
    block_type_map = {1: "heading1", 2: "heading2", 3: "heading3"}
    field_name = block_type_map.get(level, "heading3")
    return {
        "block_type": _BLOCK_HEADING1 if level == 1 else (
            _BLOCK_HEADING2 if level == 2 else _BLOCK_HEADING3
        ),
        field_name: {
            "rich_text": _rich_text(content),
        },
    }


def _paragraph_block(content: str) -> Dict[str, Any]:
    """构造普通段落块。

    Args:
        content: 文本

    Returns:
        dict: paragraph block JSON
    """
    return {
        "block_type": _BLOCK_TEXT,
        "text": {
            "rich_text": _rich_text(content),
        },
    }


def _bullet_block(content: str) -> Dict[str, Any]:
    return {
        "block_type": _BLOCK_BULLET,
        "bullet": {
            "rich_text": _rich_text(content),
        },
    }


def _ordered_block(content: str, line_num: int) -> Dict[str, Any]:
    return {
        "block_type": _BLOCK_ORDERED,
        "ordered": {
            "rich_text": _rich_text(content),
            "line_number": line_num,
        },
    }


def _code_block(content: str, language: int = 1) -> Dict[str, Any]:
    """代码块。language 默认 1（plaintext），保留接口以便未来扩展。

    Args:
        content: 代码
        language: 飞书 code language 枚举（1=plaintext / 9=Python 等）
    """
    return {
        "block_type": _BLOCK_CODE,
        "code": {
            "rich_text": _rich_text(content),
            "language": language,
        },
    }


def _table_block(rows: List[List[str]]) -> Dict[str, Any]:
    """构造飞书表格 block（首行为表头，加粗背景色）。

    Args:
        rows: 二维数组，第一行视为表头

    Returns:
        dict: table block JSON（cell child 暂留空，由飞书 API 自动推断）
    """
    if not rows:
        raise ValueError("表格 rows 不能为空")
    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    children = []
    for r_idx, row in enumerate(rows):
        for c_idx in range(n_cols):
            cell_text = row[c_idx] if c_idx < len(row) else ""
            children.append({
                "block_type": 32,  # table_cell
                "table_cell": {
                    "rich_text": _rich_text(cell_text),
                },
            })
    return {
        "block_type": _BLOCK_TABLE,
        "table": {
            "property": {
                "row_size": n_rows,
                "column_size": n_cols,
                "header_row": True,
            },
            "children": children,
        },
    }


def _md_to_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """把 .md 文本解析为飞书 docx v1 block JSON 列表。

    支持语法（按优先级）：
        - ``# / ## / ###``  → heading1/2/3
        - 三反引号围栏 ``` → code block
        - ``| ... |`` + ``|---|---|`` 分隔行 → table
        - ``- xxx`` / ``* xxx`` → bullet
        - ``1. xxx`` / ``1) xxx`` → ordered
        - 其余非空行 → paragraph

    复用契约：复用 ``MarkdownToCardConverter`` 的正则常量，与项目内 md
    解析语义保持一致；若 Converter 未来加新正则，本 helper 必须同步评估
    是否支持。

    Args:
        markdown_text: 原始 markdown 文本

    Returns:
        list[dict]: 飞书 docx block JSON 列表
    """
    if not markdown_text or not markdown_text.strip():
        return []

    blocks: List[Dict[str, Any]] = []
    lines = markdown_text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 空行：跳过
        if not stripped:
            i += 1
            continue

        # 代码围栏
        if stripped.startswith("```"):
            lang = stripped.lstrip("`").strip() or "plaintext"
            i += 1
            code_lines: List[str] = []
            while i < n and not lines[i].lstrip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            # 跳过闭合 ```
            if i < n:
                i += 1
            blocks.append(_code_block("\n".join(code_lines), language=_lang_to_code(lang)))
            continue

        # 表格：连续两行匹配 _RE_TABLE_ROW + _RE_TABLE_SEP
        if (
            _RE_TABLE_ROW.match(line)
            and i + 1 < n
            and _RE_TABLE_SEP.match(lines[i + 1])
        ):
            header_cells = _parse_table_cells(line)
            n_cols = len(header_cells)
            row_list: List[List[str]] = [header_cells]
            j = i + 2
            while j < n and _RE_TABLE_ROW.match(lines[j]):
                cells = _parse_table_cells(lines[j])
                # 列数对齐：不足补空，多余截断
                if len(cells) < n_cols:
                    cells = cells + [""] * (n_cols - len(cells))
                elif len(cells) > n_cols:
                    cells = cells[:n_cols]
                row_list.append(cells)
                j += 1
            blocks.append(_table_block(row_list))
            i = j
            continue

        # 标题
        m_h = _RE_HEADING.match(line)
        if m_h:
            level = len(m_h.group(0).split()[0])  # "# " 数量
            level = max(1, min(level, 6))
            content = stripped.lstrip("#").strip()
            blocks.append(_heading_block(level, content))
            i += 1
            continue

        # 有序列表（必须匹配整段前缀，不能只匹配 1 字符——_RE_ORDERED_LIST 仅探测）
        m_o = _RE_ORDERED_LIST.match(line)
        if m_o:
            content = _strip_ordered_marker(line)
            if not content:
                blocks.append(_paragraph_block(line.strip()))
            else:
                blocks.append(_ordered_block(content, line_num=len(blocks)))
            i += 1
            continue

        # 无序列表（_RE_LIST 仅探测；用 _strip_bullet_marker 安全剥离前缀）
        m_l = _RE_LIST.match(line)
        if m_l:
            content = _strip_bullet_marker(line)
            if not content:
                blocks.append(_paragraph_block(line.strip()))
            else:
                blocks.append(_bullet_block(content))
            i += 1
            continue

        # 普通段落（合并连续非空行直到遇到空行/特殊标记）
        para_lines = [stripped]
        j = i + 1
        while j < n and lines[j].strip() and not (
            _RE_HEADING.match(lines[j])
            or _RE_LIST.match(lines[j])
            or _RE_ORDERED_LIST.match(lines[j])
            or lines[j].lstrip().startswith("```")
            or _RE_TABLE_ROW.match(lines[j])
        ):
            para_lines.append(lines[j].strip())
            j += 1
        blocks.append(_paragraph_block(" ".join(para_lines)))
        i = j

    return blocks


def _parse_table_cells(line: str) -> List[str]:
    """把 ``| a | b | c |`` 这种行切成单元格列表。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


def _strip_bullet_marker(line: str) -> str:
    """剥离无序列表前缀。

    注意：``MarkdownToCardConverter._RE_LIST`` 是「探测型」（只匹配 1 字符），
    因此不能用它直接 ``sub``——会把 ``- 苹果`` 中的「苹」误剥。

    Args:
        line: 原始行

    Returns:
        str: 剥离后的内容
    """
    stripped = line.lstrip()
    if stripped[:1] in {"-", "*", "+"} and len(stripped) >= 2 and stripped[1] in {" ", "\t"}:
        return stripped[2:].lstrip()
    return stripped


def _strip_ordered_marker(line: str) -> str:
    """剥离有序列表前缀（``1. xxx`` / ``2) yyy``）。

    Args:
        line: 原始行

    Returns:
        str: 剥离后的内容
    """
    import re as _re

    stripped = line.lstrip()
    m = _re.match(r"^(\d{1,2})[.)]\s+(.+)$", stripped)
    if m:
        return m.group(2).strip()
    return stripped


_LANG_NAME_TO_CODE = {
    "plaintext": 1,
    "text": 1,
    "python": 9,
    "py": 9,
    "javascript": 13,
    "js": 13,
    "typescript": 20,
    "ts": 20,
    "json": 22,
    "bash": 5,
    "shell": 5,
    "sh": 5,
    "sql": 27,
}


def _lang_to_code(name: str) -> int:
    """语言字符串 → 飞书 docx code block language 枚举。"""
    return _LANG_NAME_TO_CODE.get((name or "").lower().strip(), 1)


# =============================================================================
# FeishuDocxClient
# =============================================================================


class FeishuDocxClient:
    """飞书 docx v1 服务客户端。

    Attributes:
        _client: 已构造好的 ``lark.Client`` 实例（由调用方注入，
            通常来自 ``FeishuEndpointResolver.build_lark_client(endpoint``)
    """

    def __init__(self, lark_client):
        """初始化。

        Args:
            lark_client: ``lark.Client`` 实例；测试环境可注入 MagicMock。
        """
        self._client = lark_client

    async def create_document(
        self,
        title: str,
        folder_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建飞书 docx 文档。

        对应 ``POST /open-apis/docx/v1/documents``。

        Args:
            title: 文档标题（必填）
            folder_token: 飞书 drive 文件夹 token；为空则落到根目录

        Returns:
            dict: 成功 ``{"success": True, "document_id", "url"}``；
                失败 ``{"success": False, "error", "code"}``
        """
        try:
            from lark_oapi.api.docx.v1 import (
                CreateDocumentRequest,
                CreateDocumentRequestBody,
            )
            body = CreateDocumentRequestBody.builder().title(title)
            if folder_token:
                body = body.folder_token(folder_token)
            req = (
                CreateDocumentRequest.builder()
                .request_body(body.build())
                .build()
            )
            response = await asyncio.to_thread(self._client.docx.v1.document.create, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            document_id = getattr(response.data, "document_id", None) if response.data else None
            return {
                "success": True,
                "document_id": document_id,
                "url": _build_docx_url(document_id),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_docx_client] create_document 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def get_document_raw_content(self, document_id: str) -> Dict[str, Any]:
        """读取文档纯文本内容。

        对应 ``GET /open-apis/docx/v1/documents/{document_id}/raw_content``。

        Args:
            document_id: 文档 ID

        Returns:
            dict: 成功 ``{"success": True, "content"}``；失败同上
        """
        try:
            from lark_oapi.api.docx.v1 import GetDocumentRawContentRequest
            req = (
                GetDocumentRawContentRequest.builder()
                .document_id(document_id)
                .build()
            )
            response = await asyncio.to_thread(
                self._client.docx.v1.document_raw_content.get, req
            )
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            content = getattr(response.data, "content", "") if response.data else ""
            return {"success": True, "content": content or ""}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_docx_client] get_document_raw_content 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def list_blocks(self, document_id: str) -> Dict[str, Any]:
        """列出文档根 block 树。

        对应 ``GET /open-apis/docx/v1/documents/{document_id}/blocks``。
        注：当前仅实现根 block 列表，不展开分页（飞书 v1 接口默认 limit）。

        Args:
            document_id: 文档 ID

        Returns:
            dict: 成功 ``{"success": True, "blocks": list[dict]}``；
                失败同上
        """
        try:
            from lark_oapi.api.docx.v1 import ListDocumentBlocksRequest
            req = (
                ListDocumentBlocksRequest.builder()
                .document_id(document_id)
                .build()
            )
            response = await asyncio.to_thread(self._client.docx.v1.document_block.list, req)
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            items = getattr(response.data, "items", []) if response.data else []
            return {"success": True, "blocks": list(items)}
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_docx_client] list_blocks 失败: %s", e)
            return {"success": False, "error": str(e)}

    async def append_block_children(
        self,
        document_id: str,
        block_id: str,
        children: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """在指定 block 下追加子 block 列表。

        对应 ``POST /open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children``。

        Args:
            document_id: 文档 ID
            block_id: 父 block ID；通常是文档根 block_id
            children: block JSON 列表（来自 ``_md_to_blocks`` 或手工构造）

        Returns:
            dict: 成功 ``{"success": True, "children": list, "child_count"}``；
                失败同上
        """
        try:
            from lark_oapi.api.docx.v1 import (
                CreateDocumentBlockChildrenRequest,
                CreateDocumentBlockChildrenRequestBody,
            )
            body = (
                CreateDocumentBlockChildrenRequestBody.builder()
                .children(json.dumps(children, ensure_ascii=False))
                .build()
            )
            req = (
                CreateDocumentBlockChildrenRequest.builder()
                .document_id(document_id)
                .block_id(block_id)
                .request_body(body)
                .build()
            )
            response = await asyncio.to_thread(
                self._client.docx.v1.document_block_children.create, req
            )
            if not response.success():
                return {
                    "success": False,
                    "code": response.code,
                    "msg": response.msg,
                    "log_id": response.get_log_id(),
                }
            return {
                "success": True,
                "child_count": len(children),
                "response_data": getattr(response, "data", None),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[feishu_docx_client] append_block_children 失败: %s", e)
            return {"success": False, "error": str(e)}


def _build_docx_url(document_id: Optional[str]) -> Optional[str]:
    """构造飞书 docx URL（仅供前端用户访问，不能用于 ACL 校验）。"""
    if not document_id:
        return None
    return f"https://feishu.cn/docx/{document_id}"