# -*- coding:utf-8 -*-
"""
测试 SandboxSettings 配置模块

验证 2026-06-12 新增的沙箱容器化部署配置：
- 默认值
- 字段约束（Literal 枚举、ge/le 边界）
- 环境变量覆盖
- Pydantic 校验失败场景
- Settings.get_sandbox_config() 聚合方法
"""

import pytest
from pydantic import ValidationError

from app.core.config.settings import SandboxSettings, Settings


# 防止 .env 中的环境变量污染测试默认值
_ENV_KEYS = [
    "SANDBOX_DOCKER_MODE",
    "SANDBOX_DOCKER_HOST",
    "SANDBOX_IMAGE",
    "SANDBOX_MAX_MEMORY_MB",
    "SANDBOX_MAX_CPU_PERCENT",
    "SANDBOX_NETWORK_ENABLED",
    "SANDBOX_DEFAULT_TIMEOUT",
    "SANDBOX_CONTAINER_WORKSPACE",
    "SANDBOX_HOST_WORKSPACE_PREFIX",
    "SANDBOX_K8S_NAMESPACE",
    "SANDBOX_FALLBACK_TO_LOCAL",
]


@pytest.fixture(autouse=True)
def _clear_sandbox_env(monkeypatch):
    """每个测试前清空沙箱相关环境变量，确保默认值测试稳定。"""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestSandboxSettingsDefaults:
    """SandboxSettings 默认值测试"""

    def test_settings_importable(self):
        """P0: SandboxSettings 可导入，类型正确。"""
        from app.core.config.settings import SandboxSettings as Cls

        assert Cls is SandboxSettings

    def test_default_docker_mode_is_local(self):
        """P1: 默认 docker_mode 为 local。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_docker_mode == "local"

    def test_default_docker_host_is_empty(self):
        """P2: docker_host 默认空字符串（local 模式不需要）。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_docker_host == ""

    def test_default_image(self):
        """P1: 默认镜像为 python:3.12-alpine。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_image == "python:3.12-alpine"

    def test_default_memory(self):
        """P1: 默认内存限制 512MB。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_max_memory_mb == 512

    def test_default_cpu(self):
        """P1: 默认 CPU 限制 100%。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_max_cpu_percent == 100

    def test_default_network_disabled(self):
        """P1: 默认禁用网络。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_network_enabled is False

    def test_default_timeout(self):
        """P1: 默认命令超时 60 秒。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_default_timeout == 60

    def test_default_container_workspace(self):
        """P1: 默认容器内工作目录 /workspace。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_container_workspace == "/workspace"

    def test_default_host_workspace_prefix_empty(self):
        """P2: 默认 host_workspace_prefix 空字符串。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_host_workspace_prefix == ""

    def test_default_k8s_namespace(self):
        """P2: 默认 K8s 命名空间 default。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_k8s_namespace == "default"

    def test_default_fallback_to_local_is_false(self):
        """P1: 默认不开启本地回退。"""
        cfg = SandboxSettings()
        assert cfg.sandbox_fallback_to_local is False


class TestSandboxSettingsConstraints:
    """字段约束测试"""

    @pytest.mark.parametrize("mode", ["local", "socket", "dind", "k8s"])
    def test_valid_docker_modes_accepted(self, mode):
        """P1: 4 种合法 docker_mode 都被接受。"""
        cfg = SandboxSettings(sandbox_docker_mode=mode)
        assert cfg.sandbox_docker_mode == mode

    @pytest.mark.parametrize("mode", ["", "docker", "DinD", "K8S", "invalid"])
    def test_invalid_docker_mode_rejected(self, mode):
        """P1: 非法 docker_mode 抛 ValidationError。"""
        with pytest.raises(ValidationError) as exc_info:
            SandboxSettings(sandbox_docker_mode=mode)
        # pydantic 2.x 错误格式
        assert "sandbox_docker_mode" in str(exc_info.value)

    @pytest.mark.parametrize("value", [64, 100, 512, 4096])
    def test_memory_ge_64_accepted(self, value):
        """P1: 内存 ≥64MB 合法。"""
        cfg = SandboxSettings(sandbox_max_memory_mb=value)
        assert cfg.sandbox_max_memory_mb == value

    @pytest.mark.parametrize("value", [0, 32, 63])
    def test_memory_below_64_rejected(self, value):
        """P1: 内存 <64MB 抛 ValidationError。"""
        with pytest.raises(ValidationError):
            SandboxSettings(sandbox_max_memory_mb=value)

    @pytest.mark.parametrize("value", [10, 50, 100])
    def test_cpu_in_range_accepted(self, value):
        """P1: CPU 10-100 合法。"""
        cfg = SandboxSettings(sandbox_max_cpu_percent=value)
        assert cfg.sandbox_max_cpu_percent == value

    @pytest.mark.parametrize("value", [0, 5, 9, 101, 200])
    def test_cpu_out_of_range_rejected(self, value):
        """P1: CPU 越界抛 ValidationError。"""
        with pytest.raises(ValidationError):
            SandboxSettings(sandbox_max_cpu_percent=value)

    @pytest.mark.parametrize("value", [1, 60, 300, 3600])
    def test_timeout_ge_1_accepted(self, value):
        """P1: 超时 ≥1 秒合法。"""
        cfg = SandboxSettings(sandbox_default_timeout=value)
        assert cfg.sandbox_default_timeout == value

    @pytest.mark.parametrize("value", [0, -1])
    def test_timeout_below_1_rejected(self, value):
        """P1: 超时 <1 抛 ValidationError。"""
        with pytest.raises(ValidationError):
            SandboxSettings(sandbox_default_timeout=value)

    @pytest.mark.parametrize("value", ["true", "True", "false", "False", "1", "0", "yes", "no"])
    def test_network_enabled_string_parsing(self, value):
        """P1: 字符串布尔值正确解析。"""
        cfg = SandboxSettings(sandbox_network_enabled=value)
        expected = value.lower() in ("true", "1", "yes", "on")
        assert cfg.sandbox_network_enabled is expected

    @pytest.mark.parametrize("value", ["true", "True", "false", "False", "1", "0", "yes", "no"])
    def test_fallback_to_local_string_parsing(self, value):
        """P1: fallback_to_local 字符串布尔值正确解析。"""
        cfg = SandboxSettings(sandbox_fallback_to_local=value)
        expected = value.lower() in ("true", "1", "yes", "on")
        assert cfg.sandbox_fallback_to_local is expected


class TestSandboxSettingsEnvOverride:
    """环境变量覆盖测试"""

    def test_docker_mode_env_override(self, monkeypatch):
        """P1: SANDBOX_DOCKER_MODE 环境变量覆盖默认值。"""
        monkeypatch.setenv("SANDBOX_DOCKER_MODE", "socket")
        cfg = SandboxSettings()
        assert cfg.sandbox_docker_mode == "socket"

    def test_image_env_override(self, monkeypatch):
        """P1: SANDBOX_IMAGE 环境变量覆盖。"""
        monkeypatch.setenv("SANDBOX_IMAGE", "python:3.11-slim")
        cfg = SandboxSettings()
        assert cfg.sandbox_image == "python:3.11-slim"

    def test_memory_env_override(self, monkeypatch):
        """P1: SANDBOX_MAX_MEMORY_MB 环境变量覆盖。"""
        monkeypatch.setenv("SANDBOX_MAX_MEMORY_MB", "1024")
        cfg = SandboxSettings()
        assert cfg.sandbox_max_memory_mb == 1024

    def test_host_workspace_prefix_env_override(self, monkeypatch):
        """P1: SANDBOX_HOST_WORKSPACE_PREFIX 环境变量覆盖。"""
        monkeypatch.setenv("SANDBOX_HOST_WORKSPACE_PREFIX", "/host/app/data")
        cfg = SandboxSettings()
        assert cfg.sandbox_host_workspace_prefix == "/host/app/data"

    def test_fallback_to_local_env_override(self, monkeypatch):
        """P1: SANDBOX_FALLBACK_TO_LOCAL 环境变量覆盖。"""
        monkeypatch.setenv("SANDBOX_FALLBACK_TO_LOCAL", "true")
        cfg = SandboxSettings()
        assert cfg.sandbox_fallback_to_local is True


class TestSettingsGetSandboxConfig:
    """Settings.get_sandbox_config() 聚合方法测试"""

    def test_get_sandbox_config_returns_all_keys(self):
        """P1: get_sandbox_config 返回所有必要字段。"""
        from app.core.config.settings import Settings

        s = Settings()
        cfg = s.get_sandbox_config()
        expected_keys = {
            "docker_mode", "docker_host", "image", "max_memory_mb",
            "max_cpu_percent", "network_enabled", "default_timeout",
            "container_workspace", "host_workspace_prefix", "k8s_namespace",
            "fallback_to_local",
        }
        assert set(cfg.keys()) == expected_keys

    def test_get_sandbox_config_values_match(self):
        """P1: get_sandbox_config 字段值与 SandboxSettings 一致。"""
        from app.core.config.settings import Settings

        s = Settings()
        cfg = s.get_sandbox_config()
        sb = s.sandbox
        assert cfg["docker_mode"] == sb.sandbox_docker_mode
        assert cfg["image"] == sb.sandbox_image
        assert cfg["max_memory_mb"] == sb.sandbox_max_memory_mb
        assert cfg["container_workspace"] == sb.sandbox_container_workspace
        assert cfg["host_workspace_prefix"] == sb.sandbox_host_workspace_prefix

    def test_get_sandbox_config_is_dict(self):
        """P2: 返回类型为 dict。"""
        from app.core.config.settings import Settings

        s = Settings()
        cfg = s.get_sandbox_config()
        assert isinstance(cfg, dict)
