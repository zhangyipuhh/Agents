# -*- coding:utf-8 -*-
"""system_settings_admin_router 系统基本设置管理路由

端点:
- GET    /api/admin/system-settings              列出所有组(脱敏)
- GET    /api/admin/system-settings/{group}      读单组(脱敏)
- PUT    /api/admin/system-settings/{group}      更新单组(校验+加密+落库+审计)
- POST   /api/admin/system-settings/{group}/reset 重置单组为 default

权限: require_admin_or_menu_acl('system.basic-settings')
审计: LogService.emit
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.services.system_config_service import SystemConfigService
from app.shared.utils.auth.Safety import require_admin_or_menu_acl

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/system-settings",
    tags=["system-settings"],
)


class UpdateGroupRequest(BaseModel):
    """更新组请求"""
    config: Dict[str, Any] = Field(..., description="配置字段(部分)")


def _get_service(request: Request) -> SystemConfigService:
    """从 app.state 取 service"""
    svc = getattr(request.app.state, "system_config_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="SystemConfigService 未初始化")
    return svc


@router.get("")
async def list_groups(
    request: Request,
    _: Any = Depends(require_admin_or_menu_acl("system.basic-settings")),
    svc: SystemConfigService = Depends(_get_service),
):
    """列出所有组(脱敏)"""
    groups = await svc.list_groups()
    # 按 tab 分组
    by_tab: Dict[str, list] = {}
    for g in groups:
        by_tab.setdefault(g["tab"], []).append(g)
    return {"tabs": by_tab}


@router.get("/{group_key}")
async def get_group(
    group_key: str,
    request: Request,
    _: Any = Depends(require_admin_or_menu_acl("system.basic-settings")),
    svc: SystemConfigService = Depends(_get_service),
):
    """读单组(脱敏)"""
    try:
        return await svc.get_group(group_key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"组不存在: {group_key}")


@router.put("/{group_key}")
async def update_group(
    group_key: str,
    body: UpdateGroupRequest,
    request: Request,
    _: Any = Depends(require_admin_or_menu_acl("system.basic-settings")),
    svc: SystemConfigService = Depends(_get_service),
):
    """更新单组"""
    operator = getattr(request.state, "username", "unknown")
    try:
        return await svc.update_group(group_key, body.config, operator=operator)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"组不存在: {group_key}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{group_key}/reset")
async def reset_group(
    group_key: str,
    request: Request,
    _: Any = Depends(require_admin_or_menu_acl("system.basic-settings")),
    svc: SystemConfigService = Depends(_get_service),
):
    """重置单组为 default"""
    operator = getattr(request.state, "username", "unknown")
    try:
        return await svc.reset_group(group_key, operator=operator)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"组不存在: {group_key}")
