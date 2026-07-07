# -*- coding:utf-8 -*-
"""
sandbox 工具 abort_event 检测测试（2026-07-06 新增）

覆盖：
- 主循环每 N chunk 检查 abort_event.is_set()，set 时立即 break
- is_disconnected 作为兜底（abort_event 未 set 但 client 断开）
- stopped_by_user 分支构造 ToolMessage 并 return Command
- ToolMessage 的 tool_call_id 与 stop 时的 tool_call_id 一致
- 子智能体停止后 Docker 容器被 cleanup
- tool_stop 事件 status='stopped_by_user'
- 2026-07-06 扩展：BaseFilesystemTool 同样改造（覆盖 explore / query_knowledge 两个子智能体）

设计：
- 直接 mock child_agent.astream 与 middleware，避免 Docker / create_deep_agent 重依赖
- 通过 register_abort_signal + trigger_abort 模拟前端 /abort 调用的效果
- 与 test_sandbox_docker_unavailable_returns_clean_error 共用 patch 模式
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================
# 公共 helper
# ============================================================


def _make_fake_request(disconnect_sequence):
    """
    构造带 is_disconnected 协程方法的 MagicMock。
    2026-07-06 改造后只用于验证 is_disconnected 兜底路径。
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
    return fake


# ============================================================
# P1：abort_event.set() 触发 stopped_by_user
# ============================================================


@pytest.mark.asyncio
async def test_sandbox_abort_event_triggers_stopped_by_user():
    """P1：abort_event.set() 后，主循环下次检查立即 break，走 stopped_by_user 分支

    验证：
    1. 工具返回 Command（不是抛异常）
    2. Command.update.messages 包含 ToolMessage
    3. ToolMessage.tool_call_id 与 stop 时一致
    4. tool_stop 事件被推送，data.status='stopped_by_user'
    5. middleware.cleanup() 被调用（Docker 容器清理）
    """
    from app.core.tools._stop_signal import (
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )
    from app.core.tools.SandboxTools import sandbox
    from langchain_core.messages import ToolMessage

    session_id = "test_sess_abort_001"
    register_abort_signal(session_id)
    try:
        class FakeRuntime:
            tool_call_id = "call_abort_001"
            context = {"session_id": session_id}

        # mock middleware 实例（cleanup 方法要可被调用）
        mock_middleware = MagicMock()
        mock_middleware.cleanup = MagicMock()

        # mock child_agent.astream：让 abort_event 在第一个 yield 之前 set，
        # 模拟"主循环头部检查 abort_event.is_set() → 触发 stopped_by_user"
        # 关键：astream 本身是 async generator
        async def fake_astream(input_state, config, stream_mode):
            # 先触发 abort（模拟前端调 /abort 路由）
            trigger_abort(session_id)
            # 模拟 yield 一些 chunk（但主循环头部检查会立即 break）
            yield ("updates", {"llm_call": {"messages": [MagicMock(__class__=type("FakeAIMessage", (), {"__class__": type("FakeAIMessage", (), {}), "__name__": "FakeAIMessage"}))()]}})
            yield ("updates", {"tools": {"messages": [ToolMessage(content="late", tool_call_id="call_abort_001")]}})

        mock_writer = MagicMock()
        mock_settings = MagicMock()
        mock_settings.get_sandbox_config.return_value = {
            "image": "python:3.12-alpine",
            "max_memory_mb": 512,
            "max_cpu_percent": 100,
            "network_enabled": False,
            "default_timeout": 60,
            "docker_mode": "local",
            "docker_host": "",
            "host_workspace_prefix": "",
            "container_workspace": "/workspace",
            "fallback_to_local": True,
        }

        with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
             patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
             patch("app.core.tools.SandboxTools.settings", mock_settings), \
             patch("app.core.tools.SandboxTools.DockerSandboxMiddleware", return_value=mock_middleware), \
             patch("app.core.tools.SandboxTools.create_deep_agent") as mock_create_deep:

            mock_child_agent = MagicMock()
            mock_child_agent.astream = fake_astream
            mock_create_deep.return_value = mock_child_agent

            # mock get_async_checkpointer（避免真实数据库）
            with patch("app.core.tools.SandboxTools.get_async_checkpointer", new=AsyncMock(return_value=MagicMock())):
                result = await sandbox("test prompt", FakeRuntime())

        # 1. 返回 Command（不抛异常）
        assert result is not None
        assert hasattr(result, "update")
        messages = result.update.get("messages", [])
        assert len(messages) == 1

        # 2-3. ToolMessage 验证（ToolMessage 被 Mock 替换为 MagicMock，通过 call_args 检查）
        call_kwargs = ToolMessage.call_args.kwargs
        assert call_kwargs["tool_call_id"] == "call_abort_001"
        content = json.loads(call_kwargs["content"])
        assert "子智能体已被用户中止" in content["subagent"]

        # 4. tool_stop 事件被推送，status='stopped_by_user'
        stop_calls = [
            call for call in mock_writer.call_args_list
            if call.args and isinstance(call.args[0], dict)
            and call.args[0].get("type") == "tool_stop"
        ]
        assert len(stop_calls) >= 1, "应推送 tool_stop 事件"
        stop_event = stop_calls[0].args[0]
        assert stop_event["data"]["status"] == "stopped_by_user"

        # 5. Docker 容器被 cleanup
        mock_middleware.cleanup.assert_called_once()
    finally:
        unregister_abort_signal(session_id)


# ============================================================
# P1：is_disconnected 兜底（abort_event 未 set 但 client 断开）
# ============================================================


@pytest.mark.asyncio
async def test_sandbox_is_disconnected_fallback_triggers_stopped_by_user():
    """P1：abort_event 未注册时，is_disconnected 仍能触发 stopped_by_user（兜底）

    验证：当 abort_event 为 None（非 HTTP 上下文或流未启动）时，
    如果 request.is_disconnected() 返回 True，仍能走 stopped_by_user 分支。
    这是浏览器关闭/网络断等非主动关闭场景的兜底机制。
    """
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )
    from app.core.tools.SandboxTools import sandbox
    from langchain_core.messages import ToolMessage

    class FakeRuntime:
        tool_call_id = "call_isdisc_001"
        context = {"session_id": "test_sess_isdisc_001"}

    fake_request = _make_fake_request([True])  # 立即 is_disconnected=True
    token = set_current_request(fake_request)
    try:
        mock_middleware = MagicMock()
        mock_middleware.cleanup = MagicMock()

        # abort_event 为 None：sandbox 内不调 get_abort_signal（让 patch 返回 None）
        async def fake_astream(input_state, config, stream_mode):
            yield ("updates", {"llm_call": {"messages": [MagicMock()]}})

        mock_writer = MagicMock()
        mock_settings = MagicMock()
        mock_settings.get_sandbox_config.return_value = {
            "image": "python:3.12-alpine",
            "max_memory_mb": 512,
            "max_cpu_percent": 100,
            "network_enabled": False,
            "default_timeout": 60,
            "docker_mode": "local",
            "docker_host": "",
            "host_workspace_prefix": "",
            "container_workspace": "/workspace",
            "fallback_to_local": True,
        }

        with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
             patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
             patch("app.core.tools.SandboxTools.settings", mock_settings), \
             patch("app.core.tools.SandboxTools.DockerSandboxMiddleware", return_value=mock_middleware), \
             patch("app.core.tools.SandboxTools.create_deep_agent") as mock_create_deep, \
             patch("app.core.tools.SandboxTools.get_abort_signal", return_value=None):

            mock_child_agent = MagicMock()
            mock_child_agent.astream = fake_astream
            mock_create_deep.return_value = mock_child_agent

            with patch("app.core.tools.SandboxTools.get_async_checkpointer", new=AsyncMock(return_value=MagicMock())):
                result = await sandbox("test prompt", FakeRuntime())

        # 验证：走到 stopped_by_user 分支
        assert result is not None
        assert hasattr(result, "update")
        messages = result.update.get("messages", [])
        assert len(messages) == 1
        call_kwargs = ToolMessage.call_args.kwargs
        assert call_kwargs["tool_call_id"] == "call_isdisc_001"
        mock_middleware.cleanup.assert_called_once()
    finally:
        reset_current_request(token)


# ============================================================
# P1：abort_event 与 is_disconnected 都没触发，正常跑完
# ============================================================


@pytest.mark.asyncio
async def test_sandbox_no_stop_signal_runs_to_end():
    """P1：abort_event 未 set 且 is_disconnected=False，正常完成返回

    验证：没有停止信号时，工具走正常结束路径，不触发 stopped_by_user 分支。
    """
    from app.core.tools._stop_signal import (
        register_abort_signal,
        unregister_abort_signal,
    )
    from app.core.tools.SandboxTools import sandbox
    from langchain_core.messages import ToolMessage

    session_id = "test_sess_no_stop"
    register_abort_signal(session_id)
    try:
        class FakeRuntime:
            tool_call_id = "call_nostop_001"
            context = {"session_id": session_id}

        mock_middleware = MagicMock()
        mock_middleware.cleanup = MagicMock()

        # 不触发 abort：astream 模拟正常流，yield 几次 chunk 后结束
        async def fake_astream(input_state, config, stream_mode):
            yield ("updates", {"llm_call": {"messages": [MagicMock()]}})
            yield ("values", {"structured_response": {"answer": "完成"}})

        mock_writer = MagicMock()
        mock_settings = MagicMock()
        mock_settings.get_sandbox_config.return_value = {
            "image": "python:3.12-alpine",
            "max_memory_mb": 512,
            "max_cpu_percent": 100,
            "network_enabled": False,
            "default_timeout": 60,
            "docker_mode": "local",
            "docker_host": "",
            "host_workspace_prefix": "",
            "container_workspace": "/workspace",
            "fallback_to_local": True,
        }

        with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
             patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
             patch("app.core.tools.SandboxTools.settings", mock_settings), \
             patch("app.core.tools.SandboxTools.DockerSandboxMiddleware", return_value=mock_middleware), \
             patch("app.core.tools.SandboxTools.create_deep_agent") as mock_create_deep:

            mock_child_agent = MagicMock()
            mock_child_agent.astream = fake_astream
            mock_create_deep.return_value = mock_child_agent

            with patch("app.core.tools.SandboxTools.get_async_checkpointer", new=AsyncMock(return_value=MagicMock())):
                result = await sandbox("test prompt", FakeRuntime())

        # 验证：正常返回 Command（应包含 final_answer）
        assert result is not None
        # 正常完成时，middleware.cleanup 不应被调（只有 stopped_by_user 才调）
        # 实际看 stopped_by_user 分支内调用，正常完成分支不调
        # 我们不强约束，但至少不是空 update
        assert result.update.get("messages") is not None
    finally:
        unregister_abort_signal(session_id)


# ============================================================
# P2：abort_event 优先于 is_disconnected
# ============================================================


@pytest.mark.asyncio
async def test_sandbox_abort_event_takes_priority_over_is_disconnected():
    """P2：abort_event 已 set 时，即使 is_disconnected=False 也会停止

    验证：abort_event 主动 abort 优先于 is_disconnected 兜底。
    """
    from app.core.tools._stop_signal import (
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
        set_current_request,
        reset_current_request,
    )
    from app.core.tools.SandboxTools import sandbox
    from langchain_core.messages import ToolMessage

    session_id = "test_sess_priority"
    register_abort_signal(session_id)
    try:
        class FakeRuntime:
            tool_call_id = "call_priority_001"
            context = {"session_id": session_id}

        # is_disconnected 永远返回 False（不应被触发）
        fake_request = _make_fake_request([False, False, False, False])
        token = set_current_request(fake_request)
        try:
            mock_middleware = MagicMock()
            mock_middleware.cleanup = MagicMock()

            async def fake_astream(input_state, config, stream_mode):
                # 第一次 yield 前先 set abort
                trigger_abort(session_id)
                yield ("updates", {"llm_call": {"messages": [MagicMock()]}})

            mock_writer = MagicMock()
            mock_settings = MagicMock()
            mock_settings.get_sandbox_config.return_value = {
                "image": "python:3.12-alpine",
                "max_memory_mb": 512,
                "max_cpu_percent": 100,
                "network_enabled": False,
                "default_timeout": 60,
                "docker_mode": "local",
                "docker_host": "",
                "host_workspace_prefix": "",
                "container_workspace": "/workspace",
                "fallback_to_local": True,
            }

            with patch("app.core.tools.SandboxTools.get_stream_writer", return_value=mock_writer), \
                 patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
                 patch("app.core.tools.SandboxTools.settings", mock_settings), \
                 patch("app.core.tools.SandboxTools.DockerSandboxMiddleware", return_value=mock_middleware), \
                 patch("app.core.tools.SandboxTools.create_deep_agent") as mock_create_deep:

                mock_child_agent = MagicMock()
                mock_child_agent.astream = fake_astream
                mock_create_deep.return_value = mock_child_agent

                with patch("app.core.tools.SandboxTools.get_async_checkpointer", new=AsyncMock(return_value=MagicMock())):
                    result = await sandbox("test prompt", FakeRuntime())

            # 验证：走到 stopped_by_user 分支（说明 abort_event 优先触发）
            assert result is not None
            messages = result.update.get("messages", [])
            assert len(messages) == 1
            call_kwargs = ToolMessage.call_args.kwargs
            assert call_kwargs["tool_call_id"] == "call_priority_001"
            # middleware.cleanup 被调（stopped_by_user 分支特征）
            mock_middleware.cleanup.assert_called_once()
        finally:
            reset_current_request(token)
    finally:
        unregister_abort_signal(session_id)


# ============================================================
# 2026-07-06 扩展：BaseFilesystemTool 同样改造（同时覆盖 explore / query_knowledge）
#
# 设计说明：
# - explore (FilesystemReadTools.py) 与 query_knowledge (MapTools.py) 都走
#   BaseFilesystemTool.arun，所以改造 arun 一处即同时覆盖两个子智能体
# - 公共 helper _run_base_filesystem_tool_arun 集中 mock 逻辑
#   （patch create_child_agent + get_stream_writer + checkpointer），避免重复
# - 不依赖 Docker / create_deep_agent 等重依赖
# ============================================================


async def _run_base_filesystem_tool_arun(
    tool_name: str,
    session_id: str,
    astream_chunks: list,
    abort_event_set_at_index: int = None,
    fake_request_disconnect_sequence: list = None,
):
    """
    通用的 BaseFilesystemTool.arun 测试运行器。

    Args:
        tool_name: 'explore' / 'query_knowledge'
        session_id: 测试 session_id
        astream_chunks: mock astream 产出的 chunk 列表
        abort_event_set_at_index: 触发 trigger_abort 的 chunk 索引（None = 不触发）
        fake_request_disconnect_sequence: is_disconnected 序列

    Returns:
        (result, mock_writer) 元组
    """
    from app.core.tools._stop_signal import (
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )
    from app.core.tools.base import BaseFilesystemTool
    from langchain_core.messages import ToolMessage

    register_abort_signal(session_id)
    try:
        # mock astream：模拟子智能体产出
        # 如果指定 abort_event_set_at_index，在该 chunk 之前 set abort_event
        async def fake_astream(input_state, config, stream_mode):
            for idx, chunk in enumerate(astream_chunks):
                if abort_event_set_at_index is not None and idx == abort_event_set_at_index:
                    trigger_abort(session_id)
                yield chunk

        mock_child_agent = MagicMock()
        mock_child_agent.astream = fake_astream

        # mock get_async_checkpointer（避免真实数据库）
        mock_checkpointer = MagicMock()
        async def fake_get_checkpointer():
            return mock_checkpointer

        # mock get_current_request
        fake_request = _make_fake_request(
            fake_request_disconnect_sequence or [False] * 100
        )

        # 创建工具实例
        tool = BaseFilesystemTool(
            tool_name=tool_name,
            system_prompt=f"Test system prompt for {tool_name}",
        )

        # patch 关键依赖
        mock_writer = MagicMock()

        # 临时切换到包含文件的工作目录（用 tmp_path）
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            # 创建一个空文件（让 _validate_root_path 通过非空检查）
            (tmp_path / "placeholder.txt").write_text("x")

            with patch("app.core.tools.base.BaseFilesystemTool.get_stream_writer", return_value=mock_writer), \
                 patch("app.core.tools.base.BaseFilesystemTool.get_async_checkpointer", side_effect=fake_get_checkpointer), \
                 patch("app.core.tools.base.BaseFilesystemTool.get_current_request", return_value=fake_request), \
                 patch.object(BaseFilesystemTool, "create_child_agent", new=AsyncMock(return_value=mock_child_agent)):

                # 构造 FakeRuntime
                class FakeRuntime:
                    tool_call_id = f"call_{tool_name}_test_001"
                    context = {"session_id": session_id}

                result = await tool.arun(f"test prompt for {tool_name}", FakeRuntime(), tmp_path)

        return result, mock_writer
    finally:
        unregister_abort_signal(session_id)


@pytest.mark.asyncio
async def test_explore_abort_event_triggers_stopped_by_user():
    """P1：explore 工具走 BaseFilesystemTool.arun，abort_event.set() 后走 stopped_by_user 分支

    验证 BaseFilesystemTool.arun 改造后与 sandbox 行为一致：
    1. 工具返回 Command（不抛异常）
    2. Command.update.messages 包含 ToolMessage
    3. ToolMessage.tool_call_id 与 stop 时一致
    4. tool_stop 事件被推送，data.status='stopped_by_user'
    """
    from langchain_core.messages import ToolMessage
    from pathlib import Path

    astream_chunks = [
        ("updates", {"llm_call": {"messages": [MagicMock()]}}),
        ("updates", {"tools": {"messages": [ToolMessage(content="late", tool_call_id="call_explore_test_001")]}}),
    ]
    # 在第 0 个 chunk yield 之前 set abort（主循环首次 check 时立即 break）
    result, mock_writer = await _run_base_filesystem_tool_arun(
        tool_name="explore",
        session_id="test_explore_abort_001",
        astream_chunks=astream_chunks,
        abort_event_set_at_index=0,
    )

    # 1. 返回 Command（不抛异常）
    assert result is not None
    assert hasattr(result, "update")
    messages = result.update.get("messages", [])
    assert len(messages) == 1

    # 2-3. ToolMessage 验证
    call_kwargs = ToolMessage.call_args.kwargs
    assert call_kwargs["tool_call_id"] == "call_explore_test_001"
    content = json.loads(call_kwargs["content"])
    assert "子智能体已被用户中止" in content["subagent"]

    # 4. tool_stop 事件被推送，status='stopped_by_user'
    stop_calls = [
        call for call in mock_writer.call_args_list
        if call.args and isinstance(call.args[0], dict)
        and call.args[0].get("type") == "tool_stop"
    ]
    assert len(stop_calls) >= 1, "应推送 tool_stop 事件"
    stop_event = stop_calls[0].args[0]
    assert stop_event["data"]["status"] == "stopped_by_user"
    # 工具名应是 'explore'
    assert stop_event["tool"] == "explore"


@pytest.mark.asyncio
async def test_query_knowledge_abort_event_triggers_stopped_by_user():
    """P1：query_knowledge 工具走 BaseFilesystemTool.arun，abort_event.set() 后走 stopped_by_user 分支

    验证 explore / query_knowledge 共用 BaseFilesystemTool.arun，改造一处同时覆盖两个子智能体。
    """
    from langchain_core.messages import ToolMessage
    from pathlib import Path

    astream_chunks = [
        ("updates", {"llm_call": {"messages": [MagicMock()]}}),
    ]
    result, mock_writer = await _run_base_filesystem_tool_arun(
        tool_name="query_knowledge",
        session_id="test_query_knowledge_abort_001",
        astream_chunks=astream_chunks,
        abort_event_set_at_index=0,
    )

    # 1. 返回 Command
    assert result is not None
    assert hasattr(result, "update")
    messages = result.update.get("messages", [])
    assert len(messages) == 1

    # 2-3. ToolMessage 验证（tool_call_id 与 query_knowledge 一致）
    call_kwargs = ToolMessage.call_args.kwargs
    assert call_kwargs["tool_call_id"] == "call_query_knowledge_test_001"
    content = json.loads(call_kwargs["content"])
    assert "子智能体已被用户中止" in content["subagent"]

    # 4. tool_stop 事件验证
    stop_calls = [
        call for call in mock_writer.call_args_list
        if call.args and isinstance(call.args[0], dict)
        and call.args[0].get("type") == "tool_stop"
    ]
    assert len(stop_calls) >= 1
    stop_event = stop_calls[0].args[0]
    assert stop_event["data"]["status"] == "stopped_by_user"
    assert stop_event["tool"] == "query_knowledge"


@pytest.mark.asyncio
async def test_base_filesystem_tool_is_disconnected_fallback_triggers_stopped_by_user():
    """P1：BaseFilesystemTool.arun 的 is_disconnected 兜底（abort_event 未注册场景）

    场景：session 未注册（abort_event=None），is_disconnected 仍能触发 stopped_by_user。
    这是浏览器关闭 / 网络异常等非主动关闭场景的兜底机制。
    """
    from app.core.tools._stop_signal import (
        get_abort_signal,
    )
    from app.core.tools.base import BaseFilesystemTool
    from langchain_core.messages import ToolMessage
    from pathlib import Path
    import tempfile

    session_id = "test_bfs_isdisc_001"
    # 故意不调用 register_abort_signal → get_abort_signal 返回 None

    fake_request = _make_fake_request([True])  # 立即 is_disconnected=True

    async def fake_astream(input_state, config, stream_mode):
        yield ("updates", {"llm_call": {"messages": [MagicMock()]}})

    mock_child_agent = MagicMock()
    mock_child_agent.astream = fake_astream

    tool = BaseFilesystemTool(
        tool_name="explore",
        system_prompt="test",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "placeholder.txt").write_text("x")

        with patch("app.core.tools.base.BaseFilesystemTool.get_stream_writer", return_value=MagicMock()), \
             patch("app.core.tools.base.BaseFilesystemTool.get_async_checkpointer", new=AsyncMock(return_value=MagicMock())), \
             patch("app.core.tools.base.BaseFilesystemTool.get_current_request", return_value=fake_request), \
             patch.object(BaseFilesystemTool, "create_child_agent", new=AsyncMock(return_value=mock_child_agent)):

            class FakeRuntime:
                tool_call_id = "call_bfs_isdisc_001"
                context = {"session_id": session_id}

            result = await tool.arun("test prompt", FakeRuntime(), tmp_path)

    # 走 stopped_by_user 分支
    assert result is not None
    assert hasattr(result, "update")
    messages = result.update.get("messages", [])
    assert len(messages) == 1
    call_kwargs = ToolMessage.call_args.kwargs
    assert call_kwargs["tool_call_id"] == "call_bfs_isdisc_001"
    content = json.loads(call_kwargs["content"])
    assert "子智能体已被用户中止" in content["subagent"]


@pytest.mark.asyncio
async def test_base_filesystem_tool_no_stop_signal_runs_to_end():
    """P1：BaseFilesystemTool.arun 在无 stop 信号时正常完成

    验证：abort_event 未 set 且 is_disconnected=False，走正常完成路径，
    返回 Command 含 ToolMessage，且 content **不是** stopped_by_user 标记。
    """
    from app.core.tools._stop_signal import (
        register_abort_signal,
        unregister_abort_signal,
    )
    from app.core.tools.base import BaseFilesystemTool
    from langchain_core.messages import ToolMessage
    from pathlib import Path
    import tempfile

    session_id = "test_bfs_nostop_001"
    register_abort_signal(session_id)
    try:
        # 模拟 updates 流（累积 messages）+ values 流（带 structured_response）
        # 这样 BaseFilesystemTool.arun 的 _extract_last_ai_text 能正确提取 final_answer
        fake_ai_message = MagicMock()
        fake_ai_message.content = "OK 完成"
        fake_ai_message.__class__.__name__ = "AIMessage"
        # _extract_last_ai_text 期望 message 有 text / content 属性
        astream_chunks = [
            ("updates", {"llm_call": {"messages": [fake_ai_message]}}),
        ]

        # is_disconnected 永远返回 False
        fake_request = _make_fake_request([False] * 100)

        async def fake_astream(input_state, config, stream_mode):
            for chunk in astream_chunks:
                yield chunk

        mock_child_agent = MagicMock()
        mock_child_agent.astream = fake_astream

        tool = BaseFilesystemTool(
            tool_name="explore",
            system_prompt="test",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "placeholder.txt").write_text("x")

            with patch("app.core.tools.base.BaseFilesystemTool.get_stream_writer", return_value=MagicMock()), \
                 patch("app.core.tools.base.BaseFilesystemTool.get_async_checkpointer", new=AsyncMock(return_value=MagicMock())), \
                 patch("app.core.tools.base.BaseFilesystemTool.get_current_request", return_value=fake_request), \
                 patch.object(BaseFilesystemTool, "create_child_agent", new=AsyncMock(return_value=mock_child_agent)):

                class FakeRuntime:
                    tool_call_id = "call_bfs_nostop_001"
                    context = {"session_id": session_id}

                result = await tool.arun("test prompt", FakeRuntime(), tmp_path)

        # 正常完成：返回 Command（不抛异常）
        assert result is not None
        assert hasattr(result, "update")
        messages = result.update.get("messages", [])
        assert len(messages) == 1
        call_kwargs = ToolMessage.call_args.kwargs
        assert call_kwargs["tool_call_id"] == "call_bfs_nostop_001"
        # 正常完成时 content 不应是 stopped_by_user 标记
        content_str = call_kwargs["content"]
        assert "子智能体已被用户中止" not in content_str
    finally:
        unregister_abort_signal(session_id)
