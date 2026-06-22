# -*- coding:utf-8 -*-
"""
SandboxTools 配置注入测试（2026-06-12 新增，2026-06-15 更新为 async 适配，2026-06-18 增加 fallback 字段）

验证 sandbox 工具从 Settings.get_sandbox_config() 读取容器化部署配置，
并把配置正确透传给 DockerSandboxMiddleware。

测试覆盖：
    - 默认配置下，工具把 SandboxSettings 默认值透传给中间件
    - 自定义配置下（socket 模式 + prefix），工具正确透传所有字段
    - 配置变更（mock settings）后，工具透传变更后的值

## 2026-06-15 同步更新（async 适配）

sandbox 工具从同步 ``def sandbox`` 升级为 ``async def sandbox``（支持子智能体停止信号），
内部 ``child_agent.stream()`` 改为 ``child_agent.astream()``。

测试同步调整：
- ``mock_agent.return_value.stream`` → ``mock_agent.return_value.astream``（同步 MagicMock，
  ``side_effect`` 在调用时立即抛错，跳过 async for 迭代）
- ``SandboxTools.sandbox("test prompt", FakeRuntime())`` → ``asyncio.run(
  SandboxTools.sandbox.coroutine("test prompt", FakeRuntime()))``（同步驱动 async 函数）
"""

import asyncio
from unittest.mock import MagicMock, patch


def _invoke_async_sandbox(prompt, runtime):
    """
    同步驱动 async sandbox 工具函数（用于同步 pytest 用例）。

    ## 2026-06-15 备注：conftest 模拟环境下 @tool 是 identity

    ``app/tests/conftest.py`` 把 ``langchain.tools.tool`` mock 为
    ``lambda *args, **kwargs: lambda func: func``，即装饰器不改变函数。
    因此在测试环境下 ``SandboxTools.sandbox`` 就是原 async 函数本身，
    没有 ``.coroutine`` 属性（那是真实 langchain 1.x StructuredTool 才有的）。

    生产环境（conftest 不生效时）``@tool`` 会把 async 函数包装为
    ``StructuredTool`` 并保留 ``.coroutine`` 指向原函数。两种环境下
    ``asyncio.run(SandboxTools.sandbox(prompt, runtime))`` 都能工作
    （生产环境调用 ``__call__`` → 走 StructuredTool 包装 → 内部 await coroutine）。
    """
    return asyncio.run(SandboxTools.sandbox(prompt, runtime))


class TestSandboxConfigInjection:
    """sandbox 工具配置注入测试"""

    def test_sandbox_passes_default_config_to_middleware(self):
        """P1: 默认 SandboxSettings 配置下，工具把所有字段透传给中间件。"""
        global SandboxTools  # noqa: PLW0603 - 用于 _invoke_async_sandbox 闭包
        from app.core.tools import SandboxTools

        captured_kwargs = {}

        def mock_middleware_ctor(**kwargs):
            captured_kwargs.update(kwargs)
            mock_middleware = MagicMock()
            mock_middleware.cleanup = MagicMock()
            return mock_middleware

        with patch("app.core.tools.SandboxTools.get_stream_writer"), \
             patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
             patch(
                 "app.core.tools.SandboxTools.DockerSandboxMiddleware",
                 side_effect=mock_middleware_ctor,
             ), \
             patch("app.core.tools.SandboxTools.create_deep_agent") as mock_agent:

            # 2026-06-15 更新：mock astream（不是 stream），调用时立即抛错
            mock_agent.return_value.astream = MagicMock(
                side_effect=RuntimeError("stop_after_middleware")
            )

            class FakeRuntime:
                tool_call_id = "call_cfg_default"
                context = {"session_id": "test-default"}

            try:
                _invoke_async_sandbox("test prompt", FakeRuntime())
            except RuntimeError as e:
                assert str(e) == "stop_after_middleware"

        # 验证中间件收到所有配置字段
        assert "image" in captured_kwargs
        assert "docker_mode" in captured_kwargs
        assert "docker_host" in captured_kwargs
        assert "host_workspace_prefix" in captured_kwargs
        assert "container_workspace" in captured_kwargs
        assert "fallback_to_local" in captured_kwargs
        # 默认值
        assert captured_kwargs["image"] == "python:3.12-alpine"
        assert captured_kwargs["docker_mode"] == "local"
        assert captured_kwargs["container_workspace"] == "/workspace"
        assert captured_kwargs["max_memory_mb"] == 512
        assert captured_kwargs["max_cpu_percent"] == 100
        assert captured_kwargs["network_enabled"] is False
        assert captured_kwargs["default_timeout"] == 60
        # Settings 中 sandbox_fallback_to_local 默认为 True
        assert captured_kwargs["fallback_to_local"] is True

    def test_sandbox_passes_socket_mode_config(self):
        """P1: socket 模式 + prefix 时，工具正确透传所有容器化字段。"""
        from app.core.tools import SandboxTools

        captured_kwargs = {}

        def mock_middleware_ctor(**kwargs):
            captured_kwargs.update(kwargs)
            mock_middleware = MagicMock()
            mock_middleware.cleanup = MagicMock()
            return mock_middleware

        # 用 monkeypatch 风格的 mock 替换 settings.get_sandbox_config
        custom_config = {
            "docker_mode": "socket",
            "docker_host": "unix:///var/run/docker.sock",
            "image": "python:3.11-slim",
            "max_memory_mb": 1024,
            "max_cpu_percent": 50,
            "network_enabled": True,
            "default_timeout": 120,
            "container_workspace": "/sandbox",
            "host_workspace_prefix": "/host/app/data",
            "k8s_namespace": "default",
            "fallback_to_local": True,
        }

        with patch("app.core.tools.SandboxTools.get_stream_writer"), \
             patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
             patch("app.core.tools.SandboxTools.settings") as mock_settings, \
             patch(
                 "app.core.tools.SandboxTools.DockerSandboxMiddleware",
                 side_effect=mock_middleware_ctor,
             ), \
             patch("app.core.tools.SandboxTools.create_deep_agent") as mock_agent:

            mock_settings.get_sandbox_config.return_value = custom_config
            # 2026-06-15 更新：mock astream
            mock_agent.return_value.astream = MagicMock(
                side_effect=RuntimeError("stop_after_middleware")
            )

            class FakeRuntime:
                tool_call_id = "call_cfg_socket"
                context = {"session_id": "test-socket"}

            try:
                _invoke_async_sandbox("test prompt", FakeRuntime())
            except RuntimeError as e:
                assert str(e) == "stop_after_middleware"

        # 验证容器化字段全部正确透传
        assert captured_kwargs["docker_mode"] == "socket"
        assert captured_kwargs["docker_host"] == "unix:///var/run/docker.sock"
        assert captured_kwargs["host_workspace_prefix"] == "/host/app/data"
        assert captured_kwargs["container_workspace"] == "/sandbox"
        assert captured_kwargs["image"] == "python:3.11-slim"
        assert captured_kwargs["max_memory_mb"] == 1024
        assert captured_kwargs["max_cpu_percent"] == 50
        assert captured_kwargs["network_enabled"] is True
        assert captured_kwargs["default_timeout"] == 120
        assert captured_kwargs["fallback_to_local"] is True

    def test_sandbox_calls_get_sandbox_config_exactly_once(self):
        """P2: sandbox 工具每次调用恰好读取一次配置（避免重复开销）。"""
        from app.core.tools import SandboxTools

        def mock_middleware_ctor(**kwargs):
            return MagicMock(cleanup=MagicMock())

        with patch("app.core.tools.SandboxTools.get_stream_writer"), \
             patch("app.core.tools.SandboxTools.ModelFactory.create_model"), \
             patch("app.core.tools.SandboxTools.settings") as mock_settings, \
             patch(
                 "app.core.tools.SandboxTools.DockerSandboxMiddleware",
                 side_effect=mock_middleware_ctor,
             ), \
             patch("app.core.tools.SandboxTools.create_deep_agent") as mock_agent:

            mock_settings.get_sandbox_config.return_value = {
                "docker_mode": "local",
                "docker_host": "",
                "image": "python:3.12-alpine",
                "max_memory_mb": 512,
                "max_cpu_percent": 100,
                "network_enabled": False,
                "default_timeout": 60,
                "container_workspace": "/workspace",
                "host_workspace_prefix": "",
                "k8s_namespace": "default",
                "fallback_to_local": False,
            }
            # 2026-06-15 更新：mock astream
            mock_agent.return_value.astream = MagicMock(
                side_effect=RuntimeError("stop_after_middleware")
            )

            class FakeRuntime:
                tool_call_id = "call_cfg_once"
                context = {"session_id": "test-once"}

            try:
                _invoke_async_sandbox("test prompt", FakeRuntime())
            except RuntimeError as e:
                assert str(e) == "stop_after_middleware"

        # 验证 get_sandbox_config 被调用了 1 次（在创建中间件之前）
        assert mock_settings.get_sandbox_config.call_count == 1


class TestSandboxConfigKeys:
    """sandbox_cfg dict 字段完整性测试（防止新增字段时漏传）"""

    def test_sandbox_cfg_has_all_required_keys(self):
        """P1: settings.get_sandbox_config 返回的 dict 包含中间件所需的全部键。"""
        from app.core.config.settings import settings as global_settings

        cfg = global_settings.get_sandbox_config()
        required_keys = {
            "docker_mode", "docker_host", "image", "max_memory_mb",
            "max_cpu_percent", "network_enabled", "default_timeout",
            "container_workspace", "host_workspace_prefix", "fallback_to_local",
        }
        missing = required_keys - set(cfg.keys())
        assert not missing, f"配置缺失必要字段: {missing}"

    def test_sandbox_cfg_docker_mode_value(self):
        """P1: docker_mode 是合法的 4 个枚举值之一。"""
        from app.core.config.settings import settings as global_settings

        cfg = global_settings.get_sandbox_config()
        assert cfg["docker_mode"] in ("local", "socket", "dind", "k8s")
