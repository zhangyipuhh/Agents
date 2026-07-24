#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent Permission Admin Router 模块

提供用户智能体访问权限管理接口（admin 权限）：
- GET    /api/admin/permissions/agents/catalog        全部可选智能体列表
- GET    /api/admin/permissions/agents/users/{id}/grants    查某用户已授权智能体
- PUT    /api/admin/permissions/agents/users/{id}/grants    全量覆盖保存

所有路由均通过 require_admin 鉴权（Depends 注入，router 级别）。
service 实例从 request.app.state.agent_permission_service 获取，
生产对等初始化点：app/core/server.py lifespan 中
`app.state.agent_permission_service = AgentPermissionService(...)`。

完全 mirror menu_permission_router.py 的实现模式。

Date: 2026-07-24
Author: AI Assistant
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.auth.Safety import require_admin


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/permissions/agents",
    tags=["Agent Permission Admin"],
    dependencies=[Depends(require_admin)],
)


# === Pydantic 模型 ===


class AgentItem(BaseModel):
    """智能体摘要（用于 catalog 响应）。"""

    name: str
    display_name: str = ""


class AgentCatalogResponse(BaseModel):
    """智能体目录响应。"""

    items: List[AgentItem]


class UserAgentGrantsResponse(BaseModel):
    """用户智能体授权响应。"""

    agent_names: List[str] = Field(default_factory=list)


class UserAgentGrantsUpdateRequest(BaseModel):
    """全量覆盖保存请求体。"""

    agent_names: List[str] = Field(default_factory=list)


# === 工具函数 ===


def _get_service(request: Request):
    """从 app.state 取 AgentPermissionService；不存在返 500。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.agent_permission_service = AgentPermissionService(...)`。
    DB 不可用时 lifespan 仍会初始化 db=None 实例，保证属性存在。

    参数:
        request: FastAPI Request 对象

    返回:
        AgentPermissionService: 服务实例

    异常:
        HTTPException 500: 服务未初始化
    """
    service = getattr(request.app.state, "agent_permission_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="agent_permission_service 未初始化",
        )
    return service


def _get_agent_config_service(request: Request):
    """从 app.state 取 AgentConfigService；不存在返 500。"""
    service = getattr(request.app.state, "agent_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="agent_config_service 未初始化",
        )
    return service


# === 路由端点 ===


@router.get("/catalog", response_model=AgentCatalogResponse)
async def get_agent_catalog(request: Request) -> AgentCatalogResponse:
    """返全量可选智能体列表（含未启用项，admin 配权限时用）。

    参数:
        request: FastAPI Request 对象

    返回:
        AgentCatalogResponse: items 是 AgentItem 列表（name + display_name）

    异常:
        HTTPException 500: agent_config_service 未初始化
    """
    service = _get_agent_config_service(request)
    agents = await service.list_all_agents_admin()
    items = [
        AgentItem(
            name=str(a.get("name", "")),
            display_name=str(a.get("display_name", "")),
        )
        for a in agents
        if a.get("name")
    ]
    return AgentCatalogResponse(items=items)


@router.get("/users/{user_id}/grants", response_model=UserAgentGrantsResponse)
async def get_user_agent_grants(user_id: int, request: Request) -> UserAgentGrantsResponse:
    """查某用户已授权智能体 name 列表。

    参数:
        user_id: 用户 ID（URL path）
        request: FastAPI Request 对象

    返回:
        UserAgentGrantsResponse: agent_names 升序数组

    异常:
        HTTPException 500: 服务未初始化
    """
    service = _get_service(request)
    granted = await service.get_user_agent_grants(user_id)
    return UserAgentGrantsResponse(agent_names=sorted(granted))


@router.put("/users/{user_id}/grants", response_model=UserAgentGrantsResponse)
async def put_user_agent_grants(
    user_id: int,
    body: UserAgentGrantsUpdateRequest,
    request: Request,
) -> UserAgentGrantsResponse:
    """全量覆盖某用户的智能体授权。

    调用 service.replace(user_id, set(agent_names), operator_id=request.state.user_id)，
    先清空 DB 旧行再批量写新行，最后同步内存缓存。

    参数:
        user_id: 目标用户 ID（URL path）
        body: {agent_names: [...]}
        request: FastAPI Request 对象

    返回:
        UserAgentGrantsResponse: 保存后的 agent_names（升序）

    异常:
        HTTPException 500: 服务未初始化或 DB 写入失败
    """
    service = _get_service(request)
    operator_id = getattr(request.state, "user_id", None)
    try:
        await service.replace(user_id, set(body.agent_names), operator_id=operator_id)
    except Exception as exc:
        logger.exception("保存智能体授权失败: user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存失败: {exc}",
        )
    granted = await service.get_user_agent_grants(user_id)
    return UserAgentGrantsResponse(agent_names=sorted(granted))
