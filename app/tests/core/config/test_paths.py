# -*- coding:utf-8 -*-
"""
app/core/config/paths.py 单元测试

覆盖：
- 公共常量可导入
- 私有 _PROJECT_ROOT 等于本仓库根（基于 __file__ 推导）
- KNOWLEDGE_DIR / METADATA_FILE 路径构成正确
- TMP_DIR 是 KNOWLEDGE_DIR 的别名

Date: 2026-06-29
Author: AI Assistant
"""

from pathlib import Path


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_paths_module_importable():
    """
    P0: app.core.config.paths 模块可导入。
    """
    from app.core.config import paths  # noqa: F401

    assert paths is not None


def test_knowledge_dir_importable():
    """
    P0: KNOWLEDGE_DIR 常量可从 app.core.config.paths 导入。
    """
    from app.core.config.paths import KNOWLEDGE_DIR

    assert isinstance(KNOWLEDGE_DIR, str)
    assert KNOWLEDGE_DIR != ""


def test_metadata_file_importable():
    """
    P0: METADATA_FILE 常量可从 app.core.config.paths 导入。
    """
    from app.core.config.paths import METADATA_FILE

    assert isinstance(METADATA_FILE, str)
    assert METADATA_FILE.endswith("metadata.json")


def test_tmp_dir_importable():
    """
    P0: TMP_DIR 常量可从 app.core.config.paths 导入。
    """
    from app.core.config.paths import TMP_DIR

    assert isinstance(TMP_DIR, str)


# ============================================================
# P1: 路径正确性
# ============================================================


def test_private_project_root_matches_repo_root():
    """
    P1: 私有 _PROJECT_ROOT 等于本仓库根（由 __file__ 向上 4 级 dirname）。

    本测试文件位于 app/tests/core/config/test_paths.py，距离项目根共 5 级：
    core/config/test_paths.py -> core/config/ -> core/ -> app/ -> <root>
    而 paths.py 位于 app/core/config/paths.py，距离项目根共 4 级：
    core/config/paths.py -> core/config/ -> core/ -> app/ -> <root>
    两者应解析到同一个项目根。
    """
    from app.core.config import paths as paths_module

    # 通过测试文件自身位置推导项目根
    # test_paths.py -> config/ -> core/ -> tests/ -> app/ -> <root>
    expected_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    actual_root = Path(paths_module._PROJECT_ROOT).resolve()

    assert actual_root == expected_root


def test_knowledge_dir_under_project_root():
    """
    P1: KNOWLEDGE_DIR 位于项目根的 data/Knowledge 子目录。
    """
    from app.core.config import paths as paths_module
    from app.core.config.paths import KNOWLEDGE_DIR

    expected = Path(paths_module._PROJECT_ROOT) / "data" / "Knowledge"

    assert Path(KNOWLEDGE_DIR) == expected


def test_metadata_file_under_tmp_knowledge():
    """
    P1: METADATA_FILE 位于项目根的 data/tmp/Knowledge/metadata.json。
    """
    from app.core.config import paths as paths_module
    from app.core.config.paths import METADATA_FILE

    expected = (
        Path(paths_module._PROJECT_ROOT) / "data" / "tmp" / "Knowledge" / "metadata.json"
    )

    assert Path(METADATA_FILE) == expected


def test_tmp_dir_is_knowledge_dir_alias():
    """
    P1: TMP_DIR 是 KNOWLEDGE_DIR 的别名（字符串值相等）。
    """
    from app.core.config.paths import KNOWLEDGE_DIR, TMP_DIR

    assert TMP_DIR == KNOWLEDGE_DIR


def test_knowledge_dir_is_absolute():
    """
    P1: KNOWLEDGE_DIR 是绝对路径（不在依赖调用方 CWD）。
    """
    from app.core.config.paths import KNOWLEDGE_DIR

    assert Path(KNOWLEDGE_DIR).is_absolute()
