# -*- coding:utf-8 -*-
"""
Safety 模块单元测试

测试 JWTAuth 的令牌生成、验证、白名单以及 auth_middleware 对 refresh token 的拦截。
"""
import asyncio
import json
import sys
from unittest.mock import MagicMock

# 环境可能未安装 asyncpg，预先 mock 以避免导入链失败
if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = MagicMock()

import jwt
import pytest
from fastapi import Request

from app.shared.utils.auth.Safety import (
    JWTAuth,
    SESSION_WHITELIST_PREFIXES,
    jwt_auth,
    auth_middleware,
    require_admin,
    require_menu_acl,
    require_admin_or_menu_acl,
)


def _run_async(coro):
    """辅助函数：在新的事件循环中运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_jwt_auth_generate_token(jwt_auth):
    """
    测试 JWTAuth.generate_token 返回非空字符串

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(jwt_auth.generate_token("testuser"))
    assert isinstance(token, str)
    assert len(token) > 0


def test_jwt_auth_decode_token(jwt_auth):
    """
    测试使用真实 jwt.decode 正确解析 generate_token 生成的 payload

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(jwt_auth.generate_token("testuser"))
    payload = jwt.decode(token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm])
    assert payload["username"] == "testuser"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_whitelist_add_and_check(jwt_auth):
    """
    测试白名单的添加和检查功能

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    path = "/api/test/whitelist"
    assert not jwt_auth.is_whitelisted(path)
    jwt_auth.add_to_whitelist(path)
    assert jwt_auth.is_whitelisted(path)


def test_verify_credentials_memory_mode():
    """
    测试 memory 模式下 verify_credentials 验证注入凭据（admin/P@ssword1!）。

    2026-08-09 改造（等保三级 Task 2）：原测试使用硬编码 ``admin/123456``，
    现已迁移为构造 ``JWTAuth(bootstrap_username, bootstrap_password)`` 并断言
    注入值生效；旧硬编码值的 fail-loud 行为由
    ``test_jwt_auth_verify_credentials_rejects_default_hardcoded`` 覆盖。

    Returns:
        None
    """
    from app.shared.utils.auth.Safety import JWTAuth

    auth = JWTAuth(bootstrap_username="admin", bootstrap_password="P@ssword1!")
    result = _run_async(auth.verify_credentials("admin", "P@ssword1!"))
    assert result is True

    result_wrong = _run_async(auth.verify_credentials("admin", "wrong_password"))
    assert result_wrong is False


def test_refresh_token_rejected_by_auth_middleware(jwt_auth):
    """
    测试 type=refresh 的 token 被 auth_middleware 拒绝

    构造一个携带 refresh token 的 mock Request，验证中间件返回 401。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    refresh_token = _run_async(jwt_auth.generate_refresh_token("admin"))

    request = MagicMock(spec=Request)
    request.url.path = "/api/protected"
    request.headers.get.return_value = f"Bearer {refresh_token}"

    async def mock_call_next(request):
        from fastapi.responses import JSONResponse
        return JSONResponse(content={"ok": True})

    response = _run_async(auth_middleware(request, mock_call_next))

    assert response.status_code == 401
    body = json.loads(response.body)
    assert "无效的令牌类型" in body["detail"]


def test_authenticate_sets_allowed_agents(jwt_auth, monkeypatch):
    """
    测试 JWTAuth.authenticate 将 allowed_agents 写入 request.state。

    2026-07-24 改造：allowed_agents 数据源从 users.allowed_agents (JSONB 旧字段)
    切换到 user_agent_acl (新表，由 agent_permission_service 缓存读)。
    - 普通用户：request.state.allowed_agents 应等于 agent_permission_service 缓存里的授权
    - admin：返 []（让上游 agent_router 走 admin bypass）

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    access_token = _run_async(jwt_auth.generate_token("testuser"))

    async def fake_get_user(username):
        return {
            "id": 2,
            "username": "testuser",
            "role": "user",
            # 即便 user.allowed_agents 还有历史值，也不应再被读到
            "allowed_agents": ["map_agent"],
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    # 模拟 agent_permission_service 缓存：授权 map_agent / project
    class _StubAgentSvc:
        def get_user_agent_grants_sync(self, user_id):
            return {"map_agent", "project"}

    stub_app_state = type("S", (), {"agent_permission_service": _StubAgentSvc()})()
    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {access_token}"
    request.app.state = stub_app_state

    payload = _run_async(jwt_auth.authenticate(request))
    assert payload is not None
    # 普通用户从 agent_permission_service 读 ACL，按字母序排序
    assert request.state.allowed_agents == ["map_agent", "project"]


def test_authenticate_admin_role_empty_allowed_agents(jwt_auth, monkeypatch):
    """admin 角色 request.state.allowed_agents 应为 []，由上游 bypass。

    2026-07-24 新增：避免 admin 用户因 user_agent_acl 无记录而被踢出。
    """
    access_token = _run_async(jwt_auth.generate_token("admin"))

    async def fake_get_user(username):
        return {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "allowed_agents": ["map_agent", "project"],
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {access_token}"

    payload = _run_async(jwt_auth.authenticate(request))
    assert payload is not None
    assert request.state.role == "admin"
    assert request.state.allowed_agents == []


def test_authenticate_service_unavailable_fail_secure(jwt_auth, monkeypatch):
    """agent_permission_service 不可用时返 []（fail-secure，不再 fallback 到旧字段）。

    2026-07-24 新增：避免历史 users.allowed_agents 残留导致越权。
    """
    access_token = _run_async(jwt_auth.generate_token("testuser"))

    async def fake_get_user(username):
        return {
            "id": 2,
            "username": "testuser",
            "role": "user",
            "allowed_agents": ["map_agent"],  # 旧字段有值，但不应再生效
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    # service 不可用
    stub_app_state = type("S", (), {"agent_permission_service": None})()
    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {access_token}"
    request.app.state = stub_app_state

    payload = _run_async(jwt_auth.authenticate(request))
    assert payload is not None
    assert request.state.allowed_agents == []


def test_upload_config_is_in_session_whitelist():
    """2026-07-17 新增：/api/core/upload-config 必须在 Session 白名单中。

    复现：onMounted 阶段 localStorage.session_id 为空时拉取配置，
    强制 X-Session-ID 校验会 400。前端用户每次刷新都看到噪音。
    """
    assert "/api/core/upload-config" in SESSION_WHITELIST_PREFIXES


def test_upload_file_is_not_in_session_whitelist():
    """2026-07-17 新增：/api/core/uploadfile 必须仍要求 X-Session-ID（不能误伤写接口）。"""
    # 用 startswith 检查白名单没有覆盖整个 /api/core 前缀
    for prefix in SESSION_WHITELIST_PREFIXES:
        assert not prefix.startswith("/api/core") or prefix == "/api/core/upload-config"
    # 更直接的断言：白名单不能前缀匹配 /api/core/uploadfile
    matched = [p for p in SESSION_WHITELIST_PREFIXES if "/api/core/uploadfile".startswith(p)]
    assert matched == ["/api/core/upload-config"] or matched == [], (
        "意外白名单: %s 覆盖 /api/core/uploadfile 的前缀" % matched
    )
    # 关键：/api/core/uploadfile 不应仅因 /api/core/upload-config 在白名单就被放行
    # 用 startswith 反向验证
    assert not any(
        p == "/api/core" for p in SESSION_WHITELIST_PREFIXES
    ), "/api/core 不能整段放行（会误伤 uploadfile / merge-chunks 等写接口）"


# ============================================================================
# 2026-07-23 新增：菜单 ACL 守卫（双重门改造）
# ============================================================================


class _StubState:
    """最小 state 模拟，role/user_id 字段可设。"""

    def __init__(self, role='user', user_id=None):
        self.role = role
        self.user_id = user_id


class _StubRequest:
    """最小 FastAPI Request 模拟，state + app.state 字段可设。"""

    def __init__(self, role='user', user_id=None, menu_service=None):
        self.state = _StubState(role=role, user_id=user_id)

        class _App:
            def __init__(self, svc):
                self.state = type('S', (), {'menu_permission_service': svc})()

        self.app = _App(menu_service)


class _StubMenuService:
    """最小 MenuPermissionService stub，仅实现 get_visible_menu_ids。"""

    def __init__(self, visible_ids=None, fail=False):
        self._visible = set(visible_ids or [])
        self._fail = fail

    async def get_visible_menu_ids(self, user_id, is_admin):
        if self._fail:
            raise RuntimeError('db error')
        return sorted(self._visible)


def _run(coro):
    """asyncio.run 包装（与现有 _run_async 等价命名）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_require_admin_admin_role_passes():
    """admin role 通过 require_admin。"""
    req = _StubRequest(role='admin')
    assert _run(require_admin(req)) is True


def test_require_admin_normal_user_403():
    """普通用户被 require_admin 拦截（403）。"""
    from fastapi import HTTPException
    req = _StubRequest(role='user', user_id=5)
    with pytest.raises(HTTPException) as exc:
        _run(require_admin(req))
    assert exc.value.status_code == 403


def test_require_menu_acl_admin_bypass():
    """admin 角色绕过 ACL 直接通过（不读 menu_permission_service）。"""
    req = _StubRequest(role='admin', user_id=1, menu_service=None)
    # 即使 menu_service 为 None，admin 不查 ACL
    assert _run(require_menu_acl(req, 'any-menu-id')) is None


def test_require_menu_acl_normal_user_granted():
    """普通用户被 ACL 授权时通过。"""
    svc = _StubMenuService(visible_ids={'task-scheduler', 'task-scheduler.email-settings'})
    req = _StubRequest(role='user', user_id=5, menu_service=svc)
    assert _run(require_menu_acl(req, 'task-scheduler')) is None


def test_require_menu_acl_normal_user_not_granted_403():
    """普通用户没被 ACL 授权时返 403。"""
    from fastapi import HTTPException
    svc = _StubMenuService(visible_ids={'profile'})
    req = _StubRequest(role='user', user_id=5, menu_service=svc)
    with pytest.raises(HTTPException) as exc:
        _run(require_menu_acl(req, 'task-scheduler'))
    assert exc.value.status_code == 403
    assert 'task-scheduler' in exc.value.detail


def test_require_menu_acl_user_id_missing_401():
    """user_id 缺失（auth_middleware 未注入）时返 401。"""
    from fastapi import HTTPException
    svc = _StubMenuService(visible_ids={'task-scheduler'})
    req = _StubRequest(role='user', user_id=None, menu_service=svc)
    with pytest.raises(HTTPException) as exc:
        _run(require_menu_acl(req, 'task-scheduler'))
    assert exc.value.status_code == 401


def test_require_menu_acl_service_unavailable_503():
    """menu_permission_service 未初始化（lifespan 失败）时返 503。"""
    from fastapi import HTTPException
    req = _StubRequest(role='user', user_id=5, menu_service=None)
    with pytest.raises(HTTPException) as exc:
        _run(require_menu_acl(req, 'task-scheduler'))
    assert exc.value.status_code == 503


def test_require_admin_or_menu_acl_factory_returns_dep():
    """require_admin_or_menu_acl 工厂返回可调用的 dependency。"""
    dep = require_admin_or_menu_acl('task-scheduler.email-settings.server')
    assert callable(dep)


def test_require_admin_or_menu_acl_admin_passes():
    """admin 通过组合守卫（不查 ACL）。"""
    req = _StubRequest(role='admin', user_id=1, menu_service=None)
    dep = require_admin_or_menu_acl('task-scheduler.email-settings.server')
    assert _run(dep(req)) is None


def test_require_admin_or_menu_acl_normal_user_passes():
    """普通用户被 ACL 授权时通过组合守卫。"""
    svc = _StubMenuService(
        visible_ids={'task-scheduler.email-settings', 'task-scheduler.email-settings.server'}
    )
    req = _StubRequest(role='user', user_id=5, menu_service=svc)
    dep = require_admin_or_menu_acl('task-scheduler.email-settings.server')
    assert _run(dep(req)) is None


def test_require_admin_or_menu_acl_normal_user_denied():
    """普通用户未被 ACL 授权时返 403。"""
    from fastapi import HTTPException
    svc = _StubMenuService(visible_ids={'profile'})
    req = _StubRequest(role='user', user_id=5, menu_service=svc)
    dep = require_admin_or_menu_acl('task-scheduler.email-settings.server')
    with pytest.raises(HTTPException) as exc:
        _run(dep(req))
    assert exc.value.status_code == 403


# ============================================================================
# 2026-08-08 新增：HttpOnly Cookie 兜底 + CSRF 头校验（Task 2 of 13）
# 设计：Bearer 优先 → Cookie 兜底 → 中间件对 Cookie 写请求校验 X-Requested-With
# ============================================================================


def test_authenticate_cookie_fallback(jwt_auth, monkeypatch):
    """无 Authorization 头时回退读取 HttpOnly Cookie access_token。

    浏览器主应用场景：Access Token 存 HttpOnly Cookie（JS 不可见），
    只能通过 Cookie 自动随请求发送；authenticate 应能从 ``request.cookies``
    读取 token 并标记 ``auth_via == 'cookie'``。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    access_token = _run_async(jwt_auth.generate_token("admin"))

    async def fake_get_user(username):
        return {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "allowed_agents": [],
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    request = MagicMock(spec=Request)
    request.headers.get.return_value = None
    request.cookies = {"access_token": access_token}

    payload = _run_async(jwt_auth.authenticate(request))
    assert payload is not None
    assert request.state.auth_via == "cookie"


def test_authenticate_bearer_precedence_over_cookie(jwt_auth, monkeypatch):
    """Bearer 与 Cookie 同时存在时优先 Bearer（第三方/程序化客户端兼容）。

    设计动机：第三方 API 客户端/CLI/Postman 通常用 Authorization Header，
    同时浏览器开发者工具可能手动注入 Cookie。两个都存在时以 Bearer 为准，
    避免 Cookie 携带过期/失效令牌意外劫持会话。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）
        monkeypatch: pytest monkeypatch fixture

    Returns:
        None
    """
    access_token = _run_async(jwt_auth.generate_token("admin"))

    async def fake_get_user(username):
        return {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "allowed_agents": [],
        }

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    # 故意把 Cookie 配成坏 token，但 Bearer 是好 token → 应走 Bearer 成功
    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {access_token}"
    request.cookies = {"access_token": "bad-token"}

    payload = _run_async(jwt_auth.authenticate(request))
    assert payload is not None
    assert request.state.auth_via == "bearer"


def test_authenticate_no_header_no_cookie_raises_401(jwt_auth):
    """既无 Bearer 又无 Cookie 时抛 401。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    from fastapi import HTTPException

    request = MagicMock(spec=Request)
    request.headers.get.return_value = None
    request.cookies = {}

    with pytest.raises(HTTPException) as exc_info:
        _run_async(jwt_auth.authenticate(request))
    assert exc_info.value.status_code == 401


# ============================================================================
# 2026-08-08 新增：extract_access_token 共享 helper（Task 4 review 修复）
# 设计：Bearer 优先 → Cookie 兜底 → Basic 等非 Bearer 一律 401（不静默回退）
# ============================================================================


def test_extract_access_token_returns_bearer(jwt_auth):
    """Authorization: Bearer <token> 直接返回 token 字符串。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    access_token = _run_async(jwt_auth.generate_token("admin"))

    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {access_token}"
    request.cookies = {}

    assert jwt_auth.extract_access_token(request) == access_token


def test_extract_access_token_falls_back_to_cookie(jwt_auth):
    """无 Authorization 头时回退读取 HttpOnly Cookie access_token。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    access_token = _run_async(jwt_auth.generate_token("admin"))

    request = MagicMock(spec=Request)
    request.headers.get.return_value = None
    request.cookies = {"access_token": access_token}

    assert jwt_auth.extract_access_token(request) == access_token


def test_extract_access_token_no_header_no_cookie_raises_401(jwt_auth):
    """既无 Authorization 又无 Cookie 时抛 401。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    from fastapi import HTTPException

    request = MagicMock(spec=Request)
    request.headers.get.return_value = None
    request.cookies = {}

    with pytest.raises(HTTPException) as exc_info:
        jwt_auth.extract_access_token(request)
    assert exc_info.value.status_code == 401


def test_extract_access_token_rejects_basic_header_with_cookie(jwt_auth):
    """Authorization: Basic 即使携带有效 Cookie 也必须 401，不静默回退。

    设计动机：原 ``validate_token`` 实现的回退逻辑遇到 ``Basic xyz`` 头时
    会静默跳过 Basic 走到 Cookie 鉴权（200 通过），与 ``authenticate()`` 的
    401 行为不一致。helper 必须统一拒绝。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    from fastapi import HTTPException

    access_token = _run_async(jwt_auth.generate_token("admin"))

    request = MagicMock(spec=Request)
    request.headers.get.return_value = "Basic xyz"
    request.cookies = {"access_token": access_token}

    with pytest.raises(HTTPException) as exc_info:
        jwt_auth.extract_access_token(request)
    assert exc_info.value.status_code == 401
    assert "无效的认证格式" in str(exc_info.value.detail)


def test_extract_access_token_rejects_unknown_auth_scheme(jwt_auth):
    """Authorization: Digest / Token / 自定义 scheme 一律 401。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    from fastapi import HTTPException

    access_token = _run_async(jwt_auth.generate_token("admin"))

    for scheme in ("Digest foo", "Token abc", "Custom xyz"):
        request = MagicMock(spec=Request)
        request.headers.get.return_value = scheme
        request.cookies = {"access_token": access_token}

        with pytest.raises(HTTPException) as exc_info:
            jwt_auth.extract_access_token(request)
        assert exc_info.value.status_code == 401


def test_extract_access_token_bearer_precedence_over_cookie(jwt_auth):
    """Bearer 与 Cookie 同时存在时优先 Bearer。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    bearer_token = _run_async(jwt_auth.generate_token("admin"))

    request = MagicMock(spec=Request)
    request.headers.get.return_value = f"Bearer {bearer_token}"
    request.cookies = {"access_token": "another-token"}

    assert jwt_auth.extract_access_token(request) == bearer_token


# ============================================================================
# 2026-08-09 新增：JWTAuth bootstrap 凭据注入（等保三级 Task 2）
# 设计：取消硬编码 admin/123456，凭据必须从 lifespan 注入；memory 模式下
# 注入缺失时直接 fail-loud（RuntimeError），禁止回退到任何默认值。
# ============================================================================


def test_jwt_auth_verify_credentials_uses_bootstrap_password(monkeypatch):
    """注入 bootstrap_username/bootstrap_password 后，verify_credentials 走注入值。

    等保三级 Task 2 要求取消硬编码 admin/123456，凭据由 lifespan 注入。
    """
    from app.shared.utils.auth.Safety import JWTAuth

    auth = JWTAuth(bootstrap_username="ops", bootstrap_password="P@ssword1!")
    assert _run_async(auth.verify_credentials("ops", "P@ssword1!")) is True
    assert _run_async(auth.verify_credentials("admin", "123456")) is False


def test_jwt_auth_verify_credentials_rejects_default_hardcoded(monkeypatch):
    """无注入时不允许走硬编码 admin/123456（fail-loud）。

    设计动机：旧实现 ``verify_credentials`` 在 memory 模式直接比较
    ``username == "admin" and password == "123456"``，这是历史上 admin 默认
    弱口令。等保三级要求移除硬编码凭据；未注入时必须 RuntimeError，
    禁止回退到任何默认值。
    """
    from app.shared.utils.auth.Safety import JWTAuth

    auth = JWTAuth()
    with pytest.raises(RuntimeError):
        _run_async(auth.verify_credentials("admin", "123456"))


# ============================================================
# 2026-08-11 等保三级 §1.7：JWT payload 携带 user_id 测试
# ============================================================


def test_generate_token_payload_contains_user_id(jwt_auth):
    """Access Token payload 必须包含 ``user_id`` 字段（等保三级 §1.7 强化）。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(jwt_auth.generate_token("alice", user_id=42))
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert payload["username"] == "alice"
    assert payload["user_id"] == 42
    assert payload["type"] == "access"


def test_generate_refresh_token_payload_contains_user_id(jwt_auth):
    """Refresh Token payload 必须包含 ``user_id`` 字段。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(
        jwt_auth.generate_refresh_token("alice", user_id=42)
    )
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert payload["username"] == "alice"
    assert payload["user_id"] == 42
    assert payload["type"] == "refresh"


def test_generate_token_without_user_id_omits_field(jwt_auth):
    """兼容旧调用：``user_id=None`` 时 payload 不写 ``user_id`` 字段。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(jwt_auth.generate_token("alice"))
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert "user_id" not in payload


def test_generate_token_with_user_id_and_amr(jwt_auth):
    """``user_id`` 与 ``amr`` 同时存在时互不干扰。

    Args:
        jwt_auth: JWTAuth 实例（来自 conftest）

    Returns:
        None
    """
    token = _run_async(
        jwt_auth.generate_token(
            "alice", user_id=42, auth_methods=["pwd", "totp"]
        )
    )
    payload = jwt.decode(
        token, jwt_auth.secret_key, algorithms=[jwt_auth.algorithm]
    )
    assert payload["user_id"] == 42
    assert payload["amr"] == ["pwd", "totp"]
