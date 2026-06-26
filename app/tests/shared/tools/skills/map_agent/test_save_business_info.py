# -*- coding:utf-8 -*-
"""
save_business_info 工具测试

覆盖：
- 导入/存在性
- ToolRegistry 注册
- _validate_business_info 字段级验证（空值 / 手机号格式 / 长度超限）
- save_business_info 验证失败返回 validation_error Command

Date: 2026-06-26
Author: AI Assistant
"""

import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_save_business_info_importable():
    """
    P0: save_business_info 工具可导入且为 async 函数。
    """
    from app.shared.tools.skills.map_agent.MapTools import save_business_info
    import inspect

    assert save_business_info is not None
    assert inspect.iscoroutinefunction(save_business_info)


def test_save_business_info_input_model_importable():
    """
    P0: SaveBusinessInfoInput Pydantic 模型可导入，所有字段允许 None 默认值。
    """
    from app.shared.tools.skills.map_agent.MapTools import SaveBusinessInfoInput

    # 允许全部为空（验证在函数内手动执行）
    empty = SaveBusinessInfoInput()
    assert empty.project_name is None
    assert empty.unit_name is None
    assert empty.contact_person is None
    assert empty.contact_phone is None
    assert empty.unit_address is None

    # 正常赋值
    full = SaveBusinessInfoInput(
        project_name="某项目",
        unit_name="某单位",
        contact_person="张三",
        contact_phone="13800138000",
        unit_address="北京市朝阳区",
    )
    assert full.project_name == "某项目"
    assert full.contact_phone == "13800138000"


def test_save_business_info_registered():
    """
    P0: save_business_info 已注册到 ToolRegistry。
    """
    from app.shared.tools.skills.map_agent import MapTools  # noqa: F401
    from app.shared.tools.registry import ToolRegistry

    info = ToolRegistry._tools.get("save_business_info")
    assert info is not None, "save_business_info 未注册到 ToolRegistry"
    assert info["agent"] == "map_agent"


# ============================================================
# P1: 验证函数失败路径
# ============================================================


def test_validate_business_info_empty_fields():
    """
    P1: 5 字段全部为空时返回 5 条错误信息。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        SaveBusinessInfoInput,
        _validate_business_info,
    )

    empty = SaveBusinessInfoInput()
    errors = _validate_business_info(empty)

    assert len(errors) == 5, f"期望 5 条错误，实际 {len(errors)} 条"
    # 检查每条错误都提到对应字段名
    error_text = " ".join(errors)
    assert "project_name" in error_text
    assert "unit_name" in error_text
    assert "contact_person" in error_text
    assert "contact_phone" in error_text
    assert "unit_address" in error_text


def test_validate_business_info_phone_format():
    """
    P1: 非中国大陆手机号格式应返回错误。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        SaveBusinessInfoInput,
        _validate_business_info,
    )

    cases = [
        ("12345", True),               # 太短
        ("1380013800", True),          # 少一位
        ("138001380000", True),        # 多一位
        ("23800138000", True),         # 非法开头
        ("1380013800a", True),         # 含字母
        ("13800138000", False),        # 合法
        ("15912345678", False),        # 合法
    ]

    for phone, expect_error in cases:
        data = SaveBusinessInfoInput(
            project_name="项目",
            unit_name="单位",
            contact_person="张三",
            contact_phone=phone,
            unit_address="地址",
        )
        errors = _validate_business_info(data)
        has_phone_error = any("contact_phone" in e for e in errors)
        assert has_phone_error == expect_error, \
            f"phone='{phone}' 期望错误={expect_error}，实际 has_phone_error={has_phone_error}"


def test_validate_business_info_length_exceeds():
    """
    P1: 字段长度超限时返回错误。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        SaveBusinessInfoInput,
        _validate_business_info,
    )

    # project_name > 200 字符
    too_long_name = "x" * 201
    data = SaveBusinessInfoInput(
        project_name=too_long_name,
        unit_name="单位",
        contact_person="张三",
        contact_phone="13800138000",
        unit_address="地址",
    )
    errors = _validate_business_info(data)
    assert any("project_name" in e and "200" in e for e in errors), \
        "project_name 长度超限应报错"


def test_validate_business_info_valid_passes():
    """
    P1: 合法输入返回空错误列表。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        SaveBusinessInfoInput,
        _validate_business_info,
    )

    data = SaveBusinessInfoInput(
        project_name="沈阳某高速公路项目",
        unit_name="沈阳某建设有限公司",
        contact_person="张三",
        contact_phone="13800138000",
        unit_address="沈阳市浑南区某路100号",
    )
    errors = _validate_business_info(data)
    assert errors == [], f"合法输入不应有错误，实际: {errors}"


# ============================================================
# P1: 工具失败路径
# ============================================================


def test_save_business_info_validation_error_command():
    """
    P1: 验证失败时返回 status=validation_error 的 Command。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        save_business_info,
        SaveBusinessInfoInput,
    )
    from langgraph.types import Command

    rt = MagicMock()
    rt.tool_call_id = "call_biz"
    rt.context = {"session_id": "s1"}
    rt.state = {}

    data = SaveBusinessInfoInput()  # 全部为空，验证必失败
    result = asyncio.run(save_business_info(data, rt))

    assert isinstance(result, Command)
    assert "business_info" in result.update
    biz_data = result.update["business_info"]
    assert biz_data["status"] == "validation_error"
    # message 应包含字段修正提示
    assert "project_name" in biz_data["message"]
    assert "13800138000" in biz_data["message"]


def test_save_business_info_uses_db_when_enabled():
    """
    P1: 当 DatabasePool.is_enabled() 为 True 时调用数据库原子 Upsert 生成编号。
    """
    from app.shared.tools.skills.map_agent.MapTools import (
        save_business_info,
        SaveBusinessInfoInput,
    )
    from langgraph.types import Command

    rt = MagicMock()
    rt.tool_call_id = "call_biz_ok"
    rt.context = {"session_id": "s_ok"}
    rt.state = {}

    valid_data = SaveBusinessInfoInput(
        project_name="测试项目",
        unit_name="测试单位",
        contact_person="李四",
        contact_phone="13912345678",
        unit_address="北京市海淀区中关村大街1号",
    )

    with patch("app.shared.tools.skills.map_agent.MapTools.DatabasePool") as MockDB:
        MockDB.is_enabled.return_value = True

        # Mock 异步 fetchrow 返回 business_no=1
        async def fake_fetchrow(*args, **kwargs):
            return {"current_seq": 7}

        async def fake_execute(*args, **kwargs):
            return None

        MockDB.fetchrow = fake_fetchrow
        MockDB.execute = fake_execute

        result = asyncio.run(save_business_info(valid_data, rt))

    assert isinstance(result, Command)
    biz_data = result.update["business_info"]
    assert biz_data["status"] == "saved"
    # 业务编号格式：YDT + YYYYMMDD + 0007
    assert biz_data["business_no"].startswith("YDT")
    assert biz_data["business_no"].endswith("0007")
