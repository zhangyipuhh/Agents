# -*- coding:utf-8 -*-
"""
DockerSandboxBackend 路径解析测试（2026-06-12 新增）

专门覆盖容器化部署场景下 _resolve_host_workspace 的行为，
不依赖真实 Docker daemon —— 通过 mock docker.from_env 跳过实际连接，
只验证路径投影逻辑。

测试覆盖：
    - local / dind 模式：host_workspace == workspace
    - socket 模式 + prefix：host_workspace = prefix + workspace
    - socket 模式 + 空 prefix：抛 RuntimeError
    - k8s 模式：抛 NotImplementedError
    - 容器内 volumes 绑定使用 host_workspace 而非 workspace
"""

from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_docker_client():
    """提供模拟的 Docker 客户端，跳过真实连接。"""
    from docker.errors import NotFound

    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_client.images.get.return_value = Mock()
    mock_client.containers.get.side_effect = NotFound("not found")
    mock_container = Mock()
    mock_container.id = "abc123"
    mock_container.name = "sandbox-test"
    mock_container.status = "running"
    mock_container.exec_run.return_value = Mock(output=b"", exit_code=0)
    mock_client.containers.run.return_value = mock_container
    return mock_client


class TestResolveHostWorkspace:
    """_resolve_host_workspace 路径投影测试"""

    def test_local_mode_host_workspace_equals_workspace(self, mock_docker_client, tmp_path):
        """P1: local 模式下 host_workspace == workspace。"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="local-mode",
                workspace=workspace,
                docker_mode="local",
            )
            assert backend.host_workspace == workspace
            assert backend.workspace == workspace
            backend.cleanup()

    def test_dind_mode_host_workspace_equals_workspace(self, mock_docker_client, tmp_path):
        """P1: dind 模式下 host_workspace == workspace（内嵌 daemon 看到的"宿主机"就是当前容器）。"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="dind-mode",
                workspace=workspace,
                docker_mode="dind",
            )
            assert backend.host_workspace == workspace
            backend.cleanup()

    def test_socket_mode_with_prefix_projects_path(self, mock_docker_client, tmp_path):
        """P1: socket 模式 + prefix，host_workspace = prefix + workspace。"""
        # 跳过 _init_docker（_resolve_host_workspace 在那之前）
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="socket-mode",
                workspace=workspace,
                docker_mode="socket",
                docker_host="unix:///var/run/docker.sock",
                host_workspace_prefix="/host/app/data",
            )
            assert backend.host_workspace == "/host/app/data" + workspace
            backend.cleanup()

    def test_socket_mode_strips_trailing_slash_from_prefix(
        self, mock_docker_client, tmp_path
    ):
        """P2: host_workspace_prefix 末尾的 / 会被去除，避免双斜杠。"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="socket-slash",
                workspace=workspace,
                docker_mode="socket",
                docker_host="unix:///var/run/docker.sock",
                host_workspace_prefix="/host/app/data/",  # 末尾带斜杠
            )
            assert backend.host_workspace == "/host/app/data" + workspace
            backend.cleanup()

    def test_socket_mode_without_prefix_raises(self, tmp_path):
        """P1: socket 模式 + 空 prefix 抛 RuntimeError（在 _init_docker 之前的 _resolve_host_workspace 阶段）。"""
        # 此时不需要 docker mock，因为 _resolve_host_workspace 在 __init__ 早期就抛错
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxBackend,
        )
        workspace = str(tmp_path / "sandbox")
        with pytest.raises(RuntimeError) as exc_info:
            DockerSandboxBackend(
                session_id="socket-no-prefix",
                workspace=workspace,
                docker_mode="socket",
                docker_host="unix:///var/run/docker.sock",
                host_workspace_prefix="",  # 空 prefix
            )
        assert "SANDBOX_HOST_WORKSPACE_PREFIX" in str(exc_info.value) or \
               "host_workspace_prefix" in str(exc_info.value)

    def test_k8s_mode_raises_not_implemented(self, tmp_path):
        """P1: k8s 模式抛 NotImplementedError。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxBackend,
        )
        workspace = str(tmp_path / "sandbox")
        with pytest.raises(NotImplementedError) as exc_info:
            DockerSandboxBackend(
                session_id="k8s-mode",
                workspace=workspace,
                docker_mode="k8s",
            )
        assert "k8s" in str(exc_info.value).lower()


class TestVolumesBinding:
    """验证 bind mount key 使用 host_workspace 而非 workspace"""

    def test_volumes_key_uses_host_workspace_local_mode(
        self, mock_docker_client, tmp_path
    ):
        """P1: local 模式 volumes key == workspace（应用 = 宿主机）。"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            workspace = str(tmp_path / "sandbox")
            backend = DockerSandboxBackend(
                session_id="vol-local",
                workspace=workspace,
                docker_mode="local",
            )
            call_kwargs = mock_docker_client.containers.run.call_args.kwargs
            # 在 local 模式下，host_workspace == workspace，所以 key 就是 workspace
            assert workspace in call_kwargs["volumes"]
            assert call_kwargs["volumes"][workspace]["bind"] == "/workspace"
            backend.cleanup()

    def test_volumes_key_uses_host_workspace_socket_mode(
        self, mock_docker_client, tmp_path
    ):
        """P1: socket 模式 volumes key == host_workspace（宿主机视角）。"""
        # socket 模式走 docker.DockerClient(base_url=...)，必须 patch 正确位置
        with patch(
            "app.shared.tools.middleware.docker_sandbox_backend.docker.DockerClient",
            return_value=mock_docker_client,
        ):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            workspace = str(tmp_path / "sandbox")
            prefix = "/host/app/data"
            backend = DockerSandboxBackend(
                session_id="vol-socket",
                workspace=workspace,
                docker_mode="socket",
                docker_host="unix:///var/run/docker.sock",
                host_workspace_prefix=prefix,
            )
            call_kwargs = mock_docker_client.containers.run.call_args.kwargs
            expected_host_workspace = prefix + workspace
            # 关键断言：bind mount key 必须是宿主机视角，不能是应用视角
            assert expected_host_workspace in call_kwargs["volumes"]
            assert workspace not in call_kwargs["volumes"], (
                "volumes key 不应是应用视角 workspace，否则宿主机 Docker daemon 无法解析"
            )
            assert call_kwargs["volumes"][expected_host_workspace]["bind"] == "/workspace"
            backend.cleanup()

    def test_volumes_bind_target_is_container_workspace(
        self, mock_docker_client, tmp_path
    ):
        """P2: bind mount target 使用 container_workspace 字段（默认 /workspace）。"""
        with patch("docker.from_env", return_value=mock_docker_client):
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            backend = DockerSandboxBackend(
                session_id="bind-target",
                workspace=str(tmp_path / "sandbox"),
                docker_mode="local",
                container_workspace="/custom/sandbox/path",
            )
            call_kwargs = mock_docker_client.containers.run.call_args.kwargs
            # bind target 是容器内路径，由 container_workspace 控制
            assert call_kwargs["working_dir"] == "/custom/sandbox/path"
            for vol_spec in call_kwargs["volumes"].values():
                assert vol_spec["bind"] == "/custom/sandbox/path"
            backend.cleanup()


class TestDockerClientSelection:
    """Docker 客户端按 docker_mode 选择测试"""

    def test_socket_mode_uses_docker_client_with_base_url(
        self, mock_docker_client, tmp_path
    ):
        """P1: socket 模式调用 docker.DockerClient(base_url=...)，不调 docker.from_env()。"""
        with patch("docker.from_env") as mock_from_env:
            with patch(
                "app.shared.tools.middleware.docker_sandbox_backend.docker.DockerClient",
                return_value=mock_docker_client,
            ) as mock_docker_client_ctor:
                from app.shared.tools.middleware.docker_sandbox_backend import (
                    DockerSandboxBackend,
                )
                backend = DockerSandboxBackend(
                    session_id="client-socket",
                    workspace=str(tmp_path / "sandbox"),
                    docker_mode="socket",
                    docker_host="unix:///var/run/docker.sock",
                    host_workspace_prefix="/host",
                )
                # 关键：socket 模式应使用 DockerClient(base_url=...)，而不是 from_env()
                mock_from_env.assert_not_called()
                mock_docker_client_ctor.assert_called_once_with(
                    base_url="unix:///var/run/docker.sock"
                )
                backend.cleanup()

    def test_local_mode_uses_docker_from_env(self, mock_docker_client, tmp_path):
        """P1: local 模式调用 docker.from_env()。"""
        with patch("docker.from_env", return_value=mock_docker_client) as mock_from_env:
            from app.shared.tools.middleware.docker_sandbox_backend import (
                DockerSandboxBackend,
            )
            backend = DockerSandboxBackend(
                session_id="client-local",
                workspace=str(tmp_path / "sandbox"),
                docker_mode="local",
            )
            mock_from_env.assert_called_once()
            backend.cleanup()

    def test_socket_mode_without_docker_host_raises(self, tmp_path):
        """P1: socket 模式 + 空 docker_host 抛 RuntimeError。"""
        from app.shared.tools.middleware.docker_sandbox_backend import (
            DockerSandboxBackend,
        )
        with pytest.raises(RuntimeError) as exc_info:
            DockerSandboxBackend(
                session_id="socket-no-host",
                workspace=str(tmp_path / "sandbox"),
                docker_mode="socket",
                docker_host="",  # 空
                host_workspace_prefix="/host",
            )
        assert "SANDBOX_DOCKER_HOST" in str(exc_info.value) or \
               "docker_host" in str(exc_info.value)
