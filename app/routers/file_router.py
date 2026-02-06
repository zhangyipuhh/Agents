#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件上传下载路由模块

本模块定义了文件上传下载相关的API路由。
主要功能包括：
- 批量上传文件
- 下载文件
- 获取文件信息
- 删除文件
- 列出所有文件
- 支持会话隔离，每个会话的文件存储在独立目录中

注意：会话的创建和删除请使用 /api/session 路由

Date: 2026/2/6
Author: 张镒谱
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from typing import List
from pydantic import BaseModel
from app.utils.files.fileTransfer import FileTransfer


class FileDeleteRequest(BaseModel):
    """
    文件删除请求模型
    
    定义删除文件时需要的数据结构。
    
    Attributes:
        uuids (List[str]): 要删除的文件UUID列表
    """
    uuids: List[str]


class FileDeleteResponse(BaseModel):
    """
    文件删除响应模型
    
    定义删除操作后的响应数据结构。
    
    Attributes:
        success (List[str]): 删除成功的文件UUID列表
        failed (List[dict]): 删除失败的文件列表，包含UUID和失败原因
    """
    success: List[str]
    failed: List[dict]


class FileInfo(BaseModel):
    """
    文件信息模型
    
    定义文件信息的数据结构。
    
    Attributes:
        uuid (str): 文件的UUID
        filename (str): 文件名
        size (int): 文件大小（字节）
        created_time (float): 文件创建时间戳
        modified_time (float): 文件修改时间戳
    """
    uuid: str
    filename: str
    size: int
    created_time: float
    modified_time: float


class FileListResponse(BaseModel):
    """
    文件列表响应模型
    
    定义文件列表的响应数据结构。
    
    Attributes:
        files (List[FileInfo]): 文件信息列表
        count (int): 文件总数
    """
    files: List[FileInfo]
    count: int


class FileUploadResponse(BaseModel):
    """
    文件上传响应模型
    
    定义上传操作后的响应数据结构。
    
    Attributes:
        fileids (List[dict]): 上传成功后的文件ID列表，每个元素包含 id 和 filename
        count (int): 上传成功的文件数量
    """
    fileids: List[dict]
    count: int


# 创建文件传输工具实例
file_transfer = FileTransfer()

# 创建API路由实例，设置前缀和标签
# prefix='/api/files': 所有路由路径将以/api/files开头
# tags=['File Management']: 用于API文档分组，便于在Swagger UI中查看
router = APIRouter(prefix='/api/files', tags=['File Management'])


@router.post('/upload', response_model=FileUploadResponse)
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    """
    批量上传文件API端点
    
    接收多个文件并上传到服务器，每个文件使用UUID命名。
    支持同时上传多个文件，返回所有上传文件的ID和文件名列表。
    文件将存储在指定会话的目录中，实现会话隔离。
    
    工作流程：
    1. 接收多个文件和会话ID
    2. 为每个文件生成UUID文件名
    3. 将文件保存到对应会话的上传目录
    4. 返回所有文件的ID（无扩展名）和文件名（无扩展名）列表
    
    Args:
        request (Request): FastAPI 请求对象，包含 session_id
        files (List[UploadFile]): 要上传的文件列表，使用FastAPI的File表单数据
        
    Returns:
        FileUploadResponse: 包含上传成功的文件ID列表和数量，每个文件包含 id 和 filename
        
    Raises:
        HTTPException: 当上传过程中发生错误时抛出500错误
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        uploaded_files = await file_transfer.upload_files(files, session_id)
        return FileUploadResponse(
            fileids=uploaded_files,
            count=len(uploaded_files)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get('/download/{file_uuid}')
async def download_file(request: Request, file_uuid: str):
    """
    下载文件API端点
    
    根据文件UUID和会话ID下载对应的文件。
    
    工作流程：
    1. 接收文件UUID和会话ID参数
    2. 验证文件是否存在
    3. 返回文件内容
    
    Args:
        request (Request): FastAPI 请求对象，包含 session_id
        file_uuid (str): 要下载的文件UUID
        
    Returns:
        FileResponse: 文件响应对象，包含文件内容
        
    Raises:
        HTTPException: 当文件不存在时抛出404错误
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        file_path = file_transfer.get_file_path(file_uuid, session_id)
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type='application/octet-stream'
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.get('/info/{file_uuid}', response_model=FileInfo)
async def get_file_info(request: Request, file_uuid: str):
    """
    获取文件信息API端点
    
    根据文件UUID和会话ID获取文件的详细信息。
    
    工作流程：
    1. 接收文件UUID和会话ID参数
    2. 验证文件是否存在
    3. 返回文件信息
    
    Args:
        request (Request): FastAPI 请求对象，包含 session_id
        file_uuid (str): 要查询的文件UUID
        
    Returns:
        FileInfo: 包含文件详细信息的对象
        
    Raises:
        HTTPException: 当文件不存在时抛出404错误
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        file_info = await file_transfer.get_file_info(file_uuid, session_id)
        return FileInfo(**file_info)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件信息失败: {str(e)}")


@router.delete('/delete', response_model=FileDeleteResponse)
async def delete_files(request: Request, delete_request: FileDeleteRequest):
    """
    批量删除文件API端点
    
    根据文件UUID列表批量删除文件。
    
    工作流程：
    1. 接收要删除的文件UUID列表和会话ID
    2. 逐个删除文件
    3. 返回删除结果，包括成功和失败的文件列表
    
    Args:
        request (Request): FastAPI 请求对象，包含 session_id
        delete_request (FileDeleteRequest): 包含要删除的文件UUID列表的请求对象
        
    Returns:
        FileDeleteResponse: 包含删除结果的响应对象
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        result = await file_transfer.delete_files(delete_request.uuids, session_id)
        return FileDeleteResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get('/list', response_model=FileListResponse)
async def list_files(request: Request):
    """
    列出所有文件API端点
    
    获取指定会话的所有已上传文件列表。
    
    工作流程：
    1. 扫描指定会话的上传目录
    2. 获取所有文件的信息
    3. 返回文件列表
    
    Args:
        request (Request): FastAPI 请求对象，包含 session_id
        
    Returns:
        FileListResponse: 包含所有文件信息的列表和总数
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        files = await file_transfer.list_files(session_id)
        return FileListResponse(
            files=[FileInfo(**file) for file in files],
            count=len(files)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")
