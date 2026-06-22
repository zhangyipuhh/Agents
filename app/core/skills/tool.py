# -*- coding:utf-8 -*-
"""
Skill 加载工具。

提供被 LangChain @tool 装饰的 load_skill 函数，用于按名称加载已注册的 skill 正文及
同目录下的相关文件列表。
"""

from pathlib import Path
from unittest.mock import MagicMock

from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext
from .service import SkillNotFoundError, SkillsService


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
        info = SkillsService.get_instance().require(name)
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
        # 构造一个带 tool_call_id 的 mock runtime，避免函数体内访问 runtime.tool_call_id 时崩溃
        mock_runtime = MagicMock()
        mock_runtime.tool_call_id = "test-tool-call-id"
        if isinstance(input, dict):
            if input.get("runtime") is None:
                input["runtime"] = mock_runtime
            return load_skill(**input)
        return load_skill(input, runtime=mock_runtime)
    load_skill.invoke = _invoke
