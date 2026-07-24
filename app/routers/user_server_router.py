#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
UserServerRouter - 用户服务器配置管理 API（2026-07-24 新增）

提供 /api/admin/user-servers 下的树节点 CRUD、节点详情、批量导入接口。
所有接口要求 admin 角色或 task-scheduler.server-management 菜单 ACL 授权。
服务实例由 app/core/server.py lifespan 初始化到 app.state.user_server_service。

端点契约（与 api_config_router 同形）：
    - GET    /api/admin/user-servers/tree
    - POST   /api/admin/user-servers/nodes
    - PUT    /api/admin/user-servers/nodes/{id}
    - DELETE /api/admin/user-servers/nodes/{id}
    - GET    /api/admin/user-servers/nodes/{id}/config
    - POST   /api/admin/user-servers/import
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.shared.utils.auth.Safety import require_admin_or_menu_acl
from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.user_server_service import (
    UserServerNodeNotEmptyError,
    UserServerNodeNotFoundError,
    UserServerService,
)


router = APIRouter(
    prefix="/api/admin/user-servers",
    tags=["User Server Management"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateNodeRequest(BaseModel):
    """创建节点请求体。

    Attributes:
        parent_id: 父节点 ID；None 表示根节点。
        node_type: 节点类型，'folder' 或 'server'。
        name: 节点名称。
        source_devops_server_id: server 节点引用的 devops_servers.id；
            folder 节点必须为 None。
    """

    parent_id: Optional[int] = Field(default=None)
    node_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=255)
    source_devops_server_id: Optional[int] = Field(default=None)

    @field_validator("node_type")
    @classmethod
    def _validate_node_type(cls, value: str) -> str:
        """约束 node_type 枚举（与 DB CHECK 对齐）。"""
        if value not in ("folder", "server"):
            raise ValueError("node_type 必须是 'folder' 或 'server'")
        return value


class UpdateNodeRequest(BaseModel):
    """更新节点请求体，未传字段保持原值。

    Attributes:
        name: 新名称。
        parent_id: 新父节点 ID。
        sort_order: 新排序权重。
    """

    name: Optional[str] = Field(default=None, max_length=255)
    parent_id: Optional[int] = Field(default=None)
    sort_order: Optional[int] = Field(default=None)


class ImportServersRequest(BaseModel):
    """批量导入 devops_servers 节点请求体。

    Attributes:
        parent_id: 父 folder ID；None 表示根。
        business_names: 要导入的 devops_servers.business_name 列表。
    """

    parent_id: Optional[int] = Field(default=None)
    business_names: List[str] = Field(default_factory=list)

    @field_validator("business_names")
    @classmethod
    def _validate_business_names(cls, value: List[str]) -> List[str]:
        """过滤空白字符串，保持原顺序。"""
        return [v.strip() for v in value if v and v.strip()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_service(request: Request) -> UserServerService:
    """从 app.state 获取 UserServerService。

    参数:
        request: FastAPI Request 对象。

    返回:
        UserServerService: 用户服务器配置服务实例。

    异常:
        HTTPException: 服务未初始化时抛出 500。
    """
    service = getattr(request.app.state, "user_server_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="UserServerService not initialized",
        )
    return service


def _handle_service_error(exc: Exception) -> None:
    """将 service 异常转换为 HTTPException。

    参数:
        exc: service 层异常。

    返回:
        None。

    异常:
        HTTPException: UserServerNodeNotFoundError → 404；ValueError → 400；
        UserServerNodeNotEmptyError → 400；其他向上抛。
    """
    if isinstance(exc, (UserServerNodeNotFoundError, LookupError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    if isinstance(exc, (UserServerNodeNotEmptyError, ValueError)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    raise exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/tree",
    response_model=Dict[str, Any],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.server-management"))
    ],
)
async def get_tree(request: Request) -> Dict[str, Any]:
    """获取节点树平铺列表（按当前用户归属过滤）。

    参数:
        request: FastAPI Request 对象。

    返回:
        Dict[str, Any]: {"nodes": [...]}，前端自行组树。
    """
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    nodes = service.list_nodes(scope)
    return {"nodes": nodes}


@router.post(
    "/nodes",
    status_code=status.HTTP_201_CREATED,
    response_model=Dict[str, Any],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.server-management"))
    ],
)
async def create_node(
    request: Request, body: CreateNodeRequest
) -> Dict[str, Any]:
    """创建节点（folder / server）。

    server 节点必须传 ``source_devops_server_id``，folder 节点必须为 None。

    参数:
        request: FastAPI Request 对象。
        body: 创建请求体。

    返回:
        Dict[str, Any]: 新建节点对象。
    """
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    try:
        return await service.create_node(
            body.parent_id,
            body.node_type,
            body.name,
            scope,
            source_devops_server_id=body.source_devops_server_id,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.put(
    "/nodes/{node_id}",
    response_model=Dict[str, Any],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.server-management"))
    ],
)
async def update_node(
    request: Request,
    node_id: int,
    body: UpdateNodeRequest,
) -> Dict[str, Any]:
    """更新节点名称 / 父节点 / 排序权重。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。
        body: 更新请求体。

    返回:
        Dict[str, Any]: 更新后的节点对象。
    """
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    try:
        return await service.update_node(
            node_id,
            scope,
            name=body.name,
            parent_id=body.parent_id,
            sort_order=body.sort_order,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.delete(
    "/nodes/{node_id}",
    response_model=Dict[str, Any],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.server-management"))
    ],
)
async def delete_node(request: Request, node_id: int) -> Dict[str, Any]:
    """删除节点；folder 非空时 400。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。

    返回:
        Dict[str, Any]: {"ok": true}。
    """
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    try:
        await service.delete_node(node_id, scope)
        return {"ok": True}
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.get(
    "/nodes/{node_id}/config",
    response_model=Dict[str, Any],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.server-management"))
    ],
)
async def get_node_config(request: Request, node_id: int) -> Dict[str, Any]:
    """获取节点详情。

    folder 节点：仅返回节点元数据。
    server 节点：额外 JOIN devops_servers 取白名单 + 巡检脚本字段（与
    「服务器扫描入库」详情端点同口径，绝不返回 ip/port/账号/密码）。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。

    返回:
        Dict[str, Any]: 节点详情字典。
    """
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    try:
        return await service.get_node_config(node_id, scope)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.post(
    "/import",
    response_model=Dict[str, Any],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.server-management"))
    ],
)
async def import_servers(
    request: Request, body: ImportServersRequest
) -> Dict[str, Any]:
    """批量把 devops_servers 导入到用户私有 tree。

    参数:
        request: FastAPI Request 对象。
        body: 导入请求体（parent_id + business_names）。

    返回:
        Dict[str, Any]: ``{"imported": int, "skipped": int, "failed": int, "node_ids": [int]}``
    """
    service = _get_service(request)
    scope = OwnershipScope.from_request(request)
    try:
        return await service.import_from_devops_servers(
            body.parent_id, body.business_names, scope
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise
