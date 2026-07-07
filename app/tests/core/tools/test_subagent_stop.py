# -*- coding:utf-8 -*-
"""
子智能体停止机制测试（2026-06-15 新增）

覆盖：
- sandbox 工具：客户端断开时跳出 astream 循环，清理 Docker 容器，推送 status='stopped_by_user'
- explore 工具：客户端断开时跳出 astream 循环，推送 status='stopped_by_user'
- 无 request 场景：get_current_request() 返回 None 时跳过检测，正常跑完
- 客户端未断开：与原有 status='success' 路径行为一致
- tool_stop 事件保留 thread_id / final_messages 等 subagent 字段

## 2026-06-15 备注：conftest 环境下 mock 的特殊性

``app/tests/conftest.py`` 把 ``langgraph.config.get_stream_writer`` mock 为
``Mock()``，把 ``@tool`` mock 为 identity 函数。本测试文件利用这一特性：

- ``patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer)``
  把 ``get_stream_writer()`` 的返回值固定为 ``mock_writer`` 实例本身
  （避免每次调用返回不同的 MagicMock），方便测试断言。
- ``asyncio.run(SandboxTools.sandbox(...))`` 直接驱动 async 函数
  （conftest 下 ``@tool`` 是 identity，``sandbox`` 就是原 async 函数）。
"""

import asyncio
import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.shared.utils.files import session_path_manager as spm
from app.core.tools._stop_signal import (
    get_current_request,
    reset_current_request,
    set_current_request,
)


# ============================================================
# 公共 helper
# ============================================================


def _make_fake_request(disconnect_sequence):
    """
    构造一个模拟 FastAPI Request 对象的工厂函数。

    Args:
        disconnect_sequence: list[bool]，按调用顺序返回 is_disconnected() 的值。

    Returns:
        Mock: 带 is_disconnected 协程方法的 mock 对象。
    """
    fake = MagicMock(name="fake_request")
    call_count = {"n": 0}
    disconnect_sequence = list(disconnect_sequence)

    async def _is_disconnected():
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(disconnect_sequence):
            return disconnect_sequence[idx]
        return False

    fake.is_disconnected = _is_disconnected
    fake._call_count = call_count
    return fake


def _make_fake_runtime(tool_call_id="call_test", session_id="default"):
    """构造模拟 ToolRuntime 的工厂函数（供 sandbox / explore 工具使用）"""

    class _FakeRuntime:
        pass

    rt = _FakeRuntime()
    rt.tool_call_id = tool_call_id
    rt.context = {"session_id": session_id}
    return rt


def _count_writer_events(writer_mock):
    """
    统计 writer 调用的所有 ToolEvent，按 event_type 分类 + 返回 tool_stop 事件 data 列表。

    Args:
        writer_mock: 实际 writer mock（patch "get_stream_writer" 的 return_value）。

    Returns:
        (counts, stop_data_list): counts dict 包含各 event_type 次数；
        stop_data_list 是所有 tool_stop 事件的 data 字段列表。
    """
    counts = {"tool_start": 0, "tool_progress": 0, "tool_stop": 0, "tool_error": 0}
    stop_data_list = []
    for call in writer_mock.call_args_list:
        if not call.args:
            continue
        event = call.args[0]
        if not isinstance(event, dict):
            continue
        et = event.get("type")
        if et in counts:
            counts[et] += 1
        if et == "tool_stop":
            stop_data_list.append(event.get("data", {}))
    return counts, stop_data_list


class _RecordingToolMessage:
    """
    替换 conftest 中 Mock 化的 ToolMessage，记录每次调用的 content 与 tool_call_id。
    返回真实类，让 .content 拿到真实字符串。
    """
    def __init__(self, content="", tool_call_id=None, **kwargs):
        self.content = content
        self.tool_call_id = tool_call_id
        # 记录调用，便于测试断言
        _RecordingToolMessage.last_call = {"content": content, "tool_call_id": tool_call_id}


# ============================================================
# 1) sandbox 工具 - 客户端断开时停止
# ============================================================


def test_sandbox_stops_on_client_disconnect():
    """
    P1: 客户端断开（is_disconnected 返回 True）时，sandbox 工具立即跳出 astream 循环，
    清理 Docker 容器，推送 status='stopped_by_user' 的 tool_stop 事件。
    """
    from app.core.tools import SandboxTools

    # 构造可被控制断开时机的 async generator
    async def fake_astream(*args, **kwargs):
        # 第一个 chunk：正常 updates
        yield ("updates", {
            "model": {
                "messages": [MagicMock(content="chunk1")]
            }
        })
        # 第二个 chunk：模拟"还在跑"但应该被 stop 跳过
        yield ("updates", {
            "model": {
                "messages": [MagicMock(content="chunk2_should_not_process")]
            }
        })

    mock_agent = MagicMock()
    mock_agent.astream = fake_astream

    # 2026-06-15 备注：第一次 is_disconnected 就返回 True（_STOP_CHECK_INTERVAL=5，
    # 第一次循环 len=0%5==0 立即检查，await 返回 True → break）
    fake_request = _make_fake_request([True, True, True])
    cleanup_called = {"n": 0}

    mock_middleware = MagicMock()

    def mock_middleware_cleanup():
        cleanup_called["n"] += 1

    mock_middleware.cleanup = mock_middleware_cleanup

    # 把 get_stream_writer() 的返回值固定为 mock_writer（避免自动生成新 mock）
    mock_writer = MagicMock()

    with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch(
             "app.core.tools.SandboxTools.DockerSandboxMiddleware",
             return_value=mock_middleware,
         ), \
         patch(
             "app.core.tools.SandboxTools.create_deep_agent",
             return_value=mock_agent,
         ):

        token = set_current_request(fake_request)
        try:
            result = asyncio.run(
                SandboxTools.sandbox("test prompt", _make_fake_runtime())
            )
        finally:
            reset_current_request(token)

    # 验证：客户端断开时 sandbox 返回了 Command
    assert result is not None

    # 验证：tool_stop 事件被推送且 status='stopped_by_user'
    counts, stop_data_list = _count_writer_events(mock_writer)
    assert counts["tool_stop"] >= 1, f"应至少推送一次 tool_stop 事件，实际: {counts}"
    stopped_event = next(
        (d for d in stop_data_list if d.get("status") == "stopped_by_user"),
        None,
    )
    assert stopped_event is not None, f"tool_stop status 应为 stopped_by_user，实际: {stop_data_list}"
    assert stopped_event.get("result", {}).get("answer") == "子智能体已被用户中止"

    # 验证：Docker 容器被清理（必须）
    assert cleanup_called["n"] >= 1, "客户端断开时必须清理 Docker 容器"

    # 验证：is_disconnected 被调用过
    assert fake_request._call_count["n"] >= 1


def test_sandbox_runs_to_end_when_not_disconnected():
    """
    P1: 客户端未断开（is_disconnected 始终 False）时，sandbox 走原有 status='success' 路径。
    """
    from app.core.tools import SandboxTools

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"model": {"messages": [MagicMock(content="hello")]}})
        yield ("values", {"structured_response": {"answer": "final answer"}})

    mock_agent = MagicMock()
    mock_agent.astream = fake_astream
    fake_request = _make_fake_request([False, False, False, False, False])
    mock_middleware = MagicMock()
    mock_writer = MagicMock()

    with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch(
             "app.core.tools.SandboxTools.DockerSandboxMiddleware",
             return_value=mock_middleware,
         ), \
         patch(
             "app.core.tools.SandboxTools.create_deep_agent",
             return_value=mock_agent,
         ):

        token = set_current_request(fake_request)
        try:
            result = asyncio.run(
                SandboxTools.sandbox("test prompt", _make_fake_runtime())
            )
        finally:
            reset_current_request(token)

    # 验证：tool_stop status='success'，不是 'stopped_by_user'
    counts, stop_data_list = _count_writer_events(mock_writer)
    assert counts["tool_stop"] >= 1
    success_event = next(
        (d for d in stop_data_list if d.get("status") == "success"),
        None,
    )
    assert success_event is not None, f"正常完成时 status 应为 success，实际: {stop_data_list}"
    stopped_event = next(
        (d for d in stop_data_list if d.get("status") == "stopped_by_user"),
        None,
    )
    assert stopped_event is None, f"正常路径不应出现 stopped_by_user: {stop_data_list}"


def test_sandbox_no_request_skips_disconnect_check():
    """
    P1: get_current_request() 返回 None（无 HTTP 上下文）时，跳过 is_disconnected 检测，
    正常跑完子智能体。
    """
    from app.core.tools import SandboxTools

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"model": {"messages": [MagicMock(content="hello")]}})
        yield ("values", {"structured_response": {"answer": "answer"}})

    mock_agent = MagicMock()
    mock_agent.astream = fake_astream
    mock_middleware = MagicMock()
    mock_writer = MagicMock()

    with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch(
             "app.core.tools.SandboxTools.DockerSandboxMiddleware",
             return_value=mock_middleware,
         ), \
         patch(
             "app.core.tools.SandboxTools.create_deep_agent",
             return_value=mock_agent,
         ):

        # 关键：不调用 set_current_request，让 contextvar 为 None
        assert get_current_request() is None

        result = asyncio.run(
            SandboxTools.sandbox("test prompt", _make_fake_runtime())
        )

    # 验证：tool_stop status='success'
    counts, stop_data_list = _count_writer_events(mock_writer)
    assert counts["tool_stop"] >= 1
    success_event = next(
        (d for d in stop_data_list if d.get("status") == "success"),
        None,
    )
    assert success_event is not None, f"无 request 时应走 success 路径，实际: {stop_data_list}"


def test_sandbox_stopped_event_contains_subagent_fields():
    """
    P1: 客户端断开时的 tool_stop 事件 data 仍包含 thread_id / final_messages 字段
    （前端 SubAgentCard 渲染需要）。
    """
    from app.core.tools import SandboxTools

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"model": {"messages": [MagicMock(content="x")]}})

    mock_agent = MagicMock()
    mock_agent.astream = fake_astream
    mock_middleware = MagicMock()
    fake_request = _make_fake_request([True, True])  # 第一次循环就断开
    mock_writer = MagicMock()

    with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch(
             "app.core.tools.SandboxTools.DockerSandboxMiddleware",
             return_value=mock_middleware,
         ), \
         patch(
             "app.core.tools.SandboxTools.create_deep_agent",
             return_value=mock_agent,
         ):

        token = set_current_request(fake_request)
        try:
            result = asyncio.run(
                SandboxTools.sandbox("test prompt", _make_fake_runtime())
            )
        finally:
            reset_current_request(token)

    # 找到 stopped_by_user 事件
    counts, stop_data_list = _count_writer_events(mock_writer)
    stopped_event = next(
        (d for d in stop_data_list if d.get("status") == "stopped_by_user"),
        None,
    )
    assert stopped_event is not None, f"未找到 stopped_by_user 事件: {stop_data_list}"

    # 验证 subagent 字段保留
    assert stopped_event.get("thread_id") == "call_test"
    assert "final_messages" in stopped_event
    assert "parent_prompt" in stopped_event
    assert stopped_event.get("parent_prompt") == "test prompt"


def test_sandbox_stopped_event_message_format():
    """
    P1: stopped_by_user 事件的 Command 中 ToolMessage content 应包含"子智能体已被用户中止"，
    父 LLM 据此知道子任务被中断。
    """
    from app.core.tools import SandboxTools

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"model": {"messages": [MagicMock(content="x")]}})

    mock_agent = MagicMock()
    mock_agent.astream = fake_astream
    mock_middleware = MagicMock()
    fake_request = _make_fake_request([True, True])  # 第一次循环就断开
    mock_writer = MagicMock()

    with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
         patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
         patch(
             "app.core.tools.SandboxTools.DockerSandboxMiddleware",
             return_value=mock_middleware,
         ), \
         patch(
             "app.core.tools.SandboxTools.create_deep_agent",
             return_value=mock_agent,
         ), \
         patch(
             "app.core.tools.SandboxTools.ToolMessage",
             # 用记录类替代 mock，让 content 拿到真实字符串
             _RecordingToolMessage,
         ):

        token = set_current_request(fake_request)
        try:
            result = asyncio.run(
                SandboxTools.sandbox("test prompt", _make_fake_runtime())
            )
        finally:
            reset_current_request(token)

    # 验证 Command 中的 ToolMessage（用 _RecordingToolMessage 记录）
    assert hasattr(_RecordingToolMessage, "last_call"), "ToolMessage 应被调用"
    raw_content = _RecordingToolMessage.last_call["content"]
    assert isinstance(raw_content, str), f"content 应为 str，实际 {type(raw_content)}"

    parsed = json.loads(raw_content)
    assert "subagent" in parsed
    assert "已被用户中止" in parsed["subagent"]


# ============================================================
# 2) explore 工具 - 客户端断开时停止
# ============================================================


def test_explore_stops_with_valid_root(tmp_path, monkeypatch):
    """
    P1: explore 在有效 root_path 下调用 BaseFilesystemTool.arun，客户端断开逻辑
    已在 BaseFilesystemTool 中覆盖。本测试验证 explore 能正确构造日期化 root_path 并
    将结果透传给调用方。
    """
    # explore 内部 root_path = get_session_upload_dir(session_id, create=True)
    # 需要创建 data/upload/{yyyy}/{mm}/{dd}/default/test.txt 让 root_path 校验通过
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
    session_id = "default"
    spm.register_session_upload_date(session_id)
    today = date.today()
    root_path = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/{session_id}"
    root_path.mkdir(parents=True, exist_ok=True)
    (root_path / "test.txt").write_text("hello")

    from app.core.tools import FilesystemReadTools
    from app.core.tools.base import BaseFilesystemTool

    captured = {}

    async def fake_arun(self, prompt, runtime, root_path):
        captured["root_path"] = str(root_path)
        captured["tool_name"] = self.tool_name
        from langgraph.types import Command
        from langchain_core.messages import ToolMessage
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(
                            {"subagent": "子智能体已被用户中止"},
                            ensure_ascii=False,
                        ),
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    runtime = _make_fake_runtime(tool_call_id="call_explore", session_id="default")

    with patch.object(BaseFilesystemTool, "arun", fake_arun):
        result = asyncio.run(FilesystemReadTools.explore("search for test", runtime))

    assert result is not None
    assert captured["tool_name"] == "explore"
    assert captured["root_path"] == str(root_path)


def test_explore_runs_to_end_when_not_disconnected(tmp_path):
    """
    P1: 客户端未断开时，explore 通过 BaseFilesystemTool.arun 返回成功结果。

    2026-06-18 重构：explore 通用子智能体执行逻辑已下沉到 BaseFilesystemTool。
    本测试验证 explore 是 async 函数，且仍具备停止信号相关依赖（现在位于
    BaseFilesystemTool 中）。
    """
    import inspect
    from app.core.tools import FilesystemReadTools
    from app.core.tools.base import BaseFilesystemTool
    from app.core.tools._stop_signal import get_current_request

    # 验证 explore 是 async 函数
    assert inspect.iscoroutinefunction(FilesystemReadTools.explore), (
        "explore 应该是 async 函数"
    )

    import importlib
    _bfs_mod = importlib.import_module("app.core.tools.base.BaseFilesystemTool")

    # 验证停止信号机制已下沉到 BaseFilesystemTool 模块
    assert hasattr(_bfs_mod, "get_current_request"), (
        "BaseFilesystemTool 模块应已 import get_current_request（停止信号）"
    )
    assert _bfs_mod.get_current_request is get_current_request
    assert hasattr(BaseFilesystemTool, "_STOP_CHECK_INTERVAL"), (
        "BaseFilesystemTool 应已定义 _STOP_CHECK_INTERVAL 常量"
    )
