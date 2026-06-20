# -*- coding:utf-8 -*-
"""
SkillsAwarePrompt 单元测试。

覆盖 system prompt 拼接顺序、空参数处理、无可用 skill 提示、
agent bootstrap 路径透传以及 Runnable 返回类型。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import Runnable

from app.core.skills.message_transformer import SkillsAwarePrompt
from app.core.skills.schemas import SkillInfo, SkillsConfig


@pytest.fixture
def fake_service(monkeypatch):
    """
    返回并注入伪造的 SkillsService 实例，避免真实文件系统扫描。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        伪造的 SkillsService 实例。
    """
    service = MagicMock()
    service.all.return_value = []
    service.config = SkillsConfig(bootstrap_path="user/bootstrap.md")

    def _get_instance(*, agent_name=None, config=None):
        return service

    monkeypatch.setattr(
        "app.core.skills.message_transformer.SkillsService.get_instance",
        _get_instance,
    )
    return service


@pytest.fixture
def stub_bootstrap(monkeypatch):
    """
    将 BootstrapProvider.render 替换为返回固定 bootstrap 块的存根。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    monkeypatch.setattr(
        "app.core.skills.message_transformer.BootstrapProvider.render",
        lambda self, *, agent_bootstrap_path=None, user_global_path=None: (
            "<EXTREMELY_IMPORTANT>\nBOOTSTRAP\n</EXTREMELY_IMPORTANT>"
        ),
    )


@pytest.fixture
def stub_skills_block(monkeypatch):
    """
    将 render_available_skills_block 替换为返回固定 skills 块的存根。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    monkeypatch.setattr(
        "app.core.skills.message_transformer.render_available_skills_block",
        lambda skills: "<available_skills>SKILLS</available_skills>",
    )


def test_build_order_is_base_agent_bootstrap_skills(
    fake_service, stub_bootstrap, stub_skills_block
):
    """
    build() 输出应严格按照 base → agent_specific → bootstrap → available_skills 顺序拼接。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        stub_bootstrap: bootstrap 渲染存根 fixture。
        stub_skills_block: skills 块渲染存根 fixture。

    Returns:
        None
    """
    fake_service.all.return_value = [
        SkillInfo(
            name="demo",
            description="demo skill",
            location="/tmp/SKILL.md",
            content="body",
            base_dir="/tmp",
        )
    ]

    prompt = SkillsAwarePrompt(
        base="BASE_PART",
        agent_specific="AGENT_PART",
        agent_name="map_agent",
    )
    result = prompt.build()

    base_pos = result.index("BASE_PART")
    agent_pos = result.index("AGENT_PART")
    bootstrap_pos = result.index("<EXTREMELY_IMPORTANT>")
    skills_pos = result.index("<available_skills>")

    assert base_pos < agent_pos < bootstrap_pos < skills_pos


def test_build_includes_all_four_parts(
    fake_service, stub_bootstrap, stub_skills_block
):
    """
    build() 输出应同时包含 base、agent_specific、bootstrap 和 available_skills 四部分。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        stub_bootstrap: bootstrap 渲染存根 fixture。
        stub_skills_block: skills 块渲染存根 fixture。

    Returns:
        None
    """
    prompt = SkillsAwarePrompt(
        base="BASE_PART",
        agent_specific="AGENT_PART",
        agent_name="map_agent",
    )
    result = prompt.build()

    assert "BASE_PART" in result
    assert "AGENT_PART" in result
    assert "<EXTREMELY_IMPORTANT>" in result
    assert "</EXTREMELY_IMPORTANT>" in result
    assert "<available_skills>" in result


def test_build_with_empty_agent_specific(fake_service, stub_bootstrap, stub_skills_block):
    """
    agent_specific 为空字符串时，build() 仍应返回有效字符串并包含其他部分。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        stub_bootstrap: bootstrap 渲染存根 fixture。
        stub_skills_block: skills 块渲染存根 fixture。

    Returns:
        None
    """
    prompt = SkillsAwarePrompt(
        base="BASE_PART",
        agent_specific="",
        agent_name="map_agent",
    )
    result = prompt.build()

    assert isinstance(result, str)
    assert "BASE_PART" in result
    assert "<EXTREMELY_IMPORTANT>" in result
    assert "<available_skills>" in result


def test_build_with_empty_base(fake_service, stub_bootstrap, stub_skills_block):
    """
    base 为空字符串时，build() 仍应返回有效字符串，并以 agent_specific 开头。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        stub_bootstrap: bootstrap 渲染存根 fixture。
        stub_skills_block: skills 块渲染存根 fixture。

    Returns:
        None
    """
    prompt = SkillsAwarePrompt(
        base="",
        agent_specific="AGENT_PART",
        agent_name="map_agent",
    )
    result = prompt.build()

    assert isinstance(result, str)
    assert result.startswith("AGENT_PART")
    assert "<EXTREMELY_IMPORTANT>" in result
    assert "<available_skills>" in result


def test_build_with_no_skills_returns_no_skills_message(fake_service, stub_bootstrap):
    """
    service 没有加载任何 skill 时，build() 输出应包含 "No skills are currently available."。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        stub_bootstrap: bootstrap 渲染存根 fixture。

    Returns:
        None
    """
    fake_service.all.return_value = []

    prompt = SkillsAwarePrompt(
        base="BASE_PART",
        agent_specific="AGENT_PART",
    )
    result = prompt.build()

    assert "No skills are currently available." in result


def test_build_passes_agent_bootstrap_to_bootstrap_provider(fake_service, monkeypatch):
    """
    传入 agent_name 时，build() 应将 agent bootstrap 路径透传给 BootstrapProvider.render。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    captured = {}

    def _fake_render(self, *, agent_bootstrap_path=None, user_global_path=None):
        """记录 render 接收到的参数并返回固定 bootstrap 块。"""
        captured["agent_bootstrap_path"] = agent_bootstrap_path
        captured["user_global_path"] = user_global_path
        return "<EXTREMELY_IMPORTANT>\nBOOTSTRAP\n</EXTREMELY_IMPORTANT>"

    monkeypatch.setattr(
        "app.core.skills.message_transformer.BootstrapProvider.render",
        _fake_render,
    )
    fake_service.config = SkillsConfig(bootstrap_path="global/bootstrap.md")

    prompt = SkillsAwarePrompt(
        base="BASE_PART",
        agent_specific="AGENT_PART",
        agent_name="test_agent",
    )
    prompt.build()

    assert captured["agent_bootstrap_path"] == str(
        Path("app/features/test_agent/config/bootstrap.md")
    )
    assert captured["user_global_path"] == "global/bootstrap.md"


def test_as_runnable_returns_runnable(fake_service, stub_bootstrap, stub_skills_block):
    """
    as_runnable() 应返回 langchain Runnable 实例，且调用结果与 build() 一致。

    Args:
        fake_service: 伪造的 SkillsService 实例。
        stub_bootstrap: bootstrap 渲染存根 fixture。
        stub_skills_block: skills 块渲染存根 fixture。

    Returns:
        None
    """
    prompt = SkillsAwarePrompt(
        base="BASE_PART",
        agent_specific="AGENT_PART",
    )
    runnable = prompt.as_runnable()

    assert isinstance(runnable, Runnable)
    assert runnable.invoke({}) == prompt.build()
