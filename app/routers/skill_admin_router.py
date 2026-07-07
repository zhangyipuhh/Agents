#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Skill Admin Router 模块

提供 skill 注册中心（SkillRegistryService）的完整 CRUD 管理接口（admin 权限）：
- GET    /api/admin/skills                列出所有已注册 skill
- GET    /api/admin/skills/unregistered   列出未注册 skill 文件（源码扫描）
- POST   /api/admin/skills                注册新 skill
- PUT    /api/admin/skills/{name}         更新 skill 配置
- DELETE /api/admin/skills/{name}         删除 skill
- PUT    /api/admin/skills/{name}/enabled 启用/禁用 skill
- POST   /api/admin/skills/scan           扫描未注册 skill 文件

所有路由均通过 require_admin 鉴权（Depends 注入，router 级别）。
service 实例从 request.app.state.skill_service 获取，生产对等初始化点：
app/core/server.py lifespan 中 `app.state.skill_service = SkillRegistryService(db_pool)`。

Date: 2026-06-29
Author: AI Assistant
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.shared.utils.agent.skill_service import (
    SkillAlreadyExistsError,
    SkillNotFoundError,
    SkillRegistryService,
)
from app.shared.utils.auth.Safety import require_admin


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/skills",
    tags=["Skill Admin"],
    dependencies=[Depends(require_admin)],
)


# === Pydantic 请求体模型 ===

class SkillCreateRequest(BaseModel):
    """注册新 skill 请求体。

    Attributes:
        name: skill 唯一标识（与 SKILL.md frontmatter 中的 name 一致）
        display_name: 展示名称（管理界面用）
        category: skill 分类
        description: skill 描述
        location: SKILL.md 文件绝对路径
        base_dir: SKILL.md 所在目录绝对路径
        content: 去除 frontmatter 后的正文
        enabled: 是否启用
        sort_order: 排序权重
    """

    name: str = Field(..., min_length=1, max_length=100, description="skill 唯一标识")
    display_name: Optional[str] = Field(None, max_length=200, description="展示名称")
    category: str = Field(..., min_length=1, max_length=100, description="skill 分类")
    description: Optional[str] = Field(None, max_length=2000, description="skill 描述")
    location: Optional[str] = Field(None, max_length=1000, description="SKILL.md 文件绝对路径")
    base_dir: Optional[str] = Field(None, max_length=1000, description="SKILL.md 所在目录绝对路径")
    content: Optional[str] = Field(None, description="去除 frontmatter 后的正文")
    enabled: bool = Field(True, description="是否启用")
    sort_order: int = Field(0, description="排序权重")


class SkillUpdateRequest(BaseModel):
    """更新 skill 配置请求体（全量更新，None 字段用默认值替换）。

    注意：name 不可修改（由 URL path 指定）；location / base_dir / content
    涉及源文件位置与内容，修改需谨慎，调用方需传入完整配置。

    Attributes:
        display_name: 展示名称
        category: skill 分类
        description: skill 描述
        location: SKILL.md 文件绝对路径
        base_dir: SKILL.md 所在目录绝对路径
        content: 去除 frontmatter 后的正文
        enabled: 是否启用
        sort_order: 排序权重
    """

    display_name: Optional[str] = Field(None, max_length=200, description="展示名称")
    category: Optional[str] = Field(None, max_length=100, description="skill 分类")
    description: Optional[str] = Field(None, max_length=2000, description="skill 描述")
    location: Optional[str] = Field(None, max_length=1000, description="SKILL.md 文件绝对路径")
    base_dir: Optional[str] = Field(None, max_length=1000, description="SKILL.md 所在目录绝对路径")
    content: Optional[str] = Field(None, description="去除 frontmatter 后的正文")
    enabled: Optional[bool] = Field(None, description="是否启用")
    sort_order: Optional[int] = Field(None, description="排序权重")


class SkillEnabledRequest(BaseModel):
    """启用/禁用 skill 请求体。

    Attributes:
        enabled: True 启用 / False 禁用
    """

    enabled: bool = Field(..., description="True 启用 / False 禁用")


# === 工具函数 ===

def _get_service(request: Request) -> SkillRegistryService:
    """从 app.state 获取 SkillRegistryService 实例。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.skill_service = SkillRegistryService(db_pool)`（db_pool 存在时）。
    lifespan 用 try/except 包裹，初始化失败时 app.state.skill_service 不会存在，
    此处返回 500 让调用方感知服务不可用。

    参数:
        request: FastAPI Request 对象

    返回:
        SkillRegistryService: 服务实例

    异常:
        HTTPException: 服务未初始化时抛出 500
    """
    service = getattr(request.app.state, "skill_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SkillRegistryService not initialized",
        )
    return service


def _handle_skill_error(e: Exception) -> HTTPException:
    """统一转换 service 异常为 HTTPException。

    参数:
        e: service 层抛出的异常

    返回:
        HTTPException: 转换后的 HTTP 异常
        - SkillNotFoundError → 404
        - SkillAlreadyExistsError → 409
        - KeyError / ValueError → 400
        - 其他 → 500
    """
    if isinstance(e, SkillNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, SkillAlreadyExistsError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if isinstance(e, (KeyError, ValueError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.exception("Unexpected error in skill admin router: %s", e)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Internal error: {str(e)}",
    )


async def _invalidate_agent_config_cache(request: Request) -> None:
    """失效 agent_config 缓存（skill 变更影响 agent 可用 skill 列表）。

    skill 注册/更新/删除/启停后，agent 通过 skill_bindings 绑定的 skill
    可能失效（disabled skill 不再被加载；新注册 skill 加入可绑定池）。
    需清空 AgentConfigService 全部缓存强制下次重新加载。

    生产对等初始化点：app/core/server.py lifespan 中
    `app.state.agent_config_service = AgentConfigService(...)`。
    服务未初始化时静默跳过（不抛异常），避免 skill 写操作因缓存失效失败。

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
async def list_skills(request: Request) -> List[Dict[str, Any]]:
    """列出所有已注册 skill。

    调用 skill_service.list_skills()，优先读缓存（仅 enabled=TRUE），
    缓存为空时回退 DB 查询所有 skill（含禁用项，供 admin 查看）。

    参数:
        request: FastAPI Request 对象

    返回:
        List[Dict[str, Any]]: skill 元数据列表，每项包含
            name / display_name / category / description / location /
            base_dir / content / enabled / sort_order

    异常:
        HTTPException 500: SkillRegistryService 未初始化
    """
    service = _get_service(request)
    return await service.list_skills()


@router.get("/unregistered", response_model=List[Dict[str, Any]])
async def list_unregistered_skills(request: Request) -> List[Dict[str, Any]]:
    """列出未注册 skill 文件（源码扫描）。

    调用 skill_service.scan_unregistered()，扫描默认根（app/skills、
    .agents/skills）与用户扩展路径下的 SKILL.md，找出未在 DB 注册的 skill。

    参数:
        request: FastAPI Request 对象

    返回:
        List[Dict[str, Any]]: 未注册 skill 列表，每项包含
            name / description / location / base_dir

    异常:
        HTTPException 500: SkillRegistryService 未初始化
    """
    service = _get_service(request)
    return await service.scan_unregistered()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_skill(
    request: Request, req: SkillCreateRequest
) -> Dict[str, Any]:
    """注册新 skill。

    调用 skill_service.create_skill(payload)，写 DB 后刷新缓存。
    必填字段：name / category。

    参数:
        request: FastAPI Request 对象
        req: skill 配置请求体

    返回:
        Dict[str, Any]: 新创建的 skill 记录

    异常:
        HTTPException 409: name 已存在
        HTTPException 400: 缺少必需键 / 字段非法
        HTTPException 500: SkillRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    payload = req.model_dump(exclude_none=False)
    try:
        result = await service.create_skill(payload)
    except (SkillAlreadyExistsError, KeyError, ValueError) as e:
        raise _handle_skill_error(e)

    # 失效 agent_config 缓存（skill 变更影响 agent 可用 skill 列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.put("/{name}", response_model=Dict[str, Any])
async def update_skill(
    request: Request, name: str, req: SkillUpdateRequest
) -> Dict[str, Any]:
    """更新 skill 配置。

    调用 skill_service.update_skill(name, payload)，部分更新 skill 的可变字段，
    未传入字段保持数据库原值，写 DB 后刷新缓存。

    参数:
        request: FastAPI Request 对象
        name: skill 名称（URL path 参数）
        req: skill 更新请求体

    返回:
        Dict[str, Any]: 更新后的 skill 记录

    异常:
        HTTPException 404: skill 不存在
        HTTPException 400: 字段非法
        HTTPException 500: SkillRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    payload = req.model_dump(exclude_none=True)
    try:
        result = await service.update_skill(name, payload)
    except (SkillNotFoundError, ValueError) as e:
        raise _handle_skill_error(e)

    # 失效 agent_config 缓存（skill 变更影响 agent 可用 skill 列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(request: Request, name: str) -> None:
    """删除 skill。

    调用 skill_service.delete_skill(name)，写 DB 后失效缓存。

    参数:
        request: FastAPI Request 对象
        name: skill 名称（URL path 参数）

    返回:
        None

    异常:
        HTTPException 404: skill 不存在
        HTTPException 500: SkillRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    try:
        await service.delete_skill(name)
    except SkillNotFoundError as e:
        raise _handle_skill_error(e)

    # 失效 agent_config 缓存（skill 变更影响 agent 可用 skill 列表）
    await _invalidate_agent_config_cache(request)


@router.put("/{name}/enabled", response_model=Dict[str, Any])
async def set_skill_enabled(
    request: Request, name: str, req: SkillEnabledRequest
) -> Dict[str, Any]:
    """启用/禁用 skill。

    调用 skill_service.set_skill_enabled(name, enabled)，写 DB 后刷新缓存
    （enabled=TRUE 时加入缓存，enabled=FALSE 时从缓存移除）。

    参数:
        request: FastAPI Request 对象
        name: skill 名称（URL path 参数）
        req: 启用/禁用请求体

    返回:
        Dict[str, Any]: 更新后的 skill 记录

    异常:
        HTTPException 404: skill 不存在
        HTTPException 500: SkillRegistryService 未初始化或其他内部错误
    """
    service = _get_service(request)
    try:
        result = await service.set_skill_enabled(name, req.enabled)
    except SkillNotFoundError as e:
        raise _handle_skill_error(e)

    # 失效 agent_config 缓存（skill 启用状态变更影响 agent 可用 skill 列表）
    await _invalidate_agent_config_cache(request)
    return result


@router.post("/scan", response_model=List[Dict[str, Any]])
async def scan_unregistered_skills(request: Request) -> List[Dict[str, Any]]:
    """扫描未注册 skill 文件。

    与 GET /unregistered 功能相同，调用 skill_service.scan_unregistered()。
    提供 POST 语义供前端「主动触发扫描」按钮使用（扫描是较重操作，
    用 POST 表达副作用语义更清晰）。

    参数:
        request: FastAPI Request 对象

    返回:
        List[Dict[str, Any]]: 未注册 skill 列表，每项包含
            name / description / location / base_dir

    异常:
        HTTPException 500: SkillRegistryService 未初始化
    """
    service = _get_service(request)
    return await service.scan_unregistered()
