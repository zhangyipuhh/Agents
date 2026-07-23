#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Menu Permission Admin Router 模块

提供菜单权限管理接口（admin 权限）：
- GET    /api/admin/permissions/menu-catalog         全量菜单注册表
- GET    /api/admin/permissions/users/{id}/grants    查某用户已授权菜单
- PUT    /api/admin/permissions/users/{id}/grants    全量覆盖保存

所有路由均通过 require_admin 鉴权（Depends 注入，router 级别）。
service 实例从 request.app.state.menu_permission_service 获取，
生产对等初始化点：app/core/server.py lifespan 中
`app.state.menu_permission_service = MenuPermissionService(...)`。

详见 docs/superpowers/specs/2026-07-23-menu-permission-design.md § 5

Date: 2026-07-23
Author: AI Assistant
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.menu_registry import MenuItem, get_full_catalog
from app.shared.utils.auth.Safety import require_admin


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/permissions",
    tags=["Menu Permission Admin"],
    dependencies=[Depends(require_admin)],
)


# === Pydantic 模型 ===


class MenuCatalogResponse(BaseModel):
    """菜单注册表响应。"""

    items: List[MenuItem]


class UserGrantsResponse(BaseModel):
    """用户菜单授权响应。"""

    menu_ids: List[str] = Field(default_factory=list)


class UserGrantsUpdateRequest(BaseModel):
    """全量覆盖保存请求体。"""

    menu_ids: List[str] = Field(default_factory=list)


# === 工具函数 ===


def _get_service(request: Request):
    """从 app.state 取 MenuPermissionService；不存在返 500。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.menu_permission_service = MenuPermissionService(...)`。
    DB 不可用时 lifespan 仍会初始化 db=None 实例，保证属性存在。

    参数:
        request: FastAPI Request 对象

    返回:
        MenuPermissionService: 服务实例

    异常:
        HTTPException 500: 服务未初始化
    """
    service = getattr(request.app.state, "menu_permission_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="menu_permission_service 未初始化",
        )
    return service


# === 路由端点 ===


@router.get("/menu-catalog", response_model=MenuCatalogResponse)
async def get_menu_catalog() -> MenuCatalogResponse:
    """返全量菜单注册表（含 enabled=False 项，admin 配权限时用）。

    详见 docs/superpowers/specs/2026-07-23-menu-permission-design.md § 5

    返回:
        MenuCatalogResponse: items 是 MenuItem 列表
    """
    items = get_full_catalog()
    return MenuCatalogResponse(items=items)


@router.get("/users/{user_id}/grants", response_model=UserGrantsResponse)
async def get_user_grants(user_id: int, request: Request) -> UserGrantsResponse:
    """查某用户已授权菜单 id 列表。

    参数:
        user_id: 用户 ID（URL path）
        request: FastAPI Request 对象

    返回:
        UserGrantsResponse: menu_ids 升序数组

    异常:
        HTTPException 500: 服务未初始化
    """
    service = _get_service(request)
    granted = await service.get_user_grants(user_id)
    return UserGrantsResponse(menu_ids=sorted(granted))


@router.put("/users/{user_id}/grants", response_model=UserGrantsResponse)
async def put_user_grants(
    user_id: int,
    body: UserGrantsUpdateRequest,
    request: Request,
) -> UserGrantsResponse:
    """全量覆盖某用户的菜单授权。

    调用 service.replace(user_id, set(menu_ids), operator_id=request.state.user_id)，
    先清空 DB 旧行再批量写新行，最后同步内存缓存。

    参数:
        user_id: 目标用户 ID（URL path）
        body: {menu_ids: [...]}
        request: FastAPI Request 对象

    返回:
        UserGrantsResponse: 保存后的 menu_ids（升序）

    异常:
        HTTPException 500: 服务未初始化或 DB 写入失败
    """
    service = _get_service(request)
    operator_id = getattr(request.state, "user_id", None)
    try:
        await service.replace(user_id, set(body.menu_ids), operator_id=operator_id)
    except Exception as exc:
        logger.exception("保存菜单授权失败: user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存失败: {exc}",
        )
    granted = await service.get_user_grants(user_id)
    return UserGrantsResponse(menu_ids=sorted(granted))