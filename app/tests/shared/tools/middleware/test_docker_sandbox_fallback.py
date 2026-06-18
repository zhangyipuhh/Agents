# -*- coding:utf-8 -*-
"""
DockerSandboxMiddleware Docker 不可用降级测试

验证 2026-06-18 新增的 fallback_to_local 行为：
- fallback_to_local=false 时，Docker 不可用仍抛 RuntimeError
- fallback_to_local=true 时，Docker 不可用自动降级到 LocalShellBackend
- cleanup() 在本地回退模式下不会调用 LocalShellBackend 不存在的 cleanup()
"""

from unittest.mock import patch, MagicMock

import pytest

from docker.errors import DockerException


class TestDockerSandboxMiddlewareFallback:
    """DockerSandboxMiddleware fallback 行为测试"""

    def test_docker_unavailable_without_fallback_raises(self, tmp_path):
        """P1: fallback_to_local=false 时，Docker 不可用继续抛 RuntimeError。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
        )

        workspace = str(tmp_path / "sandbox")
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend",
        ) as mock_backend_cls:
            mock_backend_cls.side_effect = RuntimeError("Docker daemon 未运行")

            with pytest.raises(RuntimeError) as exc_info:
                DockerSandboxMiddleware(
                    session_id="no-fallback",
                    workspace=workspace,
                    fallback_to_local=False,
                )

            assert "Docker daemon 未运行" in str(exc_info.value)

    def test_docker_unavailable_with_fallback_uses_local_shell(self, tmp_path):
        """P1: fallback_to_local=true 时，Docker 不可用降级到 LocalShellBackend。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
        )
        from deepagents.backends.local_shell import LocalShellBackend

        workspace = str(tmp_path / "sandbox")
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend",
        ) as mock_backend_cls:
            mock_backend_cls.side_effect = DockerException("Docker daemon 连接失败")

            middleware = DockerSandboxMiddleware(
                session_id="with-fallback",
                workspace=workspace,
                fallback_to_local=True,
            )

            assert isinstance(middleware.backend, LocalShellBackend)
            assert middleware._docker_backend is False

    def test_docker_available_uses_docker_backend(self, tmp_path):
        """P1: Docker 可用时仍使用 DockerSandboxBackend。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
            DockerSandboxBackend,
        )

        workspace = str(tmp_path / "sandbox")
        mock_docker_backend = MagicMock()
        mock_docker_backend.__class__ = DockerSandboxBackend

        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend",
            return_value=mock_docker_backend,
        ) as mock_backend_cls:
            middleware = DockerSandboxMiddleware(
                session_id="docker-ok",
                workspace=workspace,
                fallback_to_local=True,
            )

            mock_backend_cls.assert_called_once()
            assert middleware.backend is mock_docker_backend
            assert middleware._docker_backend is True

    def test_cleanup_skips_local_backend(self, tmp_path):
        """P1: 本地回退模式下 cleanup() 不调用 backend.cleanup()。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
        )
        from deepagents.backends.local_shell import LocalShellBackend

        workspace = str(tmp_path / "sandbox")
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend",
        ) as mock_backend_cls:
            mock_backend_cls.side_effect = DockerException("Docker daemon 连接失败")

            middleware = DockerSandboxMiddleware(
                session_id="cleanup-local",
                workspace=workspace,
                fallback_to_local=True,
            )

            assert isinstance(middleware.backend, LocalShellBackend)
            # LocalShellBackend 没有 cleanup 方法；调用 middleware.cleanup() 不应抛异常
            middleware.cleanup()

    def test_cleanup_calls_docker_backend(self, tmp_path):
        """P1: Docker 模式下 cleanup() 调用 backend.cleanup()。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
            DockerSandboxBackend,
        )

        workspace = str(tmp_path / "sandbox")
        mock_docker_backend = MagicMock()
        mock_docker_backend.__class__ = DockerSandboxBackend

        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend",
            return_value=mock_docker_backend,
        ):
            middleware = DockerSandboxMiddleware(
                session_id="cleanup-docker",
                workspace=workspace,
                fallback_to_local=True,
            )

            middleware.cleanup()
            mock_docker_backend.cleanup.assert_called_once()
