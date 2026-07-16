#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
脚本管理 Admin Router 模块。

提供 /api/admin/scripts 下的脚本列表与扫描接口。
所有接口要求 admin 权限，服务实例由 app/core/server.py lifespan
初始化到 app.state.script_discovery_service。
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.shared.utils.auth.Safety import require_admin


router = APIRouter(
    prefix="/api/admin/scripts",
    tags=["Script Admin"],
    dependencies=[Depends(require_admin)],
)


# 白名单字段，防止未来 RegisteredScript 新增内部字段意外泄露
_PUBLIC_FIELDS = ("name", "display_name", "description", "params_schema", "module_path")
_SCAN_FIELDS = ("scanned", "registered", "failed")


def _get_service(request: Request):
    """从 app.state 获取 ScriptDiscoveryService。

    参数:
        request: FastAPI Request 对象。

    返回:
        ScriptDiscoveryService 实例。

    异常:
        HTTPException: 服务未初始化时抛出 500。
    """
    service = getattr(request.app.state, "script_discovery_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ScriptDiscoveryService not initialized",
        )
    return service


class ScanSummary(BaseModel):
    """脚本扫描结果摘要。

    Attributes:
        scanned: 扫描的 .py 文件总数。
        registered: registry 中的脚本总数。
        failed: 加载失败的文件数。
    """

    scanned: int
    registered: int
    failed: int


@router.get("", response_model=List[Dict[str, Any]])
async def list_scripts(request: Request) -> List[Dict[str, Any]]:
    """列出所有已注册脚本元数据。

    参数:
        request: FastAPI Request 对象。

    返回:
        List[Dict[str, Any]]: 脚本元数据列表（白名单字段）。
    """
    service = _get_service(request)
    raw = service.list_scripts()
    # 防御性白名单过滤，即使 list_scripts 未来加了字段也不会泄露
    return [{k: item.get(k) for k in _PUBLIC_FIELDS} for item in raw]


@router.post("/scan", response_model=ScanSummary)
async def scan_scripts(request: Request) -> ScanSummary:
    """触发脚本目录扫描。

    参数:
        request: FastAPI Request 对象。

    返回:
        ScanSummary: 三字段统计。

    异常:
        HTTPException: 扫描过程异常时返回 500。
    """
    service = _get_service(request)
    try:
        raw = await service.scan()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"scan failed: {type(exc).__name__}",
        )
    return ScanSummary(**{k: raw.get(k, 0) for k in _SCAN_FIELDS})
