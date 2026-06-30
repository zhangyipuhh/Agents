# -*- coding:utf-8 -*-
"""
load_skill / read_skill_file 工具单元测试。

被测对象位于 app.core.tools.SkillTools（自 2026-06-26 从 app.core.skills.tool 迁移）。

load_skill：覆盖成功加载返回 XML 块、包含 base_dir URI、文件列表过滤、skill 不存在时返回错误、
文件数量限制为 10 以及 @tool 装饰器注册验证。

read_skill_file：覆盖绝对路径读取、存在性校验、白名单校验、大小校验、UTF-8 校验、
parent_skill 识别以及 @tool 装饰器注册验证。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from app.core.skills.schemas import SkillInfo
from app.core.skills.service import SkillNotFoundError


class _RealToolMessage:
    """
    真实可断言的 ToolMessage 替身。

    conftest 将 langchain_core.messages.ToolMessage 整体 mock 为 Mock()，
    构造出的对象属性访问仍返回 Mock，无法对 content / tool_call_id 做字符串断言。
    本类提供 content / tool_call_id 两个真实属性，patch 后 SkillTools 内的
    ToolMessage(content=..., tool_call_id=...) 调用会生成可断言的实例。
    """

    def __init__(self, content, tool_call_id):
        self.content = content
        self.tool_call_id = tool_call_id


def _make_service_mock(info: SkillInfo | None = None, available: list[str] | None = None) -> MagicMock:
    """
    构造一个用于替换 SkillsService.get_instance() 返回值的 mock 服务。

    Args:
        info: 调用 require 时返回的 SkillInfo；为 None 时抛出 SkillNotFoundError。
        available: skill 不存在时异常中包含的可用 skill 列表。

    Returns:
        配置好的 MagicMock 服务实例。
    """
    service = MagicMock()
    # 同时支持 .get(name)（新代码 _resolve_skill_with_fallback 使用）与
    # .require(name)（旧调用方可能仍在使用）
    service.get.return_value = info

    def _require(name: str) -> SkillInfo:
        if info is None:
            raise SkillNotFoundError(name, available or [])
        return info

    service.require.side_effect = _require
    return service


@pytest.fixture(autouse=True)
def _reset_singleton():
    """
    每个用例前后清空 SkillsService 单例缓存，避免状态泄漏。

    Yields:
        None
    """
    from app.core.skills.service import SkillsService

    SkillsService.reset()
    yield
    SkillsService.reset()


@pytest.fixture(autouse=True)
def _patch_tool_message():
    """
    将 SkillTools 模块内的 ToolMessage 替换为 _RealToolMessage，使 Command 中的
    ToolMessage 实例具有可断言的真实 content / tool_call_id 属性。

    Yields:
        None
    """
    with patch("app.core.tools.SkillTools.ToolMessage", _RealToolMessage):
        yield


def _unwrap(result):
    """
    从 load_skill 返回的 Command 中解包出 ToolMessage.content 字符串。

    Args:
        result: load_skill.invoke() 的返回值，应为 Command 实例。

    Returns:
        Command.update["messages"][0].content 字符串。

    Raises:
        AssertionError: 当 result 不是 Command 或 messages 数量不为 1 时。
    """
    assert isinstance(result, Command)
    messages = result.update["messages"]
    assert len(messages) == 1
    return messages[0].content


def test_load_skill_returns_skill_content_block(monkeypatch, tmp_path: Path):
    """
    成功加载时返回 Command，content 含 <skill_content>、正文与 <skill_files> 的 XML 块。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="This is the alpha skill body.",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert "<skill_content name=\"alpha\">" in content
    assert "This is the alpha skill body." in content
    assert "<skill_files>" in content
    assert "</skill_files>" in content
    # 验证 tool_call_id 透传
    assert result.update["messages"][0].tool_call_id == "test-tool-call-id"


def test_load_skill_includes_base_dir_uri(monkeypatch, tmp_path: Path):
    """
    返回结果中包含 skill 所在目录的 file:/// URI。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert "Base directory for this skill: file:///" in content


def test_load_skill_includes_file_list(monkeypatch, tmp_path: Path):
    """
    base_dir 包含 SKILL.md 与另外两个文件时，返回结果列出这两个文件。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    (base_dir / "SKILL.md").write_text("---\nname: alpha\n---\nbody", encoding="utf-8")
    (base_dir / "script.py").write_text("# script", encoding="utf-8")
    (base_dir / "reference.md").write_text("# reference", encoding="utf-8")
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.count("<file>") == 2
    assert "script.py" in content
    assert "reference.md" in content
    assert "SKILL.md" not in content.split("<skill_files>")[1].split("</skill_files>")[0]


def test_load_skill_returns_error_for_missing_skill(monkeypatch):
    """
    require 抛出 SkillNotFoundError 时，工具返回 Command，content 以 Error: 开头且不传播异常。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        None
    """
    service = _make_service_mock(None, available=["alpha", "bravo"])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import load_skill

    result = load_skill.invoke({"name": "nope"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "nope" in content


def test_load_skill_limits_files_to_10(monkeypatch, tmp_path: Path):
    """
    base_dir 包含 15 个非 SKILL.md 文件时，返回结果最多列出 10 个。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    (base_dir / "SKILL.md").write_text("---\nname: alpha\n---\nbody", encoding="utf-8")
    for i in range(15):
        (base_dir / f"file_{i:02d}.txt").write_text(f"content {i}", encoding="utf-8")
    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.count("<file>") == 10


def test_load_skill_tool_is_registered_as_langchain_tool():
    """
    导入的 load_skill 已被 @tool 注册为 LangChain 工具，具备 invoke 方法。

    Returns:
        None
    """
    from app.core.tools.SkillTools import load_skill

    assert hasattr(load_skill, "invoke")


# ---------------------------------------------------------------------------
# read_skill_file 测试
# ---------------------------------------------------------------------------


def _make_service_with_skills(skills: list[SkillInfo]) -> MagicMock:
    """
    构造一个用于替换 SkillsService.get_instance() 的 mock 服务，
    其 .all() 返回给定的 skill 列表（read_skill_file 白名单校验使用）。

    Args:
        skills: 预注册的 SkillInfo 列表。

    Returns:
        MagicMock: 配置好的 mock 服务。
    """
    service = MagicMock()
    service.all.return_value = skills
    return service


def test_read_skill_file_returns_file_content(monkeypatch, tmp_path: Path):
    """
    路径在某个 skill base_dir 下时，返回 <skill_file> XML 块、含正文、parent_skill、size。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    target = base_dir / "scripts" / "run.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('hello')\n", encoding="utf-8")

    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location=str(base_dir / "SKILL.md"),
        content="body",
        base_dir=str(base_dir),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    result = read_skill_file.invoke({"file_path": str(target)})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("<skill_file ")
    assert 'parent_skill="alpha"' in content
    assert f'path="file:///{target.resolve().as_posix().lstrip("/")}"' in content or \
           f'path="{target.as_uri()}"' in content
    assert "print('hello')" in content
    assert content.rstrip().endswith("</skill_file>")
    # tool_call_id 透传
    assert result.update["messages"][0].tool_call_id == "test-tool-call-id"


def test_read_skill_file_returns_error_for_missing_file(monkeypatch, tmp_path: Path):
    """
    file_path 不存在时返回 Error: File not found 字符串，不抛异常。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    missing = base_dir / "absent.py"
    info = SkillInfo(
        name="alpha",
        description="",
        location=str(base_dir / "SKILL.md"),
        content="",
        base_dir=str(base_dir),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    result = read_skill_file.invoke({"file_path": str(missing)})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "File not found" in content


def test_read_skill_file_returns_error_for_directory(monkeypatch, tmp_path: Path):
    """
    file_path 指向目录而非文件时返回 Error: Not a regular file。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha" / "scripts"
    base_dir.mkdir(parents=True)
    info = SkillInfo(
        name="alpha",
        description="",
        location=str(tmp_path / "skills" / "alpha" / "SKILL.md"),
        content="",
        base_dir=str(tmp_path / "skills" / "alpha"),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    result = read_skill_file.invoke({"file_path": str(base_dir)})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "Not a regular file" in content


def test_read_skill_file_rejects_path_outside_skill_dir(monkeypatch, tmp_path: Path):
    """
    绝对路径在 /tmp 下但不在任何已注册 skill base_dir 内时返回拒绝错误。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    # 已注册 skill 在 tmp_path/skills/alpha,但目标文件在 tmp_path/elsewhere
    skill_dir = tmp_path / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere" / "secret.txt"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text("top secret", encoding="utf-8")

    info = SkillInfo(
        name="alpha",
        description="",
        location=str(skill_dir / "SKILL.md"),
        content="",
        base_dir=str(skill_dir),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    result = read_skill_file.invoke({"file_path": str(elsewhere)})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "not within any registered skill directory" in content


def test_read_skill_file_rejects_relative_path(monkeypatch, tmp_path: Path):
    """
    相对路径（resolve 后指向真实存在但不在 skill 目录的文件）应被白名单拒绝。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    # skill 目录在 tmp_path/skills/alpha
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    # 真实文件在 tmp_path/outside/secret.txt —— 不在 skill 目录内
    external = tmp_path / "outside" / "secret.txt"
    external.parent.mkdir(parents=True)
    external.write_text("external", encoding="utf-8")

    info = SkillInfo(
        name="alpha",
        description="",
        location=str(base_dir / "SKILL.md"),
        content="",
        base_dir=str(base_dir),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )
    # 切到 tmp_path，让 external 可用相对路径表示
    monkeypatch.chdir(tmp_path)

    from app.core.tools.SkillTools import read_skill_file

    # 相对路径 "outside/secret.txt" resolve 后 = tmp_path/outside/secret.txt（真实存在），
    # 但不在 skills/alpha 内，应被白名单拒绝
    result = read_skill_file.invoke({"file_path": "outside/secret.txt"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "not within any registered skill directory" in content


def test_read_skill_file_rejects_oversized_file(monkeypatch, tmp_path: Path):
    """
    1.5 MB 文件应被拒绝，返回 File too large 错误。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    big = base_dir / "big.bin"
    # 写 1.5 MB（>1 MB 上限）
    big.write_bytes(b"a" * (1_572_864))  # 1.5 * 1024 * 1024

    info = SkillInfo(
        name="alpha",
        description="",
        location=str(base_dir / "SKILL.md"),
        content="",
        base_dir=str(base_dir),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    result = read_skill_file.invoke({"file_path": str(big)})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "File too large" in content
    assert "max 1 MB" in content


def test_read_skill_file_identifies_correct_parent_skill(monkeypatch, tmp_path: Path):
    """
    多个 skill 同时存在时，能正确识别文件所属的 skill 名称。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    alpha_dir = tmp_path / "skills" / "alpha"
    bravo_dir = tmp_path / "skills" / "bravo"
    alpha_dir.mkdir(parents=True)
    bravo_dir.mkdir(parents=True)

    alpha_file = alpha_dir / "alpha_doc.md"
    bravo_file = bravo_dir / "bravo_doc.md"
    alpha_file.write_text("# alpha doc", encoding="utf-8")
    bravo_file.write_text("# bravo doc", encoding="utf-8")

    info_alpha = SkillInfo(
        name="alpha",
        description="",
        location=str(alpha_dir / "SKILL.md"),
        content="",
        base_dir=str(alpha_dir),
    )
    info_bravo = SkillInfo(
        name="bravo",
        description="",
        location=str(bravo_dir / "SKILL.md"),
        content="",
        base_dir=str(bravo_dir),
    )
    service = _make_service_with_skills([info_alpha, info_bravo])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    # 读 alpha 文件
    result_a = read_skill_file.invoke({"file_path": str(alpha_file)})
    content_a = _unwrap(result_a)
    assert 'parent_skill="alpha"' in content_a
    assert 'parent_skill="bravo"' not in content_a

    # 读 bravo 文件
    result_b = read_skill_file.invoke({"file_path": str(bravo_file)})
    content_b = _unwrap(result_b)
    assert 'parent_skill="bravo"' in content_b
    assert 'parent_skill="alpha"' not in content_b


def test_read_skill_file_handles_unicode_decode_error(monkeypatch, tmp_path: Path):
    """
    文件含非 UTF-8 字节时返回 Error，不传播异常。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    binary = base_dir / "binary.dat"
    # 写非 UTF-8 字节序列（Latin-1 编码也无法被 UTF-8 解码）
    binary.write_bytes(b"\xff\xfe\x00\x80\x90")

    info = SkillInfo(
        name="alpha",
        description="",
        location=str(base_dir / "SKILL.md"),
        content="",
        base_dir=str(base_dir),
    )
    service = _make_service_with_skills([info])
    monkeypatch.setattr(
        "app.core.tools.SkillTools.SkillsService.get_instance", lambda: service
    )

    from app.core.tools.SkillTools import read_skill_file

    result = read_skill_file.invoke({"file_path": str(binary)})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert content.startswith("Error:")
    assert "not valid UTF-8" in content


def test_read_skill_file_tool_is_registered_as_langchain_tool():
    """
    导入的 read_skill_file 已被 @tool 注册为 LangChain 工具，具备 invoke 方法。

    Returns:
        None
    """
    from app.core.tools.SkillTools import read_skill_file

    assert hasattr(read_skill_file, "invoke")


# ---------------------------------------------------------------------------
# agent_name 维度降级查找测试（2026-06-22 落地）
# ---------------------------------------------------------------------------


def _make_agent_aware_resolver(
    agent_info: SkillInfo | None = None,
    global_info: SkillInfo | None = None,
    agent_skills: list[SkillInfo] | None = None,
    global_skills: list[SkillInfo] | None = None,
) -> tuple[callable, MagicMock, MagicMock]:
    """
    构造一个根据 agent_name 参数返回不同 mock 服务的 resolver。

    Args:
        agent_info: agent 维度 SkillsService.get(name) 返回值。
        global_info: 全局 SkillsService.get(name) 返回值。
        agent_skills: agent 维度 SkillsService.all() 返回列表。
        global_skills: 全局 SkillsService.all() 返回列表。

    Returns:
        (resolver, agent_service_mock, global_service_mock) 三元组。
    """
    agent_service = MagicMock()
    agent_service.get.return_value = agent_info
    agent_service.all.return_value = agent_skills or []
    global_service = MagicMock()
    global_service.get.return_value = global_info
    global_service.all.return_value = global_skills or []

    def _resolver(config=None, agent_name=None):
        if agent_name:
            return agent_service
        return global_service

    return _resolver, agent_service, global_service


def test_load_skill_finds_agent_skill_first(monkeypatch, tmp_path: Path):
    """
    runtime.state["agent_name"]="map_agent" 时，先查 agent 维度；
    命中即返回，不再调用全局实例（避免 agent skill 被全局覆盖语义破坏）。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "data-skill"
    base_dir.mkdir(parents=True)
    agent_info = SkillInfo(
        name="data-skill",
        description="agent-level",
        location=str(base_dir / "SKILL.md"),
        content="body-from-agent",
        base_dir=str(base_dir),
    )
    resolver, agent_service, global_service = _make_agent_aware_resolver(
        agent_info=agent_info,
    )
    monkeypatch.setattr("app.core.tools.SkillTools.SkillsService.get_instance", resolver)

    from app.core.tools.SkillTools import load_skill

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-agent"
    mock_runtime.state = {"agent_name": "map_agent"}

    result = load_skill(name="data-skill", runtime=mock_runtime)

    content = _unwrap(result)
    assert '<skill_content name="data-skill">' in content
    assert "body-from-agent" in content
    agent_service.get.assert_called_once_with("data-skill")
    # 命中 agent 维度后应直接返回，不再降级到全局
    global_service.get.assert_not_called()


def test_load_skill_falls_back_to_global_when_not_in_agent(
    monkeypatch, tmp_path: Path
):
    """
    agent 维度没有该 skill 时降级到全局实例查找；命中全局则返回成功。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "global" / "shared-skill"
    base_dir.mkdir(parents=True)
    global_info = SkillInfo(
        name="shared-skill",
        description="global-only",
        location=str(base_dir / "SKILL.md"),
        content="body-from-global",
        base_dir=str(base_dir),
    )
    resolver, agent_service, global_service = _make_agent_aware_resolver(
        agent_info=None,
        global_info=global_info,
    )
    monkeypatch.setattr("app.core.tools.SkillTools.SkillsService.get_instance", resolver)

    from app.core.tools.SkillTools import load_skill

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-fallback"
    mock_runtime.state = {"agent_name": "map_agent"}

    result = load_skill(name="shared-skill", runtime=mock_runtime)

    content = _unwrap(result)
    assert '<skill_content name="shared-skill">' in content
    assert "body-from-global" in content
    # 先查 agent（返回 None），再降级到全局
    agent_service.get.assert_called_once_with("shared-skill")
    global_service.get.assert_called_once_with("shared-skill")


def test_load_skill_returns_error_when_not_in_any_scope(
    monkeypatch, tmp_path: Path
):
    """
    agent 维度和全局都没有该 skill 时，ToolMessage 以 "Error: " 开头，
    且 available 列表合并两个维度已加载 skill 名称（去重排序）。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    agent_dir = tmp_path / "agent"
    global_dir = tmp_path / "global"
    agent_info = SkillInfo(
        name="agent-only",
        description="",
        location=str(agent_dir / "SKILL.md"),
        content="",
        base_dir=str(agent_dir),
    )
    global_info = SkillInfo(
        name="global-only",
        description="",
        location=str(global_dir / "SKILL.md"),
        content="",
        base_dir=str(global_dir),
    )
    resolver, _, _ = _make_agent_aware_resolver(
        agent_info=None,
        global_info=None,
        agent_skills=[agent_info],
        global_skills=[global_info],
    )
    monkeypatch.setattr("app.core.tools.SkillTools.SkillsService.get_instance", resolver)

    from app.core.tools.SkillTools import load_skill

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-missing"
    mock_runtime.state = {"agent_name": "map_agent"}

    result = load_skill(name="does-not-exist", runtime=mock_runtime)

    content = _unwrap(result)
    assert content.startswith("Error: ")
    assert "agent-only" in content
    assert "global-only" in content


def test_read_skill_file_accepts_path_from_agent_skill(monkeypatch, tmp_path: Path):
    """
    file_path 落在 agent 维度 skill 的 base_dir 下时，白名单校验通过。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "skills" / "data-skill"
    base_dir.mkdir(parents=True)
    target = base_dir / "scripts" / "parse_file.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('agent')\n", encoding="utf-8")
    info = SkillInfo(
        name="data-skill",
        description="",
        location=str(base_dir / "SKILL.md"),
        content="",
        base_dir=str(base_dir),
    )
    resolver, _, _ = _make_agent_aware_resolver(
        agent_skills=[info],
        global_skills=[],
    )
    monkeypatch.setattr("app.core.tools.SkillTools.SkillsService.get_instance", resolver)

    from app.core.tools.SkillTools import read_skill_file

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-agent-file"
    mock_runtime.state = {"agent_name": "map_agent"}

    result = read_skill_file(file_path=str(target), runtime=mock_runtime)

    content = _unwrap(result)
    assert content.startswith("<skill_file ")
    assert 'parent_skill="data-skill"' in content
    assert "print('agent')" in content


def test_read_skill_file_accepts_path_from_global_skill(
    monkeypatch, tmp_path: Path
):
    """
    file_path 落在全局 skill 的 base_dir 下时，即使 runtime.state["agent_name"]
    指向特定 agent，白名单校验依然通过（降级合并）。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录。

    Returns:
        None
    """
    base_dir = tmp_path / "global" / "shared-skill"
    base_dir.mkdir(parents=True)
    target = base_dir / "scripts" / "run.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('global')\n", encoding="utf-8")
    info = SkillInfo(
        name="shared-skill",
        description="",
        location=str(base_dir / "SKILL.md"),
        content="",
        base_dir=str(base_dir),
    )
    resolver, _, _ = _make_agent_aware_resolver(
        agent_skills=[],
        global_skills=[info],
    )
    monkeypatch.setattr("app.core.tools.SkillTools.SkillsService.get_instance", resolver)

    from app.core.tools.SkillTools import read_skill_file

    mock_runtime = MagicMock()
    mock_runtime.tool_call_id = "call-global-file"
    mock_runtime.state = {"agent_name": "map_agent"}

    result = read_skill_file(file_path=str(target), runtime=mock_runtime)

    content = _unwrap(result)
    assert content.startswith("<skill_file ")
    assert 'parent_skill="shared-skill"' in content
    assert "print('global')" in content


def test_load_skill_works_when_state_is_missing():
    """
    runtime.state 为 None / 不含 agent_name 键时，_get_agent_name 不抛异常
    且返回 None，确保 load_skill 降级到全局 SkillsService 实例。

    Returns:
        None
    """
    from app.core.tools.SkillTools import _get_agent_name

    # state 为 None
    mock_runtime_none = MagicMock()
    mock_runtime_none.state = None
    assert _get_agent_name(mock_runtime_none) is None

    # state 是 dict 但缺少 agent_name 键
    mock_runtime_empty = MagicMock()
    mock_runtime_empty.state = {}
    assert _get_agent_name(mock_runtime_empty) is None

    # state 是 dict 且 agent_name 为 None
    mock_runtime_explicit = MagicMock()
    mock_runtime_explicit.state = {"agent_name": None}
    assert _get_agent_name(mock_runtime_explicit) is None

    # state 是 dict 且 agent_name 有值
    mock_runtime_set = MagicMock()
    mock_runtime_set.state = {"agent_name": "map_agent"}
    assert _get_agent_name(mock_runtime_set) == "map_agent"


# ---------------------------------------------------------------------------
# 2026-06-30 base_dir 相对路径兼容：load_skill 应能解析 POSIX 相对路径
# ---------------------------------------------------------------------------


def test_load_skill_resolves_relative_base_dir(monkeypatch, tmp_path: Path):
    """
    SkillInfo.base_dir 为相对项目根的 POSIX 路径时，load_skill 应能
    通过 SkillRegistryService._to_absolute() 还原为绝对路径并 iterdir()。

    模拟 DB 中已存的 `app/skills/alpha` 格式相对路径。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        tmp_path: pytest 提供的临时目录，模拟项目根。

    Returns:
        None
    """
    # 在 tmp_path/app/skills/alpha/ 下创建 SKILL.md + 一个附属文件
    base_dir = tmp_path / "app" / "skills" / "alpha"
    base_dir.mkdir(parents=True)
    (base_dir / "SKILL.md").write_text("---\nname: alpha\n---\nbody", encoding="utf-8")
    (base_dir / "script.py").write_text("# script", encoding="utf-8")

    # 把 get_project_root monkeypatch 为 tmp_path
    import app.core.tools.SkillTools as tools_module
    monkeypatch.setattr(tools_module, "get_project_root", lambda: tmp_path)

    info = SkillInfo(
        name="alpha",
        description="Alpha skill",
        location="app/skills/alpha/SKILL.md",  # POSIX 相对路径
        content="body",
        base_dir="app/skills/alpha",  # POSIX 相对路径
    )
    service = _make_service_mock(info)
    monkeypatch.setattr(tools_module.SkillsService, "get_instance", lambda: service)

    from app.core.tools.SkillTools import load_skill

    result = load_skill.invoke({"name": "alpha"})

    assert isinstance(result, Command)
    content = _unwrap(result)
    assert "<skill_content name=\"alpha\">" in content
    assert content.count("<file>") == 1
    assert "script.py" in content