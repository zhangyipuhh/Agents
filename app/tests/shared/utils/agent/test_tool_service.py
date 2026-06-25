# -*- coding:utf-8 -*-
"""
ToolRegistryService 测试模块

验证工具注册中心服务的核心功能：
1. JSONB 防御性反序列化（_decode_jsonb / _decode_row）
2. 读方法优先读缓存、缓存未命中回退 DB（list_tools / get_tool_by_name / get_tools_by_names）
3. 写方法写 DB 后同步刷新/失效缓存（create_tool / update_tool / delete_tool / set_tool_enabled）
4. ast 扫描识别 @tool 装饰函数（_has_tool_decorator / _extract_args_schema / _scan_file_for_tools）
5. 缓存管理方法（_refresh_cache / _invalidate_cache / _clear_cache）
6. preload_all 动态导入 + DB 关联 + 缓存构建
"""
import asyncio
import ast
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.shared.utils.agent.tool_service import (
    ToolRegistryService,
    ToolInfo,
    ToolNotFoundError,
    ToolAlreadyExistsError,
    _PROJECT_ROOT,
    _TOOL_ROOTS,
    _FRAMEWORK_PARAMS,
)


# ==================== P0: 导入 / 存在性测试 ====================


def test_service_importable():
    """测试 tool_service 模块可导入且包含核心类与异常。"""
    from app.shared.utils.agent import tool_service
    assert hasattr(tool_service, "ToolRegistryService")
    assert hasattr(tool_service, "ToolInfo")
    assert hasattr(tool_service, "ToolNotFoundError")
    assert hasattr(tool_service, "ToolAlreadyExistsError")


def test_tool_info_dataclass_has_all_fields():
    """测试 ToolInfo dataclass 包含所有必需字段且 tool_instance 默认为 None。"""
    info = ToolInfo(
        name="test_tool",
        display_name="测试工具",
        category="test",
        description="测试描述",
        module_path="app.core.tools.test",
        file_path="app/core/tools/test.py",
        args_schema={},
        return_description="str",
        function_description="docstring",
        enabled=True,
    )
    assert info.name == "test_tool"
    assert info.tool_instance is None  # 默认值
    assert info.enabled is True


def test_constants_are_correct():
    """测试模块常量 _PROJECT_ROOT / _TOOL_ROOTS / _FRAMEWORK_PARAMS 值正确。"""
    from pathlib import Path
    assert isinstance(_PROJECT_ROOT, Path)
    assert (_PROJECT_ROOT / "app" / "core" / "tools").exists()
    assert "app/core/tools" in _TOOL_ROOTS
    assert "app/shared/tools/skills" in _TOOL_ROOTS
    assert "runtime" in _FRAMEWORK_PARAMS
    assert "self" in _FRAMEWORK_PARAMS
    assert "cls" in _FRAMEWORK_PARAMS


# ==================== _decode_jsonb / _decode_row 防御性反序列化测试 ====================


def test_decode_jsonb_none_returns_default():
    """测试 _decode_jsonb：None 入参应返回 default。"""
    assert ToolRegistryService._decode_jsonb(None, {}) == {}
    assert ToolRegistryService._decode_jsonb(None, []) == []


def test_decode_jsonb_str_parses_json():
    """测试 _decode_jsonb：str 入参应被 json.loads 解析。"""
    assert ToolRegistryService._decode_jsonb('{"key": "val"}', {}) == {"key": "val"}
    assert ToolRegistryService._decode_jsonb('["a", "b"]', []) == ["a", "b"]


def test_decode_jsonb_dict_list_passthrough():
    """测试 _decode_jsonb：dict/list 入参应原样返回（兼容 codec 已注册场景）。"""
    value = {"key": "val"}
    assert ToolRegistryService._decode_jsonb(value, {}) is value
    lst = ["a"]
    assert ToolRegistryService._decode_jsonb(lst, []) is lst


def test_decode_jsonb_invalid_str_returns_default():
    """测试 _decode_jsonb：无效 JSON 字符串时回退到 default。"""
    assert ToolRegistryService._decode_jsonb("not json", {}) == {}


def test_decode_row_decodes_args_schema():
    """测试 _decode_row：args_schema JSONB 字段被正确反序列化。"""
    service = ToolRegistryService(MagicMock())
    row = {
        "name": "test",
        "args_schema": '{"param": {"type": "str"}}',
        "enabled": True,
    }
    result = service._decode_row(row)
    assert result["args_schema"] == {"param": {"type": "str"}}
    # 非 JSONB 字段保持原样
    assert result["name"] == "test"


def test_decode_row_none_returns_none():
    """测试 _decode_row：row 为 None 时返回 None。"""
    service = ToolRegistryService(MagicMock())
    assert service._decode_row(None) is None


# ==================== _build_tool_info 测试 ====================


def test_build_tool_info_with_registered_instance():
    """测试 _build_tool_info：ToolRegistry 中有对应记录时设置 tool_instance。"""
    service = ToolRegistryService(MagicMock())
    row_dict = {
        "name": "my_tool",
        "display_name": "我的工具",
        "category": "test",
        "description": "描述",
        "module_path": "app.core.tools.my",
        "file_path": "app/core/tools/my.py",
        "args_schema": {},
        "return_description": "str",
        "function_description": "doc",
        "enabled": True,
    }
    fake_func = MagicMock()
    registered = {"my_tool": {"func": fake_func, "agent": "test", "description": "d"}}
    info = service._build_tool_info(row_dict, registered)
    assert info.name == "my_tool"
    assert info.tool_instance is fake_func


def test_build_tool_info_without_registered_instance():
    """测试 _build_tool_info：ToolRegistry 中无对应记录时 tool_instance 为 None。"""
    service = ToolRegistryService(MagicMock())
    row_dict = {
        "name": "unregistered",
        "display_name": "",
        "category": "",
        "description": "",
        "module_path": "",
        "file_path": "",
        "args_schema": {},
        "return_description": "",
        "function_description": "",
        "enabled": True,
    }
    info = service._build_tool_info(row_dict, {})
    assert info.tool_instance is None


# ==================== 读方法测试（优先读缓存） ====================


def test_list_tools_reads_from_cache():
    """测试 list_tools：缓存有数据时直接返回缓存内容。"""
    service = ToolRegistryService(MagicMock())
    service._cache["tool_a"] = ToolInfo(
        name="tool_a", display_name="A", category="cat", description="d",
        module_path="m", file_path="f", args_schema={}, return_description="",
        function_description="", enabled=True,
    )
    result = asyncio.run(service.list_tools())
    assert len(result) == 1
    assert result[0]["name"] == "tool_a"
    # tool_instance 不应出现在 dict 中
    assert "tool_instance" not in result[0]


def test_list_tools_falls_back_to_db():
    """测试 list_tools：缓存为空时回退 DB 查询。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"name": "db_tool", "args_schema": '{"k": "v"}', "enabled": True},
    ])
    service = ToolRegistryService(db)
    result = asyncio.run(service.list_tools())
    assert len(result) == 1
    assert result[0]["name"] == "db_tool"
    # JSONB 已反序列化
    assert result[0]["args_schema"] == {"k": "v"}


def test_get_tool_by_name_cache_hit():
    """测试 get_tool_by_name：缓存命中时直接返回 ToolInfo。"""
    service = ToolRegistryService(MagicMock())
    info = ToolInfo(
        name="cached", display_name="", category="", description="",
        module_path="", file_path="", args_schema={}, return_description="",
        function_description="", enabled=True,
    )
    service._cache["cached"] = info
    result = asyncio.run(service.get_tool_by_name("cached"))
    assert result is info


def test_get_tool_by_name_cache_miss_queries_db():
    """测试 get_tool_by_name：缓存未命中时查 DB 并回填缓存。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "db_tool", "display_name": "DB", "category": "c",
        "description": "d", "module_path": "m", "file_path": "f",
        "args_schema": "{}", "return_description": "str",
        "function_description": "doc", "enabled": True,
    })
    service = ToolRegistryService(db)
    # 清空 ToolRegistry 避免干扰
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    result = asyncio.run(service.get_tool_by_name("db_tool"))
    assert result.name == "db_tool"
    assert result.tool_instance is None  # ToolRegistry 中无注册
    # 验证已回填缓存
    assert "db_tool" in service._cache


def test_get_tool_by_name_not_found():
    """测试 get_tool_by_name：DB 中不存在时返回 None。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    result = asyncio.run(service.get_tool_by_name("nonexistent"))
    assert result is None


def test_get_tools_by_names_returns_instances():
    """测试 get_tools_by_names：返回有 tool_instance 的工具列表。"""
    service = ToolRegistryService(MagicMock())
    func_a = MagicMock()
    func_b = MagicMock()
    service._cache["a"] = ToolInfo(
        name="a", display_name="", category="", description="", module_path="",
        file_path="", args_schema={}, return_description="", function_description="",
        enabled=True, tool_instance=func_a,
    )
    service._cache["b"] = ToolInfo(
        name="b", display_name="", category="", description="", module_path="",
        file_path="", args_schema={}, return_description="", function_description="",
        enabled=True, tool_instance=func_b,
    )
    result = asyncio.run(service.get_tools_by_names(["a", "b"]))
    assert len(result) == 2
    assert func_a in result
    assert func_b in result


def test_get_tools_by_names_skips_missing_and_unregistered():
    """测试 get_tools_by_names：跳过不存在和 tool_instance 为 None 的工具。"""
    db = MagicMock()
    # "missing" 工具不在缓存中，会查 DB（返回 None 表示不存在）
    db.fetchrow = AsyncMock(return_value=None)
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()
    service._cache["has_instance"] = ToolInfo(
        name="has_instance", display_name="", category="", description="",
        module_path="", file_path="", args_schema={}, return_description="",
        function_description="", enabled=True, tool_instance=MagicMock(),
    )
    service._cache["no_instance"] = ToolInfo(
        name="no_instance", display_name="", category="", description="",
        module_path="", file_path="", args_schema={}, return_description="",
        function_description="", enabled=True, tool_instance=None,
    )
    result = asyncio.run(service.get_tools_by_names(["has_instance", "no_instance", "missing"]))
    assert len(result) == 1


# ==================== 写方法测试（写 DB + 同步缓存） ====================


def test_create_tool_inserts_row_and_refreshes_cache():
    """测试 create_tool：写入 DB 并刷新缓存。"""
    db = MagicMock()
    # fetchrow 被调用三次：
    # 1. 存在性检查（返回 None 表示不存在）
    # 2. INSERT ... RETURNING *（返回新插入行）
    # 3. _refresh_cache 内的 SELECT（返回同一行，enabled=True）
    new_row = {
        "name": "new_tool", "display_name": "新工具", "category": "test",
        "description": "", "module_path": "m", "file_path": "f",
        "args_schema": "{}", "return_description": "", "function_description": "",
        "enabled": True, "sort_order": 0,
    }
    db.fetchrow = AsyncMock(side_effect=[None, new_row, new_row])
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    config = {
        "name": "new_tool",
        "display_name": "新工具",
        "category": "test",
        "module_path": "m",
        "file_path": "f",
    }
    result = asyncio.run(service.create_tool(config))
    assert result["name"] == "new_tool"
    # 验证缓存已刷新（enabled=True 应加入缓存）
    assert "new_tool" in service._cache


def test_create_tool_raises_on_duplicate():
    """测试 create_tool：name 已存在时抛出 ToolAlreadyExistsError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "existing"})  # 存在性检查命中
    service = ToolRegistryService(db)

    with pytest.raises(ToolAlreadyExistsError):
        asyncio.run(service.create_tool({"name": "existing"}))


def test_create_tool_raises_on_missing_name():
    """测试 create_tool：缺少 name 键时抛出 KeyError。"""
    service = ToolRegistryService(MagicMock())
    with pytest.raises(KeyError):
        asyncio.run(service.create_tool({"display_name": "no name"}))


def test_update_tool_updates_and_refreshes_cache():
    """测试 update_tool：更新 DB 并刷新缓存。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "tool", "display_name": "更新后", "category": "c",
        "description": "", "module_path": "", "file_path": "",
        "args_schema": "{}", "return_description": "", "function_description": "",
        "enabled": True, "sort_order": 0,
    })
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    result = asyncio.run(service.update_tool("tool", {"display_name": "更新后"}))
    assert result["display_name"] == "更新后"
    assert "tool" in service._cache


def test_update_tool_raises_on_not_found():
    """测试 update_tool：工具不存在时抛出 ToolNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)  # UPDATE RETURNING 无结果
    service = ToolRegistryService(db)

    with pytest.raises(ToolNotFoundError):
        asyncio.run(service.update_tool("missing", {"display_name": "x"}))


def test_delete_tool_removes_and_invalidates_cache():
    """测试 delete_tool：删除 DB 行并失效缓存。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={"name": "tool"})  # 存在性检查
    db.execute = AsyncMock(return_value="DELETE 1")
    service = ToolRegistryService(db)
    service._cache["tool"] = MagicMock()

    asyncio.run(service.delete_tool("tool"))
    assert "tool" not in service._cache
    db.execute.assert_awaited()


def test_delete_tool_raises_on_not_found():
    """测试 delete_tool：工具不存在时抛出 ToolNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = ToolRegistryService(db)

    with pytest.raises(ToolNotFoundError):
        asyncio.run(service.delete_tool("missing"))


def test_set_tool_enabled_updates_and_refreshes_cache():
    """测试 set_tool_enabled：更新 enabled 字段并刷新缓存。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "tool", "display_name": "", "category": "", "description": "",
        "module_path": "", "file_path": "", "args_schema": "{}",
        "return_description": "", "function_description": "",
        "enabled": False, "sort_order": 0,
    })
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()
    service._cache["tool"] = MagicMock()

    asyncio.run(service.set_tool_enabled("tool", False))
    # enabled=False 时 _refresh_cache 应从缓存移除
    assert "tool" not in service._cache


def test_set_tool_enabled_raises_on_not_found():
    """测试 set_tool_enabled：工具不存在时抛出 ToolNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = ToolRegistryService(db)

    with pytest.raises(ToolNotFoundError):
        asyncio.run(service.set_tool_enabled("missing", True))


# ==================== ast 扫描测试 ====================


def test_has_tool_decorator_detects_bare_tool():
    """测试 _has_tool_decorator：识别 @tool（无括号）形式。"""
    tree = ast.parse("@tool\ndef my_tool():\n    pass\n")
    node = tree.body[0]
    assert ToolRegistryService._has_tool_decorator(node) is True


def test_has_tool_decorator_detects_tool_call():
    """测试 _has_tool_decorator：识别 @tool(...) 形式。"""
    tree = ast.parse('@tool(description="test")\ndef my_tool():\n    pass\n')
    node = tree.body[0]
    assert ToolRegistryService._has_tool_decorator(node) is True


def test_has_tool_decorator_detects_attribute_tool():
    """测试 _has_tool_decorator：识别 @langchain.tools.tool(...) 形式。"""
    tree = ast.parse('@langchain.tools.tool(description="test")\ndef my_tool():\n    pass\n')
    node = tree.body[0]
    assert ToolRegistryService._has_tool_decorator(node) is True


def test_has_tool_decorator_returns_false_for_non_tool():
    """测试 _has_tool_decorator：非 @tool 装饰器返回 False。"""
    tree = ast.parse('@register_tool(name="x")\ndef my_tool():\n    pass\n')
    node = tree.body[0]
    assert ToolRegistryService._has_tool_decorator(node) is False


def test_has_tool_decorator_returns_false_for_no_decorator():
    """测试 _has_tool_decorator：无装饰器返回 False。"""
    tree = ast.parse("def my_tool():\n    pass\n")
    node = tree.body[0]
    assert ToolRegistryService._has_tool_decorator(node) is False


def test_extract_args_schema_excludes_framework_params():
    """测试 _extract_args_schema：排除 runtime / self / cls 框架参数。"""
    tree = ast.parse(
        "def my_tool(latitude: float, runtime: ToolRuntime, self, cls) -> str:\n"
        "    pass\n"
    )
    node = tree.body[0]
    schema = ToolRegistryService._extract_args_schema(node)
    assert "latitude" in schema
    assert "runtime" not in schema
    assert "self" not in schema
    assert "cls" not in schema
    assert schema["latitude"]["type"] == "float"
    assert schema["latitude"]["required"] is True


def test_extract_args_schema_includes_defaults():
    """测试 _extract_args_schema：有默认值的参数标记为 required=False 并包含 default。"""
    tree = ast.parse(
        "def my_tool(a: str, b: int = 42, *, c: float = 3.14) -> str:\n"
        "    pass\n"
    )
    node = tree.body[0]
    schema = ToolRegistryService._extract_args_schema(node)
    assert schema["a"]["required"] is True
    assert schema["b"]["required"] is False
    assert schema["b"]["default"] == "42"
    assert schema["c"]["required"] is False
    assert schema["c"]["default"] == "3.14"


def test_extract_args_schema_no_annotation_uses_any():
    """测试 _extract_args_schema：无类型注解时 type 为 'Any'。"""
    tree = ast.parse("def my_tool(x):\n    pass\n")
    node = tree.body[0]
    schema = ToolRegistryService._extract_args_schema(node)
    assert schema["x"]["type"] == "Any"


def test_extract_return_description_with_annotation():
    """测试 _extract_return_description：有返回注解时返回注解字符串。"""
    tree = ast.parse("def my_tool() -> Command:\n    pass\n")
    node = tree.body[0]
    assert ToolRegistryService._extract_return_description(node) == "Command"


def test_extract_return_description_without_annotation():
    """测试 _extract_return_description：无返回注解时返回空字符串。"""
    tree = ast.parse("def my_tool():\n    pass\n")
    node = tree.body[0]
    assert ToolRegistryService._extract_return_description(node) == ""


def test_scan_file_for_tools_finds_real_tools():
    """测试 _scan_file_for_tools：扫描 BaseTools.py 能找到 @tool 函数。"""
    from pathlib import Path
    service = ToolRegistryService(MagicMock())
    base_tools = _PROJECT_ROOT / "app" / "core" / "tools" / "BaseTools.py"
    tools = service._scan_file_for_tools(base_tools)
    tool_names = [t["name"] for t in tools]
    # BaseTools.py 中已知有 5 个 @tool 函数
    assert "get_current_time" in tool_names
    assert "open_file" in tool_names
    assert "read_cached_chunk" in tool_names
    # 验证 file_path 使用正斜杠
    for t in tools:
        assert "/" in t["file_path"]
        assert "\\" not in t["file_path"]
        assert t["module_path"].startswith("app.core.tools")


def test_scan_file_for_tools_excludes_runtime_from_args():
    """测试 _scan_file_for_tools：args_schema 中不包含 runtime 参数。"""
    from pathlib import Path
    service = ToolRegistryService(MagicMock())
    base_tools = _PROJECT_ROOT / "app" / "core" / "tools" / "BaseTools.py"
    tools = service._scan_file_for_tools(base_tools)
    open_file = next(t for t in tools if t["name"] == "open_file")
    assert "runtime" not in open_file["args_schema"]
    assert "file_path" in open_file["args_schema"]


def test_scan_unregistered_returns_unregistered_tools():
    """测试 scan_unregistered：返回未在 DB 注册的 @tool 函数。"""
    db = MagicMock()
    # list_tools 回退 DB 查询，返回已注册工具名
    db.fetch = AsyncMock(return_value=[
        {"name": "get_current_time", "args_schema": "{}", "enabled": True},
    ])
    service = ToolRegistryService(db)
    # 清空缓存强制走 DB 路径
    service._cache.clear()

    result = asyncio.run(service.scan_unregistered())
    # BaseTools.py 中 open_file 等未注册
    names = [t["name"] for t in result]
    assert "open_file" in names
    # get_current_time 已注册，不应出现
    assert "get_current_time" not in names


# ==================== 缓存管理方法测试 ====================


def test_refresh_cache_loads_enabled_tool():
    """测试 _refresh_cache：enabled=TRUE 的工具被加载到缓存。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "tool", "display_name": "", "category": "", "description": "",
        "module_path": "", "file_path": "", "args_schema": "{}",
        "return_description": "", "function_description": "", "enabled": True,
    })
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    asyncio.run(service._refresh_cache("tool"))
    assert "tool" in service._cache


def test_refresh_cache_removes_disabled_tool():
    """测试 _refresh_cache：enabled=FALSE 的工具从缓存移除。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value={
        "name": "tool", "enabled": False,
    })
    service = ToolRegistryService(db)
    service._cache["tool"] = MagicMock()

    asyncio.run(service._refresh_cache("tool"))
    assert "tool" not in service._cache


def test_refresh_cache_removes_missing_tool():
    """测试 _refresh_cache：DB 中不存在的工具从缓存移除。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)
    service = ToolRegistryService(db)
    service._cache["ghost"] = MagicMock()

    asyncio.run(service._refresh_cache("ghost"))
    assert "ghost" not in service._cache


def test_invalidate_cache_removes_tool():
    """测试 _invalidate_cache：从缓存移除指定工具。"""
    service = ToolRegistryService(MagicMock())
    service._cache["a"] = MagicMock()
    service._cache["b"] = MagicMock()

    asyncio.run(service._invalidate_cache("a"))
    assert "a" not in service._cache
    assert "b" in service._cache


def test_invalidate_cache_idempotent():
    """测试 _invalidate_cache：移除不存在的 key 不报错（幂等）。"""
    service = ToolRegistryService(MagicMock())
    # 不应抛出异常
    asyncio.run(service._invalidate_cache("nonexistent"))


def test_clear_cache_empties_all():
    """测试 _clear_cache：清空所有缓存。"""
    service = ToolRegistryService(MagicMock())
    service._cache["a"] = MagicMock()
    service._cache["b"] = MagicMock()

    asyncio.run(service._clear_cache())
    assert len(service._cache) == 0


# ==================== preload_all 测试 ====================


def test_preload_all_loads_enabled_tools_to_cache():
    """测试 preload_all：动态导入 + DB 关联 + 缓存构建。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {
            "name": "tool_a", "display_name": "A", "category": "c",
            "description": "", "module_path": "", "file_path": "",
            "args_schema": "{}", "return_description": "",
            "function_description": "", "enabled": True, "sort_order": 0,
        },
        {
            "name": "tool_b", "display_name": "B", "category": "c",
            "description": "", "module_path": "", "file_path": "",
            "args_schema": "{}", "return_description": "",
            "function_description": "", "enabled": True, "sort_order": 1,
        },
    ])
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    # Mock _import_tool_modules 避免真实导入副作用
    with patch.object(service, "_import_tool_modules", new_callable=AsyncMock):
        asyncio.run(service.preload_all())

    assert len(service._cache) == 2
    assert "tool_a" in service._cache
    assert "tool_b" in service._cache
    # tool_instance 应为 None（ToolRegistry 中无注册）
    assert service._cache["tool_a"].tool_instance is None


def test_preload_all_skips_disabled_tools():
    """测试 preload_all：仅加载 enabled=TRUE 的工具（DB 已过滤）。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[
        {"name": "enabled_tool", "enabled": True, "args_schema": "{}"},
    ])
    service = ToolRegistryService(db)
    from app.shared.tools.registry import ToolRegistry
    ToolRegistry.clear()

    with patch.object(service, "_import_tool_modules", new_callable=AsyncMock):
        asyncio.run(service.preload_all())

    # DB 查询已带 WHERE enabled=TRUE，缓存中只有启用的工具
    assert "enabled_tool" in service._cache


def test_preload_all_imports_tool_modules():
    """测试 preload_all：调用 _import_tool_modules 动态导入模块。"""
    db = MagicMock()
    db.fetch = AsyncMock(return_value=[])
    service = ToolRegistryService(db)

    with patch.object(service, "_import_tool_modules", new_callable=AsyncMock) as mock_import:
        asyncio.run(service.preload_all())
        mock_import.assert_awaited_once()


# ==================== _tool_info_to_dict 测试 ====================


def test_tool_info_to_dict_excludes_tool_instance():
    """测试 _tool_info_to_dict：返回的 dict 不含 tool_instance 字段。"""
    info = ToolInfo(
        name="t", display_name="", category="", description="",
        module_path="", file_path="", args_schema={}, return_description="",
        function_description="", enabled=True, tool_instance=MagicMock(),
    )
    result = ToolRegistryService._tool_info_to_dict(info)
    assert "tool_instance" not in result
    assert result["name"] == "t"
    assert result["enabled"] is True
