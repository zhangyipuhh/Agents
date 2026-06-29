# -*- coding:utf-8 -*-
"""
SkillRegistryService 测试模块

验证 skill 注册中心服务的核心功能：
1. 可导入性与基本存在性
2. 写方法写 DB 后同步刷新缓存（update_skill）
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.shared.utils.agent.skill_service import (
    SkillRegistryService,
    SkillRow,
    SkillNotFoundError,
    _PROJECT_ROOT,
)


def test_skill_service_importable():
    """测试 skill_service 模块可导入且包含核心类与异常。"""
    from app.shared.utils.agent import skill_service
    assert hasattr(skill_service, "SkillRegistryService")
    assert hasattr(skill_service, "SkillRow")
    assert hasattr(skill_service, "SkillNotFoundError")
    assert hasattr(skill_service, "SkillAlreadyExistsError")


def test_skill_row_dataclass_has_all_fields():
    """测试 SkillRow dataclass 包含所有必需字段。"""
    row = SkillRow(
        name="data-skill",
        display_name="数据 Skill",
        category="data",
        description="测试描述",
        location="/tmp/app/skills/data-skill/SKILL.md",
        base_dir="/tmp/app/skills/data-skill",
        content="# 正文",
        enabled=True,
        sort_order=1,
    )
    assert row.name == "data-skill"
    assert row.enabled is True
    assert row.sort_order == 1


def test_project_root_points_to_repo_root():
    """测试 _PROJECT_ROOT 指向仓库根目录。"""
    from pathlib import Path
    assert isinstance(_PROJECT_ROOT, Path)
    assert (_PROJECT_ROOT / "app" / "core" / "skills").exists()


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
