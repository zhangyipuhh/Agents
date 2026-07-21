#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
API 接口配置 Admin Router 模块。

提供 /api/admin/api-configs 下的节点树 CRUD、请求配置 upsert、
代理发送请求与调用历史查询接口。
所有接口均要求 admin 权限，服务实例由 app/core/server.py lifespan
初始化到 app.state.api_config_service。
"""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.api_config_service import ApiConfigService
from app.shared.utils.auth.Safety import require_admin


router = APIRouter(
    prefix="/api/admin/api-configs",
    tags=["API Config Admin"],
    dependencies=[Depends(require_admin)],
)


class CreateNodeRequest(BaseModel):
    """创建节点请求体。

    Attributes:
        parent_id: 父节点 ID；None 表示根节点。
        node_type: 节点类型，'folder' 或 'api'。
        name: 节点名称。
    """

    parent_id: Optional[int] = Field(default=None, ge=1)
    node_type: Literal["folder", "api"] = Field(...)
    name: str = Field(..., min_length=1, max_length=255)


class UpdateNodeRequest(BaseModel):
    """更新节点请求体，未传字段保持原值。

    Attributes:
        name: 节点名称。
        parent_id: 新父节点 ID。
        sort_order: 排序权重。
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    parent_id: Optional[int] = Field(default=None, ge=1)
    sort_order: Optional[int] = Field(default=None)


class KeyValueItem(BaseModel):
    """键值项，用于 params / headers / form_fields。

    Attributes:
        name: 键名。
        value: 键值。
        description: 描述。
    """

    name: str = Field(default="", max_length=255)
    value: str = Field(default="")
    description: str = Field(default="")


class UpsertConfigRequest(BaseModel):
    """全量 upsert 请求配置请求体。

    Attributes:
        method: HTTP 方法，POST 或 PUT。
        url: 请求 URL。
        params: query 参数列表。
        headers: 请求头列表。
        body_type: 请求体类型。
        body_content: 请求体原文。
        form_fields: 表单字段列表。
        expectations: 预期结果断言规则列表。
    """

    method: Literal["POST", "PUT"] = Field(default="POST")
    url: str = Field(default="")
    params: List[KeyValueItem] = Field(default_factory=list)
    headers: List[KeyValueItem] = Field(default_factory=list)
    body_type: Literal["none", "json", "xml", "text", "form-data", "x-www-form-urlencoded"] = Field(default="none")
    body_content: str = Field(default="")
    form_fields: List[KeyValueItem] = Field(default_factory=list)
    expectations: List[Dict[str, Any]] = Field(default_factory=list)


def _get_service(request: Request) -> ApiConfigService:
    """从 app.state 获取 ApiConfigService。

    参数:
        request: FastAPI Request 对象。

    返回:
        ApiConfigService: API 接口配置服务实例。

    异常:
        HTTPException: 服务未初始化时抛出 500。
    """
    service = getattr(request.app.state, "api_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ApiConfigService not initialized",
        )
    return service


def _handle_service_error(exc: Exception) -> None:
    """将 service 异常转换为 HTTPException。

    参数:
        exc: service 层异常。

    返回:
        None。

    异常:
        HTTPException: LookupError → 404；ValueError → 400；其他向上抛。
    """
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


@router.get("/tree", response_model=Dict[str, Any])
async def get_tree(request: Request) -> Dict[str, Any]:
    """获取节点树平铺列表。

    参数:
        request: FastAPI Request 对象。

    返回:
        Dict[str, Any]: {"nodes": [...]}，前端自行组树。
    """
    service = _get_service(request)
    nodes = await service.get_tree()
    return {"nodes": nodes}


@router.post("/nodes", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_node(request: Request, body: CreateNodeRequest) -> Dict[str, Any]:
    """创建节点；node_type='api' 时自动创建默认配置。

    参数:
        request: FastAPI Request 对象。
        body: 创建请求体。

    返回:
        Dict[str, Any]: 新建节点对象。
    """
    service = _get_service(request)
    try:
        return await service.create_node(body.parent_id, body.node_type, body.name)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.put("/nodes/{node_id}", response_model=Dict[str, Any])
async def update_node(
    request: Request,
    node_id: int,
    body: UpdateNodeRequest,
) -> Dict[str, Any]:
    """更新节点名称 / 父节点 / 排序权重。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。
        body: 更新请求体。

    返回:
        Dict[str, Any]: 更新后的节点对象。
    """
    service = _get_service(request)
    try:
        return await service.update_node(
            node_id,
            name=body.name,
            parent_id=body.parent_id,
            sort_order=body.sort_order,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.delete("/nodes/{node_id}", response_model=Dict[str, Any])
async def delete_node(request: Request, node_id: int) -> Dict[str, Any]:
    """删除节点；api 节点级联删除配置与调用历史。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。

    返回:
        Dict[str, Any]: {"ok": true}。
    """
    service = _get_service(request)
    try:
        await service.delete_node(node_id)
        return {"ok": True}
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.get("/nodes/{node_id}/config", response_model=Dict[str, Any])
async def get_config(request: Request, node_id: int) -> Dict[str, Any]:
    """获取 api 节点的请求配置。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。

    返回:
        Dict[str, Any]: 配置对象。
    """
    service = _get_service(request)
    try:
        return await service.get_config(node_id)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.put("/nodes/{node_id}/config", response_model=Dict[str, Any])
async def upsert_config(
    request: Request,
    node_id: int,
    body: UpsertConfigRequest,
) -> Dict[str, Any]:
    """全量 upsert api 节点的请求配置。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。
        body: 配置请求体。

    返回:
        Dict[str, Any]: upsert 后的配置对象。
    """
    service = _get_service(request)
    try:
        return await service.upsert_config(
            node_id,
            method=body.method,
            url=body.url,
            params=[item.model_dump() for item in body.params],
            headers=[item.model_dump() for item in body.headers],
            body_type=body.body_type,
            body_content=body.body_content,
            form_fields=[item.model_dump() for item in body.form_fields],
            expectations=body.expectations,
        )
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.post("/nodes/{node_id}/send", response_model=Dict[str, Any])
async def send_request(request: Request, node_id: int) -> Dict[str, Any]:
    """按节点配置代理发送 HTTP 请求并校验预期结果。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。

    返回:
        Dict[str, Any]: 调用结果（run_id / http_status / duration_ms /
            response_body / check_passed / assertion_results / error_message）。
    """
    service = _get_service(request)
    try:
        return await service.send_request(node_id)
    except Exception as exc:
        _handle_service_error(exc)
        raise


@router.get("/nodes/{node_id}/runs", response_model=Dict[str, Any])
async def list_runs(
    request: Request,
    node_id: int,
    limit: int = 20,
) -> Dict[str, Any]:
    """查询 api 节点的调用历史。

    参数:
        request: FastAPI Request 对象。
        node_id: 节点 ID。
        limit: 最大返回条数。

    返回:
        Dict[str, Any]: {"runs": [...]}。
    """
    service = _get_service(request)
    try:
        runs = await service.list_runs(node_id, limit=limit)
        return {"runs": runs}
    except Exception as exc:
        _handle_service_error(exc)
        raise
