#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOps Server Admin Router（2026-07-15 新增）

职责：
    - 提供 DevOpsServerService 的管理接口（admin 权限）
    - 严格只对外暴露白名单字段（不允许 password / ip / 名单 等敏感值外泄）
    - 扫描异常统一返回通用错误，不回显原始错误细节

端点：
    - GET    /api/admin/devops-servers
          列出已配置服务器（严格只含 id / business_name / server_type / updated_at）
    - POST   /api/admin/devops-servers/scan
          触发 ``DevOpsServerService.scan_and_upsert()``，
          响应严格只含 scanned / inserted / updated / failed 4 个数字
    - DELETE /api/admin/devops-servers/{server_id}
          按 server_id 删除一行；返 204 No Content；
          不存在 → 404 + "服务器不存在"；服务未初始化 → 500 + lifespan hint

依赖：
    - service 实例从 ``request.app.state.devops_server_service`` 获取；
      生产对等初始化点：``app/core/server.py::lifespan`` 数据库池建立后
      ``app.state.devops_server_service = DevOpsServerService(...)``。
    - service 方法依赖：``list_public_servers`` / ``scan_and_upsert`` /
      ``server_exists`` / ``delete_server``
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

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

    缺失时优先返回 lifespan 缓存的可执行 hint（区分 missing / misspelled /
    invalid_fernet 三类），无 hint 时退回通用文案，便于运维一眼定位配置问题。

    Args:
        request: FastAPI Request 对象

    Returns:
        DevOpsServerService: 实例

    Raises:
        HTTPException: 服务未初始化时抛出 500，detail 含 lifespan 写入的 hint
    """
    svc = getattr(request.app.state, "devops_server_service", None)
    if svc is None:
        hint = getattr(request.app.state, "devops_server_service_hint", None)
        detail = hint or "DevOpsServerService not initialized"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
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


@router.delete(
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_devops_server(request: Request, server_id: int) -> Response:
    """按 ``server_id`` 删除一行 devops_servers。

    行为：
        - 服务未初始化 → 500 + lifespan hint（与 GET / scan 一致）
        - server_id 在 DB 中不存在 → 404 + 通用 detail「服务器不存在」（不回显 server_id）
        - DB 执行异常 → 500 + 通用 detail「删除服务器失败」（不回显 SQL / 原 detail）
        - 成功 → 204 No Content，无响应体

    Args:
        request: FastAPI Request
        server_id: devops_servers 主键 id（path int）

    Returns:
        Response: 204 空响应

    Raises:
        HTTPException: 404（不存在）/ 500（服务缺失或 DB 异常）
    """
    svc = _get_service(request)
    try:
        # 1) 探测行是否存在（避免 service 层抛 HTTPException，保持职责单一）
        exists = await svc.server_exists(server_id)
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="服务器不存在",
            )
        # 2) 调用 service 层删除（持锁：cache + DB 同步）
        await svc.delete_server(server_id)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - 异常路径不暴露细节
        logger.exception(
            "[devops_server_admin_router] delete_server(%s) failed", server_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除服务器失败",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
