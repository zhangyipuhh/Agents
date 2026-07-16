# -*- coding:utf-8 -*-
"""
Email Admin Router 测试模块。

验证 /api/admin/email/* 路由的注册、SMTP 配置 CRUD、策略 CRUD、
测试连接与邮件发送接口的权限控制与成功/失败路径。
"""
from unittest.mock import AsyncMock, patch

import pytest


# =============================================================================
# P0: 导入与路由注册
# =============================================================================

def test_email_admin_router_importable():
    """测试 email_admin_router 模块可导入且包含 router。"""
    from app.routers import email_admin_router

    assert hasattr(email_admin_router, "router")


def test_email_admin_endpoints_registered(client):
    """测试所有邮件管理端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        "/api/admin/email/server-config",
        "/api/admin/email/server-config/test",
        "/api/admin/email/emailable-users",
        "/api/admin/email/policies",
        "/api/admin/email/policies/{policy_id}",
        "/api/admin/email/test",
        "/api/admin/email/send-by-policy/{policy_id}",
    ]
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# =============================================================================
# P1: SMTP 配置
# =============================================================================

def test_get_server_config_returns_200_and_no_password(client, admin_headers):
    """测试 GET /server-config 返回配置且密码字段为空字符串。"""
    service = client.app.state.email_config_service
    service.get_server_config_public = AsyncMock(return_value={
        "host": "smtp.qq.com", "port": 465, "use_ssl": True,
        "username": "x@qq.com", "password": "",
        "sender_name": "Admin", "enabled": True,
    })

    response = client.get("/api/admin/email/server-config", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["host"] == "smtp.qq.com"
    assert data["password"] == ""


def test_get_server_config_returns_null_when_no_config(client, admin_headers):
    """测试无配置时返回 null（200）。"""
    service = client.app.state.email_config_service
    service.get_server_config_public = AsyncMock(return_value=None)

    response = client.get("/api/admin/email/server-config", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() is None


def test_update_server_config_returns_200(client, admin_headers):
    """测试 PUT /server-config 保存配置。"""
    service = client.app.state.email_config_service
    service.upsert_server_config = AsyncMock(return_value={"id": 1, "updated_at": "2026-07-16"})

    response = client.put(
        "/api/admin/email/server-config",
        headers=admin_headers,
        json={
            "host": "smtp.qq.com",
            "port": 465,
            "use_ssl": True,
            "username": "x@qq.com",
            "password": "授权码",
            "sender_name": "管理员",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_test_connection_returns_success(client, admin_headers):
    """测试 POST /server-config/test 测试连接。"""
    service = client.app.state.email_config_service
    service.test_connection = AsyncMock(return_value={"success": True, "message": "OK"})
    service.get_active_server_config = AsyncMock(return_value=None)

    response = client.post(
        "/api/admin/email/server-config/test",
        headers=admin_headers,
        json={
            "host": "smtp.qq.com",
            "port": 465,
            "use_ssl": True,
            "username": "x@qq.com",
            "password": "授权码",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


# =============================================================================
# P1: 可发邮件用户列表
# =============================================================================

def test_list_emailable_users_returns_200(client, admin_headers):
    """测试 GET /emailable-users 返回已注册且邮箱非空用户。"""
    service = client.app.state.email_config_service
    service.list_emailable_users = AsyncMock(return_value=[
        {"id": 1, "username": "u1", "real_name": "U1", "email": "u1@e.com"},
    ])

    response = client.get("/api/admin/email/emailable-users", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["email"] == "u1@e.com"


# =============================================================================
# P1: 策略 CRUD
# =============================================================================

def test_list_policies_returns_200(client, admin_headers):
    """测试 GET /policies 列出策略。"""
    service = client.app.state.email_config_service
    service.list_policies = AsyncMock(return_value=[
        {"id": 1, "name": "策略1", "description": "", "recipient_user_ids": [1, 2]},
    ])

    response = client.get("/api/admin/email/policies", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()[0]["name"] == "策略1"


def test_create_policy_returns_201(client, admin_headers):
    """测试 POST /policies 新建策略。"""
    service = client.app.state.email_config_service
    service.create_policy = AsyncMock(return_value={
        "id": 1, "name": "策略1", "description": "", "recipient_user_ids": [1],
    })

    response = client.post(
        "/api/admin/email/policies",
        headers=admin_headers,
        json={"name": "策略1", "description": "", "recipient_user_ids": [1]},
    )

    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_update_policy_returns_200(client, admin_headers):
    """测试 PUT /policies/{id} 更新策略。"""
    service = client.app.state.email_config_service
    service.update_policy = AsyncMock(return_value={
        "id": 1, "name": "更新策略", "description": "", "recipient_user_ids": [1, 2],
    })

    response = client.put(
        "/api/admin/email/policies/1",
        headers=admin_headers,
        json={"name": "更新策略"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "更新策略"


def test_delete_policy_returns_204(client, admin_headers):
    """测试 DELETE /policies/{id} 删除策略。"""
    service = client.app.state.email_config_service
    service.delete_policy = AsyncMock(return_value=True)

    response = client.delete("/api/admin/email/policies/1", headers=admin_headers)

    assert response.status_code == 204


# =============================================================================
# P1: 发送邮件
# =============================================================================

def test_send_test_email_returns_200(client, admin_headers):
    """测试 POST /test 发送测试邮件（multipart/form-data）。"""
    service = client.app.state.email_config_service
    service.get_active_server_config = AsyncMock(return_value=MockConfig())

    with patch(
        "app.routers.email_admin_router.EmailService.send_email",
        new_callable=AsyncMock,
        return_value={"success": True, "message_id": "<x@y>", "sent_to": ["a@b.com"]},
    ):
        response = client.post(
            "/api/admin/email/test",
            headers=admin_headers,
            data={"to": "a@b.com", "cc": "", "subject": "测试", "body": "hello"},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_send_test_email_returns_400_when_no_smtp_config(client, admin_headers):
    """测试未配置 SMTP 时返回 400。"""
    service = client.app.state.email_config_service
    service.get_active_server_config = AsyncMock(return_value=None)

    response = client.post(
        "/api/admin/email/test",
        headers=admin_headers,
        data={"to": "a@b.com", "subject": "测试", "body": "hello"},
    )

    assert response.status_code == 400


def test_send_by_policy_returns_200(client, admin_headers):
    """测试 POST /send-by-policy/{id} 按策略发送邮件。"""
    service = client.app.state.email_config_service
    service.get_active_server_config = AsyncMock(return_value=MockConfig())
    service.get_policy = AsyncMock(return_value={
        "id": 1,
        "name": "策略1",
        "description": "",
        "recipient_user_ids": [1],
        "recipients": [{"user_id": 1, "username": "u1", "email": "u1@e.com"}],
    })

    with patch(
        "app.routers.email_admin_router.EmailService.send_email",
        new_callable=AsyncMock,
        return_value={"success": True, "message_id": "<x@y>", "sent_to": ["u1@e.com"]},
    ):
        response = client.post(
            "/api/admin/email/send-by-policy/1",
            headers=admin_headers,
            json={"subject": "主题", "body": "正文"},
        )

    assert response.status_code == 200
    assert response.json()["sent_to"] == ["u1@e.com"]


def test_send_by_policy_returns_404_when_not_found(client, admin_headers):
    """测试按不存在的策略发送返回 404。"""
    from app.shared.utils.email.email_config_service import EmailConfigNotFoundError
    service = client.app.state.email_config_service
    service.get_active_server_config = AsyncMock(return_value=MockConfig())
    service.get_policy = AsyncMock(side_effect=EmailConfigNotFoundError("not found"))

    response = client.post(
        "/api/admin/email/send-by-policy/999",
        headers=admin_headers,
        json={"subject": "主题", "body": "正文"},
    )

    assert response.status_code == 404


# =============================================================================
# 辅助 Mock 对象
# =============================================================================

class MockConfig:
    """模拟 EmailServerConfig，避免依赖 Pydantic 校验。"""
    host = "smtp.qq.com"
    port = 465
    use_ssl = True
    username = "x@qq.com"
    password = "authcode"
    sender_name = "管理员"
    enabled = True
