# -*- coding:utf-8 -*-
"""
Sandbox Agent 冒烟测试模块

验证 Sandbox 工具的核心模块可正常导入、提示词非空。

Date: 2026-06-12
"""

from unittest.mock import Mock, patch


def test_sandbox_tools_importable():
    """测试 SandboxTools 模块可正常导入"""
    from app.core.tools.SandboxTools import sandbox, SANDBOX_SYSTEM_PROMPT
    assert sandbox is not None
    assert callable(sandbox)
    assert isinstance(SANDBOX_SYSTEM_PROMPT, str)
    assert len(SANDBOX_SYSTEM_PROMPT) > 0


def test_docker_backend_importable():
    """测试 DockerSandboxBackend 模块可正常导入"""
    with patch("docker.from_env") as mock_from_env:
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.containers.get.side_effect = Exception("not found")
        mock_container = Mock()
        mock_container.id = "test123"
        mock_container.status = "running"
        mock_client.containers.run.return_value = mock_container
        mock_from_env.return_value = mock_client

        from app.shared.tools.middleware.docker_sandbox_backend import DockerSandboxBackend
        assert DockerSandboxBackend is not None


def test_docker_middleware_importable():
    """测试 DockerSandboxMiddleware 模块可正常导入"""
    with patch("docker.from_env") as mock_from_env:
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.containers.get.side_effect = Exception("not found")
        mock_container = Mock()
        mock_container.id = "test123"
        mock_container.status = "running"
        mock_client.containers.run.return_value = mock_container
        mock_from_env.return_value = mock_client

        from app.shared.tools.middleware.docker_sandbox_backend import DockerSandboxMiddleware
        assert DockerSandboxMiddleware is not None
