#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同审批路由模块

本模块定义了合同审批相关的API路由。
主要功能包括：
- 上传并解析合同文件
- 上传并解析Base64编码的合同文件
- 获取当前会话的缓存数据

Date: 2026/3/4
Author: 张镒谱
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form
from typing import List, Dict, Any
from pydantic import BaseModel
from app.utils.files.fileTransfer import FileTransfer
from app.agents.subgraphs.audit_document.agent import AuditDocumentAgent
from app.utils.memory.document_memory_store import DocumentMemoryStore
from langchain.messages import HumanMessage


class Base64FileSchema(BaseModel):
    """
    Base64 文件上传 schema
    
    定义通过 base64 编码上传文件的数据结构。
    
    Attributes:
        file_type (str): 文件类型（如："pdf", "docx", "doc"）
        file_content (str): Base64 编码的文件内容
    """
    file_type: str  # 文件类型：pdf, docx, doc 等
    file_content: str  # Base64 编码的文件内容


class Base64UploadRequest(BaseModel):
    """
    Base64 批量文件上传请求模型
    
    定义通过 base64 编码批量上传文件的请求数据结构。
    
    Attributes:
        prompt (str): 用户提示词（如"我上传的是合同"）
        files (List[Base64FileSchema]): 要上传的文件列表
    """
    prompt: str  # 用户提示词
    files: List[Base64FileSchema]


class FileUploadResponse(BaseModel):
    """
    文件上传响应模型
    
    定义上传操作后的响应数据结构。
    
    Attributes:
        fileids (List[dict]): 上传成功后的文件ID列表，每个元素包含 id 和 filename
        count (int): 上传成功的文件数量
        parsed_results (Dict[str, Any]): 解析结果
    """
    fileids: List[dict]
    count: int
    parsed_results: Dict[str, Any]


class ContractDataResponse(BaseModel):
    """
    合同数据响应模型
    
    定义获取缓存数据的响应数据结构。
    
    Attributes:
        contract_data (List[Dict[str, Any]]): 合同解析结果数组
        transaction_data (List[Dict[str, Any]]): 成交确认书解析结果数组
        meeting_data (List[Dict[str, Any]]): 会议纪要解析结果数组
        count (int): 总文件数
    """
    contract_data: List[Dict[str, Any]]
    transaction_data: List[Dict[str, Any]]
    meeting_data: List[Dict[str, Any]]
    count: int


# 创建文件传输工具实例
file_transfer = FileTransfer()

# 创建智能体实例
audit_agent = AuditDocumentAgent()

# 创建文档存储实例
document_store = DocumentMemoryStore()

# 创建API路由实例
router = APIRouter(prefix='/api/contract', tags=['Contract Audit'])


@router.post('/uploadfile', response_model=FileUploadResponse)
async def upload_contract_files(
    request: Request,
    prompt: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    上传并解析合同文件
    
    工作流程：
    1. 从 request.state.session_id 获取会话 ID
    2. 使用 FileTransfer 保存上传的文件
    3. 调用智能体解析文件（文件路径和 file_id 存储在 LangGraph state 中）
    4. 将解析结果存入长期记忆（使用 session_id 作为 key，存储 file_id 和文件类型）
    5. 返回解析结果
    
    Args:
        request (Request): FastAPI 请求对象
        prompt (str): 用户提示词（如"我上传的是合同"）
        files (List[UploadFile]): 要上传的文件列表
        
    Returns:
        FileUploadResponse: 包含解析结果
    """
    try:
        # 从 request.state 获取 session_id（由中间件注入）
        session_id = getattr(request.state, "session_id", "default")
        
        # 使用 FileTransfer 上传文件
        uploaded_files = await file_transfer.upload_files(files, session_id)
        
        # 构建文件路径列表和 file_id 列表
        file_paths = []
        file_ids = []
        for file_info in uploaded_files:
            file_path = file_transfer.get_file_path(file_info["id"], session_id)
            file_paths.append(str(file_path))
            file_ids.append(file_info["id"])
        
        # 调用智能体解析文件
        state = {
            "session_id": session_id,
            "file_paths": file_paths,
            "file_id": file_ids[0] if file_ids else None,
            "messages": [HumanMessage(content=prompt)]
        }
        
        result = audit_agent.run(state)
        
        # 构建响应
        return FileUploadResponse(
            fileids=uploaded_files,
            count=len(uploaded_files),
            parsed_results={
                "contract_data": result.get("contract_data", []),
                "transaction_data": result.get("transaction_data", []),
                "meeting_data": result.get("meeting_data", [])
            }
        )
    except HTTPException:
        raise
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
        request (Request): FastAPI 请求对象
        upload_request (Base64UploadRequest): 包含 base64 文件列表的请求对象
        
    Returns:
        FileUploadResponse: 包含解析结果
    """
    try:
        # 从 request.state 获取 session_id（由中间件注入）
        session_id = getattr(request.state, "session_id", "default")
        
        # 准备 Base64 文件数据
        base64_files = []
        for file_info in upload_request.files:
            filename = f"temp_file.{file_info.file_type}"
            base64_files.append({
                "filename": filename,
                "base64_data": file_info.file_content
            })
        
        # 使用 FileTransfer 上传 Base64 文件
        uploaded_files = await file_transfer.upload_base64_files(base64_files, session_id)
        
        # 构建文件路径列表和 file_id 列表
        file_paths = []
        file_ids = []
        for file_info in uploaded_files:
            file_path = file_transfer.get_file_path(file_info["id"], session_id)
            file_paths.append(str(file_path))
            file_ids.append(file_info["id"])
        
        # 调用智能体解析文件
        state = {
            "session_id": session_id,
            "file_paths": file_paths,
            "file_id": file_ids[0] if file_ids else None,
            "messages": [HumanMessage(content=upload_request.prompt)]
        }
        
        result = audit_agent.run(state)
        
        # 构建响应
        return FileUploadResponse(
            fileids=uploaded_files,
            count=len(uploaded_files),
            parsed_results={
                "contract_data": result.get("contract_data", []),
                "transaction_data": result.get("transaction_data", []),
                "meeting_data": result.get("meeting_data", [])
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Base64 上传失败：{str(e)}")


@router.get('/data', response_model=ContractDataResponse)
async def get_contract_data(request: Request):
    """
    获取当前 session 的合同解析数据
    
    Args:
        request (Request): FastAPI 请求对象
        
    Returns:
        ContractDataResponse: 包含合同数组和成交确认书数组
    """
    try:
        # 从 request.state 获取 session_id（由中间件注入）
        session_id = getattr(request.state, "session_id", "default")
        
        # 从长期记忆中获取数据
        documents = document_store.get_all_documents(session_id)
        
        # 计算总文件数
        total_count = len(documents["contract_data"]) + len(documents["transaction_data"]) + len(documents["meeting_data"])
        
        # 构建响应
        return ContractDataResponse(
            contract_data=documents["contract_data"],
            transaction_data=documents["transaction_data"],
            meeting_data=documents["meeting_data"],
            count=total_count
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据失败：{str(e)}")
