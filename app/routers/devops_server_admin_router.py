#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOps Server Admin Router（2026-07-15 新增）

职责：
    - 提供 DevOpsServerService 的管理接口（admin 权限）
    - 严格只对外暴露白名单字段（不允许 password / ip / 名单 等敏感值外泄）
    - 扫描异常统一返回通用错误，不回显原始错误细节

端点：
    - GET  /api/admin/devops-servers
          列出已配置服务器（严格只含 id / business_name / server_type / updated_at）
    - POST /api/admin/devops-servers/scan
          触发 ``DevOpsServerService.scan_and_upsert()``，
          响应严格只含 scanned / inserted / updated / failed 4 个数字

依赖：
    - service 实例从 ``request.app.state.devops_server_service`` 获取；
      生产对等初始化点：``app/core/server.py::lifespan`` 数据库池建立后
      ``app.state.devops_server_service = DevOpsServerService(...)``。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.shared.utils.auth.Safety import require_admin
from app.shared.utils.devops_server_service import DevOpsServerService


logger = logging.getLogger(__name__)


# 公开字段白名单（严格只含以下字段）
_PUBLIC_FIELDS = ("id", "business_name", "server_type", "updated_at")
# 扫描结果白名单（4 个数字）
_SCAN_FIELDS = ("scanned", "inserted", "updated", "failed")


router = APIRouter(
    prefix="/api/admin/devops-servers",
    tags=["DevOps Server Admin"],
    dependencies=[Depends(require_admin)],
)


def _get_service(request: Request) -> DevOpsServerService:
    """从 ``app.state`` 取 ``DevOpsServerService``，缺失时 500。

    Args:
        request: FastAPI Request 对象

    Returns:
        DevOpsServerService: 实例

    Raises:
        HTTPException: 服务未初始化时抛出 500
    """
    svc = getattr(request.app.state, "devops_server_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DevOpsServerService not initialized",
        )
    return svc


@router.get("", response_model=List[Dict[str, Any]])
async def list_devops_servers(request: Request) -> List[Dict[str, Any]]:
    """列出已配置的服务器，严格只返回白名单字段。

    即使 service ``list_public_servers`` 内部失误返回了多余字段，
    本 router 也会再次过滤成白名单 4 字段（防御性二次过滤）。

    Args:
        request: FastAPI Request

    Returns:
        List[Dict[str, Any]]: 公开字段列表，每项仅含白名单键
    """
    svc = _get_service(request)
    raw = svc.list_public_servers()
    safe: List[Dict[str, Any]] = []
    for item in raw:
        # 严格白名单过滤：避免 service 上层失误导致敏感字段外泄
        safe.append({k: item.get(k) for k in _PUBLIC_FIELDS})
    return safe


@router.post("/scan", response_model=Dict[str, int])
async def scan_devops_servers(request: Request) -> Dict[str, int]:
    """触发一次 YAML → DB → cache 的扫描与 upsert。

    返回结构严格只含 ``scanned / inserted / updated / failed`` 4 个数字，
    即使 service 失误返回了其他字段，本 router 也会过滤成 4 字段。

    异常处理：service.scan_and_upsert 抛异常时，统一返回 500 + 通用错误，
    不回显原始 detail / 异常路径 / 密码 / 名单等敏感信息。

    Args:
        request: FastAPI Request

    Returns:
        Dict[str, int]: 扫描结果（4 个整数键）
    """
    svc = _get_service(request)
    try:
        raw = await svc.scan_and_upsert()
    except Exception:  # noqa: BLE001 - 异常路径不暴露细节
        logger.exception(
            "[devops_server_admin_router] scan_and_upsert failed"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="devops server scan failed",
        )

    # 服务侧已经保证返回 4 字段；此处再做一次白名单过滤防御。
    return {k: int(raw.get(k, 0) or 0) for k in _SCAN_FIELDS}
