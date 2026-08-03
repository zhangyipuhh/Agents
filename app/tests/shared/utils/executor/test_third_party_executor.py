# -*- coding:utf-8 -*-
"""
第三方命令执行器单测（2026-08-03 新增）。

覆盖目标：
    - 端点注册表：从 settings 加载合法端点、拒绝非 https、拒绝非法 PEM
    - ``dispatch`` 加密 body 后调用 mock httpx；mock 返回明文响应 → 正常返回
    - 异常路径：超时 / HTTP 错误 / 非 JSON 响应 / 响应缺 success 字段
    - ``normalize_response`` 把第三方响应映射为既有 payload 结构

测试策略：
    - 不真打 https；用 ``unittest.mock.AsyncMock`` 替换 httpx.AsyncClient
    - 通过 monkeypatch 注入 ``ThirdPartyEndpointRegistry.get_instance()`` 返回的端点
      列表（避免依赖真实 settings）
    - 用真实 RSA 密钥对生成公钥，确保端点可解析

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.utils.crypto.rsa_aes import (
    decrypt_body,
    encrypt_body,
    generate_rsa_keypair_pem,
)
from app.shared.utils.executor import errors as executor_errors
from app.shared.utils.executor import (
    third_party_executor as tp_module,
)
from app.shared.utils.executor.endpoints import (
    ThirdPartyEndpoint,
    ThirdPartyEndpointRegistry,
)
from app.shared.utils.executor.errors import ThirdPartyExecutorError

# 关键:``app.core.config.__init__.py`` 把 ``settings`` 重新导出为 Settings 实例,
# 会遮蔽 ``app.core.config.settings`` 子模块。必须用 importlib 强制拿到子模块,
# 否则 ``from app.core.config import settings as settings_mod`` 实际拿到 Settings 类。
import importlib

_settings_module = importlib.import_module("app.core.config.settings")
settings_mod = _settings_module


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_keys() -> Dict[str, str]:
    """RSA-2048 测试用密钥对。"""
    return generate_rsa_keypair_pem()


@pytest.fixture
def endpoint(rsa_keys: Dict[str, str]) -> ThirdPartyEndpoint:
    """构造合法端点。"""
    return ThirdPartyEndpoint(
        name="primary",
        url="https://exec.test.local/api/v1/exec",
        public_key_pem=rsa_keys["public_key_pem"],
        timeout_seconds=10,
        enabled=True,
    )


def _patch_registry(monkeypatch, endpoints: Dict[str, ThirdPartyEndpoint]) -> None:
    """用 stub registry 替换 ``ThirdPartyEndpointRegistry.get_instance``。

    Args:
        monkeypatch: pytest fixture
        endpoints: 名称 → 端点 dict
    """
    fake_registry = MagicMock(name="ThirdPartyEndpointRegistry")

    def _fake_get(name):
        ep = endpoints.get(name)
        if ep is None:
            raise ThirdPartyExecutorError(
                error_code=executor_errors.ERR_CONFIG_MISSING,
                reason=f"third_party endpoint '{name}' 未配置",
                user_message=f"第三方端点 {name} 未配置",
            )
        return ep

    fake_registry.get = MagicMock(side_effect=_fake_get)
    fake_registry.names = MagicMock(return_value=list(endpoints.keys()))
    monkeypatch.setattr(
        ThirdPartyEndpointRegistry, "get_instance", classmethod(lambda cls: fake_registry)
    )


def _make_response(
    *,
    status_code: int = 200,
    json_data: Optional[Any] = None,
    raise_exc: Optional[Exception] = None,
) -> MagicMock:
    """构造 httpx 响应 mock。"""
    resp = MagicMock(name="httpx.Response")
    resp.status_code = status_code
    if raise_exc is not None:
        resp.json = MagicMock(side_effect=raise_exc)
    else:
        resp.json = MagicMock(return_value=json_data)
    return resp


# ---------------------------------------------------------------------------
# 1. 端点注册表校验
# ---------------------------------------------------------------------------


def test_endpoint_registry_load_valid_endpoint(monkeypatch, endpoint) -> None:
    """合法端点应加载成功。"""
    import importlib

    settings_module = importlib.import_module("app.core.config.settings")
    settings_obj = settings_module.settings
    fake_cfg = MagicMock(
        endpoints_json=json.dumps(
            [
                {
                    "name": endpoint.name,
                    "url": endpoint.url,
                    "public_key_pem": endpoint.public_key_pem,
                    "timeout_seconds": 10,
                    "enabled": True,
                }
            ]
        ),
        default_endpoint="primary",
    )
    monkeypatch.setattr(settings_obj, "third_party_executor", fake_cfg)
    registry = ThirdPartyEndpointRegistry()
    registry.load_from_settings(settings=settings_obj)
    got = registry.get("primary")
    assert got.name == "primary"
    assert got.url.startswith("https://")


def test_endpoint_registry_rejects_http(monkeypatch, rsa_keys) -> None:
    """非 https URL 应被拒。"""
    import importlib

    settings_module = importlib.import_module("app.core.config.settings")
    settings_obj = settings_module.settings
    fake_cfg = MagicMock(
        endpoints_json=json.dumps(
            [
                {
                    "name": "bad",
                    "url": "http://insecure.test/api",
                    "public_key_pem": rsa_keys["public_key_pem"],
                    "timeout_seconds": 10,
                    "enabled": True,
                }
            ]
        ),
        default_endpoint="bad",
    )
    monkeypatch.setattr(settings_obj, "third_party_executor", fake_cfg)
    registry = ThirdPartyEndpointRegistry()
    registry.load_from_settings(settings=settings_obj)
    with pytest.raises(ThirdPartyExecutorError):
        registry.get("bad")


def test_endpoint_registry_rejects_invalid_pem(monkeypatch) -> None:
    """非法 PEM 应被拒。"""
    import importlib

    settings_module = importlib.import_module("app.core.config.settings")
    settings_obj = settings_module.settings
    fake_cfg = MagicMock(
        endpoints_json=json.dumps(
            [
                {
                    "name": "bad",
                    "url": "https://x.test/api",
                    "public_key_pem": "not-a-pem",
                    "timeout_seconds": 10,
                    "enabled": True,
                }
            ]
        ),
        default_endpoint="bad",
    )
    monkeypatch.setattr(settings_obj, "third_party_executor", fake_cfg)
    registry = ThirdPartyEndpointRegistry()
    registry.load_from_settings(settings=settings_obj)
    with pytest.raises(ThirdPartyExecutorError):
        registry.get("bad")


def test_endpoint_get_disabled_raises(monkeypatch, rsa_keys) -> None:
    """端点 enabled=false 时取不到。"""
    import importlib

    settings_module = importlib.import_module("app.core.config.settings")
    settings_obj = settings_module.settings
    fake_cfg = MagicMock(
        endpoints_json=json.dumps(
            [
                {
                    "name": "off",
                    "url": "https://x.test/api",
                    "public_key_pem": rsa_keys["public_key_pem"],
                    "timeout_seconds": 10,
                    "enabled": False,
                }
            ]
        ),
        default_endpoint="off",
    )
    monkeypatch.setattr(settings_obj, "third_party_executor", fake_cfg)
    registry = ThirdPartyEndpointRegistry()
    registry.load_from_settings(settings=settings_obj)
    with pytest.raises(ThirdPartyExecutorError) as ei:
        registry.get("off")
    assert ei.value.error_code == executor_errors.ERR_CONFIG_MISSING


def test_endpoint_get_unknown_name_raises(monkeypatch) -> None:
    """未配置的端点名应抛 ``ERR_CONFIG_MISSING``。"""
    import importlib

    settings_module = importlib.import_module("app.core.config.settings")
    settings_obj = settings_module.settings
    fake_cfg = MagicMock(endpoints_json="", default_endpoint="primary")
    monkeypatch.setattr(settings_obj, "third_party_executor", fake_cfg)
    registry = ThirdPartyEndpointRegistry()
    registry.load_from_settings(settings=settings_obj)
    with pytest.raises(ThirdPartyExecutorError) as ei:
        registry.get("nope")
    assert ei.value.error_code == executor_errors.ERR_CONFIG_MISSING


# ---------------------------------------------------------------------------
# 2. dispatch 成功路径
# ---------------------------------------------------------------------------


def test_dispatch_encrypts_body_and_returns_response(
    monkeypatch, endpoint, rsa_keys
) -> None:
    """dispatch 应加密 body → 调 mock httpx → 解密侧可还原（用同私钥验证）。

    Args:
        monkeypatch: pytest fixture
        endpoint: 合法端点
        rsa_keys: RSA 密钥对（解密端校验用）
    """
    _patch_registry(monkeypatch, {endpoint.name: endpoint})

    # mock httpx.AsyncClient
    fake_response = _make_response(
        status_code=200, json_data={"success": True, "output": "hello", "exit_code": 0}
    )
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.aclose = AsyncMock(return_value=None)

    captured: Dict[str, Any] = {}

    async def _capture_post(url, json=None, headers=None):
        # 解密收到的 payload，验证加密确实发生
        plaintext = decrypt_body(json, rsa_keys["private_key_pem"])
        captured["url"] = url
        captured["plaintext"] = plaintext
        return fake_response

    fake_client.post = AsyncMock(side_effect=_capture_post)

    with patch.object(tp_module.httpx, "AsyncClient", return_value=fake_client):
        resp = asyncio.run(
            tp_module.dispatch(
                endpoint_name="primary",
                command="echo hello",
                wrapped_command="/bin/bash -c 'echo hello'",
                business_name="alpha",
                timeout=10,
                server_type="linux",
            )
        )

    assert resp == {"success": True, "output": "hello", "exit_code": 0}
    assert captured["url"] == endpoint.url
    # 验证 plaintext 字段齐
    for k in (
        "command",
        "wrapped_command",
        "business_name",
        "timeout",
        "platform",
        "request_id",
        "issued_at",
    ):
        assert k in captured["plaintext"]
    assert captured["plaintext"]["command"] == "echo hello"
    assert captured["plaintext"]["business_name"] == "alpha"
    assert captured["plaintext"]["platform"] == "linux"


def test_dispatch_uses_injected_client(monkeypatch, endpoint) -> None:
    """传入 ``client`` 参数时不应新建 AsyncClient。"""
    _patch_registry(monkeypatch, {endpoint.name: endpoint})

    fake_response = _make_response(
        status_code=200, json_data={"success": True, "exit_code": 0}
    )
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.aclose = AsyncMock(return_value=None)

    with patch.object(tp_module.httpx, "AsyncClient") as ctor:
        resp = asyncio.run(
            tp_module.dispatch(
                endpoint_name="primary",
                command="ls",
                wrapped_command="/bin/bash -c 'ls'",
                business_name="alpha",
                timeout=10,
                server_type="linux",
                client=fake_client,
            )
        )
    assert resp == {"success": True, "exit_code": 0}
    ctor.assert_not_called()
    fake_client.aclose.assert_not_called()


# ---------------------------------------------------------------------------
# 3. dispatch 异常路径
# ---------------------------------------------------------------------------


def test_dispatch_timeout_raises(monkeypatch, endpoint) -> None:
    """httpx 超时 → ``ERR_TIMEOUT``。"""
    _patch_registry(monkeypatch, {endpoint.name: endpoint})
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(side_effect=httpx.TimeoutException("boom"))
    fake_client.aclose = AsyncMock(return_value=None)

    with patch.object(tp_module.httpx, "AsyncClient", return_value=fake_client):
        with pytest.raises(ThirdPartyExecutorError) as ei:
            asyncio.run(
                tp_module.dispatch(
                    endpoint_name="primary",
                    command="ls",
                    wrapped_command="/bin/bash -c 'ls'",
                    business_name="alpha",
                    timeout=10,
                    server_type="linux",
                )
            )
    assert ei.value.error_code == executor_errors.ERR_TIMEOUT


def test_dispatch_http_error_raises(monkeypatch, endpoint) -> None:
    """httpx 通用错误 → ``ERR_HTTP``。"""
    _patch_registry(monkeypatch, {endpoint.name: endpoint})
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    fake_client.aclose = AsyncMock(return_value=None)

    with patch.object(tp_module.httpx, "AsyncClient", return_value=fake_client):
        with pytest.raises(ThirdPartyExecutorError) as ei:
            asyncio.run(
                tp_module.dispatch(
                    endpoint_name="primary",
                    command="ls",
                    wrapped_command="/bin/bash -c 'ls'",
                    business_name="alpha",
                    timeout=10,
                    server_type="linux",
                )
            )
    assert ei.value.error_code == executor_errors.ERR_HTTP


def test_dispatch_http_4xx_raises(monkeypatch, endpoint) -> None:
    """HTTP 4xx/5xx → ``ERR_HTTP``。"""
    _patch_registry(monkeypatch, {endpoint.name: endpoint})
    fake_response = _make_response(status_code=500)
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.aclose = AsyncMock(return_value=None)

    with patch.object(tp_module.httpx, "AsyncClient", return_value=fake_client):
        with pytest.raises(ThirdPartyExecutorError) as ei:
            asyncio.run(
                tp_module.dispatch(
                    endpoint_name="primary",
                    command="ls",
                    wrapped_command="/bin/bash -c 'ls'",
                    business_name="alpha",
                    timeout=10,
                    server_type="linux",
                )
            )
    assert ei.value.error_code == executor_errors.ERR_HTTP
    assert "500" in ei.value.user_message


def test_dispatch_invalid_json_raises(monkeypatch, endpoint) -> None:
    """响应非 JSON → ``ERR_INVALID_RESPONSE``。"""
    _patch_registry(monkeypatch, {endpoint.name: endpoint})
    fake_response = _make_response(
        status_code=200, raise_exc=json.JSONDecodeError("err", "", 0)
    )
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.aclose = AsyncMock(return_value=None)

    with patch.object(tp_module.httpx, "AsyncClient", return_value=fake_client):
        with pytest.raises(ThirdPartyExecutorError) as ei:
            asyncio.run(
                tp_module.dispatch(
                    endpoint_name="primary",
                    command="ls",
                    wrapped_command="/bin/bash -c 'ls'",
                    business_name="alpha",
                    timeout=10,
                    server_type="linux",
                )
            )
    assert ei.value.error_code == executor_errors.ERR_INVALID_RESPONSE


def test_dispatch_response_not_dict_raises(monkeypatch, endpoint) -> None:
    """响应是 list / str → ``ERR_INVALID_RESPONSE``。"""
    _patch_registry(monkeypatch, {endpoint.name: endpoint})
    fake_response = _make_response(status_code=200, json_data=["not", "a", "dict"])
    fake_client = MagicMock(name="httpx.AsyncClient")
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.aclose = AsyncMock(return_value=None)

    with patch.object(tp_module.httpx, "AsyncClient", return_value=fake_client):
        with pytest.raises(ThirdPartyExecutorError) as ei:
            asyncio.run(
                tp_module.dispatch(
                    endpoint_name="primary",
                    command="ls",
                    wrapped_command="/bin/bash -c 'ls'",
                    business_name="alpha",
                    timeout=10,
                    server_type="linux",
                )
            )
    assert ei.value.error_code == executor_errors.ERR_INVALID_RESPONSE


def test_dispatch_unknown_endpoint_raises(monkeypatch) -> None:
    """端点不存在 → ``ERR_CONFIG_MISSING``（不应发起 HTTP）。"""
    _patch_registry(monkeypatch, {})
    with patch.object(tp_module.httpx, "AsyncClient") as ctor:
        with pytest.raises(ThirdPartyExecutorError) as ei:
            asyncio.run(
                tp_module.dispatch(
                    endpoint_name="nope",
                    command="ls",
                    wrapped_command="/bin/bash -c 'ls'",
                    business_name="alpha",
                    timeout=10,
                    server_type="linux",
                )
            )
    assert ei.value.error_code == executor_errors.ERR_CONFIG_MISSING
    ctor.assert_not_called()


# ---------------------------------------------------------------------------
# 4. normalize_response
# ---------------------------------------------------------------------------


def test_normalize_response_success() -> None:
    """success=True 的响应归一化为既有 payload 结构。"""
    out = tp_module.normalize_response(
        {"success": True, "output": "hi", "exit_code": 0}
    )
    assert out == {"success": True, "output": "hi", "exit_code": 0}


def test_normalize_response_with_stderr() -> None:
    """带 error 字段的响应归一化。"""
    out = tp_module.normalize_response(
        {"success": False, "output": "", "error": "boom", "exit_code": 2}
    )
    assert out["success"] is False
    assert out["error"] == "boom"
    assert out["exit_code"] == 2


def test_normalize_response_missing_success_raises() -> None:
    """缺 success 字段 → ``ERR_INVALID_RESPONSE``。"""
    with pytest.raises(ThirdPartyExecutorError) as ei:
        tp_module.normalize_response({"output": "x", "exit_code": 0})
    assert ei.value.error_code == executor_errors.ERR_INVALID_RESPONSE


def test_normalize_response_invalid_exit_code_raises() -> None:
    """exit_code 非法 → ``ERR_INVALID_RESPONSE``。"""
    with pytest.raises(ThirdPartyExecutorError) as ei:
        tp_module.normalize_response({"success": True, "exit_code": "abc"})
    assert ei.value.error_code == executor_errors.ERR_INVALID_RESPONSE