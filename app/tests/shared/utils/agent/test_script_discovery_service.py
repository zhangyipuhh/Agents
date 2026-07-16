# -*- coding:utf-8 -*-
"""
``ScriptDiscoveryService`` 测试。

覆盖点：
    * ``scan()`` 能加载用 ``@register_script`` 装饰的文件
    * 语法错误的文件计入 ``failed``，不中断其他文件扫描
    * ``list_scripts()`` 返回字段严格匹配白名单
    * ``get_script()`` 返回含可调用 ``func`` 的完整对象
    * ``get_script()`` 对未知名返回 ``None``
    * 目录不存在时 ``scan()`` 返回空统计
"""
import sys
from pathlib import Path

import pytest

from app.scripts.registry import clear_registry, register_script
from app.shared.utils.agent.script_discovery_service import ScriptDiscoveryService


@pytest.fixture(autouse=True)
def _clean_registry_and_modules():
    """每个用例前后清空 registry 与动态加载的测试模块，避免相互污染。

    生产中 ``ScriptDiscoveryService`` 在 lifespan 启动时扫描一次，注册表持久存在；
    测试中需要反复清空以隔离用例。同时清理 ``sys.modules`` 中以
    ``app.scripts.`` 开头但非真实包的动态加载模块。
    """
    clear_registry()
    # 清理可能被动态加载的测试模块
    keys_to_remove = [
        k for k in list(sys.modules.keys())
        if k.startswith("app.scripts.") and k not in (
            "app.scripts",
            "app.scripts.base",
            "app.scripts.registry",
            "app.scripts.examples",
            "app.scripts.examples.hello_script",
        )
    ]
    for k in keys_to_remove:
        del sys.modules[k]
    yield
    clear_registry()
    # 用例结束后再次清理
    keys_to_remove = [
        k for k in list(sys.modules.keys())
        if k.startswith("app.scripts.") and k not in (
            "app.scripts",
            "app.scripts.base",
            "app.scripts.registry",
            "app.scripts.examples",
            "app.scripts.examples.hello_script",
        )
    ]
    for k in keys_to_remove:
        del sys.modules[k]


@pytest.mark.asyncio
async def test_scan_discovers_example_scripts(tmp_path):
    """``scan()`` 应能加载用 ``@register_script`` 装饰的文件。"""
    script_content = '''
from app.scripts.base import ScriptContext
from app.scripts.registry import register_script

@register_script(name="tmp_test", display_name="T", description="")
async def run(context):
    return ""
'''
    (tmp_path / "tmp_test.py").write_text(script_content, encoding="utf-8")
    svc = ScriptDiscoveryService(tmp_path)
    result = await svc.scan()
    assert result["scanned"] == 1
    assert result["failed"] == 0
    scripts = svc.list_scripts()
    assert any(s["name"] == "tmp_test" for s in scripts)


@pytest.mark.asyncio
async def test_scan_handles_broken_file_gracefully(tmp_path):
    """语法错误的文件应计入 ``failed``，不中断其他文件扫描。"""
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    good = '''
from app.scripts.base import ScriptContext
from app.scripts.registry import register_script

@register_script(name="good", display_name="G", description="")
async def run(context):
    return ""
'''
    (tmp_path / "good.py").write_text(good, encoding="utf-8")
    svc = ScriptDiscoveryService(tmp_path)
    result = await svc.scan()
    assert result["scanned"] == 2
    assert result["failed"] >= 1
    assert svc.get_script("good") is not None


@pytest.mark.asyncio
async def test_scan_skips_init_and_base_files(tmp_path):
    """``__init__.py`` / ``base.py`` / ``registry.py`` 应被跳过，不计入 ``scanned``。"""
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "base.py").write_text("# should be skipped", encoding="utf-8")
    (tmp_path / "registry.py").write_text("# should be skipped", encoding="utf-8")
    svc = ScriptDiscoveryService(tmp_path)
    result = await svc.scan()
    assert result["scanned"] == 0
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_scan_returns_empty_when_dir_not_exists(tmp_path):
    """目录不存在时 ``scan()`` 应返回空统计且不抛异常。"""
    svc = ScriptDiscoveryService(tmp_path / "nonexistent")
    result = await svc.scan()
    assert result["scanned"] == 0
    assert result["failed"] == 0


def test_list_scripts_returns_whitelist_fields_only(tmp_path):
    """``list_scripts()`` 返回字段严格匹配白名单。"""
    async def fake_run(context):  # noqa: ANN001
        return ""

    register_script(name="wl", display_name="W", description="d")(fake_run)
    svc = ScriptDiscoveryService(tmp_path)
    scripts = svc.list_scripts()
    assert len(scripts) == 1
    allowed = {"name", "display_name", "description", "params_schema", "module_path"}
    assert set(scripts[0].keys()) == allowed


def test_list_scripts_returns_empty_when_registry_empty(tmp_path):
    """注册表为空时 ``list_scripts()`` 应返回空列表。"""
    svc = ScriptDiscoveryService(tmp_path)
    assert svc.list_scripts() == []


def test_get_script_returns_func_reference(tmp_path):
    """``get_script()`` 应返回含可调用 ``func`` 的完整对象。"""
    async def fake_run(context):  # noqa: ANN001
        return "x"

    register_script(name="fn", display_name="F", description="")(fake_run)
    svc = ScriptDiscoveryService(tmp_path)
    s = svc.get_script("fn")
    assert s is not None
    assert callable(s.func)
    assert s.name == "fn"


def test_get_script_returns_none_for_unknown(tmp_path):
    """``get_script()`` 对未知名应返回 ``None``。"""
    svc = ScriptDiscoveryService(tmp_path)
    assert svc.get_script("nonexistent") is None


def test_init_logs_warning_when_dir_not_exists(tmp_path, caplog):
    """目录不存在时 ``__init__`` 应记 warning。"""
    import logging
    with caplog.at_level(logging.WARNING):
        ScriptDiscoveryService(tmp_path / "nonexistent")
    assert any("scripts_dir" in rec.message for rec in caplog.records)
