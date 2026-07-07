#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Tool Admin Router 模块

提供工具注册中心（ToolRegistryService）的完整 CRUD 管理接口（admin 权限）：
- GET    /api/admin/tools                列出所有已注册工具
- GET    /api/admin/tools/unregistered   列出未注册工具文件（源码扫描）
- POST   /api/admin/tools                注册新工具
- PUT    /api/admin/tools/{name}         更新工具配置
- DELETE /api/admin/tools/{name}         删除工具
- PUT    /api/admin/tools/{name}/enabled 启用/禁用工具
- POST   /api/admin/tools/scan           扫描未注册工具文件

所有路由均通过 require_admin 鉴权（Depends 注入，router 级别）。
service 实例从 request.app.state.tool_service 获取，生产对等初始化点：
app/core/server.py lifespan 中 `app.state.tool_service = ToolRegistryService(db_pool)`。

Date: 2026-06-25
Author: AI Assistant
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.agent.tool_service import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
    ToolRegistryService,
)
from app.shared.utils.auth.Safety import require_admin


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/tools",
    tags=["Tool Admin"],
    dependencies=[Depends(require_admin)],
)


# === Pydantic 请求体模型 ===

class ToolCreateRequest(BaseModel):
    """注册新工具请求体。

    Attributes:
        name: 工具唯一标识（与 @tool 函数名 / DB name 一致）
        display_name: 展示名称（管理界面用）
        category: 工具分类（如 filesystem / sandbox / mcp / map 等）
        description: 工具描述（来自 docstring 摘要）
        module_path: Python 模块路径（如 app.core.tools.BaseTools）
        file_path: 源文件相对路径（如 app/core/tools/BaseTools.py）
        args_schema: 参数 schema 字典
        return_description: 返回值类型描述
        function_description: 函数完整描述（docstring 全文）
        enabled: 是否启用
        sort_order: 排序权重
    """

    name: str = Field(..., min_length=1, max_length=100, description="工具唯一标识")
    display_name: Optional[str] = Field(None, max_length=200, description="展示名称")
    category: str = Field(..., min_length=1, max_length=100, description="工具分类")
    description: Optional[str] = Field(None, max_length=2000, description="工具描述")
    module_path: str = Field(..., min_length=1, max_length=500, description="Python 模块路径")
    file_path: str = Field(..., min_length=1, max_length=500, description="源文件相对路径")
    args_schema: Dict[str, Any] = Field(default_factory=dict, description="参数 schema 字典")
    return_description: Optional[str] = Field(None, description="返回值类型描述")
    function_description: Optional[str] = Field(None, description="函数完整描述")
    enabled: bool = Field(True, description="是否启用")
    sort_order: int = Field(0, description="排序权重")


class ToolUpdateRequest(BaseModel):
    """更新工具配置请求体（部分更新，None 字段保持原值）。

    注意：name 不可修改（由 URL path 指定）；module_path / file_path 不可改
    （涉及源码位置，修改无意义）。仅允许更新展示与开关相关字段。

    Attributes:
        display_name: 展示名称
        category: 工具分类
        description: 工具描述
        args_schema: 参数 schema 字典
        return_description: 返回值类型描述
        function_description: 函数完整描述
        enabled: 是否启用
        sort_order: 排序权重
    """

    display_name: Optional[str] = Field(None, max_length=200, description="展示名称")
    category: Optional[str] = Field(None, max_length=100, description="工具分类")
    description: Optional[str] = Field(None, max_length=2000, description="工具描述")
    args_schema: Optional[Dict[str, Any]] = Field(None, description="参数 schema 字典")
    return_description: Optional[str] = Field(None, description="返回值类型描述")
    function_description: Optional[str] = Field(None, description="函数完整描述")
    enabled: Optional[bool] = Field(None, description="是否启用")
    sort_order: Optional[int] = Field(None, description="排序权重")


class ToolEnabledRequest(BaseModel):
    """启用/禁用工具请求体。

    Attributes:
        enabled: True 启用 / False 禁用
    """

    enabled: bool = Field(..., description="True 启用 / False 禁用")


# === 工具函数 ===

def _get_service(request: Request) -> ToolRegistryService:
    """从 app.state 获取 ToolRegistryService 实例。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.tool_service = ToolRegistryService(db_pool)`（db_pool 存在时）。
    lifespan 用 try/except 包裹，初始化失败时 app.state.tool_service 不会存在，
    此处返回 500 让调用方感知服务不可用。

    参数:
        request: FastAPI Request 对象

    返回:
        ToolRegistryService: 服务实例

    异常:
        HTTPException: 服务未初始化时抛出 500
    """
    service = getattr(request.app.state, "tool_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ToolRegistryService not initialized",
        )
    return service


def _handle_tool_error(e: Exception) -> HTTPException:
    """统一转换 service 异常为 HTTPException。

    参数:
        e: service 层抛出的异常

    返回:
        HTTPException: 转换后的 HTTP 异常
        - ToolNotFoundError → 404
        - ToolAlreadyExistsError → 409
        - KeyError / ValueError → 400
        - 其他 → 500
    """
    if isinstance(e, ToolNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, ToolAlreadyExistsError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if isinstance(e, (KeyError, ValueError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.exception("Unexpected error in tool admin router: %s", e)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Internal error: {str(e)}",
    )


async def _invalidate_agent_config_cache(request: Request) -> None:
    """失效 agent_config 缓存（工具变更影响 agent 工具列表）。

    工具注册/更新/删除/启停后，agent 通过 tool_bindings 绑定的工具实例
    可能失效（disabled 工具不再被加载；新注册工具加入可绑定池）。
    需清空 AgentConfigService 全部缓存强制下次重新加载。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.agent_config_service = AgentConfigService(...)`。
    服务未初始化时静默跳过（不抛异常），避免工具写操作因缓存失效失败。

    参数:
        request: FastAPI Request 对象

    返回:
        None
    """
    agent_service = getattr(request.app.state, "agent_config_service", None)
    if agent_service is not None:
        await agent_service.invalidate_all_cache()


# === 路由端点 ===

@router.get("", response_model=List[Dict[str, Any]])
async def list_tools(request: Request) -> List[Dict[str, Any]]:
    """列出所有已注册工具。

    调用 tool_service.list_tools()，优先读缓存（仅 enabled=TRUE），
    缓存为空时回退 DB 查询所有工具（含禁用项，供 admin 查看）。

    参数:
        request: FastAPI Request 对象

    返回:
        List[Dict[str, Any]]: 工具元数据列表，每项包含
            name / display_name / category / description / module_path /
            file_path / args_schema / return_description /
            function_description / enabled

    异常:
        HTTPException 500: ToolRegistryService 未初始化
    """
    service = _get_service(request)
    return await service.list_tools()


@router.get("/unregistered", response_model=List[Dict[str, Any]])
async def list_unregistered_tools(request: Request) -> List[Dict[str, Any]]:
    """列出未注册工具文件（源码扫描）。

    调用 tool_service.scan_unregistered()，用 ast.parse 扫描
    app/core/tools/ 和 app/shared/tools/skills/ 下所有 .py 文件，
    找出未在 DB 注册的 @tool 函数。

    参数:
        request: FastAPI Request 对象

    返回:
        List[Dict[str, Any]]: 未注册工具列表，每项包含
            name / file_path / module_path / args_schema /
            return_description / function_description

    异常:
        HTTPException 500: ToolRegistryService 未初始化
    """
    service = _get_service(request)
    return await service.scan_unregistered()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_tool(
    request: Request, req: ToolCreateRequest
) -> Dict[str, Any]:
    """注册新工具。

    调用 tool_service.create_tool(payload)，写 DB 后刷新缓存。
    必填字段：name / category / module_path / file_path。

    参数:
        request: FastAPI Request 对象
        req: 工具配置请求体

    返回:
        Dict[str, Any]: 新创建的工具记录（含反序列化后的 args_schema）

    异常:
        HTTPException 409: name 已存在
        HTTPException 400: 缺少必需键 / 字段非法
        HTTPException 500: ToolRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    payload = req.model_dump(exclude_none=False)
    try:
        result = await service.create_tool(payload)
    except (ToolAlreadyExistsError, KeyError, ValueError) as e:
        raise _handle_tool_error(e)

    # 失效 agent_config 缓存（工具变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.put("/{name}", response_model=Dict[str, Any])
async def update_tool(
    request: Request, name: str, req: ToolUpdateRequest
) -> Dict[str, Any]:
    """更新工具配置。

    调用 tool_service.update_tool(name, payload)，部分更新工具的可变字段，
    未传入字段保持数据库原值，写 DB 后刷新缓存。

    参数:
        request: FastAPI Request 对象
        name: 工具名称（URL path 参数）
        req: 工具更新请求体

    返回:
        Dict[str, Any]: 更新后的工具记录

    异常:
        HTTPException 404: 工具不存在
        HTTPException 400: 字段非法
        HTTPException 500: ToolRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    payload = req.model_dump(exclude_none=True)
    try:
        result = await service.update_tool(name, payload)
    except (ToolNotFoundError, ValueError) as e:
        raise _handle_tool_error(e)

    # 失效 agent_config 缓存（工具变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(request: Request, name: str) -> None:
    """删除工具。

    调用 tool_service.delete_tool(name)，写 DB 后失效缓存。

    参数:
        request: FastAPI Request 对象
        name: 工具名称（URL path 参数）

    返回:
        None

    异常:
        HTTPException 404: 工具不存在
        HTTPException 500: ToolRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    try:
        await service.delete_tool(name)
    except ToolNotFoundError as e:
        raise _handle_tool_error(e)

    # 失效 agent_config 缓存（工具变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)


@router.put("/{name}/enabled", response_model=Dict[str, Any])
async def set_tool_enabled(
    request: Request, name: str, req: ToolEnabledRequest
) -> Dict[str, Any]:
    """启用/禁用工具。

    调用 tool_service.set_tool_enabled(name, enabled)，写 DB 后刷新缓存
    （enabled=TRUE 时加入缓存，enabled=FALSE 时从缓存移除）。

    参数:
        request: FastAPI Request 对象
        name: 工具名称（URL path 参数）
        req: 启用/禁用请求体

    返回:
        Dict[str, Any]: 更新后的工具记录

    异常:
        HTTPException 404: 工具不存在
        HTTPException 500: ToolRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    try:
        result = await service.set_tool_enabled(name, req.enabled)
    except ToolNotFoundError as e:
        raise _handle_tool_error(e)

    # 失效 agent_config 缓存（工具启用状态变更影响 agent 工具列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.post("/scan", response_model=List[Dict[str, Any]])
async def scan_unregistered_tools(request: Request) -> List[Dict[str, Any]]:
    """扫描未注册工具文件。

    与 GET /unregistered 功能相同，调用 tool_service.scan_unregistered()。
    提供 POST 语义供前端「主动触发扫描」按钮使用（扫描是较重操作，
    用 POST 表达副作用语义更清晰）。

    参数:
        request: FastAPI Request 对象

    返回:
        List[Dict[str, Any]]: 未注册工具列表，每项包含
            name / file_path / module_path / args_schema /
            return_description / function_description

    异常:
        HTTPException 500: ToolRegistryService 未初始化
    """
    service = _get_service(request)
    return await service.scan_unregistered()
