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
    P0: save_business_info 经 LangChain @tool 装饰器注册。

    迁移说明：2026-06-26 之前使用 `@register_tool(name=..., agent="map_agent", description=...)`
    强制工具归属 map_agent；迁移后改为 LangChain `@tool(description=...)` 单装饰器，
    description 文本沿用开发者向 LLM 的详细提示（含字段必填说明），归属由 DB `tools.tool_bindings` 控制。

    测试策略：AST 静态解析源码（不依赖运行时装饰器行为，因为 conftest.py
    在测试环境下把 langchain.tools.tool 替换为 identity 装饰器）。
    """
    import ast
    from pathlib import Path

    # test_save_business_info.py 位于 app/tests/shared/tools/skills/map_agent/
    # parents[5] 跳到 app/，再加 shared/tools/skills/map_agent/MapTools.py
    map_tools_path = (
        Path(__file__).resolve().parents[5]
        / "shared" / "tools" / "skills" / "map_agent" / "MapTools.py"
    )
    tree = ast.parse(map_tools_path.read_text(encoding="utf-8"))

    func_node = None
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "save_business_info":
            func_node = node
            break
    assert func_node is not None, "MapTools.save_business_info 函数不存在"

    has_tool_decorator = False
    has_description = False
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Call):
            func_name = (
                dec.func.id
                if isinstance(dec.func, ast.Name)
                else dec.func.attr
                if isinstance(dec.func, ast.Attribute)
                else None
            )
            if func_name == "tool":
                has_tool_decorator = True
                for kw in dec.keywords:
                    if kw.arg == "description":
                        # 支持三引号多行字符串（ast.Constant 字面量）
                        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            assert "保存业务信息" in kw.value.value
                            has_description = True
                            break

    assert has_tool_decorator, "save_business_info 缺少 @tool 装饰器"
    assert has_description, "save_business_info 的 @tool 装饰器缺少 description 参数"


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
