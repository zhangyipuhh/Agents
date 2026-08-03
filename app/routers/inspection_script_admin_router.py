#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
InspectionScriptAdminRouter（2026-08-03 新增）

职责：
    - 提供 InspectionScriptService 的管理接口（admin 权限）
    - 列表端点严格白名单返回（不暴露脚本原文）
    - 详情端点按需返回完整脚本内容（含 inspection_script / inspection_fields）
    - 扫描异常统一返回通用错误，不回显原始错误细节

端点：
    - GET    /api/admin/inspection-scripts
              列出已注册脚本（白名单字段：id / name / display_name /
              platform / version / inspection_parser / updated_at）。
              权限：admin OR ``task-scheduler.server-management`` ACL。
    - POST   /api/admin/inspection-scripts/scan
              触发 ``InspectionScriptService.scan_and_upsert()``，
              响应严格只含 scanned / inserted / updated / failed 4 个数字。
              权限：admin only。
    - GET    /api/admin/inspection-scripts/{script_id}
              取完整脚本详情（含 inspection_script 与 inspection_fields）。
              权限：admin only。

依赖：
    - service 实例从 ``request.app.state.inspection_script_service`` 获取；
      生产对等初始化点：``app/core/server.py::lifespan`` 数据库池建立后
      ``app.state.inspection_script_service = InspectionScriptService(...)``。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.auth.Safety import (
    require_admin,
    require_admin_or_menu_acl,
)


logger = logging.getLogger(__name__)


# 列表白名单（严格只含以下字段，不暴露脚本原文）
_LIST_FIELDS = (
    "id",
    "name",
    "display_name",
    "platform",
    "version",
    "inspection_parser",
    "updated_at",
)
# 扫描结果白名单（5 个数字；2026-08-04 编辑优先新增 skipped）
_SCAN_FIELDS = ("scanned", "inserted", "updated", "failed", "skipped")


class UpdateInspectionScriptRequest(BaseModel):
    """更新巡检脚本库条目请求体（2026-08-04 新增，admin only）。

    name 字段不在请求体内（主键语义）；其余业务字段均与 _DETAIL_FIELDS 对齐。
    """

    display_name: str = Field(..., min_length=1, max_length=200)
    platform: str = Field("linux", pattern="^(linux|windows)$")
    version: str = Field("", max_length=32)
    inspection_parser: str = Field("json", pattern="^(json|kv|csv|raw)$")
    inspection_script: Optional[str] = None
    inspection_fields: List[Dict[str, Any]] = Field(default_factory=list)


router = APIRouter(
    prefix="/api/admin/inspection-scripts",
    tags=["Inspection Script Admin"],
)


def _get_service(request: Request):
    """从 ``app.state`` 取 ``InspectionScriptService``，缺失时 500。

    Args:
        request: FastAPI Request 对象

    Returns:
        InspectionScriptService: 实例

    Raises:
        HTTPException: 服务未初始化时抛出 500
    """
    svc = getattr(request.app.state, "inspection_script_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="InspectionScriptService not initialized",
        )
    return svc


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.inspection-script-library"))
    ],
)
async def list_inspection_scripts(request: Request) -> List[Dict[str, Any]]:
    """列出已注册脚本，严格只返回白名单字段（不暴露脚本原文）。

    Args:
        request: FastAPI Request

    Returns:
        List[Dict[str, Any]]: 公开字段列表，每项仅含白名单键
    """
    svc = _get_service(request)
    raw = svc.list_scripts()
    safe: List[Dict[str, Any]] = []
    for item in raw:
        # 严格白名单过滤：避免 service 上层失误导致 inspection_script 原文外泄
        safe.append({k: item.get(k) for k in _LIST_FIELDS})
    return safe


@router.post(
    "/scan",
    response_model=Dict[str, int],
    dependencies=[Depends(require_admin)],
)
async def scan_inspection_scripts(request: Request) -> Dict[str, int]:
    """触发一次 YAML → DB → cache 的扫描与 upsert。

    返回结构严格只含 ``scanned / inserted / updated / failed`` 4 个数字。
    异常处理：service.scan_and_upsert 抛异常时统一返回 500 + 通用错误，
    不回显原始 detail / 异常路径等敏感信息。

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
            "[inspection_script_admin_router] scan_and_upsert failed"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="inspection script scan failed",
        )

    # 服务侧已保证返回 4 字段；此处再做一次白名单过滤防御
    return {k: int(raw.get(k, 0) or 0) for k in _SCAN_FIELDS}


@router.get(
    "/{script_id}",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_admin)],
)
async def get_inspection_script(request: Request, script_id: int) -> Dict[str, Any]:
    """按 ``script_id`` 取完整脚本详情（含 inspection_script / inspection_fields）。

    行为：
        - 服务未初始化 → 500
        - script_id 在 DB 中不存在 → 404 + 通用 detail「脚本不存在」（不回显 script_id）
        - 成功 → 200 + JSON

    Args:
        request: FastAPI Request
        script_id: inspection_scripts 主键 id（path int）

    Returns:
        Dict[str, Any]: 完整脚本详情

    Raises:
        HTTPException: 404（不存在）/ 500（服务缺失）
    """
    svc = _get_service(request)
    detail = svc.get_script_detail(script_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="脚本不存在",
        )
    return detail


@router.put(
    "/{script_id}",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_admin)],
)
async def update_inspection_script(
    request: Request,
    script_id: int,
    req: UpdateInspectionScriptRequest,
) -> Dict[str, Any]:
    """按 ``script_id`` 更新脚本详情（2026-08-04 新增，admin only）。

    行为：
        - 服务未初始化 → 500
        - 请求体非法 → 422
        - script_id 不存在 → 404 + 通用 detail「脚本不存在」（不回显 script_id）
        - 成功 → 200 + 更新后的完整 JSON

    Args:
        request: FastAPI Request
        script_id: inspection_scripts 主键 id（path int）
        req: 更新请求体（Pydantic 校验）

    Returns:
        Dict[str, Any]: 更新后的完整记录（_DETAIL_FIELDS 字段）

    Raises:
        HTTPException: 404 / 422 / 500
    """
    svc = _get_service(request)
    record = svc.update_script_detail(script_id, req.model_dump())
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="脚本不存在",
        )
    return record