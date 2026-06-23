# -*- coding:utf-8 -*-
"""
AGENTS.md 加载器测试模块

验证 AgentsMdLoader 能从指定路径读取 markdown 文件内容，缓存结果，
文件不存在时抛出 FileNotFoundError。
"""
import pytest
from pathlib import Path
from app.shared.utils.agent.agents_md_loader import AgentsMdLoader


def test_loader_importable():
    """测试 agents_md_loader 模块可导入。"""
    from app.shared.utils.agent import agents_md_loader
    assert hasattr(agents_md_loader, "AgentsMdLoader")


def test_loader_reads_markdown_content(tmp_path: Path):
    """测试加载器能读取 markdown 文件内容。

    参数:
        tmp_path: pytest 提供的临时目录 Path 对象

    返回:
        None
    """
    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("# 测试智能体\n\n## 身份\n这是测试。", encoding="utf-8")

    loader = AgentsMdLoader()
    content = loader.load(str(md_file))
    assert "# 测试智能体" in content
    assert "## 身份" in content


def test_loader_caches_content(tmp_path: Path):
    """测试同一路径第二次加载走缓存。

    参数:
        tmp_path: pytest 提供的临时目录 Path 对象

    返回:
        None
    """
    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("v1", encoding="utf-8")

    loader = AgentsMdLoader()
    content1 = loader.load(str(md_file))
    assert content1 == "v1"

    md_file.write_text("v2", encoding="utf-8")
    content2 = loader.load(str(md_file))
    assert content2 == "v1"


def test_loader_raises_on_missing_file():
    """测试文件不存在时抛出 FileNotFoundError。

    参数:
        None

    返回:
        None

    异常:
        FileNotFoundError: 当加载不存在的文件路径时预期抛出
    """
    loader = AgentsMdLoader()
    with pytest.raises(FileNotFoundError, match="AGENTS.md not found"):
        loader.load("/non/existent/path/AGENTS.md")


def test_loader_clear_cache(tmp_path: Path):
    """测试 clear_cache 后重新加载读取最新内容。

    参数:
        tmp_path: pytest 提供的临时目录 Path 对象

    返回:
        None
    """
    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("v1", encoding="utf-8")

    loader = AgentsMdLoader()
    loader.load(str(md_file))
    md_file.write_text("v2", encoding="utf-8")

    loader.clear_cache()
    content = loader.load(str(md_file))
    assert content == "v2"
