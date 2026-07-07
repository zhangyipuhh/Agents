# -*- coding:utf-8 -*-
"""
DockerSandboxMiddleware 单元测试模块

验证 DockerSandboxMiddleware 的核心功能：
- 模块可导入、类存在
- 继承 FilesystemMiddleware
- 自动创建并管理 DockerSandboxBackend
- 资源清理行为

Date: 2026-06-11
"""

import pytest
from unittest.mock import Mock, patch

from deepagents.middleware.filesystem import FilesystemMiddleware


class TestDockerSandboxMiddleware:
    """DockerSandboxMiddleware 测试类"""

    def test_middleware_importable(self):
        """测试 DockerSandboxMiddleware 可正常导入"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
        )

        assert DockerSandboxMiddleware is not None

    def test_middleware_inherits_filesystem_middleware(self):
        """测试 DockerSandboxMiddleware 继承 FilesystemMiddleware"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
        )

        assert issubclass(DockerSandboxMiddleware, FilesystemMiddleware)

    def test_middleware_init_creates_backend(self, tmp_path):
        """测试初始化时自动创建 DockerSandboxBackend"""
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend"
        ) as mock_backend_cls:
            mock_backend = Mock()
            mock_backend_cls.return_value = mock_backend

            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxMiddleware,
            )

            workspace = str(tmp_path / "sandbox")
            middleware = DockerSandboxMiddleware(
                session_id="test-session",
                workspace=workspace,
                image="python:3.12-alpine",
                max_memory_mb=256,
            )

            # 2026-06-12 容器化重构：新增 4 个容器化部署字段
            mock_backend_cls.assert_called_once_with(
                session_id="test-session",
                workspace=workspace,
                image="python:3.12-alpine",
                max_memory_mb=256,
                max_cpu_percent=100,
                network_enabled=False,
                default_timeout=60,
                docker_mode="local",
                docker_host="",
                host_workspace_prefix="",
                container_workspace="/workspace",
            )
            assert middleware.backend is mock_backend

    def test_middleware_has_tools_attribute(self, tmp_path):
        """测试 middleware 实例具有 tools 属性"""
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend"
        ) as mock_backend_cls:
            mock_backend = Mock()
            mock_backend_cls.return_value = mock_backend

            with patch.object(
                FilesystemMiddleware, "__init__", lambda self, **kwargs: setattr(self, "tools", [])
            ):
                from app.shared.tools.middleware.docker_sandbox_backend import (
                    DockerSandboxMiddleware,
                )

                middleware = DockerSandboxMiddleware(
                    session_id="test-tools",
                    workspace=str(tmp_path / "sandbox"),
                )
                assert hasattr(middleware, "tools")
                assert isinstance(middleware.tools, list)

    def test_middleware_cleanup_calls_backend_cleanup(self, tmp_path):
        """测试 cleanup() 会调用 backend.cleanup()"""
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend"
        ) as mock_backend_cls:
            mock_backend = Mock()
            mock_backend_cls.return_value = mock_backend

            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxMiddleware,
            )

            middleware = DockerSandboxMiddleware(
                session_id="test-cleanup",
                workspace=str(tmp_path / "sandbox"),
            )
            middleware.cleanup()

            mock_backend.cleanup.assert_called_once()

    def test_middleware_cleanup_safe_when_backend_none(self, tmp_path):
        """测试 backend 为 None 时 cleanup() 不会抛出异常"""
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend"
        ) as mock_backend_cls:
            mock_backend = Mock()
            mock_backend_cls.return_value = mock_backend

            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxMiddleware,
            )

            middleware = DockerSandboxMiddleware(
                session_id="test-safe",
                workspace=str(tmp_path / "sandbox"),
            )
            middleware.backend = None
            middleware.cleanup()  # 不应抛出异常

    def test_middleware_requires_workspace(self):
        """P1: 未传入 workspace 时抛出 ValueError。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxMiddleware,
        )

        with pytest.raises(ValueError) as exc_info:
            DockerSandboxMiddleware(session_id="no-workspace")
        assert "必须显式传入 workspace" in str(exc_info.value)

    def test_middleware_passes_kwargs_to_filesystem_middleware(self, tmp_path):
        """测试额外 kwargs 会透传给 FilesystemMiddleware 父类"""
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.DockerSandboxBackend"
        ) as mock_backend_cls:
            mock_backend = Mock()
            mock_backend_cls.return_value = mock_backend

            with patch(
                "app.shared.tools.middleware.docker_sandbox_backend.FilesystemMiddleware.__init__"
            ) as mock_fs_init:
                from app.shared.tools.middleware.docker_sandbox_backend import (
                    DockerSandboxMiddleware,
                )

                DockerSandboxMiddleware(
                    session_id="test-kwargs",
                    workspace=str(tmp_path / "sandbox"),
                    system_prompt="custom prompt",
                    max_execute_timeout=120,
                )

                mock_fs_init.assert_called_once()
                call_kwargs = mock_fs_init.call_args.kwargs
                assert call_kwargs["backend"] is mock_backend
                assert call_kwargs["system_prompt"] == "custom prompt"
                assert call_kwargs["max_execute_timeout"] == 120


class TestDockerSandboxBackend:
    """DockerSandboxBackend 属性测试类"""

    def test_backend_has_container_workspace_attribute(self, tmp_path):
        """测试 DockerSandboxBackend 初始化后具有 container_workspace 属性且值为 /workspace"""
        with patch("docker.from_env") as mock_from_env:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_client.images.get.return_value = Mock()
            from docker.errors import NotFound
            mock_client.containers.get.side_effect = NotFound("not found")
            mock_container = Mock()
            mock_container.id = "test123"
            mock_client.containers.run.return_value = mock_container
            mock_from_env.return_value = mock_client

            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            backend = DockerSandboxBackend(
                session_id="test-attr",
                workspace=str(tmp_path / "sandbox"),
            )

            assert hasattr(backend, "container_workspace")
            assert backend.container_workspace == "/workspace"
            backend.cleanup()


    def test_backend_requires_workspace(self):
        """P1: 未传入 workspace 时抛出 ValueError。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxBackend,
        )

        with pytest.raises(ValueError) as exc_info:
            DockerSandboxBackend(session_id="no-workspace")
        assert "必须显式传入 workspace" in str(exc_info.value)


class TestDockerSandboxBackendWrite:
    """DockerSandboxBackend.write/awrite 测试类。"""

    @staticmethod
    def _setup_project_root(tmp_path, monkeypatch):
        """将 paths._PROJECT_ROOT 指向临时目录，确保 resolve_tmp_mirror_path 可映射。"""
        from app.core.config import paths
        monkeypatch.setattr(paths, "_PROJECT_ROOT", str(tmp_path))

    @staticmethod
    def _make_backend(tmp_path, workspace_relative: str):
        """创建 DockerSandboxBackend 实例并返回 workspace 路径与 backend。"""
        with patch("docker.from_env") as mock_from_env:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_client.images.get.return_value = Mock()
            from docker.errors import NotFound
            mock_client.containers.get.side_effect = NotFound("not found")
            mock_container = Mock()
            mock_container.id = "test123"
            mock_client.containers.run.return_value = mock_container
            mock_from_env.return_value = mock_client

            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            workspace = tmp_path / workspace_relative
            workspace.mkdir(parents=True)
            backend = DockerSandboxBackend(
                session_id="test-write",
                workspace=str(workspace),
            )
            return workspace, backend

    def test_write_creates_original_file(self, tmp_path, monkeypatch):
        """写 /script.py 应在 workspace 下创建原文件。"""
        self._setup_project_root(tmp_path, monkeypatch)
        workspace, backend = self._make_backend(tmp_path, "data/upload/2026/07/07/session-abc")
        try:
            result = backend.write("/script.py", "print('hello')")

            assert result.error is None
            assert result.path == "/script.py"
            assert (workspace / "script.py").read_text(encoding="utf-8") == "print('hello')"
        finally:
            backend.cleanup()

    def test_write_doc_extension_creates_md_mirror(self, tmp_path, monkeypatch):
        """workspace 位于 data/upload/... 时，写 .docx 应同步生成 data/tmp/.../.md。"""
        self._setup_project_root(tmp_path, monkeypatch)
        workspace, backend = self._make_backend(tmp_path, "data/upload/2026/07/07/session-abc")
        try:
            result = backend.write("/report.docx", "# Report\ncontent")

            assert result.error is None
            assert (workspace / "report.docx").read_text(encoding="utf-8") == "# Report\ncontent"

            md_mirror = tmp_path / "data/tmp/upload/2026/07/07/session-abc/report.md"
            assert md_mirror.exists()
            assert md_mirror.read_text(encoding="utf-8") == "# Report\ncontent"
        finally:
            backend.cleanup()

    def test_write_non_doc_extension_no_mirror(self, tmp_path, monkeypatch):
        """写 .json 时不应生成 .md 镜像。"""
        self._setup_project_root(tmp_path, monkeypatch)
        workspace, backend = self._make_backend(tmp_path, "data/upload/2026/07/07/session-abc")
        try:
            result = backend.write("/data.json", "{}")

            assert result.error is None
            assert (workspace / "data.json").read_text(encoding="utf-8") == "{}"

            md_mirror = tmp_path / "data/tmp/upload/2026/07/07/session-abc/data.md"
            assert not md_mirror.exists()
        finally:
            backend.cleanup()

    def test_write_outside_workspace_returns_error(self, tmp_path, monkeypatch):
        """写 workspace 外的路径应返回错误。"""
        self._setup_project_root(tmp_path, monkeypatch)
        workspace, backend = self._make_backend(tmp_path, "data/upload/2026/07/07/session-abc")
        try:
            result = backend.write("/../../outside.txt", "should fail")

            assert result.error is not None
            assert "outside workspace" in result.error.lower()
        finally:
            backend.cleanup()

    def test_awrite_creates_original_file(self, tmp_path, monkeypatch):
        """awrite 应异步创建原文件及 .md 镜像。"""
        import asyncio

        self._setup_project_root(tmp_path, monkeypatch)
        workspace, backend = self._make_backend(tmp_path, "data/upload/2026/07/07/session-abc")
        try:
            result = asyncio.run(backend.awrite("/notes.md", "# Notes"))

            assert result.error is None
            assert (workspace / "notes.md").read_text(encoding="utf-8") == "# Notes"

            md_mirror = tmp_path / "data/tmp/upload/2026/07/07/session-abc/notes.md"
            assert md_mirror.exists()
            assert md_mirror.read_text(encoding="utf-8") == "# Notes"
        finally:
            backend.cleanup()
