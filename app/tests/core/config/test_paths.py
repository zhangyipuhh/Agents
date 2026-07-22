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

import pytest
from datetime import datetime
from pathlib import Path

from app.core.config import paths as paths_module
from app.core.config.paths import (
    KNOWLEDGE_DIR,
    METADATA_FILE,
    TASK_ATTACHMENT_DIR,
    TASK_ATTACHMENT_SUFFIX,
    TMP_DIR,
    resolve_project_dir,
    resolve_project_tmp_dir,
    resolve_task_attachment_path,
)


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


# ============================================================
# P1: 路径解析函数
# ============================================================


def test_resolve_project_dir():
    """
    P1: resolve_project_dir 将 data/project/... 解析为项目根下的绝对路径。
    """
    relative = "data/project/2026/07/01/uuid-1"
    expected = Path(paths_module._PROJECT_ROOT) / "data" / "project" / "2026" / "07" / "01" / "uuid-1"

    assert resolve_project_dir(relative) == expected


def test_resolve_project_tmp_dir():
    """
    P1: resolve_project_tmp_dir 将 data/project/... 映射为 data/tmp/project/... 绝对路径。
    """
    relative = "data/project/2026/07/01/uuid-1"
    expected = (
        Path(paths_module._PROJECT_ROOT)
        / "data"
        / "tmp"
        / "project"
        / "2026"
        / "07"
        / "01"
        / "uuid-1"
    )

    assert resolve_project_tmp_dir(relative) == expected


def test_resolve_project_dir_empty_raises():
    """
    P1: resolve_project_dir 传入空字符串时抛出 ValueError。
    """
    with pytest.raises(ValueError):
        resolve_project_dir("")


def test_resolve_project_tmp_dir_empty_raises():
    """
    P1: resolve_project_tmp_dir 传入空字符串时抛出 ValueError。
    """
    with pytest.raises(ValueError):
        resolve_project_tmp_dir("")


def test_task_attachment_dir_under_project_root():
    """
    P1: TASK_ATTACHMENT_DIR 位于项目根的 data/attachments/Task 子目录。
    """
    from app.core.config.paths import TASK_ATTACHMENT_DIR

    expected = Path(paths_module._PROJECT_ROOT) / "data" / "attachments" / "Task"

    assert Path(TASK_ATTACHMENT_DIR) == expected
    assert Path(TASK_ATTACHMENT_DIR).is_absolute()


# ============================================================
# P0/P1: resolve_task_attachment_path / TASK_ATTACHMENT_SUFFIX
#   (Phase B 沈阳不动产运维巡检报告 - 附件路径 helper)
# ============================================================


def test_task_attachment_suffix_constant():
    """
    P0: TASK_ATTACHMENT_SUFFIX 常量值为 ``"docx"``。

    与 ``TASK_ATTACHMENT_DIR`` 配合使用，标记默认附件扩展名。
    """
    assert TASK_ATTACHMENT_SUFFIX == "docx"


def test_resolve_task_attachment_path_importable():
    """
    P0: ``resolve_task_attachment_path`` 可从 ``app.core.config.paths`` 导入。
    """
    from app.core.config.paths import resolve_task_attachment_path as fn

    assert callable(fn)


def test_resolve_task_attachment_path_default_suffix():
    """
    P1: ``resolve_task_attachment_path`` 默认生成 ``.docx`` 后缀的附件路径。

    文件名规则：``{YYYYMMDD_HHMMSS}_{run_id}.docx``；父目录为任务名 slug。
    """
    p = resolve_task_attachment_path(
        name="运维巡检任务",
        run_id=42,
        when=datetime(2026, 7, 22, 15, 30, 0),
    )

    assert p.name == "20260722_153000_42.docx"
    assert p.parent.name == "运维巡检任务"  # slug
    assert str(p).endswith(".docx")


def test_resolve_task_attachment_path_custom_suffix():
    """
    P1: ``resolve_task_attachment_path`` 支持自定义文件扩展名（不含 ``.``）。
    """
    p = resolve_task_attachment_path(
        name="x",
        run_id=1,
        when=datetime(2026, 1, 1, 0, 0, 0),
        suffix="pdf",
    )

    assert p.name == "20260101_000000_1.pdf"


def test_resolve_task_attachment_path_uses_attachment_dir():
    """
    P1: ``resolve_task_attachment_path`` 返回的路径位于 ``TASK_ATTACHMENT_DIR`` 下。
    """
    p = resolve_task_attachment_path(
        name="运维巡检任务",
        run_id=42,
        when=datetime(2026, 7, 22, 15, 30, 0),
    )

    expected_root = Path(TASK_ATTACHMENT_DIR).resolve()
    assert p.parent.parent.resolve() == expected_root


def test_resolve_task_attachment_path_slugifies_name():
    """
    P1: 任务名经 ``slugify_task_name`` 安全化后作为目录名片段。

    中文与符号应被替换为下划线，禁止写穿路径或产生隐藏目录。
    """
    p = resolve_task_attachment_path(
        name="运维巡检/任务*",
        run_id=7,
        when=datetime(2026, 7, 22, 0, 0, 0),
    )

    # slug 应过滤斜杠与星号，仅保留字母数字下划线连字符
    assert p.parent.name != "运维巡检/任务*"
    assert "/" not in p.parent.name
    assert "*" not in p.parent.name
    assert p.parent.name  # 非空


def test_resolve_task_attachment_path_validates_run_id():
    """
    P1: ``run_id`` 为 0 / 负数 / None 时抛出 ``ValueError``。
    """
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id=0, when=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id=-1, when=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id=None, when=datetime(2026, 1, 1))


def test_resolve_task_attachment_path_validates_when():
    """
    P1: ``when`` 为 ``None`` 时抛出 ``ValueError``。
    """
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id=1, when=None)


def test_resolve_task_attachment_path_validates_suffix():
    """
    P1: ``suffix`` 为空字符串时抛出 ``ValueError``，防止生成无扩展名文件。
    """
    with pytest.raises(ValueError):
        resolve_task_attachment_path(
            name="x", run_id=1, when=datetime(2026, 1, 1), suffix=""
        )


def test_resolve_task_attachment_path_rejects_non_int_run_id():
    """
    P1: ``run_id`` 必须是 ``int``,不能接受 ``str`` / ``float`` / ``bool``。

    严格类型校验，避免 ``int("1") == 1`` / ``int(1.5) == 1`` / ``int(True) == 1``
    这类隐式转换绕过正整数约束。
    """
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id="1", when=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id=1.5, when=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        resolve_task_attachment_path(name="x", run_id=True, when=datetime(2026, 1, 1))
