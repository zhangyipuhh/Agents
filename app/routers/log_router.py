#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
``app/routers/log_router.py`` — 统一审计日志查询管理端路由（2026-07-29 新增）

职责：
    - 提供 admin 角色专用的「审计日志查询 / 详情」API
    - 严格白名单响应字段，不回显 password / token / IP / 用户名等敏感键原值
    - 服务缺失 → 503；权限不足 → 403；参数非法 → 422；记录不存在 → 404

端点：
    - GET /api/admin/logs
          支持 log_type / action / result / level / source / user_id / username /
          session_id / request_id / tool_call_id / correlation_id / target_type /
          target_id / target_name / created_from / created_to 过滤器；
          limit (1..200, default=50) / offset (>=0, default=0) 分页。
    - GET /api/admin/logs/{log_id}
          单条详情；存在 → 200 + JSON；不存在 → 404；
          若记录含 correlation_id,响应附带 ``related_logs``（同 cid 的其它日志）。

依赖：
    - ``request.app.state.log_service`` 必须挂有 ``LogService`` 实例；
      生产对等初始化点：``app/core/server.py::lifespan`` 中
      ``app.state.log_service = LogService(db_pool=DatabasePool._pool)``。
    - 单测可以走 ``LogService(memory_only=True)``（不需要 PostgreSQL）。

权限矩阵：
    - 全部端点 → ``Depends(require_admin)``（router 级守卫，非 admin 直接 403）

created_at 序列化约定：
    - 入库时 ``LogEvent.timestamp`` 是 naive UTC（``datetime.utcnow()`` 或
      ``_ensure_naive_utc`` 归一化）。
    - API 输出统一由 Pydantic 模型自动序列化为 ``"YYYY-MM-DDTHH:MM:SS[.ffffff]""
      naive ISO 字符串（无 tz 后缀，便于客户端按 UTC 解释）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.shared.utils.auth.Safety import require_admin
from app.shared.utils.log_service import LogService


router = APIRouter(
    prefix="/api/admin/logs",
    tags=["Audit Logs Admin"],
    dependencies=[Depends(require_admin)],
)


# 列表响应字段白名单：与 ``audit_logs`` 表 / ``LogService`` 内存行 schema 对齐。
_LIST_RESPONSE_FIELDS: tuple = (
    "id",
    "log_type",
    "result",
    "level",
    "source",
    "action",
    "message",
    "session_id",
    "request_id",
    "tool_call_id",
    "correlation_id",
    "target_type",
    "target_id",
    "target_name",
    "user_id",
    "username",
    "ip_address",
    "metadata",
    "created_at",
)


def _get_log_service(request: Request) -> LogService:
    """从 ``app.state.log_service`` 取 LogService 实例,缺失时抛 503。

    Args:
        request: FastAPI Request 对象。

    Returns:
        LogService: 真实服务实例。

    Raises:
        HTTPException: 服务未初始化时 503,detail 提示 lifespan 未启动。
    """
    svc = getattr(request.app.state, "log_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="log_service 未初始化（lifespan 未启动）",
        )
    return svc


def _project_response(row: Dict[str, Any]) -> Dict[str, Any]:
    """把 ``LogService`` 内存/DB 行投影到 ``_LIST_RESPONSE_FIELDS`` 白名单。

    防御性二次过滤：即使 LogService 失误返回了多余字段,router 也会锁回白名单。

    Args:
        row: ``LogService._memory_records`` / ``query_logs`` 元素。

    Returns:
        Dict[str, Any]: 仅含白名单键的字典。
    """
    return {k: row.get(k) for k in _LIST_RESPONSE_FIELDS}


@router.get(
    "",
    response_model=Dict[str, Any],
    summary="查询审计日志",
)
async def list_logs(
    request: Request,
    log_type: Optional[str] = Query(None, description="日志类型（auth/user/session/ssh/system）"),
    action: Optional[str] = Query(None, description="业务动作名"),
    result: Optional[str] = Query(None, description="结果（success/failure/blocked/pending/skipped）"),
    level: Optional[str] = Query(None, description="日志级别（info/warning/error）"),
    source: Optional[str] = Query(None, description="模块来源标识"),
    user_id: Optional[int] = Query(None, description="用户 ID"),
    username: Optional[str] = Query(None, description="用户名"),
    session_id: Optional[str] = Query(None, description="会话 ID"),
    request_id: Optional[str] = Query(None, description="请求 ID"),
    tool_call_id: Optional[str] = Query(None, description="工具调用 ID"),
    correlation_id: Optional[str] = Query(None, description="关联批次 ID"),
    target_type: Optional[str] = Query(None, description="操作目标类型"),
    target_id: Optional[str] = Query(None, description="操作目标 ID"),
    target_name: Optional[str] = Query(None, description="操作目标名称"),
    created_from: Optional[datetime] = Query(None, description="起始时间（ISO naive UTC）"),
    created_to: Optional[datetime] = Query(None, description="截止时间（ISO naive UTC）"),
    limit: int = Query(50, ge=1, le=200, description="单页条数（1..200, 默认 50）"),
    offset: int = Query(0, ge=0, description="分页偏移（>=0）"),
) -> Dict[str, Any]:
    """按固定白名单字段查询审计日志,按 ``created_at`` 倒序返回。

    同一过滤器分别调用 ``query_logs`` / ``count_logs``,返回 ``{items,total,limit,offset}``
    信封结构,便于前端分页渲染。

    字段语义：
        - 全部过滤器均为「精确匹配」,空值表示不过滤。
        - 时间范围按 ``created_at`` 闭区间 ``[created_from, created_to]`` 过滤。
        - ``created_at`` 为 naive UTC（无 tz 后缀）,序列化由 Pydantic JSON 自动处理。
        - ``total`` 与 ``items.length`` 可能不同:``total`` 是过滤后总数,``items.length`` 是当页数量。

    Returns:
        Dict[str, Any]: ``{"items": [...], "total": int, "limit": int, "offset": int}``。
    """
    svc = _get_log_service(request)
    # 同一过滤器分别 await query_logs / count_logs
    rows = await svc.query_logs(
        log_type=log_type,
        action=action,
        result=result,
        level=level,
        source=source,
        user_id=user_id,
        username=username,
        session_id=session_id,
        request_id=request_id,
        tool_call_id=tool_call_id,
        correlation_id=correlation_id,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
    total = await svc.count_logs(
        log_type=log_type,
        action=action,
        result=result,
        level=level,
        source=source,
        user_id=user_id,
        username=username,
        session_id=session_id,
        request_id=request_id,
        tool_call_id=tool_call_id,
        correlation_id=correlation_id,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        created_from=created_from,
        created_to=created_to,
    )
    return {
        "items": [_project_response(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/{log_id}",
    response_model=Dict[str, Any],
    summary="按 ID 取日志详情",
)
async def get_log(request: Request, log_id: int) -> Dict[str, Any]:
    """按 ``log_id`` 取单条日志;若记录含 ``correlation_id`` 则附带同 cid 的关联日志。

    Args:
        request: FastAPI Request 对象。
        log_id: 日志主键 ID（path int,FastAPI 自动校验 int 类型）。

    Returns:
        Dict[str, Any]: 单条日志详情 + ``related_logs`` 数组。
        - 不存在 → 404 + ``"日志不存在"``。
        - ``related_logs`` 始终返回 list；无 ``correlation_id`` 时为空数组。
    """
    svc = _get_log_service(request)
    row = await svc.get_log(log_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="日志不存在",
        )
    payload = _project_response(row)
    cid = payload.get("correlation_id")
    related: List[Dict[str, Any]] = []
    if cid:
        related_rows = await svc.get_correlated_logs(cid)
        for item in related_rows:
            related.append(_project_response(item))
    payload["related_logs"] = related
    return payload
