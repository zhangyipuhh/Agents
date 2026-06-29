# -*- coding:utf-8 -*-
"""
SkillRegistryService 测试模块

验证 skill 注册中心服务模块的可导入性与基本存在性。
"""
from app.shared.utils.agent.skill_service import (
    SkillRow,
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
