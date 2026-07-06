#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
项目管理路由模块（2026-06-30 新增）

提供项目文件夹元数据的 CRUD 接口，供前端聊天框下拉框使用：
- POST /api/project/create   创建新项目（uuid = 当前 session_id）
- GET  /api/project/list     当前用户的项目列表
- GET  /api/project/{id}/info  单项目详情
- PUT  /api/project/session/bind   将当前会话绑定到指定项目
- PUT  /api/project/session/unbind 解除当前会话与项目的关联

设计原则：
- 项目文件夹是逻辑概念：原文件落到 data/project/{uuid}/，解析 md 到 data/tmp/project/{uuid}/
- 多会话可共享同一项目（通过 sessions.project_id 关联）
- 上传/下载路径计算已统一在中间件 + 工具层处理，路由只负责元数据维护

Date: 2026-06-30
Author: AI Assistant
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.shared.utils.auth.user_db import UserDB
from app.shared.utils.project.project_db import ProjectDB
from app.shared.utils.auth.session_db import SessionDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/project', tags=['Project Management'])


class ProjectCreateRequest(BaseModel):
    """项目创建请求体

    Attributes:
        name: 项目名称（用户输入，1-50 字符）。
        uuid: 项目唯一标识，约定 = 创建时的 session_id。
    """
    name: str
    uuid: str


class ProjectInfo(BaseModel):
    """项目信息响应

    Attributes:
        id: 项目主键 ID。
        name: 项目名称。
        uuid: 项目 uuid（= 创建时的 session_id）。
        user_id: 创建者用户 ID。
        created_at: 创建时间（ISO 字符串）。
    """
    id: int
    name: str
    uuid: str
    user_id: int
    created_at: Optional[str] = None


class BindSessionRequest(BaseModel):
    """会话-项目绑定请求体

    Attributes:
        session_id: 目标会话 ID。
        project_id: 目标项目 ID（绑定）；unbind 端点不使用此字段。
    """
    session_id: str
    project_id: Optional[int] = None


class RenameProjectRequest(BaseModel):
    """项目重命名请求体

    Attributes:
        name: 新的项目名称（1-50 字符）。
    """
    name: str


def _project_to_dict(p: dict) -> dict:
    """将 ProjectDB 返回的 dict 序列化为响应 dict

    Args:
        p: 来自 ProjectDB 的项目字典。

    Returns:
        dict: API 响应字典。
    """
    created = p.get('created_at')
    return {
        'id': p.get('id'),
        'name': p.get('name'),
        'uuid': p.get('uuid'),
        'user_id': p.get('user_id'),
        'created_at': created.isoformat() if created else None,
    }


@router.post('/create')
async def create_project(request: Request, body: ProjectCreateRequest):
    """创建新项目

    入参：
        name: 用户输入的项目名称
        uuid: 由前端传入 = 当前 session_id

    Returns:
        dict: 新创建项目的完整信息

    Raises:
        HTTPException: 401 未认证 / 400 参数错误 / 500 创建失败
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")

        if not body.name or not body.name.strip():
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        if len(body.name) > 50:
            raise HTTPException(status_code=400, detail="项目名称不能超过 50 字符")
        if not body.uuid or not body.uuid.strip():
            raise HTTPException(status_code=400, detail="uuid 不能为空")

        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        # 创建项目
        project = await ProjectDB.create_project(
            user_id=user['id'],
            name=body.name.strip(),
            uuid=body.uuid.strip(),
        )
        if not project:
            raise HTTPException(status_code=500, detail="项目创建失败")

        # 自动把当前会话绑定到该项目（如果传入了 session_id 走 bind，否则由前端单独调）
        return {
            "success": True,
            "message": "项目创建成功",
            "project": _project_to_dict(project),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("创建项目失败: %s", e)
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.get('/list')
async def list_projects(request: Request):
    """获取当前用户的项目列表

    Returns:
        dict: projects 字段为按 created_at DESC 排序的项目列表
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        projects = await ProjectDB.list_user_projects(user['id'])
        return {"projects": [_project_to_dict(p) for p in projects]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取项目列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取项目列表失败: {str(e)}")


@router.get('/{project_id}/info')
async def get_project_info(project_id: int, request: Request):
    """获取单个项目详情

    Args:
        project_id: 项目主键 ID。

    Returns:
        dict: project 字段为项目信息
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
        project = await ProjectDB.get_project_by_id(project_id, user_id=user['id'])
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在或无权访问")
        return {"project": _project_to_dict(project)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取项目详情失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取项目详情失败: {str(e)}")


@router.put('/session/bind')
async def bind_session_to_project(request: Request, body: BindSessionRequest):
    """将会话绑定到指定项目

    流程：
    1. 校验项目归属
    2. 校验 session 归属
    3. 调 SessionDB.update_session_project 持久化关联

    Args:
        body.session_id: 目标会话 ID
        body.project_id: 目标项目 ID

    Returns:
        dict: success / message
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        if not body.project_id:
            raise HTTPException(status_code=400, detail="project_id 不能为空")

        # 校验项目归属
        project = await ProjectDB.get_project_by_id(body.project_id, user_id=user['id'])
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在或无权访问")

        # 校验 session 归属
        is_valid = await SessionDB.verify_session(body.session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        # 绑定
        await SessionDB.update_session_project(body.session_id, body.project_id)
        return {"success": True, "message": "会话已绑定到项目"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("绑定会话到项目失败: %s", e)
        raise HTTPException(status_code=500, detail=f"绑定失败: {str(e)}")


@router.put('/session/unbind')
async def unbind_session_from_project(request: Request, body: BindSessionRequest):
    """解除会话与项目的关联（"不使用文件夹"）

    流程：调 SessionDB.update_session_project(session_id, None)

    Args:
        body.session_id: 目标会话 ID

    Returns:
        dict: success / message
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        # 校验 session 归属
        is_valid = await SessionDB.verify_session(body.session_id, username)
        if not is_valid:
            raise HTTPException(status_code=403, detail="无权访问该会话")

        await SessionDB.update_session_project(body.session_id, None)
        return {"success": True, "message": "会话已解除项目关联"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("解除会话项目关联失败: %s", e)
        raise HTTPException(status_code=500, detail=f"解除失败: {str(e)}")


@router.delete('/{project_id}/delete')
async def delete_project(project_id: int, request: Request):
    """删除项目

    删除项目元数据，并将当前用户下所有绑定到该项目的会话解除关联。

    Args:
        project_id: 项目主键 ID。

    Returns:
        dict: success / message
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        # 先解绑当前用户下关联到该项目的会话
        sessions = await SessionDB.get_user_sessions(user['id'])
        for session in sessions:
            if session.get('project_id') == project_id:
                await SessionDB.update_session_project(session['session_id'], None)

        # 删除项目元数据
        deleted = await ProjectDB.delete_project(project_id, user_id=user['id'])
        if not deleted:
            raise HTTPException(status_code=404, detail="项目不存在或无权访问")

        return {"success": True, "message": "项目已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除项目失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除项目失败: {str(e)}")


@router.put('/{project_id}/rename')
async def rename_project(project_id: int, request: Request, body: RenameProjectRequest):
    """重命名项目

    Args:
        project_id: 项目主键 ID。
        body.name: 新的项目名称（1-50 字符）。

    Returns:
        dict: success / message / project
    """
    try:
        username = request.state.username
        if not username:
            raise HTTPException(status_code=401, detail="未认证")
        user = await UserDB.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        if len(new_name) > 50:
            raise HTTPException(status_code=400, detail="项目名称不能超过 50 字符")

        updated = await ProjectDB.rename_project(
            project_id,
            new_name=new_name,
            user_id=user['id'],
        )
        if not updated:
            raise HTTPException(status_code=404, detail="项目不存在或无权访问")

        return {
            "success": True,
            "message": "项目名称已更新",
            "project": _project_to_dict(updated),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("重命名项目失败: %s", e)
        raise HTTPException(status_code=500, detail=f"重命名项目失败: {str(e)}")
