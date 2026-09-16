#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
InspectionScriptAdminRouter(2026-08-03 新增;2026-09-16 重构)

职责:
    - 提供 InspectionScriptService 的管理接口(admin 权限)
    - 列表端点严格白名单返回(不暴露脚本原文)
    - 详情端点按需返回完整脚本内容(含 inspection_script / inspection_fields)
    - 2026-09-16 新增:分段 CRUD(inspection_script_segments)端点;
      YAML 扫描链路(`/scan`)整体移除,默认脚本通过 lifespan 播种。

端点:
    - GET    /api/admin/inspection-scripts
              列出已注册脚本(白名单字段:id / name / display_name /
              platform / version / inspection_parser / updated_at)。
              权限:admin OR ``task-scheduler.server-management`` ACL。
    - GET    /api/admin/inspection-scripts/{script_id}
              取完整脚本详情(含 inspection_script 与 inspection_fields),
              含 ``segments`` 键(全部分段白名单字段)。
              权限:admin only。
    - PUT    /api/admin/inspection-scripts/{script_id}
              更新组级字段。权限:admin only。
    - DELETE /api/admin/inspection-scripts/{script_id}
              删除脚本(显式事务内清理 segments + 服务器解绑)。权限:admin only。
    - GET    /api/admin/inspection-scripts/{script_id}/segments
              列出组的全部分段(含 disabled)。权限:admin only。
    - POST   /api/admin/inspection-scripts/{script_id}/segments
              创建分段(upsert via segment_key)。权限:admin only。
    - PUT    /api/admin/inspection-scripts/{script_id}/segments/{segment_id}
              更新分段。权限:admin only。
    - DELETE /api/admin/inspection-scripts/{script_id}/segments/{segment_id}
              删除分段。权限:admin only。

依赖:
    - service 实例从 ``request.app.state.inspection_script_service`` 获取;
      生产对等初始化点:``app/core/server.py::lifespan`` 数据库池建立后
      ``app.state.inspection_script_service = InspectionScriptService(...)``。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.shared.utils.auth.Safety import (
    require_admin,
    require_admin_or_menu_acl,
)
from app.shared.utils.log_service import (
    LogEvent,
    LogLevel,
    LogResult,
    LogType,
    get_log_service,
)


logger = logging.getLogger(__name__)


# 列表白名单(严格只含以下字段,不暴露脚本原文)
_LIST_FIELDS = (
    "id",
    "name",
    "display_name",
    "platform",
    "version",
    "inspection_parser",
    "updated_at",
)


class UpdateInspectionScriptRequest(BaseModel):
    """更新巡检脚本库条目请求体(admin only)。

    name 字段不在请求体内(主键语义);其余业务字段均与 _DETAIL_FIELDS 对齐。
    """

    display_name: str = Field(..., min_length=1, max_length=200)
    platform: str = Field("linux", pattern="^(linux|windows)$")
    version: str = Field("", max_length=32)
    inspection_parser: str = Field("json", pattern="^(json|kv|csv|raw)$")
    inspection_script: str | None = None
    inspection_fields: List[Dict[str, Any]] = Field(default_factory=list)


class UpsertSegmentRequest(BaseModel):
    """分段创建/更新请求体(2026-09-16 新增,admin only)。

    segment_key 须匹配 ``^[a-z0-9][a-z0-9_-]{0,63}$``(service 内校验);
    script 必填且非空。sort_order 必须为非负整数(默认 0)。
    """

    segment_key: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field("", max_length=200)
    sort_order: int = Field(0, ge=0)
    script: str = Field(..., min_length=1)
    enabled: bool = True


router = APIRouter(
    prefix="/api/admin/inspection-scripts",
    tags=["Inspection Script Admin"],
)


def _get_service(request: Request):
    """从 ``app.state`` 取 ``InspectionScriptService``,缺失时 500。

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


def _emit_segment_audit(
    request: Request,
    action: str,
    target_name: str,
    message: str,
) -> None:
    """写分段变更审计日志(fail-soft;模式对齐 mcp_admin_router._emit_mcp_audit)。

    参数:
        request: FastAPI Request(取操作人 user_id/username/IP)
        action: inspection_segment_create / update / delete
        target_name: 形如 ``<script_id>/<segment_key>``
        message: 业务描述(不含脚本原文)

    返回:
        None
    """
    svc = get_log_service()
    if svc is None:
        return
    client_ip = request.client.host if request.client else "unknown"
    event = LogEvent(
        action=action,
        log_type=LogType.SYSTEM,
        result=LogResult.SUCCESS,
        level=LogLevel.INFO,
        source="inspection_script_admin_router",
        username=getattr(request.state, "username", "unknown"),
        user_id=getattr(request.state, "user_id", None),
        ip_address=client_ip,
        target_type="inspection_script_segment",
        target_name=target_name,
        message=message,
    )
    try:
        svc.emit(event)
    except Exception as exc:  # pragma: no cover - 防御性 fail-soft
        logger.warning(
            "[inspection_script_admin_router] emit audit failed: %s",
            type(exc).__name__,
        )


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    dependencies=[
        Depends(require_admin_or_menu_acl("task-scheduler.inspection-script-library"))
    ],
)
async def list_inspection_scripts(request: Request) -> List[Dict[str, Any]]:
    """列出已注册脚本,严格只返回白名单字段(不暴露脚本原文)。

    Args:
        request: FastAPI Request

    Returns:
        List[Dict[str, Any]]: 公开字段列表,每项仅含白名单键
    """
    svc = _get_service(request)
    raw = svc.list_scripts()
    safe: List[Dict[str, Any]] = []
    for item in raw:
        # 严格白名单过滤:避免 service 上层失误导致 inspection_script 原文外泄
        safe.append({k: item.get(k) for k in _LIST_FIELDS})
    return safe


@router.get(
    "/{script_id}",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_admin)],
)
async def get_inspection_script(request: Request, script_id: int) -> Dict[str, Any]:
    """按 ``script_id`` 取完整脚本详情(含 inspection_script / inspection_fields / segments)。

    行为:
        - 服务未初始化 → 500
        - script_id 在 DB 中不存在 → 404 + 通用 detail「脚本不存在」(不回显 script_id)
        - 成功 → 200 + JSON

    Args:
        request: FastAPI Request
        script_id: inspection_scripts 主键 id(path int)

    Returns:
        Dict[str, Any]: 完整脚本详情(含 segments 字段)

    Raises:
        HTTPException: 404(不存在)/ 500(服务缺失)
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
    """按 ``script_id`` 更新脚本详情(admin only)。

    行为:
        - 服务未初始化 → 500
        - 请求体非法 → 422
        - script_id 不存在 → 404 + 通用 detail「脚本不存在」(不回显 script_id)
        - 组存在 enabled 分段且 parser 切到非 json → 404(2026-09-16 D3 防御)
        - 成功 → 200 + 更新后的完整 JSON

    Args:
        request: FastAPI Request
        script_id: inspection_scripts 主键 id(path int)
        req: 更新请求体(Pydantic 校验)

    Returns:
        Dict[str, Any]: 更新后的完整记录(_DETAIL_FIELDS 字段)

    Raises:
        HTTPException: 404 / 422 / 500
    """
    svc = _get_service(request)
    record = await svc.update_script_detail(script_id, req.model_dump())
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="脚本不存在",
        )
    return record


@router.delete(
    "/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_inspection_script(request: Request, script_id: int) -> Response:
    """按 ``script_id`` 删除脚本库条目(2026-09-16:事务内显式清理 segments)。

    行为:
        - 服务未初始化 → 500
        - script_id 不存在 / service 返回 False → 404 + 通用 detail「脚本不存在」
          (不回显 script_id)
        - 成功 → 204 No Content(无响应体)

    副作用:``devops_servers.inspection_script_id`` 外键 ON DELETE SET NULL;
    FK CASCADE 兜底 + 业务层 ``DELETE FROM inspection_script_segments WHERE
    script_id=$1`` 显式清理。

    Args:
        request: FastAPI Request
        script_id: inspection_scripts 主键 id(path int)

    Returns:
        Response: 204 No Content

    Raises:
        HTTPException: 404 / 500
    """
    svc = _get_service(request)
    deleted = await svc.delete_script(script_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="脚本不存在",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================================
# 2026-09-16 新增:分段 CRUD 端点(取代 /scan 链路)
# ============================================================================


@router.get(
    "/{script_id}/segments",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(require_admin)],
)
async def list_inspection_script_segments(
    request: Request, script_id: int,
) -> List[Dict[str, Any]]:
    """列出组的全部分段(含 disabled,按 sort_order 升序)。

    行为:
        - 服务未初始化 → 500
        - script_id 不存在 → 404「脚本不存在」
        - 成功 → 200 + 分段白名单列表

    参数:
        request: FastAPI Request
        script_id: inspection_scripts 主键 id

    返回:
        List[Dict[str, Any]]: 分段白名单列表

    异常:
        HTTPException: 404 / 500
    """
    svc = _get_service(request)
    segments = svc.list_segments(script_id)
    if segments is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="脚本不存在",
        )
    return segments


@router.post(
    "/{script_id}/segments",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_admin)],
)
async def create_inspection_script_segment(
    request: Request,
    script_id: int,
    req: UpsertSegmentRequest,
) -> Dict[str, Any]:
    """创建分段(若 segment_key 已存在则 upsert 覆盖);成功写审计。

    行为:
        - 请求体非法 → 422(Pydantic 校验)
        - script_id 不存在 → 404「脚本不存在」
        - service 抛 ValueError(组 parser != 'json' / segment_key 非法 /
          script 空白) → 400 + 原始消息(不含脚本原文)
        - 成功 → 200 + 分段白名单 dict + 审计 inspection_segment_create

    参数:
        request: FastAPI Request
        script_id: 所属组 id
        req: 创建请求体

    返回:
        Dict[str, Any]: 分段白名单 dict

    异常:
        HTTPException: 400 / 404 / 422 / 500
    """
    svc = _get_service(request)
    try:
        record = await svc.upsert_segment(script_id, req.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="脚本不存在",
        )
    _emit_segment_audit(
        request,
        "inspection_segment_create",
        f"{script_id}/{record.get('segment_key')}",
        "新增巡检分段",
    )
    return record


@router.put(
    "/{script_id}/segments/{segment_id}",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_admin)],
)
async def update_inspection_script_segment(
    request: Request,
    script_id: int,
    segment_id: int,
    req: UpsertSegmentRequest,
) -> Dict[str, Any]:
    """按 ``segment_id`` 更新分段;成功写审计。

    行为:
        - 请求体非法 → 422
        - 分段不存在 → 404「分段不存在」
        - service 抛 ValueError → 400
        - 成功 → 200 + 分段白名单 dict + 审计 inspection_segment_update

    参数:
        request: FastAPI Request
        script_id: 所属组 id
        segment_id: 分段 id
        req: 更新请求体

    返回:
        Dict[str, Any]: 分段白名单 dict

    异常:
        HTTPException: 400 / 404 / 422 / 500
    """
    svc = _get_service(request)
    try:
        record = await svc.upsert_segment(
            script_id, req.model_dump(), segment_id=segment_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分段不存在",
        )
    _emit_segment_audit(
        request,
        "inspection_segment_update",
        f"{script_id}/{record.get('segment_key')}",
        "更新巡检分段",
    )
    return record


@router.delete(
    "/{script_id}/segments/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_inspection_script_segment(
    request: Request,
    script_id: int,
    segment_id: int,
) -> Response:
    """按 ``segment_id`` 删除分段;成功写审计。

    行为:
        - 分段不存在 / service 返回 False → 404「分段不存在」
        - 成功 → 204 + 审计 inspection_segment_delete

    参数:
        request: FastAPI Request
        script_id: 所属组 id
        segment_id: 分段 id

    返回:
        Response: 204 No Content

    异常:
        HTTPException: 404 / 500
    """
    svc = _get_service(request)
    deleted = await svc.delete_segment(script_id, segment_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分段不存在",
        )
    _emit_segment_audit(
        request,
        "inspection_segment_delete",
        f"{script_id}/{segment_id}",
        "删除巡检分段",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
