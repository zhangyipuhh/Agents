#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
会话管理路由模块

本模块定义了会话管理相关的API路由。
主要功能包括：
- 生成新会话
- 删除会话

Date: 2026/2/6
Author: 张镒谱
"""
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.files.fileTransfer import FileTransfer


class SessionCreateResponse(BaseModel):
    """
    会话创建响应模型
    
    定义创建会话操作后的响应数据结构。
    
    Attributes:
        session_id (str): 生成的会话ID
        message (str): 操作结果消息
    """
    session_id: str
    message: str


class SessionDeleteResponse(BaseModel):
    """
    会话删除响应模型
    
    定义删除会话操作后的响应数据结构。
    
    Attributes:
        success (bool): 删除是否成功
        message (str): 操作结果消息
    """
    success: bool
    message: str


# 创建文件传输工具实例
file_transfer = FileTransfer()

# 创建API路由实例，设置前缀和标签
# prefix='/api/session': 所有路由路径将以/api/session开头
# tags=['Session Management']: 用于API文档分组，便于在Swagger UI中查看
router = APIRouter(prefix='/api/session', tags=['Session Management'])


@router.post('/create', response_model=SessionCreateResponse)
async def create_session():
    """
    创建新会话API端点
    
    生成一个新的会话ID，用于隔离不同用户的文件。
    
    工作流程：
    1. 生成唯一的会话ID（使用UUID）
    2. 创建对应的会话目录
    3. 返回会话ID
    
    Returns:
        SessionCreateResponse: 包含生成的会话ID和成功消息
        
    Raises:
        HTTPException: 当创建会话失败时抛出500错误
    """
    try:
        session_id = str(uuid.uuid4())
        session_dir = file_transfer._get_session_dir(session_id)
        
        return SessionCreateResponse(
            session_id=session_id,
            message="会话创建成功"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")


@router.delete('/delete/{session_id}', response_model=SessionDeleteResponse)
async def delete_session(session_id: str):
    """
    删除会话API端点
    
    删除指定会话的整个目录及其所有文件。
    
    工作流程：
    1. 接收会话ID参数
    2. 删除该会话目录及其所有文件
    3. 返回删除结果
    
    Args:
        session_id (str): 要删除的会话ID
        
    Returns:
        SessionDeleteResponse: 包含删除结果的响应对象
        
    Raises:
        HTTPException: 当删除过程中发生错误时抛出500错误
    """
    try:
        success = await file_transfer.delete_session(session_id)
        return SessionDeleteResponse(
            success=success,
            message="会话删除成功" if success else "会话不存在"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")
