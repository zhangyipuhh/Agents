# -*- coding:utf-8 -*-
"""
app/core/config/settings.py 中 ThirdPartyExecutorSettings 单元测试

覆盖：
- 类可导入
- env 变量名 THIRD_PARTY_EXECUTOR_ENDPOINTS 可被识别为 endpoints_json 字段
  （2026-08-05 修复：字段名默认映射的 env 名是 THIRD_PARTY_EXECUTOR_ENDPOINTS_JSON，
  与 .env 设计契约不一致，通过 AliasChoices 显式声明完整 env 名）
- 字段名构造 ThirdPartyExecutorSettings(endpoints_json=...) 保持向后兼容

Date: 2026-08-05
Author: AI Assistant
"""

import json

from app.core.config.settings import ThirdPartyExecutorSettings


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
