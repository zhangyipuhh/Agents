# -*- coding:utf-8 -*-
"""
AuditLog → LogService 迁移契约测试模块。

验证：
1. auth_router / user_router / session_router 不再依赖 AuditLog（旧 API 无生产引用）
2. 上述路由改用 LogService.emit(LogEvent) 与统一枚举（auth / user / session）
3. 日志服务缺失 / emit 失败不得改变原业务响应（业务 HTTP 状态不变）
4. 客户端伪造身份（context_overrides.log_user_id / request.state.log_user_id）
   在 agent_router 被强制覆盖（信任服务端鉴权结果）
5. task_scheduler 构造 Agent 前 overrides 注入创建者身份，伪造请求身份不得胜出
6. audit_logs schema 注册函数迁到 log_service.py 且 @register_schema
7. app/shared/utils/auth/audit_log.py 旧模块已删除（业务侧无生产引用）

说明：审计语义与原有 AuditLog.write_log 完全等价：
- login_success / login_failure 均 action='login'，log_type=auth，result 区分 success/failure
  level 区分 info（成功） / warning（失败），source='auth_router'
- logout action='logout'
- admin_update_user / admin_kick_user 为 log_type='user', target_type='user', target_id / name
- admin_delete_session 为 log_type='session', session_id 与 target 写齐

测试规范：
- 文件首行：# -*- coding:utf-8 -*-
- 模块级 docstring（中文）
- pytest 通过 monkeypatch 替换副作用入口
"""
import asyncio
import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# =============================================================================
# 1. 旧 AuditLog 无生产引用：迁移后业务代码不应再 import / 引用
# =============================================================================


def test_no_production_code_imports_old_audit_log_module():
    """验证生产代码（app/shared/routers/、app/routers/agent_router.py）不再引用旧 AuditLog。

    审计语义统一经 LogService.emit 落地。旧 AuditLog.write_log 路径已停用。
    """
    import os

    # 仅检查生产路径（不含测试）。
    # pytest rootdir = app/，当前文件位于 app/tests/shared/routers/，
    # 向上 4 层到项目根，再 join "app/..." 即可命中源码文件。
    files_to_check = [
        "app/shared/routers/auth_router.py",
        "app/shared/routers/user_router.py",
        "app/shared/routers/session_router.py",
    ]
    _project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    for relative in files_to_check:
        path = os.path.join(_project_root, relative)
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        assert "from app.shared.utils.auth.audit_log import" not in source, (
            f"{relative} 必须改为从 LogService 走审计日志，"
            "禁止继续 import 旧的 app.shared.utils.auth.audit_log。"
        )
        assert "AuditLog.write_log" not in source, (
            f"{relative} 必须改用 LogService.emit 触发审计事件，"
            "禁止继续调用旧 AuditLog.write_log。"
        )


# =============================================================================
# 2. LogService.emit 与统一日志枚举契约
#    验证路由器 emission 形态（参数 + 字段映射）符合迁移契约
# =============================================================================


def _make_capturing_log_service():
    """构造一份捕获所有 emit 事件的 LogService 桩。

    返回 (service, emitted_events) 二元组；emitted_events 是 list[LogEvent]。
    适配 log_service.LogService.emit 的同步签名 + 内部 _enqueue_sync 入队契约。
    """
    from app.shared.utils.log_service import LogEvent, LogService

    emitted = []

    async def _consume_loop():
        # 简单 drain 协程：循环读取 queue 并写入 emitted
        while not service._stop_event.is_set():
            try:
                evt = await asyncio.wait_for(service._queue.get(), timeout=0.05)
                emitted.append(evt)
            except asyncio.TimeoutError:
                continue
        # 排空残留
        while True:
            try:
                emitted.append(service._queue.get_nowait())
            except Exception:
                break

    service = LogService(memory_only=True)
    service._consumer_started = True
    service._accepting = True
    service._loop = asyncio.new_event_loop()
    service._loop.run_until_complete(_consume_loop())
    return service, emitted


@pytest.fixture
def capturing_log_service(monkeypatch):
    """提供可断言 LogEvent 序列的 LogService。

    实现：用 MagicMock 实例替换 set_log_service 注册的 LogService，
    通过 service.emit_calls 字段记录所有 emit 入参。
    """
    fake_service = MagicMock()
    fake_service.emit_calls = []

    def fake_emit(event):
        fake_service.emit_calls.append(event)
        return True

    fake_service.emit = fake_emit

    from app.shared.utils import log_service as log_service_module
    monkeypatch.setattr(log_service_module, "_log_service_singleton", fake_service)
    monkeypatch.setattr(log_service_module, "get_log_service", lambda: fake_service)
    return fake_service


# =============================================================================
# 3. auth_router 迁移契约
# =============================================================================


def test_auth_router_login_success_emits_log_event(capturing_log_service, monkeypatch):
    """login 成功时路由调用 LogService.emit(LogEvent) 一次，action='login' / result='success' / level='info' / source='auth_router' / log_type='auth'。

    验证：
    - login_success / login_failure 合并为 action='login'
    - level 与 result 联动（成功 info，失败 warning）
    - 业务 HTTP 响应正常（不被日志失败影响）
    """
    from app.shared.routers.auth_router import login_api

    # 构造 mock request：客户端 IP 是 visible；app.state 需含 menu_permission_service
    # / agent_permission_service（生产 auth_middleware 之前 lifespan 注入）；
    # 测试 SimpleNamespace 不带 app，补一个空 app.state 让 _compute_visible_menus
    # / _compute_allowed_agents 走 service=None 短路。
    request = SimpleNamespace(
        client=SimpleNamespace(host="1.2.3.4"),
        state=SimpleNamespace(username=None, user_id=None),
        app=SimpleNamespace(state=SimpleNamespace()),
    )

    # monkeypatch 凭据校验、refresh_token_store、jwt 生成等
    from app.shared.utils.auth.Safety import jwt_auth

    async def fake_verify_credentials(username, password):
        return username == "alice" and password == "Test@123"

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.verify_credentials",
        fake_verify_credentials,
        raising=False,
    )
    monkeypatch.setattr(jwt_auth, "verify_credentials", fake_verify_credentials)

    async def fake_get_user(username):
        return {"id": 7, "username": username, "role": "user", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    from app.shared.utils.auth.refresh_token_db import RefreshTokenDB

    async def fake_store_token(token_hash, user_id, expires_at, username=""):
        return True

    monkeykey = monkeypatch  # alias
    monkeykey.setattr(
        "app.shared.utils.auth.refresh_token_db.RefreshTokenDB.store_token",
        fake_store_token,
    )

    response_callable = login_api
    payload = SimpleNamespace(username="alice", password="Test@123")

    from fastapi import Response

    response = Response()

    result = asyncio.run(response_callable(payload, request, response))

    assert result.username == "alice"
    assert result.user_id == 7
    assert len(capturing_log_service.emit_calls) == 1
    evt = capturing_log_service.emit_calls[0]
    assert evt.action == "login"
    assert str(evt.log_type) == "auth"
    assert str(evt.result) == "success"
    assert str(evt.level) == "info"
    assert evt.source == "auth_router"
    assert evt.user_id == 7
    assert evt.username == "alice"


def test_auth_router_login_failure_emits_log_event(capturing_log_service, monkeypatch):
    """login 失败时路由调用 LogService.emit，action='login' / result='failure' / level='warning' / source='auth_router' / log_type='auth'。

    验证失败路径同样覆盖，level 提升为 warning。
    """
    from app.shared.utils.auth.Safety import jwt_auth
    from app.shared.routers.auth_router import login_api
    from fastapi import HTTPException

    async def fake_verify_credentials(username, password):
        return False

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.verify_credentials",
        fake_verify_credentials,
        raising=False,
    )
    monkeypatch.setattr(jwt_auth, "verify_credentials", fake_verify_credentials)

    request = SimpleNamespace(
        client=SimpleNamespace(host="5.6.7.8"),
        state=SimpleNamespace(username=None, user_id=None),
        app=SimpleNamespace(state=SimpleNamespace()),
    )
    payload = SimpleNamespace(username="ghost", password="wrong")

    from fastapi import Response

    response = Response()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(login_api(payload, request, response))
    assert exc_info.value.status_code == 401

    assert len(capturing_log_service.emit_calls) == 1
    evt = capturing_log_service.emit_calls[0]
    assert evt.action == "login"
    assert str(evt.log_type) == "auth"
    assert str(evt.result) == "failure"
    assert str(evt.level) == "warning"
    assert evt.source == "auth_router"
    assert evt.username == "ghost"


def test_auth_router_logout_emits_logout_event(capturing_log_service, monkeypatch):
    """logout 调用 LogService.emit，action='logout' / log_type='auth' / source='auth_router'。

    验证：
    - detail 信息落入 message 字段（session 已被销毁的描述）
    - 业务 200 不被日志失败影响
    """
    from app.shared.routers.auth_router import logout
    from fastapi import Response

    request = SimpleNamespace(
        client=SimpleNamespace(host="9.10.11.12"),
        state=SimpleNamespace(username="alice", user_id=7),
        headers={"X-Session-ID": "sess-X"},
        cookies={},
    )

    # monkeypatch refresh_token_db / portal_refresh_token_db
    async def fake_hash_token(t):
        return "hashed"

    async def fake_delete_token(hash_):
        return None

    async def fake_delete_user_tokens(uid):
        return 0

    monkeypatch.setattr(
        "app.shared.utils.auth.refresh_token_db.RefreshTokenDB.hash_token",
        fake_hash_token,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.refresh_token_db.RefreshTokenDB.delete_token",
        fake_delete_token,
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.portal_refresh_token_db.PortalRefreshTokenDB.delete_user_tokens",
        fake_delete_user_tokens,
    )

    async def fake_session_delete(sid):
        return True

    monkeypatch.setattr(
        "app.shared.utils.Session.SessionCache.session_cache.delete_session",
        fake_session_delete,
    )

    response = Response()
    result = asyncio.run(logout(request, response))

    assert result["message"] == "登出成功"
    assert len(capturing_log_service.emit_calls) == 1
    evt = capturing_log_service.emit_calls[0]
    assert evt.action == "logout"
    assert str(evt.log_type) == "auth"
    assert str(evt.result) == "success"
    assert evt.source == "auth_router"
    assert evt.username == "alice"
    assert evt.user_id == 7


# =============================================================================
# 4. user_router 迁移契约：admin_update_user / admin_kick_user
# =============================================================================


def _setup_user_kick_request(monkeypatch):
    """构造 admin 调用 kick_user 的最小测试环境。"""
    # UserDB
    async def fake_get_user_by_id(uid):
        return {"id": uid, "username": f"target-{uid}", "role": "user"}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_id",
        fake_get_user_by_id,
    )

    # RefreshTokenDB.delete_user_tokens
    async def fake_delete_user_tokens(uid):
        return 3

    monkeypatch.setattr(
        "app.shared.utils.auth.refresh_token_db.RefreshTokenDB.delete_user_tokens",
        fake_delete_user_tokens,
    )

    # PortalRefreshTokenDB.delete_user_tokens
    async def fake_portal_delete(uid):
        return 2

    monkeypatch.setattr(
        "app.shared.utils.auth.portal_refresh_token_db.PortalRefreshTokenDB.delete_user_tokens",
        fake_portal_delete,
    )

    # session_cache.kick_user_sessions
    async def fake_kick(uid):
        return 5

    monkeypatch.setattr(
        "app.shared.utils.Session.SessionCache.session_cache.kick_user_sessions",
        fake_kick,
    )


def test_user_router_admin_kick_emits_log_event(capturing_log_service, monkeypatch):
    """admin_kick_user 触发 LogEvent：log_type='user', target_type='user', target_id / target_name 全字段写齐。"""
    from app.shared.routers.user_router import kick_user

    _setup_user_kick_request(monkeypatch)

    request = SimpleNamespace(
        client=SimpleNamespace(host="10.20.30.40"),
        state=SimpleNamespace(username="admin", user_id=1),
    )

    result = asyncio.run(kick_user(user_id=99, req=request))

    assert result["deleted_tokens"] == 3
    assert len(capturing_log_service.emit_calls) == 1
    evt = capturing_log_service.emit_calls[0]
    assert evt.action == "admin_kick_user"
    assert str(evt.log_type) == "user"
    assert evt.target_type == "user"
    assert evt.target_id == "99"
    assert evt.target_name == "target-99"
    assert evt.source == "user_router"
    assert evt.username == "admin"
    assert evt.user_id == 1


def test_user_router_admin_update_emits_log_event(capturing_log_service, monkeypatch):
    """admin_update_user 触发 LogEvent：log_type='user', action='admin_update_user', target_type='user'。"""
    from app.shared.routers.user_router import update_user_admin

    async def fake_get_user_by_id(uid):
        return {"id": uid, "username": f"target-{uid}", "role": "user"}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_id",
        fake_get_user_by_id,
    )

    async def fake_update_user_info(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.update_user_info",
        fake_update_user_info,
    )

    request = SimpleNamespace(
        client=SimpleNamespace(host="1.1.1.1"),
        state=SimpleNamespace(username="admin", user_id=1),
    )
    payload = SimpleNamespace(
        real_name="张三",
        phone="13800138000",
        email="test@example.com",
        department="x",
        position="y",
        role="user",
        allowed_agents=[],
    )

    result = asyncio.run(update_user_admin(user_id=99, request=payload, req=request))
    assert result["message"] == "更新成功"
    assert len(capturing_log_service.emit_calls) == 1
    evt = capturing_log_service.emit_calls[0]
    assert evt.action == "admin_update_user"
    assert str(evt.log_type) == "user"
    assert evt.target_type == "user"
    assert evt.target_id == "99"
    assert evt.target_name == "target-99"


# =============================================================================
# 5. session_router admin_delete_session 迁移契约
# =============================================================================


def test_session_router_admin_delete_session_emits_log_event(capturing_log_service, monkeypatch):
    """admin_delete_session 触发 LogEvent：log_type='session', action='admin_delete_session', session_id 与 target 写齐。"""
    from app.shared.routers.session_router import admin_delete_session

    # 业务清理的几个 DB 调用（mock 即可）
    async def fake_delete_records(sid):
        return None

    monkeypatch.setattr(
        "app.shared.utils.memory.conversation_db.ConversationDB.delete_session_records",
        fake_delete_records,
    )

    async def fake_delete_attachments(sid):
        return None

    monkeypatch.setattr(
        "app.shared.utils.files.attachment_db.AttachmentDB.delete_session_attachments",
        fake_delete_attachments,
    )

    # file_transfer.delete_session
    class _FT:
        async def delete_session(self, sid):
            return True

    # 必须 patch session_router 命名空间里的 FileTransfer（其模块顶
    # ``from app.shared.utils.files.fileTransfer import FileTransfer`` 已
    # 把名字绑定到本地命名空间，仅 patch 源模块无效）。
    monkeypatch.setattr(
        "app.shared.routers.session_router.FileTransfer",
        lambda: _FT(),
    )

    # checkpointer
    # 显式把 adelete_thread 设为 AsyncMock，避免 AsyncMock 自动推断失败
    # 导致 ``await checkpointer.adelete_thread(...)`` 抛 Mock 不可 await。
    checkpointer_mock = MagicMock()
    checkpointer_mock.adelete_thread = AsyncMock()
    async def fake_checkpointer():
        return checkpointer_mock

    async def fake_sub_ids(**kwargs):
        return []

    monkeypatch.setattr(
        "app.shared.utils.memory.checkpoint.get_async_checkpointer",
        fake_checkpointer,
    )
    # CheckpointHistoryService.collect_subagent_thread_ids_for_cleanup
    from app.shared.utils.memory.checkpoint_history import CheckpointHistoryService
    monkeypatch.setattr(
        CheckpointHistoryService,
        "collect_subagent_thread_ids_for_cleanup",
        staticmethod(fake_sub_ids),
    )

    # session_cache.delete_session
    async def fake_session_delete(sid):
        return None

    monkeypatch.setattr(
        "app.shared.utils.Session.SessionCache.session_cache.delete_session",
        fake_session_delete,
    )

    request = SimpleNamespace(
        client=SimpleNamespace(host="11.11.11.11"),
        state=SimpleNamespace(username="admin", user_id=1),
    )

    result = asyncio.run(admin_delete_session(session_id="sess-998877", request=request))

    assert result["success"] is True
    assert len(capturing_log_service.emit_calls) == 1
    evt = capturing_log_service.emit_calls[0]
    assert evt.action == "admin_delete_session"
    assert str(evt.log_type) == "session"
    assert evt.session_id == "sess-998877"
    assert evt.target_type == "session"
    assert evt.target_id == "sess-998877"


# =============================================================================
# 6. 日志服务缺失 / emit 失败不阻断业务
# =============================================================================


def test_auth_router_login_succeeds_when_log_service_missing(monkeypatch):
    """get_log_service() 返回 None 时，login 业务响应必须仍然 200，不被日志失败阻断。"""
    from app.shared.utils import log_service as log_service_module
    from app.shared.routers.auth_router import login_api
    from fastapi import Response

    monkeypatch.setattr(log_service_module, "_log_service_singleton", None)
    monkeypatch.setattr(log_service_module, "get_log_service", lambda: None)

    # monkeypatch 凭据校验、refresh_token_store、jwt 生成等
    from app.shared.utils.auth.Safety import jwt_auth

    async def fake_verify_credentials(username, password):
        return True

    monkeypatch.setattr(jwt_auth, "verify_credentials", fake_verify_credentials)

    async def fake_get_user(username):
        return {"id": 1, "username": username, "role": "user", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    async def fake_store_token(token_hash, user_id, expires_at, username=""):
        return True

    monkeypatch.setattr(
        "app.shared.utils.auth.refresh_token_db.RefreshTokenDB.store_token",
        fake_store_token,
    )

    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(username=None, user_id=None),
        app=SimpleNamespace(state=SimpleNamespace()),
    )
    payload = SimpleNamespace(username="alice", password="pw")

    response = Response()
    result = asyncio.run(login_api(payload, request, response))
    assert result.username == "alice"


def test_auth_router_login_succeeds_when_emit_raises(monkeypatch):
    """LogService.emit 抛出时 login 仍必须 200（fail-soft，仅记 warning，不阻断业务）。"""
    from app.shared.utils import log_service as log_service_module
    from app.shared.routers.auth_router import login_api
    from fastapi import Response

    fake_service = MagicMock()

    def fake_emit_raises(event):
        raise RuntimeError("emit pipeline died")

    fake_service.emit = fake_emit_raises
    monkeypatch.setattr(log_service_module, "_log_service_singleton", fake_service)
    monkeypatch.setattr(log_service_module, "get_log_service", lambda: fake_service)

    from app.shared.utils.auth.Safety import jwt_auth

    async def fake_verify_credentials(username, password):
        return True

    monkeypatch.setattr(jwt_auth, "verify_credentials", fake_verify_credentials)

    async def fake_get_user(username):
        return {"id": 1, "username": username, "role": "user", "allowed_agents": []}

    monkeypatch.setattr(
        "app.shared.utils.auth.user_db.UserDB.get_user_by_username",
        fake_get_user,
    )

    async def fake_store_token(token_hash, user_id, expires_at, username=""):
        return True

    monkeypatch.setattr(
        "app.shared.utils.auth.refresh_token_db.RefreshTokenDB.store_token",
        fake_store_token,
    )

    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(username=None, user_id=None),
        app=SimpleNamespace(state=SimpleNamespace()),
    )
    payload = SimpleNamespace(username="alice", password="pw")

    response = Response()
    result = asyncio.run(login_api(payload, request, response))
    assert result.username == "alice"


# =============================================================================
# 7. agent_router 强制覆盖客户端伪造身份
# =============================================================================


def test_agent_router_overrides_client_supplied_log_user_id(monkeypatch):
    """客户端在 context_overrides.log_user_id 伪造身份（如777777777）时，
    agent_router 必须在 build_agent_instance 之前强制覆盖为 request.state.user_id 的真值。
    """
    from app.routers import agent_router as router_module

    captured = {}
    real_user_id = 42

    async def fake_build(**kwargs):
        captured.update(kwargs.get("context_overrides") or {})
        return MagicMock(name="agent"), MagicMock(name="ctx"), MagicMock(name="state")

    # 必须替换成 AsyncMock，因为 agent_router 中是 ``await service.build_agent_instance(...)``。
    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        AsyncMock(side_effect=fake_build),
    )

    async def fake_get(name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="x",
            description="",
            system_prompt="",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "s"}),
        )

    # get_agent_config 也是被 await 的，必须 AsyncMock
    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        AsyncMock(side_effect=fake_get),
    )

    # session_auth_middleware 写入 request.state.user_id = real_user_id；
    # request.state.username = real_username
    from fastapi import Request

    fake_request = MagicMock(spec=Request)
    fake_request.app.state.agent_config_service = MagicMock()
    fake_request.headers = {"X-Session-ID": "s"}
    fake_request.state.user_id = real_user_id
    fake_request.state.username = "real_admin"
    fake_request.state.role = "admin"
    fake_request.state.allowed_agents = []

    from app.routers.agent_router import chat, ChatRequest

    # 客户端伪造身份：log_user_id=999999 远大于真实 42
    chat_request = ChatRequest(
        message="hi",
        session_id="s",
        agent_name="default",
        context_overrides={"log_user_id": 999999, "log_username": "forged"},
    )

    # fake_request 是 MagicMock(spec=Request)，app.state.agent_config_service
    # 也是 MagicMock。需要把 service.build_agent_instance 替换为 AsyncMock
    # 让 ``await service.build_agent_instance(...)`` 可用。
    captured.clear()
    fake_request = MagicMock(spec=Request)
    fake_request.headers = {"X-Session-ID": "s"}
    fake_request.state.user_id = real_user_id
    fake_request.state.username = "real_admin"
    fake_request.state.role = "admin"
    fake_request.state.allowed_agents = []
    fake_request.client = SimpleNamespace(host="1.2.3.4")
    fake_service = MagicMock()
    fake_service.build_agent_instance = AsyncMock(side_effect=fake_build)
    fake_request.app.state.agent_config_service = fake_service
    # 同样让 get_agent_config 可用（agent_router 也会 await 它）
    fake_service.get_agent_config = AsyncMock(side_effect=fake_get)

    # fastapi 自动注入忽略不传 req 参数即可；通过 fake_build 捕获
    monkeypatch.setattr(
        "app.routers.agent_router.generate_stream_response",
        lambda *a, **k: iter(["data: test\n\n"]),
    )

    asyncio.run(chat(fake_request, chat_request))

    # 核心断言：客户端伪造的 log_user_id 被强制覆盖为真值
    assert captured.get("log_user_id") == real_user_id, (
        f"客户端伪造 log_user_id=999999 必须被覆盖为服务端鉴权结果 {real_user_id}, "
        f"实际收到 {captured.get('log_user_id')!r}"
    )
    assert captured.get("log_username") == "real_admin"


# =============================================================================
# 8. task_scheduler 注入创建者身份
# =============================================================================


def test_task_scheduler_injects_creator_identity_into_overrides(monkeypatch):
    """TaskSchedulerService.execute_schedule 在调用 build_agent_instance 前，
    必须把 created_by_user_id / username（任务所有者真实身份）注入 context_overrides；
    即便 schedule.context_overrides 含伪造身份也被覆盖。
    """
    from app.shared.utils.agent import task_scheduler_service as task_mod

    captured = {}

    class _FakeAgentConfigService:
        async def get_agent_config(self, name):
            return SimpleNamespace(display_name="地图智能体")

        async def build_agent_instance(self, *, agent_name, session_id, message=None,
                                       context_overrides=None, resume=None,
                                       state_class_kwargs=None, system_prompt_override=None):
            captured["overrides"] = dict(context_overrides or {})
            captured["session_id"] = session_id
            fake_agent = MagicMock()

            async def fake_invoke(*a, **kw):
                return {"messages": [SimpleNamespace(content="OK")]}

            fake_agent.invoke = fake_invoke
            return fake_agent, SimpleNamespace(session_id=session_id), {"messages": []}

    fake_acs = _FakeAgentConfigService()

    db = MagicMock()
    db.fetchrow = AsyncMock()

    async def fetchrow_side(query, *args):
        if "FROM users" in query:
            return {"id": args[0], "username": "creator-real"}
        # 没有正在运行的 run
        if "status = 'running'" in query:
            return None
        # 默认记录
        return SimpleNamespace(
            id=42,
            session_id="sess",
            schedule_id=42,
            user_id=99,  # 创建者真实 user_id
            username="creator",
            agent_name="map_agent",
            prompt="hello",
            cron_expression="* * * * *",
            timezone="Asia/Shanghai",
            enabled=True,
            created_by_user_id=99,
            context_overrides={},  # 客户端伪造入口
            max_concurrent_runs=1,
            target_type="agent",
            script_name=None,
            script_args={},
            notify_enabled=False,
            notify_policy_id=None,
            last_run_at=None,
            next_run_at=None,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )

    db.fetchrow.side_effect = fetchrow_side
    db.execute = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    db.acquire = MagicMock()

    service = task_mod.TaskSchedulerService(db=db, agent_config_service=fake_acs, scheduler=MagicMock())

    # 客户端伪造 schedule.context_overrides 含伪造身份
    monkeypatch.setattr(service, "_calculate_next_run_at", lambda x: None)

    # 直接构造 schedule dict 覆盖伪造身份
    fake_schedule = {
        "id": 42,
        "session_id": "sess",
        "agent_name": "map_agent",
        "prompt": "hello",
        "cron_expression": "* * * * *",
        "timezone": "Asia/Shanghai",
        "enabled": True,
        "created_by_user_id": 99,
        "context_overrides": {
            "log_user_id": 999999,
            "log_username": "forged",
        },
        "max_concurrent_runs": 1,
        "target_type": "agent",
        "script_name": None,
        "script_args": {},
        "notify_enabled": False,
        "notify_policy_id": None,
        "last_run_at": None,
        "next_run_at": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }

    async def fake_get_schedule_internal(_id):
        return fake_schedule

    monkeypatch.setattr(service, "get_schedule_internal", fake_get_schedule_internal)
    monkeypatch.setattr(service, "_create_run", AsyncMock(return_value={"id": 1, "schedule_id": 42}))
    monkeypatch.setattr(service, "_update_run", AsyncMock())
    monkeypatch.setattr(service, "_mark_schedule_run_completed", AsyncMock())
    monkeypatch.setattr(service, "_install_run_logger", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(service, "_uninstall_run_logger", lambda *a, **kw: None)

    # SessionDB.add_session / update_session_agent 都要 mock
    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.add_session",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.shared.utils.auth.session_db.SessionDB.update_session_agent",
        AsyncMock(),
    )

    asyncio.run(service.execute_schedule(schedule_id=42, trigger_type="manual"))

    overrides = captured["overrides"]
    # 创建者身份注入（覆盖客户端伪造的 999999）
    assert overrides.get("log_user_id") == 99
    assert overrides.get("log_username") == "creator-real"


# =============================================================================
# 9. audit_logs schema 入口归属于 log_service
# =============================================================================


def test_audit_logs_schema_registered_in_log_service():
    """验证 @register_schema 装饰的 audit_log schema 初始化函数现在位于 log_service 模块。

    旧路径 app.shared.utils.auth.audit_log.init_audit_log_schema 被弃用。
    """
    from app.shared.utils import log_service as log_service_module

    source = inspect.getsource(log_service_module)
    # 必须存在 init_audit_log_schema 函数声明（与原版语义等价）
    assert "async def init_audit_log_schema" in source, (
        "log_service 必须包含 init_audit_log_schema 函数（迁移旧 audit_log.py 的 schema 入口）"
    )
    # 该函数必须 @register_schema 装饰（启动时由 DatabasePool.register_schemas() 自动调用）
    # 检测：函数定义前一行或同一装饰器段含 register_schema
    # 我们用全局 _registered_schemas 反向验证：装饰器在 import-time 已生效
    from app.core.database import _registered_schemas

    func_names = [f.__name__ for f in _registered_schemas]
    assert "init_audit_log_schema" in func_names, (
        "log_service.init_audit_log_schema 必须 @register_schema 注册，"
        "由 DatabasePool.register_schemas() 自动调用。"
    )

    # 旧路径下应用层 init 入口已被删除
    import importlib.util

    spec = importlib.util.find_spec("app.shared.utils.auth.audit_log")
    assert spec is None, (
        "app/shared/utils/auth/audit_log.py 必须删除；"
        "schema 入口归 log_service.py 统一。"
    )


def test_init_all_tables_sql_has_audit_logs_schema():
    """init_all_tables.sql 已经包含 audit_logs 表与扩展列。

    即使 audit_log.py 删了，schema 入口仍由 init_all_tables.sql 与
    log_service.init_audit_log_schema 双重保证。
    """
    from pathlib import Path
    # pytest rootdir = app/，当前文件位于 app/tests/shared/routers/，
    # parents[4] = 项目根，与 migrations 目录同级。
    sql_path = (
        Path(__file__).resolve().parents[4] / "app" / "migrations" / "init_all_tables.sql"
    )
    sql = sql_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS audit_logs" in sql
    assert "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS log_type" in sql
    assert "IN ('auth', 'user', 'session', 'ssh', 'system')" in sql


# =============================================================================
# 10. AgentContext 含 log_user_id / log_username 字段
# =============================================================================


def test_agent_context_has_log_user_id_and_log_username_fields():
    """AgentContext TypedDict 必须含 Optional log_user_id / log_username 字段及中文注释。"""
    from app.core.agent.AgentContext import AgentContext

    annotations = AgentContext.__annotations__ if hasattr(AgentContext, "__annotations__") else {}
    assert "log_user_id" in annotations, (
        "AgentContext 必须声明 log_user_id 字段，类型 Optional[int]，默认 None"
    )
    assert "log_username" in annotations, (
        "AgentContext 必须声明 log_username 字段，类型 Optional[str]，默认 None"
    )
    # 模块 docstring 必须包含中文注释说明这两个字段的用途
    from app.core.agent import AgentContext as ctx_module

    src = inspect.getsource(ctx_module)
    assert "log_user_id" in src
    assert "log_username" in src
    # 检查中文注释存在
    has_cn = any(
        keyword in src for keyword in ["审计", "日志", "创建者", "请求方", "覆盖"]
    )
    assert has_cn, "AgentContext 模块须有中文注释解释 log_user_id / log_username 用途"


# =============================================================================
# 11. AgentContext 含 log_ip 字段（2026-07-30 新增,与 log_user_id / log_username 同款）
# =============================================================================


def test_agent_context_has_log_ip_field():
    """AgentContext TypedDict 必须含 Optional log_ip 字段及中文注释。

    业务语义(2026-07-30 新增):写入 ``audit_logs.ip_address`` 的真值来源,
    禁止信任客户端。``agent_router`` 用 ``request.client.host`` 强制覆盖后
    注入到 ``runtime.context['log_ip']``,SSH 工具读取后写入 LogEvent.ip_address。
    """
    from app.core.agent.AgentContext import AgentContext

    annotations = AgentContext.__annotations__ if hasattr(AgentContext, "__annotations__") else {}
    assert "log_ip" in annotations, (
        "AgentContext 必须声明 log_ip 字段，类型 Optional[str]，默认 None"
    )
    # 模块 docstring 必须包含中文注释说明 log_ip 字段的用途
    from app.core.agent import AgentContext as ctx_module

    src = inspect.getsource(ctx_module)
    assert "log_ip" in src
    # 验证中文注释存在
    has_cn = any(
        keyword in src for keyword in ["审计", "日志", "客户端", "覆盖"]
    )
    assert has_cn, "AgentContext 模块须有中文注释解释 log_ip 用途"


# =============================================================================
# 12. agent_router 强制覆盖 log_ip（2026-07-30 新增,与 log_user_id 同款）
# =============================================================================


def test_agent_router_overrides_client_supplied_log_ip(monkeypatch):
    """客户端在 context_overrides.log_ip 伪造 IP 时,
    agent_router 必须在 build_agent_instance 之前强制覆盖为 request.client.host 真值。

    业务语义(2026-07-30 新增):与 log_user_id / log_username 同款防伪机制,
    防止客户端通过 context_overrides 写入伪造 IP 污染审计日志。
    """
    from fastapi import Request

    captured = {}
    real_client_host = "198.51.100.7"

    async def fake_build(**kwargs):
        captured.update(kwargs.get("context_overrides") or {})
        return MagicMock(name="agent"), MagicMock(name="ctx"), MagicMock(name="state")

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.build_agent_instance",
        AsyncMock(side_effect=fake_build),
    )

    async def fake_get(name):
        from app.shared.utils.agent.agent_config_service import UnifiedAgentConfig
        return UnifiedAgentConfig(
            name=name,
            display_name="x",
            description="",
            system_prompt="",
            state_class=MagicMock(return_value={"messages": []}),
            context_class=MagicMock(return_value={"session_id": "s"}),
        )

    monkeypatch.setattr(
        "app.shared.utils.agent.agent_config_service.AgentConfigService.get_agent_config",
        AsyncMock(side_effect=fake_get),
    )

    fake_request = MagicMock(spec=Request)
    fake_request.headers = {"X-Session-ID": "s"}
    fake_request.state.user_id = 42
    fake_request.state.username = "real_admin"
    fake_request.state.role = "admin"
    fake_request.state.allowed_agents = []
    # 服务端真实连接 IP（auth_middleware 注入后由 request.client.host 提供）
    fake_request.client = SimpleNamespace(host=real_client_host)
    fake_service = MagicMock()
    fake_service.build_agent_instance = AsyncMock(side_effect=fake_build)
    fake_request.app.state.agent_config_service = fake_service
    fake_service.get_agent_config = AsyncMock(side_effect=fake_get)

    monkeypatch.setattr(
        "app.routers.agent_router.generate_stream_response",
        lambda *a, **k: iter(["data: test\n\n"]),
    )

    from app.routers.agent_router import chat, ChatRequest

    # 客户端伪造 IP：log_ip=9.9.9.9
    chat_request = ChatRequest(
        message="hi",
        session_id="s",
        agent_name="default",
        context_overrides={"log_ip": "9.9.9.9"},
    )

    captured.clear()
    asyncio.run(chat(fake_request, chat_request))

    # 核心断言：客户端伪造的 log_ip 被强制覆盖为服务端真值
    assert captured.get("log_ip") == real_client_host, (
        f"客户端伪造 log_ip='9.9.9.9' 必须被覆盖为服务端鉴权结果 {real_client_host!r}, "
        f"实际收到 {captured.get('log_ip')!r}"
    )
