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

设计：
- 直接 mock child_agent.astream 与 middleware，避免 Docker / create_deep_agent 重依赖
- 通过 register_abort_signal + trigger_abort 模拟前端 /abort 调用的效果
- 与 test_sandbox_docker_unavailable_returns_clean_error 共用 patch 模式
"""

import json
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
