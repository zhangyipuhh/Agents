# -*- coding:utf-8 -*-
"""
app/core/config/settings.py 中 ThirdPartyExecutorSettings 单元测试

覆盖：
- 类可导入
- env 变量名 THIRD_PARTY_EXECUTOR_ENDPOINTS 可被识别为 endpoints_json 字段
  （2026-08-05 修复：字段名默认映射的 env 名是 THIRD_PARTY_EXECUTOR_ENDPOINTS_JSON，
  与 .env 设计契约不一致，通过 AliasChoices 显式声明完整 env 名）
- 字段名构造 ThirdPartyExecutorSettings(endpoints_json=...) 保持向后兼容
- env_file 绝对路径（_ENV_FILE_PATH）：CWD 变化不影响 .env 加载
  （2026-08-05 修复：原 env_file=".env" 相对路径依赖进程工作目录，
  服务进程 CWD 非项目根时整个 .env 加载失败，第三方端点报"未配置"）

Date: 2026-08-05
Author: AI Assistant
"""

import json
import os

from app.core.config.settings import ThirdPartyExecutorSettings, _ENV_FILE_PATH


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_third_party_settings_importable():
    """
    P0: ThirdPartyExecutorSettings 可导入。
    """
    assert ThirdPartyExecutorSettings is not None


# ============================================================
# P1: env 名映射（AliasChoices 修复回归保护）
# ============================================================


def test_third_party_settings_env_name_endpoints(monkeypatch):
    """
    P1: 环境变量 THIRD_PARTY_EXECUTOR_ENDPOINTS 应被解析到 endpoints_json 字段。

    Args:
        monkeypatch: pytest monkeypatch fixture，用于注入环境变量

    Returns:
        None

    Raises:
        AssertionError: 若 env 名未被识别，endpoints_json 为空或解析失败
    """
    monkeypatch.setenv(
        "THIRD_PARTY_EXECUTOR_ENDPOINTS",
        json.dumps(
            [
                {
                    "name": "primary",
                    "url": "https://example.com/sybdc-service/ssh/execute",
                    "public_key_pem": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAAB\n-----END PUBLIC KEY-----",
                    "timeout_seconds": 60,
                    "enabled": True,
                }
            ]
        ),
    )
    s = ThirdPartyExecutorSettings()
    assert s.endpoints_json, "endpoints_json 不应为空"
    data = json.loads(s.endpoints_json)
    assert data[0]["name"] == "primary"


# ============================================================
# P1: 字段名构造向后兼容
# ============================================================


def test_third_party_settings_field_name_construct():
    """
    P1: 通过字段名 ThirdPartyExecutorSettings(endpoints_json=...) 构造仍可用。

    Returns:
        None

    Raises:
        AssertionError: 若 AliasChoices 破坏字段名构造
    """
    s = ThirdPartyExecutorSettings(endpoints_json="[]")
    assert s.endpoints_json == "[]"


# ============================================================
# P1: env_file 绝对路径（CWD 无关性回归保护）
# ============================================================


def test_env_file_path_is_absolute_and_exists():
    """
    P1: _ENV_FILE_PATH 应为指向项目根 .env 的绝对路径且文件存在。

    Returns:
        None

    Raises:
        AssertionError: 若路径非绝对、文件不存在或文件名不是 .env
    """
    assert os.path.isabs(_ENV_FILE_PATH)
    assert os.path.isfile(_ENV_FILE_PATH)
    assert os.path.basename(_ENV_FILE_PATH) == ".env"


def test_third_party_settings_cwd_independent(monkeypatch, tmp_path):
    """
    P1: 进程工作目录变化不应影响 .env 加载（env_file 绝对路径修复回归保护）。

    原 env_file=".env" 为相对路径，CWD 非项目根时整个 .env 加载失败；
    修复后基于文件位置推导绝对路径，CWD 变化不影响配置加载。

    Args:
        monkeypatch: pytest monkeypatch fixture，用于切换 CWD
        tmp_path: pytest 临时目录 fixture

    Returns:
        None

    Raises:
        AssertionError: 若 CWD 切换后配置加载结果与基线不一致
    """
    baseline = ThirdPartyExecutorSettings().endpoints_json
    monkeypatch.chdir(tmp_path)
    other = ThirdPartyExecutorSettings().endpoints_json
    assert other == baseline


def test_env_override_empty_empties_new_settings_instance(monkeypatch):
    """
    P1: os.environ 中空值 THIRD_PARTY_EXECUTOR_ENDPOINTS 会使新构造的 settings 该字段为空。

    2026-08-05 根因复现：pydantic-settings 环境变量优先级高于 .env 文件，
    运行环境（IDE 调试 / shell profile）存在空值该键时，endpoints_json 被覆盖为空，
    端点注册表加载 0 端点、报"primary 未配置"。此用例固化对优先级行为的理解，
    配合 endpoints.py 的 _read_env_file_endpoints_fallback 兜底机制使用。

    Args:
        monkeypatch: pytest monkeypatch fixture，用于注入空值环境变量

    Returns:
        None

    Raises:
        AssertionError: 若空值环境变量未覆盖 endpoints_json（pydantic 行为变更时提示）
    """
    monkeypatch.setenv("THIRD_PARTY_EXECUTOR_ENDPOINTS", "")
    s = ThirdPartyExecutorSettings()
    assert s.endpoints_json == ""
