# -*- coding:utf-8 -*-
"""
Agent Router /abort 端点测试（2026-07-06 新增）

覆盖：
- POST /api/agent/{session_id}/abort 路由注册
- 已注册 session → 触发 abort_event + 返回 status=aborted
- 未注册 session → 返回 status=not_found（不抛错）
- 重复调用 idempotent
- 路由与 GET /{agent_name}/agents-md 不冲突

测试策略：使用 client fixture + 真实路由注册，绕开 _stream_helper 的副作用。
"""

import pytest


def test_abort_endpoint_registered(client):
    """测试 POST /api/agent/{session_id}/abort 路由已注册"""
    routes = [r.path for r in client.app.routes if hasattr(r, "path")]
    assert "/api/agent/{session_id}/abort" in routes


def test_abort_unknown_session_returns_not_found(client, admin_headers):
    """测试对未注册 session 调 abort 返回 200 + status=not_found

    场景：前端误调 abort（session 已结束或从未启动），后端应容错。
    """
    headers = {**admin_headers, "X-Session-ID": "test-session"}
    response = client.post(
        "/api/agent/some_nonexistent_session_id_xyz/abort",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_found"
    assert data["session_id"] == "some_nonexistent_session_id_xyz"


def test_abort_registered_session_triggers_abort_event(client, admin_headers):
    """测试对已注册 session 调 abort → 触发 abort_event + 返回 status=aborted

    验证：
    1. 路由返回 200 + status=aborted
    2. 全局 _abort_signals 中对应 session 的 event 已被 set
    3. 清理（unregister）在测试结束后由 teardown 兜底
    """
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        unregister_abort_signal,
    )

    session_id = "test_abort_endpoint_registered_001"
    register_abort_signal(session_id)
    try:
        # 初始：未 set
        assert not get_abort_signal(session_id).is_set()

        # 调 abort
        headers = {**admin_headers, "X-Session-ID": "test-session"}
        response = client.post(
            f"/api/agent/{session_id}/abort",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "aborted"
        assert data["session_id"] == session_id

        # 验证 event 已被 set
        assert get_abort_signal(session_id).is_set()
    finally:
        unregister_abort_signal(session_id)


def test_abort_idempotent_multiple_calls(client, admin_headers):
    """测试多次调 abort 同一 session 不抛错（idempotent）"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        unregister_abort_signal,
    )

    session_id = "test_abort_idempotent_001"
    register_abort_signal(session_id)
    try:
        headers = {**admin_headers, "X-Session-ID": "test-session"}
        for _ in range(3):
            response = client.post(
                f"/api/agent/{session_id}/abort",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.json()["status"] == "aborted"
        assert get_abort_signal(session_id).is_set()
    finally:
        unregister_abort_signal(session_id)


def test_abort_does_not_conflict_with_agents_md_route(client):
    """测试 abort 路由与 agents-md 路由不冲突

    abort: POST /api/agent/{session_id}/abort
    agents-md: GET /api/agent/{agent_name}/agents-md
    两者路径不同（abort 有 /abort 后缀），应能正确路由。
    """
    # 两个路径都应在路由表中
    routes = [r.path for r in client.app.routes if hasattr(r, "path")]
    assert "/api/agent/{session_id}/abort" in routes
    assert "/api/agent/{agent_name}/agents-md" in routes
