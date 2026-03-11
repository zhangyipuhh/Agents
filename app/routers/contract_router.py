#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同审批路由模块

本模块定义了合同审批解析附件智能体相关的 API 路由。
主要功能包括：
- 上传并解析合同文件
- 上传并解析 Base64 编码的合同文件
- 获取当前 session 的缓存数据

Date: 2026-03-05
Author: AI Assistant
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form
from typing import List, Optional
from pydantic import BaseModel
from app.utils.files.fileTransfer import FileTransfer
from app.agents.subgraphs.audit_document.agent import get_audit_document_agent
from app.utils.memory.document_memory_store import document_memory_store


class Base64FileSchema(BaseModel):
    file_type: str
    file_content: str


class Base64UploadRequest(BaseModel):
    prompt: str
    files: List[Base64FileSchema]


class ContractDataResponse(BaseModel):
    contract_data: List[dict]
    transaction_data: List[dict]
    meeting_data: List[dict]
    count: int


class ParsedResult(BaseModel):
    file_id: str
    file_type: str
    status: str


class FileUploadResponse(BaseModel):
    fileids: List[dict]
    count: int
    parsed_results: List[ParsedResult]


file_transfer = FileTransfer()
router = APIRouter(prefix='/api/contract', tags=['Contract Audit'])


@router.post('/uploadfile', response_model=FileUploadResponse)
async def upload_contract_files(
    request: Request,
    prompt: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    上传并解析合同文件

    Args:
        request: FastAPI 请求对象
        prompt: 用户提示词（如"我上传的是合同"）
        files: 要上传的文件列表

    Returns:
        FileUploadResponse: 包含解析结果
    """
    try:
        session_id = getattr(request.state, "session_id", "default")

        uploaded_files = await file_transfer.upload_files(files, session_id)

        file_paths = []
        file_ids = []
        for file_info in uploaded_files:
            file_path = file_transfer.get_file_path(file_info["id"], session_id)
            file_paths.append(str(file_path))
            file_ids.append(file_info["id"])

        agent = get_audit_document_agent()
        result = agent.invoke(
            prompt=prompt,
            file_paths=file_paths,
            file_ids=file_ids,
            session_id=session_id
        )

        parsed_results = []
        messages = result.get("messages", [])
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                parsed_results.append(ParsedResult(
                    file_id=file_ids[0] if file_ids else "",
                    file_type="unknown",
                    status="parsed"
                ))

        if not parsed_results:
            for file_id in file_ids:
                parsed_results.append(ParsedResult(
                    file_id=file_id,
                    file_type="unknown",
                    status="parsed"
                ))

        return FileUploadResponse(
            fileids=uploaded_files,
            count=len(uploaded_files),
            parsed_results=parsed_results
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败：{str(e)}")


@router.post('/uploadfile-base64', response_model=FileUploadResponse)
async def upload_contract_base64(
    request: Request,
    upload_request: Base64UploadRequest
):
    """
    上传并解析 Base64 编码的合同文件

    Args:
        request: FastAPI 请求对象
        upload_request: 包含 base64 文件列表的请求对象

    Returns:
        FileUploadResponse: 包含解析结果
    """
    try:
        session_id = getattr(request.state, "session_id", "default")

        base64_files = []
        for file_info in upload_request.files:
            filename = f"temp_file.{file_info.file_type}"
            base64_files.append({
                "filename": filename,
                "base64_data": file_info.file_content
            })

        uploaded_files = await file_transfer.upload_base64_files(base64_files, session_id)

        file_paths = []
        file_ids = []
        for file_info in uploaded_files:
            file_path = file_transfer.get_file_path(file_info["id"], session_id)
            file_paths.append(str(file_path))
            file_ids.append(file_info["id"])

        agent = get_audit_document_agent()
        result = agent.invoke(
            prompt=upload_request.prompt,
            file_paths=file_paths,
            file_ids=file_ids,
            session_id=session_id
        )

        parsed_results = []
        for file_id in file_ids:
            parsed_results.append(ParsedResult(
                file_id=file_id,
                file_type="unknown",
                status="parsed"
            ))

        return FileUploadResponse(
            fileids=uploaded_files,
            count=len(uploaded_files),
            parsed_results=parsed_results
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Base64 上传失败：{str(e)}")


@router.get('/data', response_model=ContractDataResponse)
async def get_contract_data(request: Request):
    """
    获取当前 session 的合同解析数据

    Args:
        request: FastAPI 请求对象

    Returns:
        ContractDataResponse: 包含合同数组、成交确认书数组和会议纪要数组
    """
    try:
        session_id = getattr(request.state, "session_id", "default")

        documents = document_memory_store.get_all_documents(session_id)

        contract_data = documents.get("contract_data", [])
        transaction_data = documents.get("transaction_data", [])
        meeting_data = documents.get("meeting_data", [])

        count = len(contract_data) + len(transaction_data) + len(meeting_data)

        return ContractDataResponse(
            contract_data=contract_data,
            transaction_data=transaction_data,
            meeting_data=meeting_data,
            count=count
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据失败：{str(e)}")
