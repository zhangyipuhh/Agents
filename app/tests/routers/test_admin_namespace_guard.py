# -*- coding:utf-8 -*-
"""/api/admin/* 命名空间授权默认拒绝守卫测试（2026-09-12 渗透整改落地）。

安全开发强制标准：凡 /api/admin/ 前缀端点必须挂 require_admin 或带
__menu_acl_guard__ 标记的菜单 ACL 依赖（router 级或端点级均可）。
本测试全量扫描路由表，新增 admin 端点忘挂鉴权 = CI 直接失败。
豁免白名单必须永远为空——不允许例外。
"""

import inspect

from fastapi import Depends
from fastapi.routing import APIRoute

from app.shared.utils.auth.Safety import require_admin

_ADMIN_PREFIX = "/api/admin/"


def _route_dependency_callables(route):
    """提取路由全部依赖 callable（router 级依赖 + endpoint 签名 Depends）。"""
    deps = [d.dependency for d in getattr(route, "dependencies", []) or []]
    # 同时检查 endpoint 签名里以 _=Depends(...) 形式注入的依赖
    endpoint = getattr(route, "endpoint", None)
    if endpoint is not None:
        try:
            sig = inspect.signature(endpoint)
        except (TypeError, ValueError):
            sig = None
        if sig is not None:
            for param in sig.parameters.values():
                # Depends 是函数,实例检测用类型名识别 (FastAPI >= 0.95)
                if type(param.default).__name__ == "Depends":
                    deps.append(param.default.dependency)
    return deps


def test_all_admin_routes_have_authorization_dependency(client):
    """全部 /api/admin/ 端点必须有授权守护，豁免表为空。

    参数:
        client: TestClient fixture（含完整注册路由的 app）。

    返回值:
        None

    异常:
        AssertionError: 存在未挂授权依赖的 admin 端点时失败并列出清单
    """
    violations = []
    for route in client.app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path.startswith(_ADMIN_PREFIX) or not methods:
            continue
        callables = _route_dependency_callables(route)
        guarded = any(
            dep is require_admin
            or getattr(dep, "__menu_acl_guard__", False)
            for dep in callables
        )
        if not guarded:
            violations.append(f"{sorted(methods)} {path}")
    assert violations == [], (
        "以下 /api/admin/ 端点未挂授权依赖（require_admin / 菜单 ACL）：\n"
        + "\n".join(violations)
    )

