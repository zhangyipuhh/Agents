# -*- coding:utf-8 -*-
"""
Skill 加载工具。

提供被 LangChain @tool 装饰的工具函数，用于按名称加载已注册的 skill 正文及
同目录下的相关文件列表，或按绝对路径读取 skill 目录下的具体文件。

- load_skill: 返回 SKILL.md 正文与同目录文件清单（XML 块）
- read_skill_file: 按绝对路径读取 skill 配套资源文件（白名单限定在已注册 skill 内）
"""

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext
from .schemas import SkillInfo
from .service import SkillNotFoundError, SkillsService


# 单文件大小上限：1 MB。超出则拒绝，避免上下文爆炸。
_MAX_SKILL_FILE_SIZE_BYTES = 1 * 1024 * 1024


@tool
def load_skill(name: str,runtime: ToolRuntime[AgentContext],) -> Command:
    """Load a specialized skill when the task at hand matches one of the skills
    listed in `<available_skills>` of your system prompt.

    The output contains the skill body plus a `<skill_files>` list pointing to
    scripts and reference docs in the same directory. Use Read/Edit tools with
    those paths to load additional resources.

    Args:
        name: The skill name from `<available_skills>`.

    Returns:
        `Command` whose `update["messages"]` 包含一条 `ToolMessage`：
        成功时 content 为 `<skill_content>` XML 块；skill 不存在时 content 为
        以 `Error: ...` 开头的字符串（不抛异常）。
    """
    try:
        # 从 runtime.state 读取 agent_name，按 "agent 维度 → 全局" 降级查找。
        # 不存在时构造 SkillNotFoundError 并包装为 Error: ... ToolMessage，
        # 与历史行为保持一致（不向上抛异常）。
        agent_name = _get_agent_name(runtime)
        info = _resolve_skill_with_fallback(name, agent_name)
        if info is None:
            err = SkillNotFoundError(name, _merged_available(agent_name))
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=f"Error: {err}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ]
                }
            )
    except SkillNotFoundError as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"Error: {e}",
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    base_dir = Path(info.base_dir)
    files = sorted(
        p for p in base_dir.iterdir()
        if p.is_file() and p.name != "SKILL.md"
    )[:10]
    base_url = base_dir.as_uri()

    parts = [
        f'<skill_content name="{info.name}">',
        f"# Skill: {info.name}",
        "",
        info.content.strip(),
        "",
        f"Base directory for this skill: {base_url}",
        "Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.",
        "Note: file list is sampled.",
        "",
        "<skill_files>",
        *(f"<file>{p.resolve()}</file>" for p in files),
        "</skill_files>",
        "</skill_content>",
    ]
    content = "\n".join(parts)
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id,
                )
            ]
        }
    )


# 兼容测试环境：conftest 将 @tool mock 为 identity，需补充 invoke 方法以统一调用接口
if not hasattr(load_skill, "invoke"):
    def _invoke(input, config=None):
        # 构造一个带 tool_call_id 与 state 的 mock runtime，避免函数体内访问
        # runtime.state.get("agent_name") 时返回 MagicMock 而被误用
        mock_runtime = MagicMock()
        mock_runtime.tool_call_id = "test-tool-call-id"
        mock_runtime.state = {"agent_name": None}
        if isinstance(input, dict):
            if input.get("runtime") is None:
                input["runtime"] = mock_runtime
            return load_skill(**input)
        return load_skill(input, runtime=mock_runtime)
    load_skill.invoke = _invoke


# ---------------------------------------------------------------------------
# read_skill_file：按绝对路径读取已注册 skill 目录下的资源文件
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# agent_name 解析与 skill 降级查找（按 "agent 维度 → 全局" 顺序）
# ---------------------------------------------------------------------------


def _get_agent_name(runtime: ToolRuntime[AgentContext]) -> Optional[str]:
    """
    从 ToolRuntime.state 安全读取 agent_name，state 缺失或异常时返回 None。

    Args:
        runtime: 工具运行时上下文。

    Returns:
        str | None: agent_name（可能为 None）。
    """
    try:
        state = runtime.state
        if state is None:
            return None
        # state 是 Mapping（如 TypedDict），用 .get 安全读取
        return state.get("agent_name")
    except Exception:
        return None


def _resolve_skill_with_fallback(
    name: str, agent_name: Optional[str]
) -> Optional[SkillInfo]:
    """
    按 "agent 维度 → 全局" 顺序查找 skill，命中即返回。

    Args:
        name: skill 名。
        agent_name: 可选 agent 名，传入时优先查 agent 维度实例。

    Returns:
        SkillInfo 或 None（两个维度都没有时）。
    """
    if agent_name:
        info = SkillsService.get_instance(agent_name=agent_name).get(name)
        if info is not None:
            return info
    return SkillsService.get_instance().get(name)


def _merged_available(agent_name: Optional[str]) -> list[str]:
    """
    合并 agent 维度与全局维度已加载 skill 名称（去重 + 排序）。

    Args:
        agent_name: 可选 agent 名。

    Returns:
        排序去重后的 skill 名称列表。
    """
    names: list[str] = []
    if agent_name:
        names.extend(
            s.name for s in SkillsService.get_instance(agent_name=agent_name).all()
        )
    names.extend(s.name for s in SkillsService.get_instance().all())
    return sorted(set(names))


def _resolve_all_skills(agent_name: Optional[str]) -> list[SkillInfo]:
    """
    合并 agent 维度与全局维度的 SkillInfo 列表（供 read_skill_file 白名单校验用）。

    Args:
        agent_name: 可选 agent 名。

    Returns:
        合并后的 SkillInfo 列表（agent 维度优先，全局做补充）。
    """
    skills: dict[str, SkillInfo] = {}
    if agent_name:
        for s in SkillsService.get_instance(agent_name=agent_name).all():
            skills[s.name] = s
    for s in SkillsService.get_instance().all():
        skills.setdefault(s.name, s)
    return list(skills.values())


# ---------------------------------------------------------------------------
# read_skill_file：按绝对路径读取已注册 skill 目录下的资源文件
# ---------------------------------------------------------------------------


def _resolve_skill_root(skills: list[SkillInfo], path: Path) -> Optional[str]:
    """
    判断 path 是否落在某个已注册 skill 的 base_dir 下。

    Args:
        skills: SkillsService.all() 返回的 skill 列表。
        path: 已规范化的待校验绝对路径。

    Returns:
        str | None: 命中的 skill 名称；无任何命中返回 None。
    """
    for info in skills:
        try:
            root = Path(info.base_dir).resolve()
        except OSError:
            continue
        try:
            if path.is_relative_to(root):
                return info.name
        except ValueError:
            # 跨盘符或无法计算相对关系
            continue
    return None


def _error_command(message: str, tool_call_id: str) -> Command:
    """
    构造一个包含错误 ToolMessage 的 Command。

    Args:
        message: 错误描述文本（不含 "Error: " 前缀）。
        tool_call_id: 当前工具调用的唯一 ID。

    Returns:
        Command: update.messages 仅含一条 ToolMessage(content="Error: <message>")。
    """
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=f"Error: {message}",
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


@tool(
    description=(
        "Read the content of a file inside a registered skill's directory by its **absolute path**.\n"
        "Use this after calling `load_skill`: the `<file>...</file>` entries returned by "
        "`load_skill` are absolute paths you can pass here.\n\n"
        "## When to use\n"
        "- When you need to read a script, reference doc, or example file that a skill "
        "lists under `<skill_files>`\n"
        "- When the user asks you to follow a skill's workflow that requires reading "
        "an external resource\n\n"
        "## When NOT to use\n"
        "- To load the SKILL.md body itself — use `load_skill` instead\n"
        "- To read files outside any registered skill directory — this tool will reject them\n"
        "- For binary files (images, PDFs, archives) — only UTF-8 text is supported\n\n"
        "## Constraints (CRITICAL)\n"
        "- `file_path` MUST be an absolute path. Relative paths are rejected.\n"
        "- The path must be located within a registered skill's base directory; "
        "otherwise the tool returns `Error: Path is not within any registered skill directory: ...`\n"
        "- Files larger than 1 MB are rejected to protect the context window.\n"
        "- Only UTF-8 text is supported; non-UTF-8 bytes return `Error: ...`.\n\n"
        "## Output\n"
        "Returns a `<skill_file>` XML block containing the file content, "
        "or an `Error: ...` string when the file is missing, oversized, outside a skill "
        "directory, or not valid UTF-8."
    )
)
def read_skill_file(
    file_path: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    按绝对路径读取已注册 skill 目录下的资源文件。

    工具会先把 file_path 解析为绝对路径，然后校验其是否落在某个已注册 skill 的
    base_dir 下；通过后再做大小（≤1 MB）与 UTF-8 校验，最终返回文件内容。

    Args:
        file_path: 待读取文件的绝对路径。建议取自 load_skill 返回的 `<file>` 节点。
        runtime: 工具运行时上下文（提供 tool_call_id）。

    Returns:
        Command: update.messages 含一条 ToolMessage。成功时 content 为
        `<skill_file path="file:///..." size="N" parent_skill="...">...</skill_file>`；
        失败时 content 为以 `Error: ...` 开头的字符串（不抛异常）。

    Raises:
        本函数不向上抛出异常；所有错误均转换为 ToolMessage。
    """
    tool_call_id = runtime.tool_call_id

    # 1) 解析为绝对路径（消除 ..、符号链接、相对路径）
    try:
        path = Path(file_path).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        return _error_command(f"Invalid file_path: {e}", tool_call_id)

    # 2) 校验存在性 + 是文件
    if not path.exists():
        return _error_command(f"File not found: {file_path}", tool_call_id)
    if not path.is_file():
        return _error_command(f"Not a regular file: {file_path}", tool_call_id)

    # 3) 白名单校验：必须落在某个已注册 skill 的 base_dir 下
    # 按 "agent 维度 → 全局" 合并 skill 列表，确保两类维度下的资源文件都可读
    try:
        agent_name = _get_agent_name(runtime)
        skills = _resolve_all_skills(agent_name)
    except Exception as e:
        return _error_command(f"SkillsService unavailable: {e}", tool_call_id)
    parent_skill = _resolve_skill_root(skills, path)
    if parent_skill is None:
        return _error_command(
            f"Path is not within any registered skill directory: {path}",
            tool_call_id,
        )

    # 4) 大小校验
    try:
        size = path.stat().st_size
    except OSError as e:
        return _error_command(f"Cannot stat file: {e}", tool_call_id)
    if size > _MAX_SKILL_FILE_SIZE_BYTES:
        size_mb = size / (1024 * 1024)
        return _error_command(
            f"File too large ({size_mb:.2f} MB, max 1 MB): {path}",
            tool_call_id,
        )

    # 5) 读取（仅 UTF-8）
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return _error_command(
            f"File is not valid UTF-8: {e}",
            tool_call_id,
        )
    except OSError as e:
        return _error_command(f"Failed to read file: {e}", tool_call_id)

    # 6) 包装为 XML 块（与 load_skill 风格保持一致）
    parts = [
        f'<skill_file path="{path.as_uri()}" size="{size}" parent_skill="{parent_skill}">',
        text.rstrip("\n"),
        "</skill_file>",
    ]
    content = "\n".join(parts)
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


# 兼容测试环境：conftest 将 @tool mock 为 identity，需补充 invoke 方法
if not hasattr(read_skill_file, "invoke"):
    def _invoke_rsf(input, config=None):
        """
        read_skill_file 的 invoke 兼容实现：测试环境下 @tool 为 identity，
        需要把 input dict 还原为 kwargs。
        """
        mock_runtime = MagicMock()
        mock_runtime.tool_call_id = "test-tool-call-id"
        mock_runtime.state = {"agent_name": None}
        if isinstance(input, dict):
            if input.get("runtime") is None:
                input["runtime"] = mock_runtime
            return read_skill_file(**input)
        return read_skill_file(input, runtime=mock_runtime)
    read_skill_file.invoke = _invoke_rsf
