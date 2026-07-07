# -*- coding:utf-8 -*-
"""
map_agent 工具 @tool 装饰器测试模块

验证迁移后的 MapTools 中 11 个工具函数均经 LangChain @tool 装饰器装饰，
description 参数直接挂在 @tool 上（不再通过 @register_tool 间接注册）。

迁移原因：@register_tool(agent=...) 强制工具只能被单一 agent 加载，
与 app/core/tools/BaseTools.py 自由绑定风格相悖；实际加载路径
（agent_config_service._load_tools → tool_service.get_tool_by_name →
_get_tool_instance_from_module）只依赖 @tool 装饰器。

测试策略：
  使用 AST 静态解析 MapTools.py 源码，而非运行时 getattr。
  原因：app/tests/conftest.py 在测试环境下把 langchain.tools.tool 替换为
  identity 装饰器（返回原函数），运行时 getattr 无法观察到 description 属性。
  AST 解析能准确读取源码中 @tool(...) 的 description 关键字参数。
"""
import ast
from pathlib import Path

import pytest


def _parse_module_source():
    """解析 MapTools.py 源码并返回 AST 模块节点。

    返回：
        ast.Module: MapTools.py 的 AST 模块节点
    """
    map_tools_path = Path(__file__).resolve().parents[3] / "shared" / "tools" / "skills" / "map_agent" / "MapTools.py"
    source = map_tools_path.read_text(encoding="utf-8")
    return ast.parse(source)


def _get_function_decorators(tree: ast.Module, func_name: str):
    """从 AST 中提取指定函数的所有装饰器节点。

    支持普通函数（ast.FunctionDef）和异步函数（ast.AsyncFunctionDef）。

    参数：
        tree: AST 模块节点
        func_name: 目标函数名

    返回：
        list[ast.expr]: 装饰器节点列表；函数不存在时返回空列表
    """
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return list(node.decorator_list)
    return []


def _get_tool_description_from_decorator(decorators: list) -> str | None:
    """从装饰器列表中提取 @tool(description="...") 的 description 字符串。

    支持的装饰器形态：
      - @tool(description="...")         → ast.Call（单行或三引号多行）
      - @tool(description=("..."))       → ast.Call，值为 ast.Tuple + ast.Constant
      - @tool                            → ast.Name（无 description）
      - @langchain.tools.tool(...)       → ast.Call，func 为 ast.Attribute

    参数：
        decorators: 装饰器节点列表

    返回：
        str | None: description 字符串字面量；未找到返回 None
    """
    for dec in decorators:
        call = None
        if isinstance(dec, ast.Call):
            call = dec
        elif isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name):
            # 形如 module.tool — 非调用形式，不处理
            continue

        if call is None:
            continue

        # 提取函数引用（@tool 或 @langchain.tools.tool）
        func_node = call.func
        is_tool_decorator = (
            (isinstance(func_node, ast.Name) and func_node.id == "tool")
            or (isinstance(func_node, ast.Attribute) and func_node.attr == "tool")
        )
        if not is_tool_decorator:
            continue

        # 提取 description 关键字参数
        for kw in call.keywords:
            if kw.arg == "description":
                value = kw.value
                # 单字符串字面量（含三引号多行）
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
                # f-string 拼接（ast.JoinedStr）
                if isinstance(value, ast.JoinedStr):
                    parts = []
                    for v in value.values:
                        if isinstance(v, ast.Constant) and isinstance(v.value, str):
                            parts.append(v.value)
                    if parts:
                        return "".join(parts)
                # 字符串字面量拼接（"a" + "b" 形式 → ast.BinOp）
                if isinstance(value, ast.BinOp):
                    parts = []
                    def _collect(node):
                        if isinstance(node, ast.Constant) and isinstance(node.value, str):
                            parts.append(node.value)
                        elif isinstance(node, ast.BinOp):
                            _collect(node.left)
                            _collect(node.right)
                    _collect(value)
                    if parts:
                        return "".join(parts)
                # 元组包裹 description=(...) — LangChain `@tool(description=("a", "b"))`
                if isinstance(value, ast.Tuple):
                    parts = []
                    for elt in value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            parts.append(elt.value)
                    if parts:
                        return "".join(parts)
        # 找到 @tool 装饰器但无 description → 返回 None（无 description 形式）
        return None

    return None


def test_map_tools_importable():
    """测试 MapTools 模块可导入。

    返回：
        None

    异常：
        AssertionError: 模块导入失败时抛出
    """
    from app.shared.tools.skills.map_agent import MapTools
    assert MapTools is not None


def test_map_tools_have_tool_decorator():
    """测试 MapTools 中 11 个工具函数均经 @tool 装饰。

    通过 AST 解析源码验证每个目标函数至少有一个 @tool 或 @tool(...) 装饰器。

    返回：
        None

    异常：
        AssertionError: 任一工具缺少 @tool 装饰器时抛出
    """
    tree = _parse_module_source()
    expected = [
        "set_map_center", "set_map_zoom", "add_map_marker",
        "remove_map_marker", "clear_map_markers", "get_map_state",
        "draw_map_polygon", "set_map_layer", "generate_report",
        "save_business_info", "query_knowledge",
    ]
    for func_name in expected:
        decorators = _get_function_decorators(tree, func_name)
        assert len(decorators) > 0, f"工具 {func_name} 缺少装饰器"

        # 检查至少有一个装饰器是 @tool / @tool(...)
        has_tool = False
        for dec in decorators:
            if isinstance(dec, ast.Name) and dec.id == "tool":
                has_tool = True
                break
            if isinstance(dec, ast.Call):
                func_node = dec.func
                if (isinstance(func_node, ast.Name) and func_node.id == "tool") or \
                   (isinstance(func_node, ast.Attribute) and func_node.attr == "tool"):
                    has_tool = True
                    break
        assert has_tool, f"工具 {func_name} 缺少 @tool 装饰器"


def test_map_tools_have_no_register_tool_decorator():
    """测试 MapTools 中所有工具均不再使用 @register_tool 装饰器。

    验证迁移完成后，@register_tool 已从 MapTools.py 完全移除。

    返回：
        None

    异常：
        AssertionError: 发现残留 @register_tool 时抛出
    """
    tree = _parse_module_source()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_node = node.func
            if isinstance(func_node, ast.Name) and func_node.id == "register_tool":
                pytest.fail(
                    f"发现残留 @register_tool 调用（行 {node.lineno}）："
                    f"应改用 LangChain @tool(description=...)"
                )


def test_map_tools_migrated_descriptions():
    """测试 9 个原 @tool 无参工具已迁移 description 到 @tool 装饰器。

    验证 9 个工具的 @tool 装饰器 description 与原 @register_tool 第三参数一致：
    - set_map_center: 设置地图中心点坐标
    - set_map_zoom: 设置地图缩放级别
    - add_map_marker: 在地图上添加标记点
    - remove_map_marker: 移除指定的地图标记
    - clear_map_markers: 清除地图上所有标记
    - get_map_state: 获取当前地图状态信息
    - draw_map_polygon: 在地图上绘制多边形区域
    - set_map_layer: 设置地图显示图层类型
    - generate_report: 根据项目信息生成Word报告

    返回：
        None

    异常：
        AssertionError: 任一工具 description 与预期不符时抛出
    """
    tree = _parse_module_source()
    expected_descriptions = {
        "set_map_center": "设置地图中心点坐标",
        "set_map_zoom": "设置地图缩放级别",
        "add_map_marker": "在地图上添加标记点",
        "remove_map_marker": "移除指定的地图标记",
        "clear_map_markers": "清除地图上所有标记",
        "get_map_state": "获取当前地图状态信息",
        "draw_map_polygon": "在地图上绘制多边形区域",
        "set_map_layer": "设置地图显示图层类型",
        "generate_report": "根据项目信息生成Word报告",
    }
    for func_name, expected_desc in expected_descriptions.items():
        decorators = _get_function_decorators(tree, func_name)
        actual_desc = _get_tool_description_from_decorator(decorators)
        assert actual_desc is not None, (
            f"工具 {func_name} 的 @tool 装饰器缺少 description 参数"
        )
        assert expected_desc in actual_desc, (
            f"工具 {func_name} description 与预期不符："
            f"expected={expected_desc!r}, actual={actual_desc!r}"
        )


def test_save_business_info_and_query_knowledge_have_description():
    """测试 save_business_info 和 query_knowledge 已有详细 description。

    这两个工具迁移前已有 @tool(description=...)，迁移后应保留：
    - save_business_info: 包含"保存业务信息到数据库"
    - query_knowledge: 包含"knowledge base"（英文描述）

    返回：
        None

    异常：
        AssertionError: 描述缺失或不包含预期关键词时抛出
    """
    tree = _parse_module_source()

    # save_business_info 中文描述
    save_decorators = _get_function_decorators(tree, "save_business_info")
    save_desc = _get_tool_description_from_decorator(save_decorators)
    assert save_desc is not None, "save_business_info 缺少 @tool description"
    assert "保存业务信息" in save_desc, (
        f"save_business_info description 缺失关键文本：actual={save_desc!r}"
    )

    # query_knowledge 英文描述
    qk_decorators = _get_function_decorators(tree, "query_knowledge")
    qk_desc = _get_tool_description_from_decorator(qk_decorators)
    assert qk_desc is not None, "query_knowledge 缺少 @tool description"
    assert "knowledge base" in qk_desc.lower(), (
        f"query_knowledge description 缺失关键文本：actual={qk_desc!r}"
    )
