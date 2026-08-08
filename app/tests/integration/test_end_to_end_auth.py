# -*- coding:utf-8 -*-
"""
端到端认证流程集成测试模块

测试完整的用户认证生命周期：
获取验证码 → 注册 → 登录 → 访问受保护路由 → 登出 → 受保护路由拒绝未认证请求

Date: 2026-06-08
"""

from unittest.mock import patch


# =============================================================================
# 端到端认证流程测试
# =============================================================================


def test_end_to_end_auth_flow(client):
    """
    端到端认证流程完整测试

    验证从注册到登出的完整用户认证生命周期，确保各阶段接口行为符合预期。

    Args:
        client: FastAPI TestClient fixture，提供 HTTP 请求能力

    Returns:
        None

    Raises:
        AssertionError: 任一阶段响应状态码或数据不符合预期时抛出
    """
    # ------------------------------------------------------------------
    # 步骤1：获取图形验证码
    # ------------------------------------------------------------------
    captcha_resp = client.get("/api/auth/captcha")
    assert captcha_resp.status_code == 200, "获取验证码应返回 200"
    captcha_data = captcha_resp.json()
    assert "captcha_key" in captcha_data, "验证码响应应包含 captcha_key"
    captcha_key = captcha_data["captcha_key"]

    # ------------------------------------------------------------------
    # 步骤2：注册新用户（mock 验证码校验确保通过）
    # ------------------------------------------------------------------
    with patch(
        "app.shared.utils.auth.captcha.CaptchaManager.verify",
        return_value=True,
    ):
        register_payload = {
            "username": "test_e2e_user",
            "password": "Test123!",
            "confirm_password": "Test123!",
            "real_name": "测试",
            "phone": "13800138000",
            "email": "test@example.com",
            "department": "测试部",
            "position": "测试员",
            "captcha_key": captcha_key,
            "captcha_code": "1234",
        }
        register_resp = client.post("/api/auth/register", json=register_payload)
        assert register_resp.status_code == 200, "注册应返回 200"
        assert register_resp.json().get("message") == "注册成功", "注册响应应提示成功"

    # ------------------------------------------------------------------
    # 步骤3：API 程序化登录获取 access_token
    # memory 模式下 jwt_auth.verify_credentials 仅认硬编码凭据，
    # 因此 patch 使其通过新注册用户的验证
    # ------------------------------------------------------------------
    from app.shared.utils.auth.Safety import jwt_auth
    with patch.object(jwt_auth, "verify_credentials", return_value=True):
        login_resp = client.post(
            "/api/auth/login-api",
            json={
                "username": "test_e2e_user",
                "password": "Test123!",
            },
        )
    assert login_resp.status_code == 200, "登录应返回 200"
    login_data = login_resp.json()
    assert "access_token" in login_data, "登录响应应包含 access_token"
    access_token = login_data["access_token"]

    # ------------------------------------------------------------------
    # 步骤4：携带 token 访问受保护路由（创建会话）
    # ------------------------------------------------------------------
    session_resp = client.post(
        "/api/session/create",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert session_resp.status_code == 200, "携带有效 token 创建会话应返回 200"
    session_data = session_resp.json()
    assert "session_id" in session_data, "创建会话响应应包含 session_id"

    # ------------------------------------------------------------------
    # 步骤5：登出
    # ------------------------------------------------------------------
    logout_resp = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_resp.status_code == 200, "登出应返回 200"
    assert logout_resp.json().get("message") == "登出成功", "登出响应应提示成功"

    # ------------------------------------------------------------------
    # 步骤6：再次访问受保护路由，不携带 token，应返回 401
    # ------------------------------------------------------------------
    unauthorized_resp = client.post("/api/session/create")
    assert unauthorized_resp.status_code == 401, "未携带 token 访问受保护路由应返回 401"


# =============================================================================
# Cookie 鉴权模式端到端集成测试（HttpOnly Cookie 迁移防线）
# =============================================================================


def test_cookie_auth_end_to_end(client):
    """
    Cookie 模式端到端：登录 Set-Cookie → Cookie 访问受保护路由 → 缺 CSRF 头 403 → 登出清 Cookie

    Args:
        client: FastAPI TestClient fixture（完整应用，Cookie Jar 自动携带）

    Returns:
        None

    Raises:
        AssertionError: 任一阶段响应状态码或 Set-Cookie 属性不符合预期时抛出
    """
    from unittest.mock import patch

    from app.shared.utils.auth.Safety import jwt_auth

    # ------------------------------------------------------------------
    # 步骤1：登录，验证 Set-Cookie 下发 access_token HttpOnly Cookie
    # ------------------------------------------------------------------
    with patch.object(jwt_auth, "verify_credentials", return_value=True):
        login_resp = client.post(
            "/api/auth/login-api",
            json={"username": "test_e2e_user", "password": "Test123!"},
        )
    assert login_resp.status_code == 200, "登录应返回 200"

    set_cookies = login_resp.headers.get_list("set-cookie")
    assert any(
        c.startswith("access_token=") and "HttpOnly" in c for c in set_cookies
    ), "登录应下发 access_token HttpOnly Cookie"

    # ------------------------------------------------------------------
    # 步骤2：Cookie + CSRF 头访问受保护路由（Cookie Jar 自动携带 access_token）
    # ------------------------------------------------------------------
    session_resp = client.post(
        "/api/session/create",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert session_resp.status_code == 200, "Cookie 鉴权 + CSRF 头应放行"

    # ------------------------------------------------------------------
    # 步骤3：缺 CSRF 头的 Cookie 写请求应被拒（403）
    # ------------------------------------------------------------------
    forbidden = client.post("/api/session/create")
    assert forbidden.status_code == 403, "缺 CSRF 头应返回 403"

    # ------------------------------------------------------------------
    # 步骤4：登出，验证 access_token Cookie 被清除（Max-Age=0）
    # ------------------------------------------------------------------
    logout_resp = client.post(
        "/api/auth/logout",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert logout_resp.status_code == 200, "登出应返回 200"

    del_cookies = logout_resp.headers.get_list("set-cookie")
    assert any(
        c.startswith("access_token=") and "Max-Age=0" in c for c in del_cookies
    ), "登出应删除 access_token Cookie"
