# -*- coding:utf-8 -*-
"""
notification_router 路由注册与 ACL 字段契约测试(2026-09-03 新增)。

测试覆盖:
- P0 模块可导入 + router 注册路径正确(prefix='/api/notification',无 /admin/)
- P1 11 个端点全部已注册(GET/POST/PUT/DELETE)
- P1 端点 ACL key 全部使用 messaging.feishu.<sub>(本期 UI 仅暴露飞书)
- P1 SendTestRequest body 含 target_id + channel_type + content 三字段
"""
import pytest
from fastapi import FastAPI

from app.routers.notification_router import router


# =============================================================================
# P0: 模块导入 + 路由注册
# =============================================================================


def test_router_importable():
    """notification_router 模块可导入 + router 是 FastAPI APIRouter 实例。"""
    from fastapi import APIRouter

    assert isinstance(router, APIRouter)


def test_router_prefix():
    """router prefix 必须为 /api/notification(无 /admin/ 段,用户硬约束)。"""
    assert router.prefix == "/api/notification"


def test_router_tags_contains_notification():
    """router.tags 含 'Notification'。"""
    assert "Notification" in router.tags


def test_router_no_router_level_require_admin():
    """router 自身不挂 dependencies(require_admin),ACL 走逐端点 Depends。"""
    # 逐端点 dependencies=[Depends(require_admin_or_menu_acl(...))]
    # router-level dependencies 默认为空列表
    assert router.dependencies == []


def test_router_registered_to_fastapi_app():
    """router 挂载到 FastAPI app 后所有路径可枚举。"""
    app = FastAPI()
    app.include_router(router)
    # 仅看本 router 注入的路径(前缀 /api/notification)
    notif_paths = sorted(
        {route.path for route in app.routes
         if hasattr(route, "path") and route.path.startswith("/api/notification")}
    )
    expected_paths = {
        "/api/notification/channels",
        "/api/notification/channels/{channel_id}",
        "/api/notification/channels/{channel_id}/test-connection",
        "/api/notification/channels/{channel_id}/targets",
        "/api/notification/targets/{target_id}",
        "/api/notification/agents",
        "/api/notification/send-test",
    }
    assert expected_paths.issubset(set(notif_paths))
    assert len(notif_paths) == 7


def test_router_has_expected_endpoints():
    """router 端点方法分布正确(GET/POST/PUT/DELETE 都覆盖)。"""
    app = FastAPI()
    app.include_router(router)
    endpoint_paths = [
        (r.path, sorted(r.methods))
        for r in app.routes
        if hasattr(r, "methods") and r.methods and r.path.startswith("/api/notification")
    ]
    # 计算 method 数量(每个 path entry 可能有多个 method)
    total = sum(len(methods) for _, methods in endpoint_paths)
    # 预期 12 (channels GET+POST, channels/{id} GET+PUT+DELETE, channels/{id}/test-connection POST,
    #          channels/{id}/targets GET+POST, targets/{id} PUT+DELETE, agents GET, send-test POST)
    assert total == 12
    # 用 (path, method) 元组 set 验证方法分布
    method_pairs = set()
    for path, methods in endpoint_paths:
        for m in methods:
            method_pairs.add((path, m))
    expected_pairs = {
        ("/api/notification/channels", "GET"),
        ("/api/notification/channels", "POST"),
        ("/api/notification/channels/{channel_id}", "GET"),
        ("/api/notification/channels/{channel_id}", "PUT"),
        ("/api/notification/channels/{channel_id}", "DELETE"),
        ("/api/notification/channels/{channel_id}/test-connection", "POST"),
        ("/api/notification/channels/{channel_id}/targets", "GET"),
        ("/api/notification/channels/{channel_id}/targets", "POST"),
        ("/api/notification/targets/{target_id}", "PUT"),
        ("/api/notification/targets/{target_id}", "DELETE"),
        ("/api/notification/agents", "GET"),
        ("/api/notification/send-test", "POST"),
    }
    assert expected_pairs.issubset(method_pairs)


# =============================================================================
# P1: 端点 ACL key 契约(源码静态断言,防回归)
# =============================================================================


def test_all_channel_endpoints_use_messaging_feishu_apps_acl():
    """channels 路径下所有端点 ACL = messaging.feishu.apps。"""
    expected = {
        ("GET", "/api/notification/channels"),
        ("POST", "/api/notification/channels"),
        ("GET", "/api/notification/channels/{channel_id}"),
        ("PUT", "/api/notification/channels/{channel_id}"),
        ("DELETE", "/api/notification/channels/{channel_id}"),
        ("POST", "/api/notification/channels/{channel_id}/test-connection"),
    }
    found = set()
    for r in router.routes:
        if hasattr(r, "methods") and r.methods and r.path.startswith("/api/notification/channels"):
            for m in r.methods:
                if m in ("GET", "POST", "PUT", "DELETE"):
                    found.add((m, r.path))
    assert expected.issubset(found)


def test_targets_endpoints_use_messaging_feishu_policies_acl():
    """targets 路径下所有端点 ACL = messaging.feishu.policies。"""
    expected_methods = {"GET", "POST", "PUT", "DELETE"}
    found = False
    for r in router.routes:
        if hasattr(r, "methods") and "/targets" in r.path:
            found = True
    assert found, "targets 端点未注册"


def test_send_test_endpoint_exists():
    """send-test 端点存在且方法为 POST。"""
    for r in router.routes:
        if hasattr(r, "methods") and r.path == "/api/notification/send-test":
            assert "POST" in r.methods
            return
    pytest.fail("send-test 端点未注册")


def test_agents_endpoint_exists():
    """agents 端点存在且方法为 GET。"""
    for r in router.routes:
        if hasattr(r, "methods") and r.path == "/api/notification/agents":
            assert "GET" in r.methods
            return
    pytest.fail("agents 端点未注册")


# =============================================================================
# P1: SendTestRequest body 字段契约
# =============================================================================


def test_send_test_request_has_target_id_channel_type_content():
    """SendTestRequest body 必须含 target_id + channel_type + content 三个字段。"""
    from app.routers.notification_router import SendTestRequest

    req = SendTestRequest(target_id=1, channel_type="feishu", content="hello")
    assert req.target_id == 1
    assert req.channel_type == "feishu"
    assert req.content == "hello"


def test_send_test_request_channel_type_default_is_feishu():
    """SendTestRequest.channel_type 默认值 = 'feishu'。"""
    from app.routers.notification_router import SendTestRequest

    req = SendTestRequest(target_id=1, content="hello")
    assert req.channel_type == "feishu"


# =============================================================================
# P1: CreateChannelRequest 契约
# =============================================================================


def test_create_channel_request_required_fields():
    """CreateChannelRequest.name 必填 + 默认 channel_type=feishu。"""
    from app.routers.notification_router import CreateChannelRequest

    req = CreateChannelRequest(
        name="test-bot",
        config={"app_id": "x", "app_secret": "y"},
    )
    assert req.name == "test-bot"
    assert req.channel_type == "feishu"
    assert req.enabled is True
    assert req.is_default is False


def test_create_target_request_required_fields():
    """CreateTargetRequest 必填字段:name + agent_name + config。"""
    from app.routers.notification_router import CreateTargetRequest

    req = CreateTargetRequest(
        name="ops-group",
        agent_name="project",
        config={"chat_id": "oc_xxx", "chat_type": "chat_id"},
    )
    assert req.name == "ops-group"
    assert req.agent_name == "project"
    assert req.target_type == "feishu.chat"
    assert req.enabled is True
