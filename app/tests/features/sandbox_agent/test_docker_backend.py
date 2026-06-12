# -*- coding:utf-8 -*-
"""
DockerSandboxBackend 单元测试模块

验证 DockerSandboxBackend 的核心功能：
- 容器生命周期管理
- 命令执行
- 文件上传/下载
- 资源清理

Date: 2026-06-11
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_docker_client():
    """提供模拟的 Docker 客户端"""
    mock_client = Mock()
    mock_client.ping.return_value = True

    # 模拟镜像存在
    mock_client.images.get.return_value = Mock()

    # 导入 docker.errors 中的异常类用于 side_effect
    from docker.errors import NotFound

    # 模拟容器不存在（首次创建）
    mock_client.containers.get.side_effect = NotFound("not found")

    mock_container = Mock()
    mock_container.id = "abc123"
    mock_container.name = "sandbox-test-session"
    mock_container.status = "running"
    mock_container.exec_run.return_value = Mock(
        output=b"hello world",
        exit_code=0,
    )
    mock_client.containers.run.return_value = mock_container

    return mock_client


class TestDockerSandboxBackend:
    """DockerSandboxBackend 测试类"""

    def test_backend_container_lifecycle(self, mock_docker_client, tmp_path):
        """测试容器创建、执行、销毁生命周期"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="test-session",
                workspace=workspace,
            )

            # 验证容器已创建
            assert backend._container is not None
            assert backend.id == "test-session"
            mock_docker_client.containers.run.assert_called_once()

            # 验证 volumes 和 working_dir 参数使用容器内路径 /workspace
            call_kwargs = mock_docker_client.containers.run.call_args.kwargs
            assert call_kwargs["volumes"][workspace]["bind"] == "/workspace"
            assert call_kwargs["working_dir"] == "/workspace"

            # 执行命令
            result = backend.execute("echo hello")
            assert result.output == "hello world"
            assert result.exit_code == 0

            # 清理
            backend.cleanup()
            assert backend._container is None
            mock_docker_client.containers.run.return_value.stop.assert_called_once()
            mock_docker_client.containers.run.return_value.remove.assert_called_once()

    def test_backend_execute_echo(self, mock_docker_client, tmp_path):
        """测试简单命令执行返回正确输出"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            backend = DockerSandboxBackend(
                session_id="test-exec",
                workspace=str(tmp_path / "sandbox"),
            )

            result = backend.execute("echo hello")
            assert "hello world" in result.output
            assert result.exit_code == 0
            assert result.truncated is False

            # 验证 exec_run 使用容器内工作目录 /workspace
            exec_call_kwargs = mock_docker_client.containers.run.return_value.exec_run.call_args.kwargs
            assert exec_call_kwargs["workdir"] == "/workspace"
            # 验证未传入 docker-py 不支持的 timeout 参数
            assert "timeout" not in exec_call_kwargs

            backend.cleanup()

    def test_backend_execute_timeout(self, mock_docker_client, tmp_path):
        """测试超时命令被终止"""
        from concurrent.futures import TimeoutError as FutureTimeoutError

        # 模拟 ThreadPoolExecutor 的 future.result() 抛出 TimeoutError
        mock_future = Mock()
        mock_future.result.side_effect = FutureTimeoutError()

        mock_executor = Mock()
        mock_executor.submit.return_value = mock_future
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=False)

        with patch("docker.from_env", return_value=mock_docker_client):
            with patch(
                "app.shared.tools.middleware.docker_sandbox_backend.ThreadPoolExecutor",
                return_value=mock_executor,
            ):
                from app.shared.tools.middleware.docker_sandbox_backend import (
                    DockerSandboxBackend,
                )

                backend = DockerSandboxBackend(
                    session_id="test-timeout",
                    workspace=str(tmp_path / "sandbox"),
                )

                result = backend.execute("sleep 100", timeout=1)
                assert result.exit_code == -1
                assert "超时" in result.output

                backend.cleanup()

    def test_backend_file_consistency(self, mock_docker_client, tmp_path):
        """测试主机写文件，容器内可读（通过 volume mount）"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="test-file",
                workspace=workspace,
            )

            # 上传文件
            upload_result = backend.upload_files(
                [("test.txt", b"hello from upload")]
            )
            assert len(upload_result) == 1
            assert upload_result[0].path == "test.txt"

            # 验证文件存在于主机工作目录
            host_file_path = os.path.join(workspace, "test.txt")
            assert os.path.exists(host_file_path)
            with open(host_file_path, "rb") as f:
                assert f.read() == b"hello from upload"

            # 下载文件
            download_result = backend.download_files(["test.txt"])
            assert len(download_result) == 1
            assert download_result[0].path == "test.txt"
            assert download_result[0].content == b"hello from upload"

            backend.cleanup()

    def test_backend_download_not_found(self, mock_docker_client, tmp_path):
        """测试下载不存在的文件返回错误"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            backend = DockerSandboxBackend(
                session_id="test-notfound",
                workspace=str(tmp_path / "sandbox"),
            )

            result = backend.download_files(["nonexistent.txt"])
            assert len(result) == 1
            assert result[0].path == "nonexistent.txt"
            assert result[0].content is None

            backend.cleanup()

    def test_backend_id_property(self, mock_docker_client, tmp_path):
        """测试 id 属性返回 session_id"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            backend = DockerSandboxBackend(
                session_id="my-session-id",
                workspace=str(tmp_path / "sandbox"),
            )
            assert backend.id == "my-session-id"
            backend.cleanup()

    def test_backend_docker_unavailable(self, tmp_path):
        """测试 Docker daemon 不可用时抛出 RuntimeError"""
        from docker.errors import DockerException
        with patch("docker.from_env", side_effect=DockerException("Docker not found")):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )

            with pytest.raises(RuntimeError) as exc_info:
                DockerSandboxBackend(
                    session_id="test-no-docker",
                    workspace=str(tmp_path / "sandbox"),
                )
            assert "Docker daemon" in str(exc_info.value)
