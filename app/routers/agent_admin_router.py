#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent Admin Router 模块

提供 Agent 配置的完整 CRUD 管理接口（admin 权限）：
- GET    /api/admin/agents                          列出所有 agent
- GET    /api/admin/agents/{name}                   获取单个 agent 完整配置
- POST   /api/admin/agents                          新增智能体
- DELETE /api/admin/agents/{name}                   删除智能体（级联清理绑定）
- PUT    /api/admin/agents/{name}/enabled           启用/禁用智能体
- GET    /api/admin/agents/check-name?name=xxx      name 唯一性预校验
- POST   /api/admin/agents/validate-md-path         AGENTS.md 路径存在性校验
- GET    /api/admin/agents/{name}/config-schema/field-template
                                                    获取 AgentConfig 字段模板列表
- PUT    /api/admin/agents/{name}/config-schema     全量替换 config_schema
- POST   /api/admin/agents/{name}/config-schema/field
                                                    增量添加字段
- DELETE /api/admin/agents/{name}/config-schema/field?section=&field_name=
                                                    增量删除字段
- GET    /api/admin/agents/{name}/tool-bindings   获取工具绑定列表
- PUT    /api/admin/agents/{name}/tool-bindings   更新工具绑定列表（全量替换）

所有路由均通过 require_admin 鉴权。

Date: 2026-06-24
Author: AI Assistant
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.agent.agent_config_service import (
    AgentAlreadyExistsError,
    AgentConfigService,
    AgentNotFoundError,
)
from app.shared.utils.agent.dynamic_schema import (
    RESERVED_CONFIG_FIELDS,
    get_agent_config_field_templates,
    get_agent_state_field_templates,
    get_agent_context_field_templates,
)
from app.shared.utils.auth.Safety import require_admin


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/agents",
    tags=["Agent Admin"],
    dependencies=[Depends(require_admin)],
)


# === Pydantic 请求体模型 ===

class CreateAgentRequest(BaseModel):
    """新增智能体请求体。"""
    name: str = Field(..., min_length=3, max_length=50,
                       pattern=r"^[a-z0-9_]+$",
                       description="智能体唯一标识（[a-z0-9_]+）")
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=500)
    agents_md_path: str = Field(..., min_length=1, max_length=500)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    mcp_tags: List[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = 0


class UpdateConfigSchemaRequest(BaseModel):
    """全量替换 config_schema 请求体。"""
    config_schema: Dict[str, Any]


class AddFieldRequest(BaseModel):
    """增量添加字段请求体。"""
    section: str = Field(..., description="root / state_fields / context_fields")
    field_name: str = Field(..., min_length=1, max_length=100,
                            pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    field_def: Dict[str, Any] = Field(..., description='如 {"type": "int", "default": 0}')


class SetEnabledRequest(BaseModel):
    """启用/禁用请求体。"""
    enabled: bool


class ValidateMdPathRequest(BaseModel):
    """AGENTS.md 路径校验请求体。"""
    path: str = Field(..., min_length=1, max_length=500)


class ToolBindingItem(BaseModel):
    """单个工具绑定项。

    用于描述 agent 与工具的绑定关系：
    - tool_name: 工具唯一标识（内置工具名 / MCP 工具名 / skill 名）
    - tool_type: 工具来源类型，"builtin" 内置 / "mcp" MCP 工具 / "skill" 技能
    - enabled: 是否启用该绑定
    - sort_order: 排序权重，越小越靠前
    """
    tool_name: str = Field(..., min_length=1, max_length=100,
                           description="工具唯一标识")
    tool_type: str = Field("builtin", description="工具来源类型：builtin / mcp / skill")
    enabled: bool = Field(True, description="是否启用该绑定")
    sort_order: int = Field(0, ge=0, description="排序权重，越小越靠前")


class ToolBindingsRequest(BaseModel):
    """更新工具绑定列表请求体。"""
    bindings: List[ToolBindingItem] = Field(default_factory=list,
                                            description="工具绑定列表（全量替换）")


# === 工具函数 ===

def _get_service(request: Request) -> AgentConfigService:
    """从 app.state 获取 AgentConfigService 实例。

    参数:
        request: FastAPI Request 对象

    返回:
        AgentConfigService: 服务实例

    异常:
        HTTPException: 服务未初始化时抛出 500
    """
    service = getattr(request.app.state, "agent_config_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AgentConfigService not initialized",
        )
    return service


def _handle_agent_error(e: Exception) -> HTTPException:
    """统一转换 service 异常为 HTTPException。"""
    if isinstance(e, AgentAlreadyExistsError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if isinstance(e, AgentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if isinstance(e, FileNotFoundError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if isinstance(e, KeyError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.exception("Unexpected error in agent admin router: %s", e)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Internal error: {str(e)}",
    )


# === 路由端点 ===

@router.get("", response_model=List[Dict[str, Any]])
async def list_agents(request: Request) -> List[Dict[str, Any]]:
    """列出所有 agent（含 config_schema 完整数据）。

    返回:
        List[Dict]: 包含 name / display_name / description / config_schema /
                    mcp_tags / enabled / sort_order 等
    """
    service = _get_service(request)
    return await service.list_all_agents_admin()


@router.get("/check-name")
async def check_name_unique(
    request: Request,
    name: str = Query(..., min_length=3, max_length=50),
) -> Dict[str, Any]:
    """name 唯一性预校验（走 service 层，避免直读 app.state.db）。"""
    service = _get_service(request)
    available = await service.check_name_unique(name)
    return {"name": name, "available": available}


@router.post("/validate-md-path")
async def validate_md_path(req: ValidateMdPathRequest) -> Dict[str, Any]:
    """校验 AGENTS.md 路径是否存在。

    用于前端「新增智能体」表单的 onBlur 实时校验。
    """
    p = Path(req.path)
    return {
        "path": req.path,
        "exists": p.is_file(),
        "is_file": p.is_file(),
    }


@router.get("/field-templates")
async def list_field_templates(
    section: str = Query("root", description="root / state_fields / context_fields"),
) -> List[Dict[str, Any]]:
    """获取指定 section 的字段模板列表。

    用于前端「添加字段」弹窗中「覆盖来源 = 已有字段」的下拉列表。

    参数:
        section: 字段所属段，root 返回 AgentConfig 字段模板，
                 state_fields 返回 AgentState 字段模板，
                 context_fields 返回 AgentContext 字段模板

    返回:
        List[Dict]: 每项为 {"field_name": str, "type": str, "default": Any}

    异常:
        HTTPException 400: section 参数非法
    """
    if section == "root":
        return get_agent_config_field_templates()
    if section == "state_fields":
        return get_agent_state_field_templates()
    if section == "context_fields":
        return get_agent_context_field_templates()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid section: {section}. Must be one of root, state_fields, context_fields.",
    )


@router.get("/{name}", response_model=Dict[str, Any])
async def get_agent(request: Request, name: str) -> Dict[str, Any]:
    """获取单个 agent 的完整配置。

    异常:
        HTTPException 404: 智能体不存在
    """
    service = _get_service(request)
    try:
        return await service.get_agent_admin(name)
    except AgentNotFoundError as e:
        raise _handle_agent_error(e)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: Request, req: CreateAgentRequest
) -> Dict[str, Any]:
    """新增智能体。

    异常:
        HTTPException 409: name 已存在
        HTTPException 400: name 格式非法 / AGENTS.md 不存在 / config_schema 校验失败
    """
    service = _get_service(request)
    payload = req.model_dump()
    try:
        return await service.create_agent(payload)
    except (AgentAlreadyExistsError, AgentNotFoundError, ValueError,
            FileNotFoundError, KeyError) as e:
        raise _handle_agent_error(e)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(request: Request, name: str) -> None:
    """删除智能体（级联清理工具/技能绑定，保留历史会话）。

    异常:
        HTTPException 404: 智能体不存在
    """
    service = _get_service(request)
    try:
        await service.delete_agent(name)
    except AgentNotFoundError as e:
        raise _handle_agent_error(e)


@router.put("/{name}/enabled")
async def set_enabled(
    request: Request, name: str, req: SetEnabledRequest
) -> Dict[str, Any]:
    """启用 / 禁用单个智能体。"""
    service = _get_service(request)
    try:
        return await service.set_agent_enabled(name, req.enabled)
    except AgentNotFoundError as e:
        raise _handle_agent_error(e)


@router.put("/{name}/config-schema")
async def update_config_schema(
    request: Request, name: str, req: UpdateConfigSchemaRequest
) -> Dict[str, Any]:
    """全量替换 config_schema。"""
    service = _get_service(request)
    try:
        return await service.update_agent_config_schema(name, req.config_schema)
    except (AgentNotFoundError, ValueError) as e:
        raise _handle_agent_error(e)


@router.post("/{name}/config-schema/field")
async def add_field(
    request: Request, name: str, req: AddFieldRequest
) -> Dict[str, Any]:
    """增量添加 config_schema 字段。

    section: root / state_fields / context_fields
    """
    service = _get_service(request)
    try:
        return await service.add_agent_config_field(
            name, req.section, req.field_name, req.field_def,
        )
    except (AgentNotFoundError, ValueError) as e:
        raise _handle_agent_error(e)


@router.put("/{name}/config-schema/field")
async def update_field(
    request: Request, name: str, req: AddFieldRequest
) -> Dict[str, Any]:
    """直接覆盖 config_schema 中已存在的字段（无需先删后加）。

    section: root / state_fields / context_fields
    """
    service = _get_service(request)
    try:
        return await service.update_agent_config_field(
            name, req.section, req.field_name, req.field_def,
        )
    except (AgentNotFoundError, ValueError) as e:
        raise _handle_agent_error(e)


@router.delete("/{name}/config-schema/field")
async def delete_field(
    request: Request,
    name: str,
    section: str = Query(..., description="root / state_fields / context_fields"),
    field_name: str = Query(..., min_length=1, max_length=100),
) -> Dict[str, Any]:
    """增量删除 config_schema 字段。"""
    service = _get_service(request)
    try:
        return await service.delete_agent_config_field(name, section, field_name)
    except (AgentNotFoundError, ValueError) as e:
        raise _handle_agent_error(e)


@router.get("/{name}/tool-bindings")
async def get_agent_tool_bindings(
    request: Request, name: str
) -> Dict[str, Any]:
    """获取 agent 的工具绑定列表。

    读取 agents.tool_bindings JSONB 字段，返回该 agent 当前绑定的全部工具。

    参数:
        name: 智能体名称（唯一标识）

    返回:
        Dict[str, Any]: {"agent_name": str, "tool_bindings": List[Dict]}
        其中 tool_bindings 每项格式：
            {"tool_name": str, "tool_type": str, "enabled": bool,
             "sort_order": int}

    异常:
        HTTPException 404: 智能体不存在
    """
    service = _get_service(request)
    try:
        bindings = await service.get_tool_bindings(name)
    except AgentNotFoundError as e:
        raise _handle_agent_error(e)
    return {"agent_name": name, "tool_bindings": bindings}


@router.put("/{name}/tool-bindings")
async def update_agent_tool_bindings(
    request: Request, name: str, req: ToolBindingsRequest
) -> Dict[str, Any]:
    """更新 agent 的工具绑定列表（全量替换）。

    将 agents.tool_bindings JSONB 字段替换为请求体中的 bindings 列表，
    写入后同步刷新缓存（tools 字段延迟重新加载）。

    参数:
        name: 智能体名称（唯一标识）
        req: 请求体，包含 bindings 列表（全量替换语义）

    返回:
        Dict[str, Any]: {"agent_name": str, "tool_bindings": List[Dict]}
        其中 tool_bindings 为更新后的完整绑定列表

    异常:
        HTTPException 404: 智能体不存在
    """
    service = _get_service(request)
    # 将 Pydantic 模型转为 dict 列表，与 service.update_tool_bindings 签名对齐
    bindings_payload = [b.model_dump() for b in req.bindings]
    try:
        result = await service.update_tool_bindings(name, bindings_payload)
    except AgentNotFoundError as e:
        raise _handle_agent_error(e)
    return {
        "agent_name": name,
        "tool_bindings": result.get("tool_bindings", []),
    }