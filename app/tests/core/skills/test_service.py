# -*- coding:utf-8 -*-
"""
SkillsService 单元测试。

覆盖单例生命周期、skill 查询、按 agent 维度隔离扫描以及
agent skills/ 目录对默认根的覆盖行为。
"""

from pathlib import Path

import pytest

from app.core.skills.schemas import SkillsConfig
from app.core.skills.service import SkillNotFoundError, SkillsService


def _write_skill(path: Path, name: str, description: str | None = None, body: str = "skill body\n") -> Path:
    """
    在指定目录写入 SKILL.md 文件。

    Args:
        path: SKILL.md 所在的目录。
        name: frontmatter 中的 name 字段。
        description: frontmatter 中的 description 字段（可选）。
        body: 去除 frontmatter 后的正文。

    Returns:
        写入的 SKILL.md 文件路径。
    """
    path.mkdir(parents=True, exist_ok=True)
    md = path / "SKILL.md"
    fm = f"name: {name}\n"
    if description is not None:
        fm += f"description: {description}\n"
    md.write_text(f"---\n{fm}---\n{body}", encoding="utf-8")
    return md


@pytest.fixture(autouse=True)
def _reset_singleton():
    """
    每个用例前后清空 SkillsService 单例缓存，避免状态泄漏。

    Yields:
        None
    """
    SkillsService.reset()
    yield
    SkillsService.reset()


def test_singleton_returns_same_instance(monkeypatch, tmp_path: Path):
    """
    两次 get_instance() 调用返回同一个实例。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    first = SkillsService.get_instance(SkillsConfig())
    second = SkillsService.get_instance(SkillsConfig())

    assert first is second


def test_reset_clears_instance(monkeypatch, tmp_path: Path):
    """
    reset() 后再次 get_instance() 会重建新实例。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)

    first = SkillsService.get_instance(SkillsConfig())
    SkillsService.reset()
    second = SkillsService.get_instance(SkillsConfig())

    assert first is not second


def test_get_returns_skill_when_present(tmp_path: Path):
    """
    get(name) 返回已加载的 SkillInfo。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a", "first skill")

    service = SkillsService(SkillsConfig(), project_root=tmp_path)
    info = service.get("a")

    assert info is not None
    assert info.name == "a"
    assert info.description == "first skill"


def test_get_returns_none_when_absent(tmp_path: Path):
    """
    get(name) 在 skill 不存在时返回 None。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    assert service.get("nope") is None


def test_require_raises_with_available_list(tmp_path: Path):
    """
    require(name) 在 skill 不存在时抛出 SkillNotFoundError，且消息包含可用 skill 列表。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a")
    _write_skill(tmp_path / "app" / "skills" / "b", "b")

    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    with pytest.raises(SkillNotFoundError) as exc_info:
        service.require("nope")

    error = exc_info.value
    assert error.name == "nope"
    assert set(error.available) == {"a", "b"}
    message = str(error)
    assert "nope" in message
    assert "a" in message
    assert "b" in message


def test_all_returns_all_skills(tmp_path: Path):
    """
    all() 返回所有已加载的 skill。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a")
    _write_skill(tmp_path / "app" / "skills" / "b", "b")

    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    assert {skill.name for skill in service.all()} == {"a", "b"}


def test_available_with_filter(tmp_path: Path):
    """
    available(name_filter) 仅返回过滤器中存在的 skill，保持过滤器的顺序。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a")
    _write_skill(tmp_path / "app" / "skills" / "b", "b")

    service = SkillsService(SkillsConfig(), project_root=tmp_path)
    skills = service.available(["b", "c", "a"])

    assert [skill.name for skill in skills] == ["b", "a"]


def test_available_without_filter_returns_all(tmp_path: Path):
    """
    available(None) 返回所有已加载的 skill。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    _write_skill(tmp_path / "app" / "skills" / "a", "a")
    _write_skill(tmp_path / "app" / "skills" / "b", "b")

    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    assert {skill.name for skill in service.available(None)} == {"a", "b"}


def test_get_instance_with_agent_name_uses_agent_skills_dir(monkeypatch, tmp_path: Path):
    """
    指定 agent_name 且 app/features/<agent>/skills/ 存在时，仅扫描 agent 目录。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    _write_skill(tmp_path / "app" / "skills" / "a", "a", "default")
    _write_skill(tmp_path / "app" / "features" / "map_agent" / "skills" / "b", "b", "agent")

    service = SkillsService.get_instance(SkillsConfig(), agent_name="map_agent")

    assert service.get("a") is None
    assert service.get("b") is not None
    assert service.get("b").description == "agent"


def test_get_instance_with_agent_name_falls_back_to_defaults(monkeypatch, tmp_path: Path):
    """
    指定 agent_name 但对应 skills/ 目录不存在时，回退到默认根扫描。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    _write_skill(tmp_path / "app" / "skills" / "a", "a", "default")

    service = SkillsService.get_instance(SkillsConfig(), agent_name="map_agent")

    assert service.get("a") is not None
    assert service.get("a").description == "default"


def test_get_instance_agent_overrides_default_roots(monkeypatch, tmp_path: Path):
    """
    agent skills/ 目录中的同名 skill 覆盖默认根中的 skill。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    _write_skill(tmp_path / "app" / "skills" / "a", "a", "default")
    _write_skill(tmp_path / "app" / "features" / "map_agent" / "skills" / "a", "a", "agent")

    service = SkillsService.get_instance(SkillsConfig(), agent_name="map_agent")

    assert service.get("a").description == "agent"


def test_get_instance_per_agent_creates_separate_instance(monkeypatch, tmp_path: Path):
    """
    相同配置但不同 agent_name 返回不同的 SkillsService 实例。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    _write_skill(tmp_path / "app" / "skills" / "a", "a", "default")
    _write_skill(tmp_path / "app" / "features" / "map_agent" / "skills" / "b", "b", "agent")

    default_service = SkillsService.get_instance(SkillsConfig())
    agent_service = SkillsService.get_instance(SkillsConfig(), agent_name="map_agent")

    assert default_service is not agent_service
    assert default_service.get("a") is not None
    assert default_service.get("b") is None
    assert agent_service.get("a") is None
    assert agent_service.get("b") is not None


# =============================================================================
# 路径解析（_resolve）单元测试
# =============================================================================


def test_resolve_expands_tilde_to_home(tmp_path: Path, monkeypatch):
    """
    ~/foo 形式的扩展路径会通过 Path.expanduser 展开到用户主目录。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    home_skills = tmp_path / "home_skills"
    monkeypatch.setenv("HOME", str(home_skills))
    monkeypatch.setenv("USERPROFILE", str(home_skills))

    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    resolved = service._resolve("~/my_skills")

    assert resolved == (home_skills / "my_skills").resolve()


def test_resolve_absolute_path_unchanged(tmp_path: Path):
    """
    绝对路径会被保留，仅经 .resolve() 归一化。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    abs_path = tmp_path / "abs" / "skills"
    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    resolved = service._resolve(str(abs_path))

    assert resolved.is_absolute()
    assert resolved == abs_path.resolve()


def test_resolve_relative_path_joins_project_root(tmp_path: Path):
    """
    相对路径会与 project_root 拼接后再 resolve。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    service = SkillsService(SkillsConfig(), project_root=tmp_path)

    resolved = service._resolve("relative/path")

    assert resolved == (tmp_path / "relative" / "path").resolve()


def test_scan_passes_resolved_paths_to_loader(tmp_path: Path, monkeypatch):
    """
    端到端验证：service._scan() 把已 resolve 的绝对路径直接交给 SkillDiscovery.scan()，
    loader 不再二次做 ~ 展开或 project_root 拼接。

    Args:
        tmp_path: pytest 提供的临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    extra_dir = tmp_path / "extra_skills"
    _write_skill(extra_dir / "extra", "extra", "extra skill")

    # 捕获传给 SkillDiscovery.scan 的 extra_paths，验证它是已 resolve 的绝对路径
    captured: dict[str, list[Path]] = {}
    original_scan = SkillsService.__module__

    def _spy_scan(self, project_root: Path, extra_paths: list[Path]) -> dict:
        captured["project_root"] = project_root
        captured["extra_paths"] = list(extra_paths)
        # 不真正扫描，避免覆盖默认根；返回空 dict
        return {}

    from app.core.skills import loader as loader_module

    monkeypatch.setattr(loader_module.SkillDiscovery, "scan", _spy_scan)

    config = SkillsConfig(paths=[str(extra_dir)])
    service = SkillsService(config, project_root=tmp_path)
    service._scan()

    assert captured["extra_paths"] == [extra_dir.resolve()]
    # 同时验证绝对路径不会被错误地拼上 project_root
    assert all(p.is_absolute() for p in captured["extra_paths"])

