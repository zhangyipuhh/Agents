# -*- coding:utf-8 -*-
"""
seed_tools_from_source.py 单元测试模块

针对 ``scripts/seed_tools_from_source.py`` 提供的离线工具种子生成脚本，覆盖以下关注点：

1. AST 解析能力（识别 ``@tool`` / ``@tool(...)`` 装饰函数、提取 ``description`` 参数）
2. 路径与分类推断（``_file_to_module_path``、``_infer_category``）
3. SQL/JSON 字符串转义（``_sql_escape``、``_json_escape``）
4. SQL 段落渲染（``render_sql`` 幂等 upsert 生成、空列表降级）
5. 端到端 CLI（``--dry-run``、``--output`` 文件写入）

注意：
- 本脚本仅依赖标准库 (``ast`` / ``json`` / ``argparse`` / ``pathlib`` / ``datetime``)，
  无 DB / 网络依赖，因此测试无需引入任何 MagicMock。
- 测试中临时工具目录通过 ``monkeypatch`` 替换模块级 ``TOOL_ROOTS`` 与 ``PROJECT_ROOT``
  实现隔离，避免污染真实工程文件。
"""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

# 让 ``import scripts.seed_tools_from_source`` 在 pytest 任意 cwd 下都能解析
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts import seed_tools_from_source as seed_mod  # noqa: E402


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

def _write_tool_file(
    directory: Path,
    rel_parts: tuple,
    func_name: str,
    decorator: str,
    docstring: str = "",
) -> Path:
    """在指定目录下写一个最小化的 ``@tool`` 函数文件。

    参数：
        directory: 文件所在目录（绝对路径）
        rel_parts: 相对 ``PROJECT_ROOT`` 的路径段元组（如 ``("app", "core", "tools")``）
        func_name: 被装饰的函数名
        decorator: 装饰器源码片段（如 ``"@tool"`` 或 ``"@tool(description='desc')"``）
        docstring: 函数 docstring 内容（默认空）

    返回：
        Path: 写入文件的绝对路径
    """
    target_dir = directory.joinpath(*rel_parts)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{func_name}.py"
    body = [
        "from langchain.tools import tool",
        "",
        decorator,
        f"def {func_name}(x: str) -> str:",
    ]
    if docstring:
        body.append(f'    """{docstring}"""')
        body.append("    return x")
    else:
        body.append("    return x")
    file_path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return file_path


@pytest.fixture
def isolated_tool_roots(monkeypatch, tmp_path):
    """把脚本的 TOOL_ROOTS / PROJECT_ROOT 指向 tmp_path 下创建的工程结构。

    返回：
        tuple[Path, Path]: (project_root, [core_tools_dir, skills_dir])
        其中 skills_dir 下还会创建 ``skills/<agent>/`` 子目录，方便验证
        ``_infer_category`` 对 ``skills/{agent}/...`` 路径的推断逻辑。
    """
    project_root = tmp_path / "fake_project"
    project_root.mkdir()
    core_tools = project_root / "app" / "core" / "tools"
    skills_dir = project_root / "app" / "shared" / "tools" / "skills"

    # module-level 常量在函数调用时才读取，因此 monkeypatch 即可生效
    monkeypatch.setattr(seed_mod, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(seed_mod, "TOOL_ROOTS", [core_tools, skills_dir])
    return project_root, [core_tools, skills_dir]


# ---------------------------------------------------------------------------
# AST 装饰器识别
# ---------------------------------------------------------------------------

def _func_node(source: str, name: str) -> ast.FunctionDef:
    """从源代码字符串解析并返回指定名字的 ``FunctionDef`` 节点。

    参数：
        source: 完整的 Python 源代码字符串
        name: 要查找的函数名

    返回：
        ast.FunctionDef: 匹配到的函数定义节点

    异常：
        AssertionError: 找不到对应名字的函数时抛出
    """
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"FunctionDef {name!r} not found")


def test_has_tool_decorator_recognizes_both_forms():
    """``_has_tool_decorator`` 必须同时识别 ``@tool`` 与 ``@tool(...)`` 两种写法。

    验证：
        - ``@tool``（``ast.Name``）→ True
        - ``@tool(description=...)``（``ast.Call``）→ True
        - ``@something_else`` → False
        - 无装饰器 → False
    """
    # @tool（无括号）
    node1 = _func_node(
        "from langchain.tools import tool\n"
        "@tool\n"
        "def my_func():\n"
        "    pass\n",
        name="my_func",
    )
    assert seed_mod._has_tool_decorator(node1) is True

    # @tool(...)（带括号 + 关键字参数）
    node2 = _func_node(
        "from langchain.tools import tool\n"
        "@tool(description='hi')\n"
        "def my_func():\n"
        "    pass\n",
        name="my_func",
    )
    assert seed_mod._has_tool_decorator(node2) is True

    # 其他装饰器
    node3 = _func_node(
        "@staticmethod\n"
        "def my_func():\n"
        "    pass\n",
        name="my_func",
    )
    assert seed_mod._has_tool_decorator(node3) is False

    # 无装饰器
    node4 = _func_node("def my_func():\n    pass\n", name="my_func")
    assert seed_mod._has_tool_decorator(node4) is False


def test_extract_tool_description_from_decorator():
    """``_extract_tool_description`` 必须提取 ``@tool(description='...')`` 的字面量。

    验证：
        - 带 description → 返回字符串内容
        - 无 description → 返回 None
        - 无装饰器括号 → 返回 None
    """
    # 正常情况
    node_with = _func_node(
        "from langchain.tools import tool\n"
        "@tool(description='echo a string')\n"
        "def echo(x: str) -> str:\n"
        "    return x\n",
        name="echo",
    )
    assert seed_mod._extract_tool_description(node_with) == "echo a string"

    # 装饰器无关键字参数
    node_without_kw = _func_node(
        "from langchain.tools import tool\n"
        "@tool()\n"
        "def echo(x: str) -> str:\n"
        "    return x\n",
        name="echo",
    )
    assert seed_mod._extract_tool_description(node_without_kw) is None

    # 无装饰器
    node_plain = _func_node(
        "def echo(x: str) -> str:\n    return x\n",
        name="echo",
    )
    assert seed_mod._extract_tool_description(node_plain) is None


# ---------------------------------------------------------------------------
# 路径与分类推断
# ---------------------------------------------------------------------------

def test_file_to_module_path():
    """``_file_to_module_path`` 必须把 ``a/b/c.py`` 转为 ``a.b.c``。"""
    rel = Path("app") / "core" / "tools" / "BaseTools.py"
    assert seed_mod._file_to_module_path(rel) == "app.core.tools.BaseTools"

    # 单段路径也支持
    assert seed_mod._file_to_module_path(Path("solo.py")) == "solo"


def test_infer_category_from_skills_path():
    """``_infer_category`` 对 ``skills/{agent}/...`` 路径必须返回 ``agent`` 名。"""
    rel = Path("app") / "shared" / "tools" / "skills" / "map_agent" / "MapTools.py"
    assert seed_mod._infer_category(rel, category_map={}) == "map_agent"

    # 即使传一个非空 category_map，路径推断的优先级低于 map 中命中（这里未命中）
    rel2 = Path("app") / "shared" / "tools" / "skills" / "audit_doc_agent" / "X.py"
    assert seed_mod._infer_category(rel2, category_map={"Other.py": "其他"}) == "audit_doc_agent"


def test_infer_category_uses_default_map():
    """``_infer_category`` 命中 ``category_map`` 时必须返回映射值，否则降级 ``未分类``。"""
    # 命中 category_map
    rel = Path("app") / "core" / "tools" / "BaseTools.py"
    assert seed_mod._infer_category(rel, category_map={"BaseTools.py": "基础工具"}) == "基础工具"

    # 未命中、不是 skills 路径 → "未分类"
    rel_unknown = Path("app") / "core" / "tools" / "RandomTools.py"
    assert seed_mod._infer_category(rel_unknown, category_map={"BaseTools.py": "基础工具"}) == "未分类"

    # 未命中、不是 skills 路径、空 map → "未分类"
    assert seed_mod._infer_category(rel_unknown, category_map={}) == "未分类"


# ---------------------------------------------------------------------------
# 端到端：scan_all_tools + tmp 目录
# ---------------------------------------------------------------------------

def test_scan_all_tools_returns_correct_count(isolated_tool_roots):
    """``scan_all_tools`` 在两个临时 .py 文件（各含 1 个 @tool）下必须返回 2 条记录。"""
    _project_root, (core_tools, skills_dir) = isolated_tool_roots

    # 在 app/core/tools 下放 1 个 @tool
    _write_tool_file(
        core_tools.parent.parent.parent,  # fake_project
        ("app", "core", "tools"),
        "BaseTools",
        "@tool(description='time helper')",
        docstring="get current time",
    )
    # 在 app/shared/tools/skills/map_agent 下放 1 个 @tool
    _write_tool_file(
        core_tools.parent.parent.parent,
        ("app", "shared", "tools", "skills", "map_agent"),
        "MapTools",
        "@tool(description='map helper')",
        docstring="map helper",
    )

    tools = seed_mod.scan_all_tools(category_map={"BaseTools.py": "基础工具"})

    # 数量正确
    assert len(tools) == 2

    # 函数名即工具名（保留大小写），不强制小写
    names = sorted(t["name"] for t in tools)
    assert names == ["BaseTools", "MapTools"]

    # 分类推断正确：core/tools 命中 map；skills 下走 agent 推断
    by_name = {t["name"]: t for t in tools}
    assert by_name["BaseTools"]["category"] == "基础工具"
    assert by_name["MapTools"]["category"] == "map_agent"

    # module_path 与 file_path 必须以正斜杠形式落到元数据里
    assert by_name["BaseTools"]["module_path"] == "app.core.tools.BaseTools"
    assert by_name["BaseTools"]["file_path"] == "app/core/tools/BaseTools.py"

    # 元数据完整性
    for t in tools:
        assert t["enabled"] is True
        assert t["args_schema"] == {}
        assert t["display_name"]  # 非空


# ---------------------------------------------------------------------------
# SQL/JSON 转义
# ---------------------------------------------------------------------------

def test_sql_escape_handles_quotes():
    """``_sql_escape`` 必须把单引号与反斜杠按 SQL 标准转义。"""
    # 单引号转义为两个单引号
    assert seed_mod._sql_escape("it's") == "'it''s'"
    # 反斜杠转义为两个反斜杠
    assert seed_mod._sql_escape("a\\b") == "'a\\\\b'"
    # 两者混合
    assert seed_mod._sql_escape("a\\b'c") == "'a\\\\b''c'"
    # 普通字符串外层用单引号包裹
    assert seed_mod._sql_escape("hello") == "'hello'"


def test_sql_escape_none_returns_null():
    """``_sql_escape(None)`` 必须返回字面量 ``NULL``（不含引号）。"""
    assert seed_mod._sql_escape(None) == "NULL"


def test_json_escape_dict():
    """``_json_escape`` 对 ``dict`` 必须产出合法 JSON 字符串字面量。"""
    payload = {"x": 1, "y": "z"}
    out = seed_mod._json_escape(payload)
    # 外层是 SQL 单引号，内部是排序后的 JSON 文本
    assert out.startswith("'") and out.endswith("'")
    inner = json.loads(out[1:-1])
    assert inner == {"x": 1, "y": "z"}

    # None 走 SQL NULL 路径
    assert seed_mod._json_escape(None) == "NULL"


# ---------------------------------------------------------------------------
# SQL 渲染
# ---------------------------------------------------------------------------

def test_render_sql_generates_upsert_statements():
    """``render_sql`` 必须为每个工具生成 ``INSERT ... ON CONFLICT (name) DO NOTHING``。"""
    tools = [
        {
            "name": "echo",
            "display_name": "Echo",
            "category": "基础工具",
            "description": "echo a string",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
            "args_schema": {},
            "return_description": None,
            "function_description": "echo a string",
            "enabled": True,
            "sort_order": 0,
        },
        {
            "name": "with_quote",
            "display_name": "With Quote",
            "category": "测试",
            "description": "it's a test",
            "module_path": "app.core.tools.X",
            "file_path": "app/core/tools/X.py",
            "args_schema": {},
            "return_description": None,
            "function_description": "desc",
            "enabled": False,
            "sort_order": 5,
        },
    ]
    sql = seed_mod.render_sql(tools, generated_at="2026-06-25 12:00:00")

    # 头部注释
    assert "-- 工具种子数据" in sql
    assert "-- 生成时间: 2026-06-25 12:00:00" in sql
    assert "-- 工具数量: 2" in sql

    # 两条 INSERT：用 "INSERT INTO tools (" 计数，可避免头部注释里
    # "ON CONFLICT (name) DO NOTHING 可重复执行" 行误命中（注释里没有 "INSERT INTO tools ("）。
    insert_lines = [line for line in sql.splitlines() if line.startswith("INSERT INTO tools (")]
    assert len(insert_lines) == 2
    for line in insert_lines:
        assert line.endswith(") VALUES")
    # 两条 ON CONFLICT 语句（仅 SQL 主体中的；头部注释里的 "可重复执行" 跟 ON CONFLICT 不在同一行）
    on_conflict_lines = [line for line in sql.splitlines() if line.strip() == "ON CONFLICT (name) DO NOTHING;"]
    assert len(on_conflict_lines) == 2

    # 单引号被转义为两个单引号
    assert "'it''s a test'" in sql

    # enabled=False 应渲染为 FALSE，sort_order=5 为整型字面量
    assert "FALSE" in sql
    assert ", 5)" in sql


def test_render_sql_empty_list():
    """``render_sql`` 对空列表必须输出头部注释 + 提示行而不抛异常。"""
    sql = seed_mod.render_sql([], generated_at="2026-06-25 12:00:00")
    assert "-- 工具数量: 0" in sql
    assert "-- (未发现任何 @tool 装饰函数)" in sql
    assert "INSERT INTO tools" not in sql


# ---------------------------------------------------------------------------
# CLI：subprocess 调用真实脚本
# ---------------------------------------------------------------------------

def test_cli_dry_run():
    """``python scripts/seed_tools_from_source.py --dry-run`` 必须返回 0 并输出工具数量。"""
    script = _PROJECT_ROOT / "scripts" / "seed_tools_from_source.py"
    assert script.exists(), f"脚本不存在: {script}"

    # Windows 默认控制台编码不是 UTF-8；显式设置 PYTHONIOENCODING=utf-8
    # 让 print() 写出中文时不走 cp936/gbk，避免解码失败。
    env = {"PYTHONIOENCODING": "utf-8"}

    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # 兜底：万一还是混进 cp936 字节，用 U+FFFD 替换不抛异常
        env={**__import__("os").environ, **env},
        timeout=60,
    )

    # 退出码
    assert result.returncode == 0, (
        f"stderr=\n{result.stderr}\nstdout=\n{result.stdout}"
    )
    # --dry-run 把报告写到 stderr，必须包含 "Found N @tool functions"
    assert "Found" in result.stderr
    assert "@tool functions" in result.stderr
    # stdout 在 dry-run 下应为空（避免污染管道）
    assert result.stdout.strip() == ""


def test_cli_output_to_file(tmp_path):
    """``--output`` 必须把 SQL 段落写入指定文件且包含 INSERT 关键字。"""
    script = _PROJECT_ROOT / "scripts" / "seed_tools_from_source.py"
    output_file = tmp_path / "seed.sql"

    env = {"PYTHONIOENCODING": "utf-8"}

    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output_file)],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**__import__("os").environ, **env},
        timeout=60,
    )

    assert result.returncode == 0, (
        f"stderr=\n{result.stderr}\nstdout=\n{result.stdout}"
    )
    assert output_file.exists(), "输出文件未生成"

    content = output_file.read_text(encoding="utf-8")
    # 头部注释与至少一条 INSERT（项目实际有 17 个 @tool）
    assert "-- 工具种子数据" in content
    assert "INSERT INTO tools" in content
    assert "ON CONFLICT (name) DO NOTHING" in content