# -*- coding:utf-8 -*-
"""
SkillRegistryService 测试模块

验证 skill 注册中心服务的核心功能：
1. 可导入性与基本存在性
2. 写方法写 DB 后同步刷新缓存（update_skill）
3. 路径归一化工具方法（_to_relative / _to_absolute / get_project_root）
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.shared.utils.agent.skill_service import (
    SkillRegistryService,
    SkillRow,
    SkillNotFoundError,
    get_project_root,
)


def test_skill_service_importable():
    """测试 skill_service 模块可导入且包含核心类与异常。"""
    from app.shared.utils.agent import skill_service
    assert hasattr(skill_service, "SkillRegistryService")
    assert hasattr(skill_service, "SkillRow")
    assert hasattr(skill_service, "SkillNotFoundError")
    assert hasattr(skill_service, "SkillAlreadyExistsError")
    assert hasattr(skill_service, "get_project_root")
    assert hasattr(SkillRegistryService, "_to_relative")
    assert hasattr(SkillRegistryService, "_to_absolute")


def test_skill_row_dataclass_has_all_fields():
    """测试 SkillRow dataclass 包含所有必需字段。"""
    row = SkillRow(
        name="data-skill",
        display_name="数据 Skill",
        category="data",
        description="测试描述",
        location="app/skills/data-skill/SKILL.md",
        base_dir="app/skills/data-skill",
        content="# 正文",
        enabled=True,
        sort_order=1,
    )
    assert row.name == "data-skill"
    assert row.enabled is True
    assert row.sort_order == 1


def test_project_root_points_to_repo_root():
    """测试 get_project_root() 指向仓库根目录。"""
    root = get_project_root()
    assert isinstance(root, Path)
    assert (root / "app" / "core" / "skills").exists()


# ==================== 路径归一化工具方法测试 ====================


def test_to_relative_under_project_root(tmp_path: Path):
    """路径在 project_root 下时返回 POSIX 形式相对路径（无反斜杠）。"""
    target = (tmp_path / "app" / "skills" / "x" / "SKILL.md").resolve()

    rel = SkillRegistryService._to_relative(target, tmp_path)

    assert rel == "app/skills/x/SKILL.md"
    assert "\\" not in rel


def test_to_relative_fallback_outside_project_root(tmp_path: Path):
    """路径不在 project_root 下时降级返回原绝对路径的 POSIX 形式。

    使用与 tmp_path 同级的 sibling 目录，确保目标路径不在 project_root 子树下。
    """
    sibling = tmp_path.parent / "sibling_dir_for_fallback_test_svc"
    sibling.mkdir(exist_ok=True)
    other = sibling / "SKILL.md"

    rel = SkillRegistryService._to_relative(other, tmp_path)

    assert rel == other.resolve().as_posix()


def test_to_absolute_relative_path(tmp_path: Path):
    """相对路径字符串与 project_root 拼接后返回绝对路径。"""
    abs_path = SkillRegistryService._to_absolute("app/skills/x/SKILL.md", tmp_path)

    assert abs_path.is_absolute()
    assert abs_path == (tmp_path / "app" / "skills" / "x" / "SKILL.md").resolve()


def test_to_absolute_empty_string_returns_project_root(tmp_path: Path):
    """空字符串降级返回 project_root（防御性，避免 iterdir 抛错）。"""
    abs_path = SkillRegistryService._to_absolute("", tmp_path)

    assert abs_path == tmp_path.resolve()


# ==================== 写方法测试（写 DB + 同步缓存） ====================


def test_update_skill_updates_and_refreshes_cache():
    """测试 update_skill：更新 DB 并刷新缓存。"""
    db = MagicMock()
    existing = {
        "name": "skill", "display_name": "原名称", "category": "c",
        "description": "原描述", "location": "loc", "base_dir": "dir",
        "content": "正文", "enabled": True, "sort_order": 0,
    }
    updated = {
        "name": "skill", "display_name": "更新后", "category": "c",
        "description": "原描述", "location": "loc", "base_dir": "dir",
        "content": "正文", "enabled": True, "sort_order": 0,
    }
    # 三次 fetchrow：1) SELECT 现有记录 2) UPDATE RETURNING 3) _refresh_cache SELECT
    db.fetchrow = AsyncMock(side_effect=[existing, updated, updated])
    service = SkillRegistryService(db)

    result = asyncio.run(service.update_skill("skill", {"display_name": "更新后"}))
    assert result["display_name"] == "更新后"
    assert "skill" in service._cache


def test_update_skill_preserves_unsent_fields():
    """测试 update_skill：未传入字段保持数据库原值，不被清空。"""
    db = MagicMock()
    existing = {
        "name": "skill", "display_name": "原名称", "category": "c",
        "description": "原描述", "location": "loc", "base_dir": "dir",
        "content": "正文", "enabled": True, "sort_order": 1,
    }
    updated = {
        "name": "skill", "display_name": "原名称", "category": "新分类",
        "description": "原描述", "location": "loc", "base_dir": "dir",
        "content": "正文", "enabled": True, "sort_order": 1,
    }
    # 三次 fetchrow：1) SELECT 现有记录 2) UPDATE RETURNING 3) _refresh_cache SELECT
    db.fetchrow = AsyncMock(side_effect=[existing, updated, updated])
    service = SkillRegistryService(db)

    result = asyncio.run(service.update_skill("skill", {"category": "新分类"}))
    assert result["category"] == "新分类"
    assert result["description"] == "原描述"
    assert result["location"] == "loc"
    assert result["base_dir"] == "dir"
    assert result["content"] == "正文"
    assert result["sort_order"] == 1


def test_update_skill_raises_on_not_found():
    """测试 update_skill：skill 不存在时抛出 SkillNotFoundError。"""
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)  # SELECT 无结果
    service = SkillRegistryService(db)

    with pytest.raises(SkillNotFoundError):
        asyncio.run(service.update_skill("missing", {"display_name": "x"}))
