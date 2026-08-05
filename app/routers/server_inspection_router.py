#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ServerInspectionRouter - 服务器采集落库与运维控制台看板 API（2026-08-05 新增）。

提供 ``/api/admin/server-inspection`` 下的：
    * ``GET  /latest``        —— 每台可见服务器的最新采集快照（运维控制台首页）
    * ``GET  /records``       —— 单台服务器的历史采集记录
    * ``POST /collect``       —— 手动触发采集 + 落库（合成 ScriptContext 走与定时任务相同的 run_server_ops + save 链路）

权限矩阵（与 ``user_server_router`` / ``devops_server_admin_router`` 对齐）：
    * ``GET /latest`` / ``GET /records`` / ``POST /collect`` 全部受
      ``require_admin_or_menu_acl('task-scheduler.server-management')`` 守卫；
    * 数据层可见性由 ``ServerInspectionRecordService.resolve_collect_targets``
      按 ``OwnershipScope`` 过滤：admin / system 透传全量，普通用户仅可
      采集自己 ``user_server_nodes`` 中可见的服务器。

服务依赖（来自 lifespan 初始化，``app.state``）：
    * ``server_inspection_record_service`` —— 三个端点都依赖；
    * ``devops_server_service`` —— ``POST /collect`` 合成 ScriptContext 时
      注入 ``context.devops_server_service``，供 ``run_server_ops`` 读取
      连接配置（SSH 凭据 / 巡检脚本原文）。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from app.scripts.base import ScriptContext
from app.scripts.server_ops import run_server_ops
from app.shared.utils.auth.Safety import require_admin_or_menu_acl
from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.server_inspection_record_service import (
    ServerInspectionNotFoundError,
    ServerInspectionPermissionError,
    ServerInspectionRecordService,
)


router = APIRouter(
    prefix="/api/admin/server-inspection",
    tags=["Server Inspection"],
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CollectRequest(BaseModel):
    """手动采集请求体。

    Attributes:
        server_ids: 待采集的 ``devops_servers.id`` 列表（1~50 项）。
    """

    server_ids: List[int] = Field(..., min_length=1, max_length=50)

    @field_validator("server_ids")
    @classmethod
    def _validate_server_ids(cls, value: List[int]) -> List[int]:
        """逐 id 校验为正整数。"""
        for index, sid in enumerate(value):
            if not isinstance(sid, int) or sid <= 0:
                raise ValueError(f"server_ids[{index}] 必须为正整数")
        return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_record_service(request: Request) -> ServerInspectionRecordService:
    """从 ``app.state`` 获取 ``ServerInspectionRecordService``。

    参数:
        request: FastAPI Request 对象。

    返回:
        ServerInspectionRecordService: 实例。

    异常:
        HTTPException: 服务未初始化时抛出 500（与其它 admin router 一致）。
    """
    service = getattr(request.app.state, "server_inspection_record_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ServerInspectionRecordService not initialized",
        )
    return service


def _get_devops_server_service(request: Request) -> Any:
    """从 ``app.state`` 获取 ``DevOpsServerService``（供 ``POST /collect`` 合成 context）。"""
    service = getattr(request.app.state, "devops_server_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DevOpsServerService not initialized",
        )
    return service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/latest")
async def get_latest(
    request: Request,
    _=Depends(require_admin_or_menu_acl("task-scheduler.server-management")),
) -> Dict[str, Any]:
    """返回每台可见服务器的最新采集快照（运维控制台首页数据源）。

    返回键白名单（不含 ``ip`` / ``port`` / ``password`` 等敏感字段）：
        ``node_id / node_name / server_id / business_name / server_type /
        status / inspection_status / collected_at / duration_ms /
        metrics / disks / parsed_values / error_message``

    每行 status 派生规则：
        * ``pass`` → ``ok``
        * ``warn`` / ``crit`` / ``success=False`` → ``err``
        * ``skipped`` / ``unassessed`` / 无快照 → ``unknown``

    admin / system 透传全量 devops_servers；普通用户按 ``user_server_nodes``
    可见集过滤（按 server_id 去重）。

    参数:
        request: FastAPI Request 对象（构造 ``OwnershipScope``）。

    返回:
        Dict[str, Any]: ``{"items": [...]}``。
    """
    service = _get_record_service(request)
    scope = OwnershipScope.from_request(request)
    items = await service.list_latest(scope)
    return {"items": items}


@router.get("/records")
async def get_records(
    request: Request,
    server_id: int = Query(..., gt=0),
    start: Optional[datetime] = Query(None, description="起始时间（含）"),
    end: Optional[datetime] = Query(None, description="截止时间（含）"),
    limit: int = Query(100, ge=1, le=1000),
    _=Depends(require_admin_or_menu_acl("task-scheduler.server-management")),
) -> Dict[str, Any]:
    """返回单台服务器的采集历史（按 ``collected_at DESC`` 排序）。

    可见性校验：admin / system → server 存在即可；普通用户 → server_id
    必须在自己 ``user_server_nodes`` 可见集内。越权 / 缺失统一 404，不回显 id。

    参数:
        request: FastAPI Request 对象。
        server_id: 必填，``devops_servers.id``。
        start: 起始时间（含）。
        end: 截止时间（含）。
        limit: 最大返回条数（1~1000，默认 100）。

    返回:
        Dict[str, Any]: ``{"items": [...]}``。

    异常:
        HTTPException: 404（越权 / 缺失），500（service 未初始化）。
    """
    service = _get_record_service(request)
    scope = OwnershipScope.from_request(request)
    try:
        records = await service.list_records(
            server_id, scope, start=start, end=end, limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        )
    if records is None:
        # 缺失/越权统一 404，不回显 server_id（与既有 router 风格一致）
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="服务器不存在或不可见",
        )
    return {"items": records}


@router.post("/collect")
async def collect(
    payload: CollectRequest,
    request: Request,
    _=Depends(require_admin_or_menu_acl("task-scheduler.server-management")),
) -> Dict[str, Any]:
    """手动触发采集 + 落库。

    流程：
        1. ``resolve_collect_targets`` 校验 ``server_ids`` 全部在
           ``OwnershipScope`` 可见集内（admin 全量放行；普通用户按
           ``user_server_nodes`` 过滤）；缺失 → 404、越权 → 403；
        2. 构造合成 ``ScriptContext``（``schedule_id=0, run_id=0,
           trigger_type='manual', devops_server_service=app.state.*``）
           → 复用 ``run_server_ops(context, server_list=business_names)``
           执行 SSH 采集；
        3. ``save_inspection_result(report, created_by_user_id=scope.user_id)``
           落库（schedule_id/run_id 均为 NULL）。

    入参:
        payload: ``CollectRequest{server_ids: [int...]}`。

    返回:
        Dict[str, Any]: ``{"collected": N, "items": [{server_id,
        business_name, success, inspection_status, duration_ms,
        error_message, field_results}]}``，供前端就地刷新 UI。
    """
    service = _get_record_service(request)
    devops_service = _get_devops_server_service(request)
    scope = OwnershipScope.from_request(request)

    # 1) 校验 + 解析 business_names
    try:
        business_names = service.resolve_collect_targets(
            list(payload.server_ids), scope,
        )
    except ServerInspectionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="采集目标不存在",
        )
    except ServerInspectionPermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="采集目标不属于当前用户",
        )

    # 2) 合成 ScriptContext，复用 run_server_ops
    synth_context = ScriptContext(
        schedule_id=0,
        run_id=0,
        session_id=f"manual-collect-{uuid.uuid4().hex[:8]}",
        schedule_name="manual-collect",
        script_args={"server_list": business_names},
        log_logger=logger,
        started_at=datetime.now(),
        trigger_type="manual",
        devops_server_service=devops_service,
        server_inspection_record_service=service,
    )

    # 3) 执行采集（fail-soft 包装：脚本执行本身的 ScriptExecutionError 仍向上抛）
    report = await run_server_ops(synth_context, server_list=business_names)

    # 4) 落库（schedule_id/run_id 留空，手动路径写入 created_by_user_id）
    saved = await service.save_inspection_result(
        report,
        created_by_user_id=scope.user_id,
    )

    items = []
    for srv in report.items:
        items.append({
            "server_id": _find_server_id(srv.business_name, business_names,
                                          devops_service),
            "business_name": srv.business_name,
            "success": srv.success,
            "inspection_status": srv.inspection_status,
            "duration_ms": srv.duration_ms,
            "error_message": srv.error_message or None,
            "field_results": srv.field_results,
        })
    return {"collected": saved, "items": items}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_server_id(
    business_name: str,
    business_names: List[str],
    devops_service: Any,
) -> Optional[int]:
    """通过 ``devops_server_service.list_public_servers`` 反查 server_id。

    仅在 ``POST /collect`` 响应组装时使用；service 未注入返回 ``None``。

    参数:
        business_name: ``devops_servers.business_name``。
        business_names: 本次采集的完整业务名列表（用于 service 异常时回退）。
        devops_service: ``DevOpsServerService`` 实例。

    返回:
        Optional[int]: ``server_id``；service 不可用返回 ``None``。
    """
    if devops_service is None:
        return None
    try:
        for row in devops_service.list_public_servers() or []:
            if row.get("business_name") == business_name:
                return row.get("id")
    except Exception:
        return None
    return None