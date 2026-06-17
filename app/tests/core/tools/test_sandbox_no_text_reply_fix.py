# -*- coding:utf-8 -*-
"""
sandbox 子智能体"父 LLM 收不到文本回复"修复回归测试（2026-06-15 新增，2026-06-15 同步更新为 async 适配）

覆盖场景：
1. 子智能体 stream 最后一块是 updates 模式（无顶层 messages 键），
   但 updates 块内累计的 all_messages 含 AIMessage，
   验证修复后父工具能从 all_messages 中拿到真实 AI 文本而非兜底字符串。
2. 子智能体完全没产出 AIMessage（仅有 HumanMessage / ToolMessage），
   验证兜底字符串 + logger.warning 被触发。

## 2026-06-15 同步更新（async 适配）

sandbox 工具从同步 ``def sandbox`` 升级为 ``async def sandbox``（支持子智能体停止信号），
内部 ``child_agent.stream()`` 改为 ``child_agent.astream()``。

测试同步调整：
- ``fake_stream`` 同步生成器 → ``fake_astream`` async 生成器
- ``mock_agent.stream.side_effect = fake_stream`` → ``mock_agent.astream = fake_astream``
- ``SandboxTools.sandbox(...)`` 同步调用 → ``asyncio.run(SandboxTools.sandbox.coroutine(...))``

Date: 2026-06-15
"""

import asyncio
import json
from unittest.mock import MagicMock, patch


class _FakeRuntime:
    """模拟 ToolRuntime，具备 tool_call_id 与 context 属性"""

    def __init__(self, tool_call_id: str = "call_test", session_id: str = "default"):
        self.tool_call_id = tool_call_id
        self.context = {"session_id": session_id}


def _make_ai_message(content: str):
    """
    构造 AIMessage 实例（Mock 风格）

    SandboxTools._extract_last_ai_text 通过 type(msg).__name__ == 'AIMessage' 识别。
    """
    msg = MagicMock()
    msg.__class__.__name__ = "AIMessage"
    msg.content = content
    return msg


def _make_human_message(content: str):
    """构造 HumanMessage 实例（Mock 风格）"""
    msg = MagicMock()
    msg.__class__.__name__ = "HumanMessage"
    msg.content = content
    return msg


def _make_tool_message(content: str, tool_call_id: str = "t1"):
    """构造 ToolMessage 实例（Mock 风格）"""
    msg = MagicMock()
    msg.__class__.__name__ = "ToolMessage"
    msg.content = content
    msg.tool_call_id = tool_call_id
    msg.name = "execute"
    return msg


def _build_stream_patches():
    """构造 sandbox 工具执行所需的 patch 上下文管理器列表（不含 ToolMessage）"""
    return [
        patch("app.core.tools.SandboxTools.get_stream_writer"),
        patch("app.core.tools.SandboxTools.ModelFactory.create_model"),
        patch("app.core.tools.SandboxTools.DockerSandboxMiddleware"),
    ]


class _RecordingToolMessage:
    """
    替换 conftest 中 Mock 化的 ToolMessage，记录每次调用的 content 与 tool_call_id。
    返回真实 dataclass-like 实例，让 .content 拿到真实字符串。
    """
    def __init__(self, content="", tool_call_id=None, **kwargs):
        self.content = content
        self.tool_call_id = tool_call_id
        # 记录调用，便于测试断言
        _RecordingToolMessage.last_call = {"content": content, "tool_call_id": tool_call_id}


def test_sandbox_returns_last_ai_text_when_last_chunk_is_updates_mode():
    """
    P0 核心修复回归测试

    模拟用户报告的 bug 场景：child_agent.astream(...) 最后一块是 updates 模式
    （data = {"model": {...}}，无顶层 messages 键）。
    验证：修复后父工具能从 all_messages 中拿到真实 AI 文本，
    而非旧的兜底字符串"沙箱子智能体执行完成，但未获取到文本回复。"。

    Args:
        无

    Returns:
        无；通过 assert 验证 ToolMessage 调用记录中包含真实 AI 文本而非兜底字符串

    Raises:
        AssertionError: 当修复未生效或 mock 设置错误时抛出
    """
    from app.core.tools import SandboxTools

    # 2026-06-15 更新：同步生成器 → async 生成器（适配 child_agent.astream）
    async def fake_astream(*args, **kwargs):
        # 模拟真实场景：子智能体多步推进，updates 流块携带 AIMessage
        yield ("updates", {
            "model": {
                "messages": [
                    _make_human_message("执行 ls -la"),
                    _make_ai_message("执行结果：/workspace 下无文件"),
                ]
            }
        })
        # 故意以 updates 模式结束，不再 yield "values" 模式
        # —— 这正是用户报告的 bug 场景

    mock_agent = MagicMock()
    # 2026-06-15 更新：mock astream（不是 stream）
    mock_agent.astream = fake_astream

    patches = _build_stream_patches()
    patches.append(
        patch("app.core.tools.SandboxTools.create_deep_agent", return_value=mock_agent)
    )
    # 替换 ToolMessage，让 .content 拿到真实字符串
    patches.append(
        patch("app.core.tools.SandboxTools.ToolMessage", _RecordingToolMessage)
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        # 2026-06-15 更新：sandbox 是 async 函数，需 asyncio.run 驱动
        # 2026-06-15 备注：conftest 把 @tool mock 为 identity，所以 sandbox 就是原 async 函数
        result = asyncio.run(SandboxTools.sandbox("test prompt", _FakeRuntime()))

    # 验证 sandbox 工具返回了 Command
    assert result is not None

    # 验证 ToolMessage 被调用，且 content 是 JSON 含 "subagent" 字段
    assert hasattr(_RecordingToolMessage, "last_call"), "ToolMessage 应被调用"
    raw_content = _RecordingToolMessage.last_call["content"]
    assert isinstance(raw_content, str), f"content 应为 str，实际 {type(raw_content)}"

    content = json.loads(raw_content)
    assert "subagent" in content
    subagent_text = content["subagent"]
    assert "执行结果：/workspace 下无文件" in subagent_text, (
        f"修复未生效，父 LLM 收到: {subagent_text}"
    )
    assert "未获取到文本回复" not in subagent_text, (
        f"仍走兜底分支，父 LLM 收到: {subagent_text}"
    )
    assert "<task_result>" in subagent_text
    assert "</task_result>" in subagent_text


def test_sandbox_returns_fallback_when_no_ai_message_in_all_messages():
    """
    P0 边界测试

    模拟子智能体异常场景：流块中仅有 HumanMessage 和 ToolMessage，
    没有 AIMessage。验证：父工具走兜底字符串 + logger.warning 被触发。

    Args:
        无

    Returns:
        无；通过 assert 验证兜底文本与 warning 日志

    Raises:
        AssertionError: 当兜底逻辑异常时抛出
    """
    from app.core.tools import SandboxTools

    # 2026-06-15 更新：同步生成器 → async 生成器
    async def fake_astream(*args, **kwargs):
        # 仅产出 HumanMessage + ToolMessage，没有 AIMessage
        # 注意：所有消息的 content 都设为空，触发 _extract_last_ai_text 返回空字符串，
        # 进而走兜底分支 + logger.warning。
        yield ("updates", {
            "model": {
                "messages": [
                    _make_human_message(""),
                    _make_tool_message("", tool_call_id="t1"),
                ]
            }
        })

    mock_agent = MagicMock()
    # 2026-06-15 更新：mock astream
    mock_agent.astream = fake_astream

    patches = _build_stream_patches()
    patches.append(
        patch("app.core.tools.SandboxTools.create_deep_agent", return_value=mock_agent)
    )
    patches.append(
        patch("app.core.tools.SandboxTools.ToolMessage", _RecordingToolMessage)
    )

    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        with patch.object(SandboxTools.logger, "warning") as mock_warning:
            # 2026-06-15 更新：sandbox 是 async 函数
            result = asyncio.run(
                SandboxTools.sandbox(
                    "test prompt", _FakeRuntime(tool_call_id="call_no_ai")
                )
            )

    # 验证 sandbox 工具返回了 Command
    assert result is not None

    # 验证 ToolMessage 被调用，且 content 含兜底字符串
    assert hasattr(_RecordingToolMessage, "last_call"), "ToolMessage 应被调用"
    raw_content = _RecordingToolMessage.last_call["content"]
    assert isinstance(raw_content, str), f"content 应为 str，实际 {type(raw_content)}"

    content = json.loads(raw_content)
    assert "subagent" in content
    assert "未获取到文本回复" in content["subagent"], (
        f"兜底字符串缺失，父 LLM 收到: {content['subagent']}"
    )

    # 验证 logger.warning 被触发
    assert mock_warning.called, "兜底分支应触发 logger.warning"
    warning_msg = mock_warning.call_args[0][0]
    assert "兜底触发" in warning_msg
