#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Docker 沙箱中间件模块

该模块提供 DockerSandboxBackend（BaseSandbox 实现）和 DockerSandboxMiddleware
（FilesystemMiddleware 子类），用于在隔离的 Docker 容器中执行代码和文件操作。

DockerSandboxMiddleware 继承 FilesystemMiddleware，自动创建并管理
DockerSandboxBackend 实例，为子智能体提供完整的沙箱工具集：
    ls, read_file, write_file, edit_file, glob, grep, execute

Date: 2026-06-11
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor

import docker
from docker.errors import DockerException, NotFound, APIError

from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileUploadResponse,
    FileDownloadResponse,
)
from deepagents.middleware.filesystem import FilesystemMiddleware

logger = logging.getLogger(__name__)


class DockerSandboxBackend(BaseSandbox):
    """Docker 容器沙箱后端

    通过 Docker 容器提供隔离的代码执行环境，支持文件操作和命令执行。
    容器在初始化时启动并保持运行，通过 docker exec 执行命令以降低延迟。

    Attributes:
        session_id: 会话ID，用于唯一标识容器和隔离工作目录
        image: Docker 镜像名，默认 python:3.12-alpine
        workspace: 主机工作目录路径，通过 volume mount 映射到容器
        container_workspace: 容器内工作目录路径，固定为 /workspace
        max_memory_mb: 容器内存限制（MB）
        max_cpu_percent: 容器 CPU 限制（百分比）
        network_enabled: 是否启用容器网络，默认 False（--network none）
        default_timeout: 命令执行默认超时（秒）
        _client: Docker SDK 客户端实例
        _container: Docker 容器对象
    """

    def __init__(
        self,
        session_id: str,
        image: str = "python:3.12-alpine",
        workspace: str | None = None,
        max_memory_mb: int = 512,
        max_cpu_percent: int = 100,
        network_enabled: bool = False,
        default_timeout: int = 60,
    ):
        """初始化 Docker 沙箱后端并预热容器

        Args:
            session_id: 会话ID，用于容器命名和工作目录隔离
            image: Docker 镜像名，默认使用 python:3.12-alpine
            workspace: 主机工作目录，默认使用 /tmp/sandbox/{session_id}
            max_memory_mb: 容器内存限制（MB），默认 512
            max_cpu_percent: 容器 CPU 限制（百分比），默认 100
            network_enabled: 是否启用网络，默认 False（完全隔离）
            default_timeout: 命令默认超时（秒），默认 60

        Raises:
            RuntimeError: Docker daemon 不可用时抛出
        """
        self.session_id = session_id
        self.image = image
        self.workspace = workspace or os.path.join("/tmp/sandbox", session_id)
        self.container_workspace = "/workspace"
        self.max_memory_mb = max_memory_mb
        self.max_cpu_percent = max_cpu_percent
        self.network_enabled = network_enabled
        self.default_timeout = default_timeout
        self._client: docker.DockerClient | None = None
        self._container = None

        # 创建工作目录
        os.makedirs(self.workspace, exist_ok=True)

        # 初始化 Docker 客户端并启动容器
        self._init_docker()

    def _init_docker(self) -> None:
        """初始化 Docker 客户端并启动/复用容器

        尝试连接 Docker daemon，若连接成功则检查同名容器是否已存在。
        存在则复用，不存在则创建新容器并保持运行。

        Raises:
            RuntimeError: Docker daemon 不可用时抛出
        """
        try:
            self._client = docker.from_env()
            # 测试连接
            self._client.ping()
        except DockerException as e:
            logger.error("Docker daemon 连接失败: %s", e)
            raise RuntimeError(
                "Docker daemon 未运行或未安装。"
                "请确保 Docker Desktop / Docker Engine 已启动。"
            ) from e

        container_name = f"sandbox-{self.session_id}"

        try:
            # 尝试复用已存在的容器
            self._container = self._client.containers.get(container_name)
            if self._container.status != "running":
                logger.info("容器 %s 已存在但未运行，正在启动...", container_name)
                self._container.start()
            else:
                logger.info("复用已存在的容器 %s", container_name)
            return
        except NotFound:
            pass

        # 创建新容器
        logger.info("正在创建沙箱容器 %s，镜像: %s", container_name, self.image)
        try:
            # 拉取镜像（如果本地不存在）
            try:
                self._client.images.get(self.image)
            except NotFound:
                logger.info("镜像 %s 不存在，正在拉取...", self.image)
                self._client.images.pull(self.image)

            mem_limit = f"{self.max_memory_mb}m"
            nano_cpus = int(self.max_cpu_percent / 100 * 1_000_000_000)
            network_mode = "bridge" if self.network_enabled else "none"

            self._container = self._client.containers.run(
                image=self.image,
                command="tail -f /dev/null",
                name=container_name,
                detach=True,
                auto_remove=False,
                mem_limit=mem_limit,
                nano_cpus=nano_cpus,
                network=network_mode,
                volumes={self.workspace: {"bind": self.container_workspace, "mode": "rw"}},
                working_dir=self.container_workspace,
                stdin_open=True,
                tty=False,
            )
            logger.info("沙箱容器 %s 创建成功，ID: %s", container_name, self._container.id)
        except APIError as e:
            logger.error("创建容器失败: %s", e)
            raise RuntimeError(f"创建 Docker 容器失败: {e}") from e

    @property
    def id(self) -> str:
        """获取沙箱唯一标识符

        Returns:
            str: 会话ID，作为沙箱唯一标识
        """
        return self.session_id

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """在容器内执行 shell 命令

        通过 docker exec 在运行中的容器内执行命令，实现低延迟隔离执行。

        Args:
            command: 要执行的 shell 命令字符串
            timeout: 超时时间（秒），None 则使用 default_timeout

        Returns:
            ExecuteResponse: 包含 stdout+stderr 合并输出、退出码、截断标志

        Raises:
            RuntimeError: 容器未运行或 Docker API 出错时抛出
        """
        if self._container is None:
            raise RuntimeError("沙箱容器未初始化")

        effective_timeout = timeout or self.default_timeout

        try:
            # 刷新容器状态
            self._container.reload()
            if self._container.status != "running":
                logger.warning("容器未运行，尝试重启...")
                self._container.start()

            logger.debug("执行命令: %s", command)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._container.exec_run,
                    cmd=["sh", "-c", command],
                    workdir=self.container_workspace,
                    stdout=True,
                    stderr=True,
                    stdin=False,
                    tty=False,
                )
                result = future.result(timeout=effective_timeout)

            output = result.output.decode("utf-8", errors="replace") if result.output else ""
            exit_code = result.exit_code

            # 简单截断判断（超过 100KB 视为截断）
            truncated = len(output) > 100_000
            if truncated:
                output = output[:100_000] + "\n...[输出已截断]"

            return ExecuteResponse(
                output=output,
                exit_code=exit_code,
                truncated=truncated,
            )
        except TimeoutError:
            logger.warning("命令执行超时（%s秒）: %s", effective_timeout, command)
            return ExecuteResponse(
                output=f"命令执行超时（{effective_timeout}秒）",
                exit_code=-1,
                truncated=False,
            )
        except Exception as e:
            logger.error("命令执行失败: %s", e)
            return ExecuteResponse(
                output=f"命令执行失败: {e}",
                exit_code=-1,
                truncated=False,
            )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """上传文件到沙箱工作目录

        由于使用 Docker volume mount，直接在主机工作目录写入文件即可，
        容器内天然可见。

        Args:
            files: 文件列表，每项为 (文件路径, 文件内容bytes)

        Returns:
            list[FileUploadResponse]: 每个文件的上传结果
        """
        responses: list[FileUploadResponse] = []
        for file_path, content in files:
            try:
                # 确保路径在工作目录内，防止目录遍历
                abs_path = os.path.abspath(file_path)
                if not abs_path.startswith(os.path.abspath(self.workspace)):
                    # 如果是相对路径，则拼接工作目录
                    if not os.path.isabs(file_path):
                        abs_path = os.path.join(self.workspace, file_path)
                    else:
                        responses.append(
                            FileUploadResponse(
                                path=file_path,
                                error="invalid_path",
                            )
                        )
                        continue

                # 创建父目录
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "wb") as f:
                    f.write(content)
                responses.append(FileUploadResponse(path=file_path, error=None))
            except PermissionError:
                responses.append(
                    FileUploadResponse(path=file_path, error="permission_denied")
                )
            except Exception as e:
                logger.error("上传文件 %s 失败: %s", file_path, e)
                responses.append(
                    FileUploadResponse(path=file_path, error=str(e))
                )
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """从沙箱工作目录下载文件

        由于使用 Docker volume mount，直接从主机工作目录读取即可。

        Args:
            paths: 文件路径列表

        Returns:
            list[FileDownloadResponse]: 每个文件的下载结果
        """
        responses: list[FileDownloadResponse] = []
        for file_path in paths:
            try:
                # 确保路径在工作目录内
                abs_path = os.path.abspath(file_path)
                if not abs_path.startswith(os.path.abspath(self.workspace)):
                    if not os.path.isabs(file_path):
                        abs_path = os.path.join(self.workspace, file_path)
                    else:
                        responses.append(
                            FileDownloadResponse(
                                path=file_path,
                                content=None,
                                error="invalid_path",
                            )
                        )
                        continue

                if os.path.isdir(abs_path):
                    responses.append(
                        FileDownloadResponse(
                            path=file_path,
                            content=None,
                            error="is_directory",
                        )
                    )
                    continue

                with open(abs_path, "rb") as f:
                    content = f.read()
                responses.append(
                    FileDownloadResponse(path=file_path, content=content, error=None)
                )
            except FileNotFoundError:
                responses.append(
                    FileDownloadResponse(
                        path=file_path,
                        content=None,
                        error="file_not_found",
                    )
                )
            except PermissionError:
                responses.append(
                    FileDownloadResponse(
                        path=file_path,
                        content=None,
                        error="permission_denied",
                    )
                )
            except Exception as e:
                logger.error("下载文件 %s 失败: %s", file_path, e)
                responses.append(
                    FileDownloadResponse(
                        path=file_path,
                        content=None,
                        error=str(e),
                    )
                )
        return responses

    def cleanup(self) -> None:
        """清理沙箱资源

        停止并删除 Docker 容器，释放资源。
        建议在 Session 结束或 Agent 销毁时调用。
        """
        if self._container is not None:
            try:
                container_name = self._container.name
                logger.info("正在清理沙箱容器 %s", container_name)
                self._container.stop(timeout=5)
                self._container.remove(force=True)
                logger.info("沙箱容器 %s 已清理", container_name)
            except Exception as e:
                logger.warning("清理容器失败: %s", e)
            finally:
                self._container = None

    def __del__(self):
        """析构时尝试清理容器"""
        try:
            self.cleanup()
        except Exception:
            pass


class DockerSandboxMiddleware(FilesystemMiddleware):
    """Docker 沙箱中间件

    继承 FilesystemMiddleware，自动创建并管理 DockerSandboxBackend 实例，
    为子智能体提供隔离的代码执行与文件操作环境。

    提供的工具与 FilesystemMiddleware 一致：
        ls, read_file, write_file, edit_file, glob, grep, execute

    Attributes:
        backend: DockerSandboxBackend 实例，由本中间件自动创建和管理

    Examples:
        >>> middleware = DockerSandboxMiddleware(
        ...     session_id="session-001",
        ...     workspace="/tmp/sandbox/session-001",
        ... )
        >>> child_agent = create_deep_agent(
        ...     model=model,
        ...     system_prompt=prompt,
        ...     middleware=[middleware],
        ...     checkpointer=MemorySaver(),
        ... )
        >>> middleware.cleanup()  # 会话结束时释放 Docker 容器
    """

    def __init__(
        self,
        session_id: str,
        image: str = "python:3.12-alpine",
        workspace: str | None = None,
        max_memory_mb: int = 512,
        max_cpu_percent: int = 100,
        network_enabled: bool = False,
        default_timeout: int = 60,
        **kwargs,
    ):
        """初始化 Docker 沙箱中间件

        自动创建 DockerSandboxBackend 实例，并将其传入 FilesystemMiddleware
        父类，使子智能体获得完整的沙箱工具集。

        Args:
            session_id: 会话ID，用于容器命名和工作目录隔离
            image: Docker 镜像名，默认使用 python:3.12-alpine
            workspace: 主机工作目录，默认使用 /tmp/sandbox/{session_id}
            max_memory_mb: 容器内存限制（MB），默认 512
            max_cpu_percent: 容器 CPU 限制（百分比），默认 100
            network_enabled: 是否启用网络，默认 False（完全隔离）
            default_timeout: 命令默认超时（秒），默认 60
            **kwargs: 额外参数，透传给 FilesystemMiddleware 父类

        Raises:
            RuntimeError: Docker daemon 不可用时抛出
        """
        self.backend = DockerSandboxBackend(
            session_id=session_id,
            image=image,
            workspace=workspace,
            max_memory_mb=max_memory_mb,
            max_cpu_percent=max_cpu_percent,
            network_enabled=network_enabled,
            default_timeout=default_timeout,
        )
        super().__init__(backend=self.backend, **kwargs)

    def cleanup(self) -> None:
        """清理沙箱资源

        停止并删除 Docker 容器，释放资源。
        建议在 Session 结束或 Agent 销毁时调用。
        """
        if hasattr(self, "backend") and self.backend is not None:
            self.backend.cleanup()

    def __del__(self):
        """析构时尝试清理容器"""
        try:
            self.cleanup()
        except Exception:
            pass
