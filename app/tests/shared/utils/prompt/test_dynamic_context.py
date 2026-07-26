# -*- coding:utf-8 -*-
"""
dynamic_context 动态上下文提示词模块测试

测试目标：
    - normalize_attachment_path：Windows 盘符剥离、反斜杠转换、Linux 路径原样保留
    - resolve_prompt_path：与 normalize 互逆的跨平台反向解析
    - sanitize_dynamic_nodes：白名单字段、长度/条数上限、非法项静默丢弃
    - build_dynamic_context_xml：<attachments> / 动态节点 构建、空状态显式化、属性转义
    - build_dynamic_system_suffix：以 attachments 表为事实源组装后缀、异常降级、动态节点注入
    - AgentContext / _BASE_CONTEXT_DEFAULTS 契约一致性（dynamic_context_suffix + referenced_servers）

Date: 2026-07-24 / 2026-07-26
Author: AI Assistant
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

import pytest

from app.core.agent.AgentContext import AgentContext
from app.core.config.paths import _PROJECT_ROOT
from app.shared.utils.agent.dynamic_schema import _BASE_CONTEXT_DEFAULTS
from app.shared.utils.prompt.dynamic_context import (
    DYNAMIC_CONTEXT_RULES,
    DYNAMIC_NODE_REGISTRY,
    build_dynamic_context_xml,
    build_dynamic_system_suffix,
    normalize_attachment_path,
    resolve_prompt_path,
    sanitize_dynamic_nodes,
    _format_size,
    _format_uploaded_at,
)


# ============================================================
# normalize_attachment_path
# ============================================================


def test_normalize_attachment_path_windows_backslash_strips_drive():
    """Windows 反斜杠绝对路径应剥离盘符并转正斜杠。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert normalize_attachment_path(r"E:\a\b\x.md") == "/a/b/x.md"


def test_normalize_attachment_path_windows_forward_slash_strips_drive():
    """Windows 正斜杠带盘符路径（如 c:/a.md）应剥离盘符。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert normalize_attachment_path("c:/a.md") == "/a.md"


def test_normalize_attachment_path_linux_absolute_kept():
    """Linux 绝对路径已是 / 开头，应原样保留。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert normalize_attachment_path("/data/tmp/upload/x.md") == "/data/tmp/upload/x.md"


def test_normalize_attachment_path_empty_returns_empty():
    """空路径输入应返回空字符串，不抛异常。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert normalize_attachment_path("") == ""
    assert normalize_attachment_path(None) == ""


# ============================================================
# resolve_prompt_path
# ============================================================


def test_resolve_prompt_path_empty_raises():
    """空路径应抛出 ValueError。

    参数:
        无

    返回:
        无

    异常:
        pytest.raises(ValueError): prompt_path 为空字符串或 None
    """
    with pytest.raises(ValueError):
        resolve_prompt_path("")
    with pytest.raises(ValueError):
        resolve_prompt_path(None)


def test_resolve_prompt_path_posix_absolute_returned_as_is():
    """Linux 下 / 开头路径本身即绝对路径，应原样返回。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    if os.name == "nt":
        pytest.skip("仅 Linux 行为")
    result = resolve_prompt_path("/data/tmp/upload/x.md")
    assert result == Path("/data/tmp/upload/x.md")


def test_resolve_prompt_path_windows_prepends_project_drive():
    """Windows 下无盘符 / 开头路径应补项目根所在盘符（如 /a.md → E:\\a.md）。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    if os.name != "nt":
        pytest.skip("仅 Windows 行为")
    drive = Path(_PROJECT_ROOT).drive
    result = resolve_prompt_path("/a.md")
    assert str(result).replace("/", "\\") == f"{drive}\\a.md"


def test_resolve_prompt_path_windows_drive_path_returned_as_is():
    """Windows 下带盘符绝对路径应原样返回。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    if os.name != "nt":
        pytest.skip("仅 Windows 行为")
    result = resolve_prompt_path(r"E:\a\b\x.md")
    assert result == Path(r"E:\a\b\x.md")


# ============================================================
# 格式化辅助函数
# ============================================================


def test_format_size_human_readable():
    """字节数应格式化为人类可读单位。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert _format_size(0) == "0B"
    assert _format_size(512) == "512B"
    assert _format_size(560 * 1024) == "560KB"
    assert _format_size(int(2.3 * 1024 * 1024)) == "2.3MB"
    assert _format_size(None) == "0B"
    assert _format_size("非法值") == "0B"


def test_format_uploaded_at_date_string():
    """创建时间应格式化为 YYYY-MM-DD。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert _format_uploaded_at(datetime(2026, 7, 24, 10, 30)) == "2026-07-24"
    assert _format_uploaded_at("2026-07-24T10:30:00") == "2026-07-24"
    assert _format_uploaded_at(None) == ""


# ============================================================
# build_dynamic_context_xml
# ============================================================


def test_build_xml_empty_state_explicit_nodes():
    """空附件 / 空服务器时应输出显式空节点，而不是省略节点。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    xml = build_dynamic_context_xml([], None)
    assert "<attachments>" in xml
    assert "</attachments>" in xml
    assert "<servers>" in xml
    assert "</servers>" in xml
    assert "<file " not in xml
    assert "<server " not in xml


def test_build_xml_renders_attachment_entries():
    """附件记录应渲染为 <file> 元素，路径经 normalize 规范化。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    attachments = [
        {
            "file_name": "需求文档.docx",
            "stored_path": r"E:\proj\data\tmp\upload\2026\07\24\sid\x.md",
            "file_size": 560 * 1024,
            "created_at": datetime(2026, 7, 24),
        }
    ]
    xml = build_dynamic_context_xml(attachments)
    assert 'name="需求文档.docx"' in xml
    assert 'path="/proj/data/tmp/upload/2026/07/24/sid/x.md"' in xml
    assert 'size="560KB"' in xml
    assert 'uploaded_at="2026-07-24"' in xml


def test_build_xml_escapes_special_chars():
    """文件名中的 XML 特殊字符应被转义，防止节点结构被破坏。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    attachments = [
        {
            "file_name": 'a"<b>&c.md',
            "stored_path": "/data/x.md",
            "file_size": 1,
            "created_at": None,
        }
    ]
    xml = build_dynamic_context_xml(attachments)
    assert 'a"<b>&c.md' not in xml
    assert "&quot;" in xml or "&lt;" in xml


def test_build_xml_renders_dynamic_nodes_entries():
    """dynamic_nodes 参数应渲染注册表中已声明节点类型的子元素（2026-07-26 重构契约）。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    xml = build_dynamic_context_xml(
        [],
        {"referenced_servers": [{"name": "prod-api", "server_type": "linux"}]},
    )
    assert '<server name="prod-api" server_type="linux" />' in xml


# ============================================================
# sanitize_dynamic_nodes
# ============================================================


def test_sanitize_keeps_whitelisted_fields_only():
    """sanitize 应仅保留白名单字段，丢弃 ip / password 等其它键。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    result = sanitize_dynamic_nodes({
        "referenced_servers": [
            {"name": "prod-api", "server_type": "linux", "ip": "1.2.3.4", "password": "x"},
        ],
    })
    assert result == {"referenced_servers": [{"name": "prod-api", "server_type": "linux"}]}


def test_sanitize_drops_items_missing_name():
    """缺 name 或 name 为空串的元素应被静默丢弃。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    result = sanitize_dynamic_nodes({
        "referenced_servers": [
            {"server_type": "linux"},            # 缺 name
            {"name": "", "server_type": "linux"},  # name 空串
            {"name": "   ", "server_type": "linux"},  # name 仅空白
            {"name": "ok", "server_type": "linux"},
        ],
    })
    assert result == {"referenced_servers": [{"name": "ok", "server_type": "linux"}]}


def test_sanitize_caps_item_count():
    """超出 max_items 的元素应被截断。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    items = [{"name": f"srv-{i}", "server_type": "linux"} for i in range(60)]
    result = sanitize_dynamic_nodes({"referenced_servers": items})
    assert len(result["referenced_servers"]) == 50  # DynamicNodeSpec 默认 max_items


def test_sanitize_caps_field_length():
    """字段值超过 max_field_len 应被截断。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    long_name = "a" * 200
    result = sanitize_dynamic_nodes({
        "referenced_servers": [{"name": long_name, "server_type": "linux"}],
    })
    assert len(result["referenced_servers"][0]["name"]) == 128


def test_sanitize_drops_non_dict_items():
    """非 dict 元素（如字符串 / None）应被丢弃，不抛错。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    result = sanitize_dynamic_nodes({
        "referenced_servers": [
            "string-item",
            None,
            123,
            {"name": "valid", "server_type": "linux"},
        ],
    })
    assert result == {"referenced_servers": [{"name": "valid", "server_type": "linux"}]}


def test_sanitize_ignores_unregistered_keys():
    """未在 DYNAMIC_NODE_REGISTRY 中声明的 overrides 键应被忽略。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    result = sanitize_dynamic_nodes({
        "unregistered_key": [{"name": "x", "server_type": "linux"}],
        "referenced_servers": [{"name": "ok", "server_type": "linux"}],
    })
    assert "unregistered_key" not in result
    assert result["referenced_servers"] == [{"name": "ok", "server_type": "linux"}]


def test_sanitize_handles_empty_or_missing():
    """空 overrides / None / 空列表 / 缺键应安全返回空字典，不抛错。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert sanitize_dynamic_nodes(None) == {}
    assert sanitize_dynamic_nodes({}) == {}
    assert sanitize_dynamic_nodes({"referenced_servers": []}) == {}
    assert sanitize_dynamic_nodes({"referenced_servers": "not-a-list"}) == {}


def test_dynamic_node_registry_contains_referenced_servers():
    """DYNAMIC_NODE_REGISTRY 应至少声明 referenced_servers 条目（契约锚点）。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    keys = {spec.overrides_key for spec in DYNAMIC_NODE_REGISTRY}
    assert "referenced_servers" in keys


# ============================================================
# XML 动态节点：未传 dynamic_nodes 时也输出显式空节点
# ============================================================


def test_build_xml_empty_dynamic_nodes_still_explicit():
    """未传 dynamic_nodes（None）时，注册表中所有节点仍输出显式空节点。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    xml = build_dynamic_context_xml([], None)
    assert "<servers>" in xml
    assert "</servers>" in xml
    assert "<server " not in xml


# ============================================================
# build_dynamic_system_suffix
# ============================================================


def test_build_suffix_includes_rules_and_xml(monkeypatch):
    """后缀应包含静态规则文本与附件 XML 节点。

    参数:
        monkeypatch: pytest monkeypatch fixture，用于替换 AttachmentDB 查询

    返回:
        无（断言失败时抛出 AssertionError）
    """
    from app.shared.utils.files.attachment_db import AttachmentDB

    async def fake_get(session_id):
        return [
            {
                "file_name": "季度财报.pdf",
                "stored_path": "/data/tmp/upload/2026/07/20/sid/report.md",
                "file_size": 1024,
                "created_at": datetime(2026, 7, 20),
            }
        ]

    monkeypatch.setattr(AttachmentDB, "get_session_attachments", staticmethod(fake_get))

    suffix = asyncio.run(build_dynamic_system_suffix("sid"))
    assert DYNAMIC_CONTEXT_RULES in suffix
    assert 'name="季度财报.pdf"' in suffix
    assert 'path="/data/tmp/upload/2026/07/20/sid/report.md"' in suffix
    assert "<servers>" in suffix


def test_build_suffix_empty_attachments_explicit_empty_node(monkeypatch):
    """无附件时后缀仍包含显式空 <attachments> 节点。

    参数:
        monkeypatch: pytest monkeypatch fixture

    返回:
        无（断言失败时抛出 AssertionError）
    """
    from app.shared.utils.files.attachment_db import AttachmentDB

    async def fake_get(session_id):
        return []

    monkeypatch.setattr(AttachmentDB, "get_session_attachments", staticmethod(fake_get))

    suffix = asyncio.run(build_dynamic_system_suffix("sid"))
    assert "<attachments>\n</attachments>" in suffix


def test_build_suffix_query_failure_degrades_to_empty(monkeypatch):
    """附件查询异常时应降级为空列表，不向上抛异常。

    参数:
        monkeypatch: pytest monkeypatch fixture

    返回:
        无（断言失败时抛出 AssertionError）
    """
    from app.shared.utils.files.attachment_db import AttachmentDB

    async def fake_get(session_id):
        raise RuntimeError("DB 连接失败")

    monkeypatch.setattr(AttachmentDB, "get_session_attachments", staticmethod(fake_get))

    suffix = asyncio.run(build_dynamic_system_suffix("sid"))
    assert "<attachments>\n</attachments>" in suffix


# ============================================================
# AgentContext / dynamic_schema 契约一致性
# ============================================================


def test_dynamic_context_suffix_declared_in_agent_context():
    """AgentContext 基类应声明 dynamic_context_suffix 字段。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert "dynamic_context_suffix" in AgentContext.__annotations__


def test_dynamic_context_suffix_in_base_context_defaults():
    """_BASE_CONTEXT_DEFAULTS 应包含 dynamic_context_suffix 兜底默认空串。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert _BASE_CONTEXT_DEFAULTS.get("dynamic_context_suffix") == ""


def test_referenced_servers_declared_in_agent_context():
    """AgentContext 基类应声明 referenced_servers 字段（2026-07-26 新增契约）。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert "referenced_servers" in AgentContext.__annotations__


def test_referenced_servers_in_base_context_defaults():
    """_BASE_CONTEXT_DEFAULTS 应包含 referenced_servers 兜底默认空列表。

    参数:
        无

    返回:
        无（断言失败时抛出 AssertionError）
    """
    assert _BASE_CONTEXT_DEFAULTS.get("referenced_servers") == []


# ============================================================
# build_dynamic_system_suffix：dynamic_nodes 端到端注入
# ============================================================


def test_build_suffix_renders_referenced_servers_xml(monkeypatch):
    """build_dynamic_system_suffix 传入 dynamic_nodes 后应将 referenced_servers 渲染进 suffix XML。

    参数:
        monkeypatch: pytest monkeypatch fixture，替换 AttachmentDB 查询返回空附件

    返回:
        无（断言失败时抛出 AssertionError）
    """
    from app.shared.utils.files.attachment_db import AttachmentDB

    async def fake_get(session_id):
        return []

    monkeypatch.setattr(AttachmentDB, "get_session_attachments", staticmethod(fake_get))

    suffix = asyncio.run(build_dynamic_system_suffix(
        "sid",
        dynamic_nodes={"referenced_servers": [{"name": "prod-api", "server_type": "linux"}]},
    ))
    assert '<server name="prod-api" server_type="linux" />' in suffix


def test_build_suffix_without_dynamic_nodes_explicit_empty(monkeypatch):
    """build_dynamic_system_suffix 不传 dynamic_nodes 时应输出显式空 servers 节点。

    参数:
        monkeypatch: pytest monkeypatch fixture

    返回:
        无（断言失败时抛出 AssertionError）
    """
    from app.shared.utils.files.attachment_db import AttachmentDB

    async def fake_get(session_id):
        return []

    monkeypatch.setattr(AttachmentDB, "get_session_attachments", staticmethod(fake_get))

    suffix = asyncio.run(build_dynamic_system_suffix("sid"))
    assert "<servers>\n</servers>" in suffix
