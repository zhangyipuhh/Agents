# -*- coding:utf-8 -*-
"""
Email Admin Router 按用户隔离（OwnershipScope）测试模块。

验证：
- 普通用户对他人创建的策略执行 update / delete / send-by-policy 时
  收到 404（不泄露策略是否存在）
- 普通用户对不存在的策略收到 404
- admin 可看到所有策略（list 透传 system scope 不限用户）
- 创建策略时把 ``created_by_user_id=request.state.user_id`` 写入 service
- ``send-by-policy`` 受归属校验保护
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _grant_testuser_email_acl(client):
    """覆盖 client 的 menu_permission_service：授予 testuser 邮件设置相关 ACL。

    普通用户（testuser）在 conftest 默认下仅可见 ``profile``，需要追加
    ``task-scheduler.email-settings.*`` ACL 才能调 ``/policies`` /
    ``/send-by-policy`` 等端点。本 helper 用 monkeypatch 风格的 stub
    替换 ``get_visible_menu_ids``。
    """
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService

    visible_set = {
        "profile",
        "task-scheduler.email-settings.server",
        "task-scheduler.email-settings.policies",
        "task-scheduler.email-settings.test",
    }

    async def fake_visible(user_id, is_admin):
        if is_admin:
            from app.core.menu_registry import get_enabled_items

            return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
        return sorted(visible_set)

    stub = MenuPermissionService(db=None)
    stub.get_visible_menu_ids = fake_visible
    client.app.state.menu_permission_service = stub


@pytest.fixture(autouse=True)
def _grant_acl_for_user_headers(client):
    """autouse：所有 user_headers 用例自动授予邮件设置 ACL。

    admin_headers 不受影响（admin 直通）；只在测试用 user_headers 时
    自动覆盖 menu_permission_service，让 testuser 拥有
    ``task-scheduler.email-settings.*`` 授权。
    """
    _grant_testuser_email_acl(client)
    yield


# =============================================================================
# P0: 端点路由已注册
# =============================================================================


def test_endpoints_registered(client):
    """policy 端点必须已注册。"""
    routes = [r.path for r in client.app.routes]
    assert "/api/admin/email/policies" in routes
    assert "/api/admin/email/policies/{policy_id}" in routes
    assert "/api/admin/email/send-by-policy/{policy_id}" in routes


# =============================================================================
# P1: list / create 透传 scope
# =============================================================================


def test_list_policies_passes_user_scope_to_service(client, admin_headers):
    """admin 调用 ``GET /policies``：service.list_policies 被调用且 scope 为 admin。"""
    service = client.app.state.email_config_service
    service.list_policies = AsyncMock(return_value=[])

    response = client.get("/api/admin/email/policies", headers=admin_headers)

    assert response.status_code == 200
    service.list_policies.assert_awaited_once()
    scope_arg = service.list_policies.await_args.args[0]
    assert scope_arg.is_admin is True
    assert scope_arg.user_id == 1  # admin 测试 fixture id


def test_list_policies_passes_user_scope_for_normal_user(client, user_headers):
    """普通用户调用 ``GET /policies``：scope.is_admin=False / user_id=2。"""
    service = client.app.state.email_config_service
    service.list_policies = AsyncMock(return_value=[])

    response = client.get("/api/admin/email/policies", headers=user_headers)

    assert response.status_code == 200
    scope_arg = service.list_policies.await_args.args[0]
    assert scope_arg.is_admin is False
    assert scope_arg.user_id == 2  # testuser id


def test_create_policy_passes_user_id_as_owner(client, admin_headers):
    """``POST /policies``：service.create_policy 收到 created_by_user_id=1 (admin)。"""
    service = client.app.state.email_config_service
    service.create_policy = AsyncMock(return_value={
        "id": 10, "name": "新策略", "description": "",
        "recipient_user_ids": [1], "subject_template": "", "body_template": "",
        "created_by_user_id": 1,
    })

    response = client.post(
        "/api/admin/email/policies",
        headers=admin_headers,
        json={"name": "新策略", "description": "", "recipient_user_ids": [1]},
    )

    assert response.status_code == 201
    assert service.create_policy.await_args.kwargs["created_by_user_id"] == 1


# =============================================================================
# P1: update / delete 越权 404
# =============================================================================


def test_update_policy_other_user_returns_404(client, user_headers):
    """普通用户更新他人策略：service 返回 None 时路由返回 404。"""
    service = client.app.state.email_config_service
    service.update_policy = AsyncMock(return_value=None)  # 越权

    response = client.put(
        "/api/admin/email/policies/1",
        headers=user_headers,
        json={"name": "改后策略"},
    )

    assert response.status_code == 404
    assert "不存在或无权访问" in response.json()["detail"]


def test_update_policy_owner_returns_200(client, user_headers):
    """普通用户更新自己的策略：返回 200 + 更新后策略。"""
    service = client.app.state.email_config_service
    service.update_policy = AsyncMock(return_value={
        "id": 1, "name": "改后策略", "description": "",
        "recipient_user_ids": [1], "subject_template": "", "body_template": "",
        "created_by_user_id": 2,
    })

    response = client.put(
        "/api/admin/email/policies/1",
        headers=user_headers,
        json={"name": "改后策略"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "改后策略"


def test_update_policy_passes_scope_to_service(client, user_headers):
    """``PUT /policies/{id}`` 把 user scope 传给 service.update_policy。"""
    service = client.app.state.email_config_service
    service.update_policy = AsyncMock(return_value={
        "id": 1, "name": "x", "description": "", "recipient_user_ids": [1],
        "subject_template": "", "body_template": "",
    })

    response = client.put(
        "/api/admin/email/policies/1", headers=user_headers, json={"name": "x"},
    )
    assert response.status_code == 200
    scope_arg = service.update_policy.await_args.kwargs["scope"]
    assert scope_arg.is_admin is False
    assert scope_arg.user_id == 2


def test_delete_policy_other_user_returns_404(client, user_headers):
    """普通用户删除他人策略：service.delete_policy 返回 False → 404。"""
    service = client.app.state.email_config_service
    service.delete_policy = AsyncMock(return_value=False)

    response = client.delete(
        "/api/admin/email/policies/1", headers=user_headers,
    )
    assert response.status_code == 404


def test_delete_policy_owner_returns_204(client, user_headers):
    """普通用户删除自己的策略：204。"""
    service = client.app.state.email_config_service
    service.delete_policy = AsyncMock(return_value=True)

    response = client.delete(
        "/api/admin/email/policies/1", headers=user_headers,
    )
    assert response.status_code == 204


def test_delete_policy_passes_scope_to_service(client, user_headers):
    """``DELETE /policies/{id}`` 把 user scope 传给 service.delete_policy。"""
    service = client.app.state.email_config_service
    service.delete_policy = AsyncMock(return_value=True)

    response = client.delete(
        "/api/admin/email/policies/1", headers=user_headers,
    )
    assert response.status_code == 204
    scope_arg = service.delete_policy.await_args.args[1]
    assert scope_arg.is_admin is False


# =============================================================================
# P1: send-by-policy 越权 404
# =============================================================================


def test_send_by_policy_other_user_returns_404(client, user_headers):
    """普通用户按他人策略发邮件：service.get_policy 返回 None → 404。"""
    service = client.app.state.email_config_service
    service.get_active_server_config = AsyncMock(return_value=MagicMock(
        host="smtp.qq.com", port=465, use_ssl=True,
        username="a@qq.com", password="p", sender_name="", enabled=True,
        force_plain=False, verify_ssl=True,
    ))
    service.get_policy = AsyncMock(return_value=None)  # 越权

    response = client.post(
        "/api/admin/email/send-by-policy/1",
        headers=user_headers,
        json={"subject": "x", "body": "y"},
    )

    assert response.status_code == 404
    assert "不存在或无权访问" in response.json()["detail"]


def test_send_by_policy_owner_calls_get_policy(client, user_headers):
    """owner 调用 send-by-policy：service.get_policy 收到 user scope。"""
    service = client.app.state.email_config_service
    fake_config = MagicMock(
        host="smtp.qq.com", port=465, use_ssl=True,
        username="a@qq.com", password="p", sender_name="", enabled=True,
        force_plain=False, verify_ssl=True,
    )
    service.get_active_server_config = AsyncMock(return_value=fake_config)
    service.get_policy = AsyncMock(return_value={
        "id": 1, "name": "我的", "recipients": [
            {"user_id": 1, "username": "u1", "email": "u1@example.com"},
        ],
        "subject_template": "", "body_template": "",
    })
    # patch EmailService.send_email 避免真发邮件
    from unittest.mock import patch as _patch
    with _patch(
        "app.routers.email_admin_router.EmailService"
    ) as mock_email_svc:
        mock_email_svc.return_value.send_email = AsyncMock(return_value={
            "success": True, "message_id": "fake", "sent_to": ["u1@example.com"],
        })
        response = client.post(
            "/api/admin/email/send-by-policy/1",
            headers=user_headers,
            json={"subject": "x", "body": "y"},
        )

    assert response.status_code == 200
    scope_arg = service.get_policy.await_args.args[1]
    assert scope_arg.is_admin is False
    assert scope_arg.user_id == 2


# =============================================================================
# P1: update 422 校验仍生效（防御回归）
# =============================================================================


def test_update_policy_validation_error_returns_400(client, admin_headers):
    """service 抛 EmailConfigValidationError 时路由返回 400（未被 404 拦截）。"""
    from app.shared.utils.email.email_config_service import EmailConfigValidationError
    service = client.app.state.email_config_service
    service.update_policy = AsyncMock(
        side_effect=EmailConfigValidationError("策略名称不能为空"),
    )
    response = client.put(
        "/api/admin/email/policies/1", headers=admin_headers, json={"name": "x"},
    )
    assert response.status_code == 400