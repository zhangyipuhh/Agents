#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同审批路由模块

本模块定义了合同审批解析附件智能体相关的 API 路由。
主要功能包括：
- 文件上传处理服务

Date: 2026-03-18
Author: AI Assistant
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from typing import List
from pydantic import BaseModel

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.utils.files.file_upload_handler import FileUploadHandler


_checkpointer = MemorySaver()
store = InMemoryStore()
store_id = "contract_audit_store"

file_upload_handler = FileUploadHandler()
router = APIRouter(prefix='/api/contract', tags=['Contract Audit'])


class FileUploadResponse(BaseModel):
    fileids: List[dict]
    count: int
    image_groups: List[List[str]]


@router.post('/uploadfile', response_model=FileUploadResponse)
async def upload_contract_files(
    request: Request,
    files: List[UploadFile] = File(...)
):
    """
    上传并处理合同文件
    
    Args:
        request: FastAPI 请求对象
        files: 要上传的文件列表
        
    Returns:
        FileUploadResponse: 包含处理结果
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        
        result = await file_upload_handler.process_files(
            store=store,
            store_id=store_id,
            session_id=session_id,
            files=files
        )
        
        file_ids = result.get("doc", [])
        image_groups = result.get("img", [])
        
        uploaded_files = [
            {"id": file_id, "file_type": "doc"}
            for file_id in file_ids
        ]
        
        return FileUploadResponse(
            fileids=uploaded_files,
            count=len(uploaded_files),
            image_groups=image_groups
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")
