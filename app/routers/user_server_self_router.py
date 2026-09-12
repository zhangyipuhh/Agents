#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
用户服务器自助读 Router（2026-09-12 渗透整改新增）。

提供 GET /api/user-servers/tree：登录态可读,OwnershipScope 按归属过滤
（admin 全量 / 普通用户仅自己 created_by_user_id 的节点）。

存在意义：InputBox # 触发器的服务器候选数据源。语义与
/api/admin/user-servers/tree 完全一致,仅迁出 /api/admin/ 命名空间——
该命名空间按安全开发标准必须 100% 挂 require_admin/菜单 ACL,
普通用户自助读路径不得滞留其中。

服务实例由 app/core/server.py lifespan 初始化到 app.state.user_server_service。
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status

from app.shared.utils.auth.ownership_scope import OwnershipScope


router = APIRouter(
    prefix="/api/user-servers",
    tags=["User Server Self"],
)


@router.get("/tree", response_model=Dict[str, Any])
async def get_my_tree(request: Request) -> Dict[str, Any]:
    """获取当前用户可见的服务器节点树平铺列表。

    参数:
        request: FastAPI Request 对象。

    返回:
        Dict[str, Any]: {"nodes": [...]},前端自行组树。

    异常:
        HTTPException: 服务未初始化时抛出 500。
    """
    service = getattr(request.app.state, "user_server_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="UserServerService not initialized",
        )
    scope = OwnershipScope.from_request(request)
    nodes = service.list_nodes(scope)
    return {"nodes": nodes}
