#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同审批路由模块

本模块定义了合同审批解析附件智能体相关的 API 路由。
主要功能包括：
- 文件上传处理服务：将上传的合同文件存储到指定目录，同时将 file_id 与文件路径的映射关系存储到 LangGraph Store
  - file_id: 存储文件唯一标识符与文件路径的映射，结构为 {file_id: file_path, ...}
- 图片转换处理服务：将 PDF 文件转换为图片，同时将 image_paths 与图片 base64 数据的映射关系存储到 LangGraph Store
  - image_paths: 存储图片唯一标识符与 base64 数据的映射，结构为 {image_id: base64_data, ...}
- 聊天对话服务：与合同审批AI助手进行多轮对话

Date: 2026-03-18
Author: 张镒谱
"""

import logging
import base64
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from typing import List, Optional, Union
from pydantic import BaseModel

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

logger = logging.getLogger(__name__)

from app.shared.utils.files.file_upload_handler import FileUploadHandler
from app.features.contract_host_agent.HtAgent import HtAgent
from app.features.contract_document_agent.DocAgent import DocAgent
from app.features.contract_approval_agent.ApprovalAgent import ApprovalAgent


_checkpointer = MemorySaver()
store = InMemoryStore()
store_id = "contract_audit_store"

file_upload_handler = FileUploadHandler()
router = APIRouter(prefix='/api/contract', tags=['Contract Audit'])

# 初始化 HtAgent 实例
ht_agent = HtAgent(
    checkpointer=_checkpointer,
    store=store,
    store_id=store_id,
)

# 初始化 DocAgent 实例
doc_agent = DocAgent(
    checkpointer=_checkpointer,
    store=store,
    store_id=store_id,
)

approval_agent = ApprovalAgent(
    checkpointer=_checkpointer,
    store=store,
    store_id=store_id,
)


class FileUploadResponse(BaseModel):
    fileids: List[dict]
    count: int
    image_groups: List[List[str]]


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class GetStoreValueRequest(BaseModel):
    id: str
    session_id: Optional[str] = None
    host_session_id: Optional[str] = None


class GetStoreValueResponse(BaseModel):
    value: Optional[Union[dict, List[dict]]]
    id: str


class DocChatRequest(BaseModel):
    message: str
    host_session_id: Optional[str] = None
    image_ids: Optional[List[str]] = None


class DocChatResponse(BaseModel):
    response: str
    session_id: str
    host_session_id: str


class ApprovalChatRequest(BaseModel):
    message: str
    host_session_id: Optional[str] = None


class ApprovalChatResponse(BaseModel):
    response: str
    session_id: str


class DownloadContractRequest(BaseModel):
    host_session_id: str


class DownloadContractResponse(BaseModel):
    file_base64: str
    file_name: str
    host_session_id: str


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


@router.post('/chat', response_model=ChatResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest
):
    """
    合同审批聊天接口
    
    与合同审批AI助手进行对话，支持多轮对话和合同审批流程。
    
    Args:
        request: FastAPI 请求对象
        chat_request: 聊天请求，包含用户消息和可选的会话ID
        
    Returns:
        ChatResponse: 包含AI助手的回复和会话ID
    """
    try:
        # 获取 session_id，优先使用请求体中的，否则从 request.state 获取
        session_id = chat_request.session_id or getattr(request.state, "session_id", "default")
        
        logger.debug(f"[DEBUG] chat 请求: message={chat_request.message}, session_id={session_id}")
        
        # 调用 HtAgent 进行对话
        result = await ht_agent.invoke(
            user_input=chat_request.message,
            session_id=session_id,
        )
        
        return ChatResponse(
            response=result,
            session_id=session_id
        )
        
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] chat 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"对话处理失败：{str(e)}")


@router.post('/doc_chat', response_model=DocChatResponse)
async def doc_chat(
    request: Request,
    doc_chat_request: DocChatRequest
):
    
    """
    文档处理聊天接口
    
    与文档处理AI助手进行对话，支持多轮对话和文档处理流程。
    
    Args:
        request: FastAPI 请求对象
        doc_chat_request: 聊天请求，包含用户消息、会话ID和发起会话ID
        
    Returns:
        DocChatResponse: 包含AI助手的回复、会话ID和发起会话ID
    """
    try:

        session_id = getattr(request.state, "session_id", "default")
        host_session_id = doc_chat_request.host_session_id or session_id
        
        logger.debug(f"[DEBUG] doc_chat 请求: message={doc_chat_request.message}, session_id={session_id}, host_session_id={host_session_id}")
        
        result = await doc_agent.invoke(
            user_input=doc_chat_request.message,
            session_id=session_id,
            host_session_id=host_session_id,
            image_ids=doc_chat_request.image_ids or [],
        )
        
        return DocChatResponse(
            response=result,
            session_id=session_id,
            host_session_id=host_session_id
        )
        
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] doc_chat 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"文档对话处理失败：{str(e)}")


@router.post('/approval_chat', response_model=ApprovalChatResponse)
async def approval_chat(
    request: Request,
    approval_chat_request: ApprovalChatRequest
):
    """
    审批处理聊天接口
    
    与审批处理AI助手进行对话，支持多轮对话和审批处理流程。
    
    Args:
        request: FastAPI 请求对象
        approval_chat_request: 聊天请求，包含用户消息、会话ID和发起会话ID
        
    Returns:
        ApprovalChatResponse: 包含AI助手的回复、会话ID和发起会话ID
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        host_session_id = approval_chat_request.host_session_id or session_id
        
        logger.debug(f"[DEBUG] approval_chat 请求: message={approval_chat_request.message}, session_id={session_id}, host_session_id={host_session_id}")
        
        result = await approval_agent.invoke(
            user_input=approval_chat_request.message,
            session_id=session_id,
            host_session_id=host_session_id,
        )
        
        return ApprovalChatResponse(
            response=result,
            session_id=session_id,
            host_session_id=host_session_id
        )
        
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] approval_chat 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"审批对话处理失败：{str(e)}")


@router.post('/store/value', response_model=GetStoreValueResponse)
async def get_store_value(
    request: Request,
    body: GetStoreValueRequest
):
    """
    根据 id 获取 store 中存储的值
    
    Args:
        request: FastAPI 请求对象
        body: 包含 id 和可选 session_id 的请求对象
        
    Returns:
        GetStoreValueResponse: 包含存储的值和 id
    """
    try:
        # 获取 session_id，优先使用请求体中的，否则从 request.state 获取
        session_id = body.session_id or getattr(request.state, "session_id", "default")
        
        # 使用 store.get 方法获取存储的值
        # namespace 使用 (store_id, session_id)，key 使用传入的 id
        result = store.get(
            namespace=(store_id,),
            key=body.id
        )
        
        # 提取 value 值
        value = result.value if result else None
        
        logger.info(f"[INFO] get_store_value 方法 ，store_id: {store_id}， id: {body.id}， value: {value}")
        
        return GetStoreValueResponse(
            value=value,
            id=body.id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取存储值失败：{str(e)}")


@router.post('/download_contract', response_model=DownloadContractResponse)
async def download_contract(
    request: Request,
    download_request: DownloadContractRequest
):
    """
    下载合同文件接口
    
    根据 host_session_id 获取对应的合同文件，并以 base64 编码返回。
    
    Args:
        request: FastAPI 请求对象
        download_request: 包含 host_session_id 的请求对象
        
    Returns:
        DownloadContractResponse: 包含 base64 编码的文件内容、文件名和 host_session_id
    """
    try:
        host_session_id = download_request.host_session_id
        
        result = store.get(
            namespace=(store_id,),
            key=f"contract/path/{host_session_id}"
        )
        
        if not result or not result.value:
            raise HTTPException(status_code=404, detail="未找到合同文件路径记录")
        
        file_path = result.value
        file_path_obj = Path(file_path)
        
        if not file_path_obj.exists():
            raise HTTPException(status_code=404, detail=f"合同文件不存在: {file_path}")
        
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        
        file_base64 = base64.b64encode(file_bytes).decode("utf-8")
        file_name = file_path_obj.name
        
        logger.info(f"[INFO] download_contract 成功: host_session_id={host_session_id}, file_path={file_path}")
        
        return DownloadContractResponse(
            file_base64=file_base64,
            file_name=file_name,
            host_session_id=host_session_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] download_contract 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"下载合同失败：{str(e)}")



