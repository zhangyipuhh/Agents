#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
动态上下文提示词模块

负责把会话的运行时状态（用户上传附件列表、用户通过 `#` 等触发键引用的服务器 /
未来其它引用对象）拼接到系统提示词末尾，供两个 chat 入口
（/api/agent/chat、/api/knowledge-chat）统一调用。

设计要点：
    1. 以 attachments 表为唯一事实源，每轮对话实时查询拼接，
       上传/删除附件后下一轮自动同步，不依赖前端请求体中的附件数组。
    2. 动态节点（<attachments> / <servers> / ...）追加在系统提示词末尾，利用近因效应。
    3. **每个节点独立判断，节点数据为空则整段不输出**（2026-08-23 落地）：
       attachments 与注册表节点（如 <servers>）的渲染决策互不影响，
       数据为空 → 不输出该节点的 XML 标签 + 不输出配套的静态规则文本。
       该规则对所有 DynamicNodeSpec（含未来 @ 知识库等）通用，详见
       memory/auth.md "动态节点渲染通用契约" 章节。
    4. 路径跨平台：注入提示词的路径统一为 POSIX 风格且剥离 Windows 盘符
       （如 ``E:\\a\\b.md`` → ``/a/b.md``）；读取侧通过
       :func:`resolve_prompt_path` 反向解析回当前平台可访问的路径。
    5. **注册表驱动的可扩展架构（2026-07-26 新增）**：
       ``DYNAMIC_NODE_REGISTRY`` 声明每类动态节点的「前端 overrides 键 → XML 结构
       与清洗规则」映射；前端 ``triggerRegistry`` 与本表镜像对称，
       未来新增引用类型（如 ``@`` 知识库）只需注册 ``DynamicNodeSpec`` 一条，
       :func:`build_dynamic_system_suffix` 与 :func:`build_dynamic_context_xml`
       签名不变。

Date: 2026-07-24 / 2026-07-26 / 2026-08-23
Author: AI Assistant
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from xml.sax.saxutils import quoteattr

from app.core.config.paths import _PROJECT_ROOT

logger = logging.getLogger(__name__)

# Windows 盘符前缀（如 "E:" / "c:"）
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

# -----------------------------------------------------------------------------
# 注册表驱动：动态节点契约
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class DynamicNodeSpec:
    """单个动态节点的契约定义。

    Attributes:
        overrides_key: 前端 ``context_overrides`` 中的键名（如 ``referenced_servers``），
            router 层会从 overrides 中按此键提取原始列表并喂给 :func:`sanitize_dynamic_nodes`
        xml_parent_tag: 渲染出的 XML 父节点名（如 ``servers``）
        xml_item_tag: 渲染出的 XML 子节点名（如 ``server``）
        allowed_fields: 元素允许保留的字段白名单（如 ``("name", "server_type")``），
            sanitize 时不在白名单中的键被丢弃
        max_items: 单节点最多允许的元素条数（超出截断）
        max_field_len: 元素每个字段值的最大字符长度（超出截断）
    """
    overrides_key: str
    xml_parent_tag: str
    xml_item_tag: str
    allowed_fields: Tuple[str, ...]
    max_items: int = 50
    max_field_len: int = 128


# 注册表：未来新增类型（如 "@知识库"）在此追加一条 DynamicNodeSpec 即可
DYNAMIC_NODE_REGISTRY: Tuple[DynamicNodeSpec, ...] = (
    DynamicNodeSpec(
        overrides_key="referenced_servers",
        xml_parent_tag="servers",
        xml_item_tag="server",
        allowed_fields=("name", "server_type"),
    ),
)


def sanitize_dynamic_nodes(
    overrides: Optional[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """根据 :data:`DYNAMIC_NODE_REGISTRY` 清洗 ``context_overrides`` 中的动态节点数据。

    清洗规则（防提示词膨胀与脏数据）：
        - 仅处理注册表中声明的 overrides_key；
        - 每条元素仅保留白名单字段，其余键丢弃；
        - 每个字段值做类型检查（必须 str）+ 长度截断（<= max_field_len）；
        - 元素条数 <= max_items，超出截断；
        - 任何非法元素（非 dict / name 缺失或空串）**静默丢弃**，不抛错。

    参数:
        overrides: 原始 ``context_overrides`` 字典（可含其它业务键，本函数只抽取注册节点）

    返回:
        Dict[str, list[dict]]: 键为 ``overrides_key``，值为清洗后的元素列表；
        未注册的键不出现在返回值中。未引用任何动态节点时返回空字典。
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    if not overrides:
        return result
    for spec in DYNAMIC_NODE_REGISTRY:
        raw = overrides.get(spec.overrides_key)
        if not raw or not isinstance(raw, list):
            continue
        cleaned: List[Dict[str, Any]] = []
        for item in raw[: spec.max_items]:
            if not isinstance(item, dict):
                continue
            sanitized: Dict[str, Any] = {}
            for key in spec.allowed_fields:
                value = item.get(key)
                if not isinstance(value, str):
                    continue
                value = value.strip()
                if not value:
                    continue
                if len(value) > spec.max_field_len:
                    value = value[: spec.max_field_len]
                sanitized[key] = value
            if "name" in spec.allowed_fields and not sanitized.get("name"):
                continue
            if sanitized:
                cleaned.append(sanitized)
        if cleaned:
            result[spec.overrides_key] = cleaned
    return result


# -----------------------------------------------------------------------------
# 静态规则文本
# -----------------------------------------------------------------------------

ATTACHMENTS_RULES = (
    "用户上传的附件列在 <attachments> 节点中。当用户询问附件内容时，"
    "必须使用该节点中列出的 path 调用 read_file 工具，禁止凭记忆或猜测编造文件名和内容。"
    "若 <attachments> 为空或其中没有用户所指的文件，直接告知用户没有该附件，不要假装读取。"
)
"""<attachments> 节点使用规则；仅在 attachments 非空时拼入后缀。"""

SERVERS_RULES = (
    "<servers> 节点列出用户通过 `#` 触发的引用项；name 字段即 DevOpsServerService 的 "
    "business_name（也是 SSH / 巡检工具的入参）。当用户要求对其中服务器执行操作时，"
    "请优先使用该节点列出的 name 调用工具；若节点为空或不含对应服务器，明确告知用户未引用。"
)
"""<servers> 节点使用规则；仅在 servers 非空时拼入后缀。"""

# 2026-08-23 后，运行时仅使用 ATTACHMENTS_RULES / SERVERS_RULES。
# DYNAMIC_CONTEXT_RULES 保留作为历史快照（两者拼接），仅供文档引用，
# 不参与 build_dynamic_system_suffix 的实际注入。
DYNAMIC_CONTEXT_RULES = f"{ATTACHMENTS_RULES}\n\n{SERVERS_RULES}"
"""<attachments> / <servers> 节点的静态使用规则汇总（历史快照）；2026-08-23 后运行时不再使用。"""


# -----------------------------------------------------------------------------
# 路径工具
# -----------------------------------------------------------------------------

def normalize_attachment_path(stored_path: str) -> str:
    """把任意平台的存储路径规范化为注入提示词用的 POSIX 风格路径。

    规则：
        - 反斜杠统一替换为正斜杠；
        - 剥离 Windows 盘符（``E:\\a\\b.md`` / ``c:/a.md` → ``/a/b.md``）；
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


# -----------------------------------------------------------------------------
# XML 构建
# -----------------------------------------------------------------------------

def build_dynamic_context_xml(
    attachments: Optional[List[Dict[str, Any]]] = None,
    dynamic_nodes: Optional[Mapping[str, List[Dict[str, Any]]]] = None,
) -> str:
    """构建 <attachments> / 动态节点 XML 片段。

    行为（2026-08-23 调整）：每个节点独立判断是否渲染。
    - attachments 非空 → 输出 ``<attachments>...</attachments>``；反之不输出。
    - 注册表中每个 ``DynamicNodeSpec`` 独立判断：对应 ``overrides_key`` 解析后
      非空 → 输出该节点的 XML 块；反之不输出。
    - 所有节点都空时返回 ``""``。

    该行为受 memory/auth.md "动态节点渲染通用契约" 约束，对所有 DynamicNodeSpec
    （含未来 @ 知识库等）通用。

    参数:
        attachments: 附件记录列表（attachments 表行字典，需含
            file_name / stored_path / file_size / created_at 键）
        dynamic_nodes: 已 sanitize 的动态节点字典，键为 ``overrides_key``，
            值为元素列表；未注册键不会出现。

    返回:
        str: 仅包含非空节点的 XML 片段，节点之间用 ``\\n`` 自然分隔；
        所有节点都空时返回 ``""``。形如::

            <attachments>
              <file name="..." path="..." size="..." uploaded_at="..." />
            </attachments>
            <servers>
              <server name="prod-api" server_type="linux" />
            </servers>
    """
    blocks: List[str] = []

    # attachments 块：仅 attachments 非空时输出（独立判断）
    if attachments:
        att_lines: List[str] = ["<attachments>"]
        for att in attachments:
            name = quoteattr(str(att.get("file_name") or ""))
            path = quoteattr(normalize_attachment_path(att.get("stored_path") or ""))
            size = quoteattr(_format_size(att.get("file_size")))
            uploaded_at = quoteattr(_format_uploaded_at(att.get("created_at")))
            att_lines.append(
                f"  <file name={name} path={path} size={size} uploaded_at={uploaded_at} />"
            )
        att_lines.append("</attachments>")
        blocks.append("\n".join(att_lines))

    # 注册表节点块：每个节点独立判断，非空才输出对应标签（互不影响）
    for spec in DYNAMIC_NODE_REGISTRY:
        nodes = (dynamic_nodes or {}).get(spec.overrides_key) or []
        if not nodes:
            continue  # 此节点空 → 不输出（不影响其它节点）
        node_lines: List[str] = [f"<{spec.xml_parent_tag}>"]
        for item in nodes:
            attrs = " ".join(
                f"{key}={quoteattr(str(item.get(key) or ''))}"
                for key in spec.allowed_fields
            )
            node_lines.append(f"  <{spec.xml_item_tag} {attrs} />")
        node_lines.append(f"</{spec.xml_parent_tag}>")
        blocks.append("\n".join(node_lines))

    return "\n".join(blocks)


async def build_dynamic_system_suffix(
    session_id: str,
    dynamic_nodes: Optional[Mapping[str, List[Dict[str, Any]]]] = None,
) -> str:
    """构建追加到系统提示词末尾的动态上下文后缀（静态规则 + XML 节点）。

    行为（2026-08-23 调整）：每个节点独立渲染，各带规则段。
    - attachments 非空 → 输出 ``ATTACHMENTS_RULES + \\n\\n + attachments XML 块``
    - 注册表节点非空 → 输出 ``SERVERS_RULES + \\n\\n + 该节点 XML 块``
    - 两者都空 → 返回 ``""``。
    - 两者都非空 → 两段独立拼接，各带规则段，前后排列（attachments 在前）。

    以 attachments 表为唯一事实源，按 session_id 实时查询附件列表；
    数据库未启用（Memory 模式）或查询异常时降级为空附件列表。

    参数:
        session_id: 会话 ID
        dynamic_nodes: 已通过 :func:`sanitize_dynamic_nodes` 清洗过的动态节点字典；
            传入空 dict 表示「无任何引用」。

    返回:
        str: 仅包含非空节点的规则段 + XML 片段；所有节点都空时返回 ``""``。
        形如::

            用户上传的附件列在 <attachments> 节点中。...
            <attachments>
              <file name="..." path="..." size="..." uploaded_at="..." />
            </attachments>

            <servers> 节点列出用户通过 `#` 触动的引用项；...
            <servers>
              <server name="..." server_type="..." />
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

    # 独立判断：attachments 与注册表节点的渲染决策互不影响
    has_attachments = bool(attachments)
    # 注册表节点逐个判断，任一非空 → 触发对应规则 + XML 输出
    has_any_dynamic = any(
        (dynamic_nodes or {}).get(spec.overrides_key)
        for spec in DYNAMIC_NODE_REGISTRY
    )

    # 两者都空 → 返回空字符串，无任何拼接
    if not has_attachments and not has_any_dynamic:
        return ""

    blocks: List[str] = []

    # attachments 段：仅在 attachments 非空时独立拼接（自带规则）
    if has_attachments:
        att_xml_lines: List[str] = ["<attachments>"]
        for att in attachments:
            name = quoteattr(str(att.get("file_name") or ""))
            path = quoteattr(normalize_attachment_path(att.get("stored_path") or ""))
            size = quoteattr(_format_size(att.get("file_size")))
            uploaded_at = quoteattr(_format_uploaded_at(att.get("created_at")))
            att_xml_lines.append(
                f"  <file name={name} path={path} size={size} uploaded_at={uploaded_at} />"
            )
        att_xml_lines.append("</attachments>")
        blocks.append(f"{ATTACHMENTS_RULES}\n\n" + "\n".join(att_xml_lines))

    # 注册表节点段：每个节点独立判断，非空才拼接（自带规则）
    for spec in DYNAMIC_NODE_REGISTRY:
        nodes = (dynamic_nodes or {}).get(spec.overrides_key) or []
        if not nodes:
            continue
        node_xml_lines: List[str] = [f"<{spec.xml_parent_tag}>"]
        for item in nodes:
            attrs = " ".join(
                f"{key}={quoteattr(str(item.get(key) or ''))}"
                for key in spec.allowed_fields
            )
            node_xml_lines.append(f"  <{spec.xml_item_tag} {attrs} />")
        node_xml_lines.append(f"</{spec.xml_parent_tag}>")
        node_xml = "\n".join(node_xml_lines)
        # 配套规则：当前仅 servers 类型
        # 未来新增 DynamicNodeSpec 时，需在此分支注册对应的规则常量
        if spec.xml_parent_tag == "servers":
            blocks.append(f"{SERVERS_RULES}\n\n{node_xml}")
        else:
            # 兜底：未注册规则的节点只输出 XML，不附带规则文本
            blocks.append(node_xml)

    return "\n\n".join(blocks)