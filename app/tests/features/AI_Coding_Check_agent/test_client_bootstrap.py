# -*- coding:utf-8 -*-
"""
AICodingCheckClient 登录凭据环境变量驱动测试。

验证 ``AICodingCheckClient.refresh_token`` 是否在缺失
``AUTH_DEFAULT_ADMIN_USERNAME`` / ``AUTH_DEFAULT_ADMIN_PASSWORD``
时返回 None 且不发起请求,以及在提供凭据时把环境变量值写入请求体。

Date: 2026-08-11
"""

import importlib
from unittest.mock import patch, MagicMock


def _reload_client(monkeypatch):
    """重新加载 AICodingCheckAgent.client 模块,让 os.environ 变更生效。

    Args:
        monkeypatch: pytest monkeypatch fixture,用于隔离环境变量。
    """
    from app.features.AI_Coding_Check_agent import client as mod

    importlib.reload(mod)
    return mod


def test_client_refresh_token_reads_env(monkeypatch):
    """环境变量同时存在时,登录请求体必须来自环境变量。"""
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("AUTH_DEFAULT_ADMIN_PASSWORD", "P@ssword1!")
    mod = _reload_client(monkeypatch)
    client = mod.AICodingCheckClient(base_url="http://x")

    with patch("app.features.AI_Coding_Check_agent.client.requests.post") as m:
        m.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"access_token": "T"},
        )
        token = client.refresh_token()
        assert token == "T"
        body = m.call_args.kwargs["json"]
        assert body == {"username": "admin", "password": "P@ssword1!"}


def test_client_refresh_token_fails_without_env(monkeypatch):
    """环境变量缺失时,不应发起任何请求,直接返回 None。"""
    monkeypatch.delenv("AUTH_DEFAULT_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("AUTH_DEFAULT_ADMIN_PASSWORD", raising=False)
    mod = _reload_client(monkeypatch)
    client = mod.AICodingCheckClient(base_url="http://x")

    with patch("app.features.AI_Coding_Check_agent.client.requests.post") as m:
        result = client.refresh_token()
        assert result is None
        assert m.call_count == 0
