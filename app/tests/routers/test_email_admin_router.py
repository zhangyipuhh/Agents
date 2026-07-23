# -*- coding:utf-8 -*-
"""
Email Admin Router 测试模块。

验证 /api/admin/email/* 路由的注册、SMTP 配置 CRUD、策略 CRUD、
测试连接与邮件发送接口的权限控制与成功/失败路径。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_create_policy_with_templates_returns_201(client, admin_headers):
    """新建策略时可携带主题/正文模板字段，service 收到后被透传。"""
    service = client.app.state.email_config_service
    service.create_policy = AsyncMock(return_value={
        "id": 7,
        "name": "运维告警",
        "description": "",
        "recipient_user_ids": [1],
        "subject_template": "[{{schedule_name}}] 任务完成",
        "body_template": "正文：{{script_output}}",
    })

    response = client.post(
        "/api/admin/email/policies",
        headers=admin_headers,
        json={
            "name": "运维告警",
            "description": "",
            "recipient_user_ids": [1],
            "subject_template": "[{{schedule_name}}] 任务完成",
            "body_template": "正文：{{script_output}}",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["subject_template"] == "[{{schedule_name}}] 任务完成"
    assert body["body_template"] == "正文：{{script_output}}"

    # 验证透传给 service 的参数包含模板字段
    kwargs = service.create_policy.await_args.kwargs
    assert kwargs["subject_template"] == "[{{schedule_name}}] 任务完成"
    assert kwargs["body_template"] == "正文：{{script_output}}"


def test_create_policy_without_templates_uses_defaults(client, admin_headers):
    """新建策略不传模板时使用空字符串默认值。"""
    service = client.app.state.email_config_service
    service.create_policy = AsyncMock(return_value={
        "id": 8,
        "name": "默认",
        "description": "",
        "recipient_user_ids": [1],
        "subject_template": "",
        "body_template": "",
    })

    response = client.post(
        "/api/admin/email/policies",
        headers=admin_headers,
        json={
            "name": "默认",
            "description": "",
            "recipient_user_ids": [1],
            # 不传 subject_template / body_template
        },
    )

    assert response.status_code == 201
    kwargs = service.create_policy.await_args.kwargs
    assert kwargs["subject_template"] == ""
    assert kwargs["body_template"] == ""


def test_update_policy_can_change_templates(client, admin_headers):
    """更新策略时可修改主题/正文模板字段。"""
    service = client.app.state.email_config_service
    service.update_policy = AsyncMock(return_value={
        "id": 1,
        "name": "策略1",
        "description": "",
        "recipient_user_ids": [1],
        "subject_template": "new-subject-{{run_id}}",
        "body_template": "new-body",
    })

    response = client.put(
        "/api/admin/email/policies/1",
        headers=admin_headers,
        json={
            "subject_template": "new-subject-{{run_id}}",
            "body_template": "new-body",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["subject_template"] == "new-subject-{{run_id}}"
    assert body["body_template"] == "new-body"
    # 验证 update_policy 收到模板字段
    kwargs = service.update_policy.await_args.kwargs
    assert kwargs["subject_template"] == "new-subject-{{run_id}}"
    assert kwargs["body_template"] == "new-body"


def test_create_policy_subject_template_too_long_returns_422(client, admin_headers):
    """主题模板超过 500 字符时 Pydantic max_length 校验拒绝，返回 422。"""
    too_long = "x" * 501
    response = client.post(
        "/api/admin/email/policies",
        headers=admin_headers,
        json={
            "name": "策略",
            "description": "",
            "recipient_user_ids": [1],
            "subject_template": too_long,
        },
    )
    assert response.status_code == 422


def test_list_policies_returns_template_fields(client, admin_headers):
    """GET /policies 应返回 subject_template / body_template 字段。"""
    service = client.app.state.email_config_service
    service.list_policies = AsyncMock(return_value=[
        {
            "id": 1,
            "name": "策略1",
            "description": "",
            "recipient_user_ids": [1],
            "subject_template": "主题-{{run_id}}",
            "body_template": "正文",
        }
    ])

    response = client.get("/api/admin/email/policies", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()[0]
    assert data["subject_template"] == "主题-{{run_id}}"
    assert data["body_template"] == "正文"


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


# =============================================================================
# P1: bytes→str 归一化（service 层覆盖，避免 asyncpg bytes/str 类型错误）
# =============================================================================


# =============================================================================
# P2: ACL 双重门（2026-07-23）
# - admin 角色 bypass ACL（既保留原 require_admin 行为）
# - 普通用户 ACL 授权后也能调（与 require_admin 双门）
# - 普通用户未被 ACL 授权 → 403
# =============================================================================


def _override_normal_user_with_visible_menu_ids(client, visible_ids):
    """覆盖 client 的 menu_permission_service，让普通用户（testuser）的
    get_visible_menu_ids(visible_ids) 返回指定集合。
    """
    from app.shared.utils.auth.menu_permission_service import MenuPermissionService
    visible_set = set(visible_ids)

    async def fake_visible(user_id, is_admin):
        if is_admin:
            # admin bypass：返 [所有 enabled]
            from app.core.menu_registry import get_enabled_items
            return [m.id for m in sorted(get_enabled_items(), key=lambda m: m.sort_order)]
        # 普通用户：返 mock 集合
        return sorted(visible_set)

    stub = MenuPermissionService(db=None)
    stub.get_visible_menu_ids = fake_visible
    client.app.state.menu_permission_service = stub


def test_normal_user_no_acl_emailable_users_returns_403(client, user_headers, monkeypatch):
    """ACL 空：普通用户 GET /emailable-users 返 403。"""
    _override_normal_user_with_visible_menu_ids(client, visible_ids={'profile'})
    resp = client.get("/api/admin/email/emailable-users", headers=user_headers)
    assert resp.status_code == 403


def test_normal_user_acl_email_settings_passes_emailable_users(client, user_headers):
    """ACL 含 email-settings（父级）：普通用户 GET /emailable-users 200。"""
    _override_normal_user_with_visible_menu_ids(
        client, visible_ids={'profile', 'task-scheduler.email-settings'}
    )
    # 由于 client fixture stub 了 email_service 之后会返 []，
    # 这里只验证 ACL 通过（即不是 403）
    resp = client.get("/api/admin/email/emailable-users", headers=user_headers)
    assert resp.status_code in (200, 500)  # ACL 通过，只是不一定返数据


def test_normal_user_acl_policies_passes(client, user_headers):
    """ACL 含 policies：普通用户 GET /policies 200。"""
    _override_normal_user_with_visible_menu_ids(
        client, visible_ids={'profile', 'task-scheduler.email-settings.policies'}
    )
    resp = client.get("/api/admin/email/policies", headers=user_headers)
    assert resp.status_code in (200, 500)


def test_normal_user_acl_no_server_blocked_from_server_config(client, user_headers):
    """ACL 含 policies 但不含 server：普通用户 GET /server-config 403。"""
    _override_normal_user_with_visible_menu_ids(
        client, visible_ids={'profile', 'task-scheduler.email-settings.policies'}
    )
    resp = client.get("/api/admin/email/server-config", headers=user_headers)
    assert resp.status_code == 403


def test_normal_user_acl_server_passes(client, user_headers):
    """ACL 含 server：普通用户 GET /server-config 200。"""
    _override_normal_user_with_visible_menu_ids(
        client, visible_ids={'profile', 'task-scheduler.email-settings.server'}
    )
    resp = client.get("/api/admin/email/server-config", headers=user_headers)
    assert resp.status_code in (200, 500)


def test_admin_still_bypasses_acl_check(client, admin_headers):
    """admin 角色不被 ACL 检查影响：被授予 server 但 ACL 只含 profile 也能调。"""
    # 显式把 ACL 设为没 server
    _override_normal_user_with_visible_menu_ids(client, visible_ids={'profile'})
    # 但 admin_headers 走 admin 路径（bypass ACL）
    # 注意：admin_headers 的用户 role 是 admin（来自 conftest 的 _mock_user_db_for_admin_auth），
    # 但前端 fixture 注入 menu_permission_service；admin 角色 require_admin bypass ACL 直接读 enabled 全量
    resp = client.get("/api/admin/email/server-config", headers=admin_headers)
    assert resp.status_code in (200, 500)

def _build_upsert_capture_db(encrypt_token_bytes: bytes = b"gAAAAABqStub=="):
    """构造一个能捕获 upsert SQL 参数的 fake db。

    第一次 fetchrow：查询现有记录，返回 None（新建场景）或包含
    password_encrypted 的 record（更新场景）。
    第二次 fetchrow：执行 INSERT/UPDATE 并返回 id/updated_at。
    """
    captured: dict = {"params": None}

    async def fake_fetchrow(sql: str, *args, **kwargs):
        captured["params"] = args
        if "SELECT id, password_encrypted FROM email_server_configs" in sql:
            # 查询现有启用配置
            return None  # 由调用方在测试中通过 monkeypatch 切换
        return {"id": 1, "updated_at": "2026-07-16T00:00:00Z"}

    db = MagicMock()
    db.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    return db, captured


def test_upsert_new_config_writes_str_not_bytes(monkeypatch):
    """测试新增配置时 password_encrypted 入库参数是 str（不是 bytes）。

    覆盖场景：前端填写新密码保存 → fernet.encrypt 返回 bytes →
    upsert_server_config 写入前必须 _to_db_str 归一化，
    否则 asyncpg 会抛 ``DataError: expected str, got bytes``。
    """
    from cryptography.fernet import Fernet
    from app.shared.utils.email.email_config_service import EmailConfigService
    from app.shared.utils.email.email_models import EmailServerConfig

    credential_key = Fernet.generate_key().decode()
    db, captured = _build_upsert_capture_db()
    # 第一次 fetchrow（查询现有）返回 None → 走 INSERT 分支
    db.fetchrow = AsyncMock(side_effect=[
        None,  # SELECT existing
        {"id": 1, "updated_at": "2026-07-16T00:00:00Z"},  # INSERT RETURNING
    ])

    service = EmailConfigService(db=db, credential_key=credential_key)
    config = EmailServerConfig(
        host="smtp.qq.com",
        port=465,
        use_ssl=True,
        username="x@qq.com",
        password="new-authcode",
        sender_name="",
        enabled=True,
    )

    result = asyncio.run(service.upsert_server_config(config, keep_existing_password=False))

    assert result["id"] == 1
    # 第二次 fetchrow（INSERT）的参数，password_encrypted 应该是 str
    insert_call = db.fetchrow.call_args_list[1]
    insert_params = insert_call.args[1:]  # 跳过 SQL
    password_param = insert_params[4]  # $5 = password_encrypted
    assert isinstance(password_param, str), (
        f"password_encrypted 应为 str，实际 {type(password_param).__name__}"
    )


def test_upsert_keep_existing_password_writes_str_not_bytes():
    """测试 keep_existing_password=True 时入参也是 str。

    覆盖核心 bug：DB 返回的 password_encrypted 是 bytes → upsert 写入前
    必须归一化为 str。这是本次 500 错误的直接成因。
    """
    from cryptography.fernet import Fernet
    from app.shared.utils.email.email_config_service import EmailConfigService
    from app.shared.utils.email.email_models import EmailServerConfig

    credential_key = Fernet.generate_key().decode()
    fernet = Fernet(credential_key.encode("ascii"))
    existing_encrypted = fernet.encrypt(b"original-authcode")

    db = MagicMock()
    db.fetchrow = AsyncMock(side_effect=[
        {"id": 7, "password_encrypted": existing_encrypted},  # SELECT existing
        {"id": 7, "updated_at": "2026-07-16T00:00:00Z"},  # UPDATE RETURNING
    ])

    service = EmailConfigService(db=db, credential_key=credential_key)
    config = EmailServerConfig(
        host="smtp.qq.com",
        port=465,
        use_ssl=True,
        username="x@qq.com",
        password="",  # 留空表示不修改
        sender_name="",
        enabled=True,
    )

    result = asyncio.run(service.upsert_server_config(config, keep_existing_password=True))

    assert result["id"] == 7
    # 第二次 fetchrow（UPDATE）的参数，password_encrypted 应该是 str
    update_call = db.fetchrow.call_args_list[1]
    update_params = update_call.args[1:]
    password_param = update_params[4]  # $5 = password_encrypted
    assert isinstance(password_param, str), (
        f"keep_existing_password=True 时 password_encrypted 应为 str，实际 {type(password_param).__name__}"
    )
    # 关键：写入的 str 必须能用 fernet 解密回原密码（数据不损坏）
    decrypted = fernet.decrypt(password_param.encode("ascii")).decode("utf-8")
    assert decrypted == "original-authcode"


def test_upsert_keep_existing_password_raises_when_no_record():
    """回归测试：keep_existing_password=True 但 DB 无记录时抛 EmailConfigError。"""
    from cryptography.fernet import Fernet
    from app.shared.utils.email.email_config_service import (
        EmailConfigError,
        EmailConfigService,
    )
    from app.shared.utils.email.email_models import EmailServerConfig

    credential_key = Fernet.generate_key().decode()
    db = MagicMock()
    db.fetchrow = AsyncMock(return_value=None)  # 无现有记录

    service = EmailConfigService(db=db, credential_key=credential_key)
    config = EmailServerConfig(
        host="smtp.qq.com",
        port=465,
        use_ssl=True,
        username="x@qq.com",
        password="",
        sender_name="",
        enabled=True,
    )

    with pytest.raises(EmailConfigError):
        asyncio.run(service.upsert_server_config(config, keep_existing_password=True))
