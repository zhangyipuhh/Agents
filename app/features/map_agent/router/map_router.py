#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
地图智能体路由模块

本模块定义了地图智能体相关的 API 路由。
主要功能包括：
- 流式聊天对话服务：与地图AI助手进行多轮对话，支持实时流式输出

Date: 2026-04-14
Author: AI Assistant
"""

import logging
import json
import os
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from typing import AsyncGenerator, Optional
from pydantic import BaseModel
from urllib.parse import quote

from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from langchain_core.messages import ToolMessage

from app.features.map_agent.MapAgent import MapAgent
from app.core.format.stream import stream_format_context
from app.features.map_agent.config.prompts import KNOWLEDGE_SYSTEM_PROMPT
from app.features.map_agent.config.MapAgentContext import MapAgentContext
from app.shared.utils.files.doc_converter import convert_doc_to_docx, check_conversion_support, get_libreoffice_installation_guide
logger = logging.getLogger(__name__)

# 初始化 MemorySaver 和 InMemoryStore
_checkpointer = MemorySaver()
store = InMemoryStore()
store_id = "map_agent_store"

# 创建 API 路由实例
router = APIRouter(prefix='/api/map', tags=['Map Agent'])

# 初始化 MapAgent 实例
map_agent = MapAgent(
    checkpointer=_checkpointer,
    store=store,
    store_id=store_id,
)


# Knowledge 目录路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
KNOWLEDGE_DIR = os.path.join(_PROJECT_ROOT, "data", "Knowledge")
METADATA_FILE = os.path.join(KNOWLEDGE_DIR, "metadata.json")
TMP_DIR = os.path.join(KNOWLEDGE_DIR, "tmp")

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}

TEXT_EXTENSIONS = {"md", "markdown", "txt", "log", "csv", "json"}
BINARY_EXTENSIONS = {
    "pdf", "docx", "doc", "xlsx", "xls",
    "jpg", "jpeg", "png", "gif", "bmp", "webp", "svg",
}

TEXT_FALLBACK_MODE = {
    "csv": "excel",
}

PREVIEW_MODE_MAP = {
    "md": "markdown",
    "markdown": "markdown",
    "txt": "text",
    "log": "text",
    "csv": "text",
    "json": "text",
    "pdf": "pdf",
    "docx": "docx",
    "doc": "docx",
    "pptx": "pptx",
    "ppt": "pptx",
    "xlsx": "excel",
    "xls": "excel",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "gif": "image",
    "bmp": "image",
    "webp": "image",
    "svg": "image",
}


def _scan_knowledge_dir() -> dict:
    """
    扫描 Knowledge 目录，生成 metadata 结构

    排除 tmp 子目录和 metadata.json 本身，处理文件夹层级结构，
    对于 md 文件尝试从内容中提取关键字和简介。

    Returns:
        dict: 包含 folders 和 files 的 metadata 字典
    """
    folders = []
    files = []

    # 确保 tmp 目录存在
    os.makedirs(TMP_DIR, exist_ok=True)

    for root, dirs, filenames in os.walk(KNOWLEDGE_DIR):
        # 排除 tmp 目录
        dirs[:] = [d for d in dirs if d != "tmp"]

        rel_root = os.path.relpath(root, KNOWLEDGE_DIR)
        if rel_root == ".":
            rel_root = ""

        # 收集文件夹信息
        if rel_root:
            folder_info = {
                "name": os.path.basename(rel_root),
                "path": rel_root,
                "children": []
            }
            folders.append(folder_info)

        for filename in filenames:
            # 排除 metadata.json 本身
            if filename == "metadata.json":
                continue

            file_path = os.path.join(root, filename)
            rel_path = os.path.join(rel_root, filename) if rel_root else filename
            # 统一使用正斜杠
            rel_path = rel_path.replace("\\", "/")

            file_size = os.path.getsize(file_path)
            file_ext = os.path.splitext(filename)[1].lstrip(".")
            file_date = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d")

            keywords = []
            summary = ""

            # 对于 md 文件，尝试从内容中提取关键字和简介
            if file_ext == "md":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # 提取关键字：查找 "## 关键字" 或 "## 关键词" 后面的内容
                    import re
                    kw_match = re.search(r"##\s*(?:关键字|关键词)\s*\n+(.+?)(?:\n#|\n##|\Z)", content, re.DOTALL)
                    if kw_match:
                        kw_text = kw_match.group(1).strip()
                        keywords = [k.strip() for k in re.split(r"[、，,\n]", kw_text) if k.strip()]

                    # 提取简介：查找 "## 概述" 或 "## 简介" 后面的内容
                    sum_match = re.search(r"##\s*(?:概述|简介|摘要)\s*\n+(.+?)(?:\n#|\n##|\Z)", content, re.DOTALL)
                    if sum_match:
                        summary = sum_match.group(1).strip().split("\n")[0]
                except Exception as e:
                    logger.warning(f"读取文件 {rel_path} 内容失败: {e}")

            file_info = {
                "name": filename,
                "path": rel_path,
                "size": file_size,
                "type": file_ext,
                "keywords": keywords,
                "date": file_date,
                "summary": summary,
                "folder": rel_root.replace("\\", "/") if rel_root else ""
            }
            files.append(file_info)

    return {"folders": folders, "files": files}


@router.get('/knowledge/files')
async def get_knowledge_files():
    """
    获取知识库文件元数据

    读取 metadata.json，如果不存在则自动扫描 Knowledge 目录生成。
    扫描时排除 tmp 子目录和 metadata.json 本身。

    Returns:
        dict: 包含 folders 和 files 的元数据
    """
    try:
        # 确保 tmp 目录存在
        os.makedirs(TMP_DIR, exist_ok=True)

        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        else:
            metadata = _scan_knowledge_dir()
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

        return metadata

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] get_knowledge_files 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取知识库文件列表失败：{str(e)}")


INLINE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}

@router.get('/knowledge/file-download')
async def download_knowledge_file(path: str):
    try:
        if not path or ".." in path or os.path.isabs(path):
            raise HTTPException(status_code=400, detail="非法文件路径")

        actual_path = os.path.normpath(os.path.join(KNOWLEDGE_DIR, path))
        if not actual_path.startswith(os.path.normpath(KNOWLEDGE_DIR)):
            raise HTTPException(status_code=400, detail="非法文件路径")

        if not os.path.isfile(actual_path):
            raise HTTPException(status_code=404, detail="文件不存在")

        ext = os.path.splitext(path)[1].lower()
        media_type = MIME_TYPES.get(ext, "application/octet-stream")

        if ext in INLINE_EXTENSIONS:
            return FileResponse(
                path=actual_path,
                media_type=media_type,
                content_disposition_type="inline",
            )

        return FileResponse(
            path=actual_path,
            media_type=media_type,
            filename=os.path.basename(actual_path),
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] download_knowledge_file 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"文件下载失败：{str(e)}")


@router.get('/knowledge/file-preview')
async def get_knowledge_file_preview(path: str):
    """
    获取知识库文件内容预览

    根据文件相对路径读取 Knowledge 目录下的文件内容，
    包含路径安全校验防止目录遍历攻击。
    对于 .doc 文件，会自动转换为 .docx 格式以支持预览。

    Args:
        path: 文件相对路径（query parameter）

    Returns:
        dict: 包含 path、content、type、preview_mode、file_url、file_name 的文件信息
    """
    try:
        logger.info(f"[FILE PREVIEW] ====== 开始处理文件预览请求 ======")
        logger.info(f"[FILE PREVIEW] 接收到的 path 参数: '{path}'")
        
        if not path or ".." in path or os.path.isabs(path):
            raise HTTPException(status_code=400, detail="非法文件路径")

        actual_path = os.path.normpath(os.path.join(KNOWLEDGE_DIR, path))
        logger.info(f"[FILE PREVIEW] 计算的 actual_path: '{actual_path}'")
        
        if not actual_path.startswith(os.path.normpath(KNOWLEDGE_DIR)):
            raise HTTPException(status_code=400, detail="非法文件路径")

        if not os.path.isfile(actual_path):
            raise HTTPException(status_code=404, detail="文件不存在")

        file_ext = os.path.splitext(path)[1].lstrip(".").lower()
        file_name = os.path.basename(path)
        logger.info(f"[FILE PREVIEW] 解析的 file_ext: '{file_ext}', file_name: '{file_name}'")
        
        normalized_path = path.replace("\\", "/")
        preview_mode = PREVIEW_MODE_MAP.get(file_ext, "unsupported")
        logger.info(f"[FILE PREVIEW] 根据 file_ext '{file_ext}' 确定 preview_mode: '{preview_mode}'")
        
        file_url = f"/api/map/knowledge/file-download?path={quote(normalized_path)}"
        logger.info(f"[FILE PREVIEW] 生成的 file_url: '{file_url}'")
        converted = False

        if file_ext == "doc":
            support = check_conversion_support()
            if not support["pywin32"] and not support["libreoffice"]:
                logger.warning(f"[FILE PREVIEW] .doc 文件转换失败: 系统缺少 Word 或 LibreOffice")
                logger.info(f"[FILE PREVIEW] 安装指引: {get_libreoffice_installation_guide()}")
            
            converted_path, error = convert_doc_to_docx(actual_path)
            if converted_path and os.path.exists(converted_path):
                normalized_converted = f"tmp/{os.path.basename(converted_path)}"
                file_url = f"/api/map/knowledge/file-download?path={quote(normalized_converted)}"
                preview_mode = "docx"
                converted = True
                logger.info(f"[FILE PREVIEW] .doc 文件已转换: {actual_path} -> {converted_path}")
            else:
                logger.warning(f"[FILE PREVIEW] .doc 文件转换失败: {error}")
                preview_mode = "unsupported"

        result = {
            "path": normalized_path,
            "content": "",
            "type": file_ext,
            "preview_mode": preview_mode,
            "file_url": file_url,
            "file_name": file_name,
            "conversion_error": error if not converted and file_ext == "doc" else None,
            "installation_guide": get_libreoffice_installation_guide() if not converted and file_ext == "doc" else None
        }

        if file_ext in TEXT_EXTENSIONS:
            try:
                with open(actual_path, "r", encoding="utf-8") as f:
                    result["content"] = f.read()
                    logger.info(f"[FILE PREVIEW] 已读取文本内容，长度: {len(result['content'])} 字符")
            except (UnicodeDecodeError, UnicodeError):
                result["preview_mode"] = TEXT_FALLBACK_MODE.get(file_ext, "unsupported")
                logger.warning(f"[FILE PREVIEW] 文本读取失败，切换到 fallback 模式: {result['preview_mode']}")

        logger.info(f"[FILE PREVIEW] 最终返回结果: preview_mode={result['preview_mode']}, file_url={result['file_url']}, content长度={len(result['content'])}")
        logger.info(f"[FILE PREVIEW] ====== 文件预览请求处理完成 ======")
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] get_knowledge_file_preview 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取文件预览失败：{str(e)}")


class ChatRequest(BaseModel):
    """
    聊天请求模型

    定义用户发送给地图智能体的请求数据结构。

    Attributes:
        message (str): 用户输入的消息内容
        session_id (Optional[str]): 会话ID，用于标识和恢复会话状态
        geometry_data (Optional[dict]): 地理数据类型，包含点、线、面的几何数据
    """
    message: str
    session_id: Optional[str] = None
    geometry_data: Optional[dict] = {}


async def generate_stream_response(
    user_input: str,
    session_id: str,
    context: any = None,
    geometry_data: dict = {}
) -> AsyncGenerator[str, None]:
    """
    生成流式响应的异步生成器

    此函数负责处理用户请求，通过 MapAgent 生成流式响应。
    使用 stream_mode=["updates", "custom", "messages"] 组合模式，
    实时获取节点状态更新、自定义数据和 LLM token，
    并通过 SSE 格式发送给前端。

    处理流程：
    1. 调用 MapAgent 的 stream 方法，使用组合模式
    2. 根据不同的流式数据类型（updates、custom、messages）进行处理
    3. 将每个数据块转换为 SSE 格式发送给前端
    4. 发送结束信号或错误信息

    Args:
        user_input (str): 用户输入内容
        session_id (str): 会话ID
        geometry_data (dict): 地理数据类型，格式为 {"point": [...], "line": [...], "polygon": [...]}

    Yields:
        str: SSE 格式的响应数据，包含 type 字段和对应的数据
    """
    try:
        # 调用 MapAgent 的 stream 方法，使用组合模式
        async for chunk in map_agent.stream(
            user_input=user_input,
            session_id=session_id,
            stream_mode=["updates", "custom", "messages"],
            context=context,
            geometry_data=geometry_data
        ):
            # 处理组合模式的输出
            # chunk 的格式为 (mode, data)
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk

                if mode == "updates":
                    # 节点状态更新
                    # data 格式: {node_name: {state_updates}}
                    yield f"data: {json.dumps({'type': 'update', 'data': data}, ensure_ascii=False, default=str)}\n\n"

                elif mode == "custom":
                    # 自定义数据
                    # data 格式: 自定义的数据结构
                    yield f"data: {json.dumps({'type': 'custom', 'data': data}, ensure_ascii=False, default=str)}\n\n"

                elif mode == "messages":
                    if isinstance(data, tuple) and len(data) == 2:
                        message_chunk, metadata = data
                        if isinstance(message_chunk, ToolMessage):
                            continue
                        content = stream_format_context.format_message(message_chunk, metadata)
                        if content is None:
                            continue
                        yield f"data: {json.dumps({'type': 'message', 'content': content, 'metadata': metadata}, ensure_ascii=False, default=str)}\n\n"
                    else:
                        # 如果数据格式不符合预期，直接序列化
                        yield f"data: {json.dumps({'type': 'message', 'data': data}, ensure_ascii=False, default=str)}\n\n"
            else:
                # 处理非组合模式的输出（向后兼容）
                yield f"data: {json.dumps({'type': 'unknown', 'data': chunk}, ensure_ascii=False, default=str)}\n\n"

        # 发送结束信号
        yield f"data: {json.dumps({'type': 'end', 'message': '会话结束'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        # 捕获异常并将错误信息转换为 SSE 格式发送给前端
        import traceback
        logger.error(f"[ERROR] generate_stream_response 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"


@router.post('/chat')
async def chat(
    request: Request,
    chat_request: ChatRequest
):
    """
    地图智能体流式聊天接口

    与地图AI助手进行对话，支持多轮对话和地图操作。
    使用 SSE (Server-Sent Events) 协议实时返回 Agent 的思考过程和响应结果。

    工作流程：
    1. 接收 POST 请求，解析为 ChatRequest 对象
    2. 获取 session_id，优先使用请求体中的，否则从 request.state 获取
    3. 调用 generate_stream_response 生成流式响应
    4. 通过 StreamingResponse 以 SSE 格式返回数据
    5. 设置适当的响应头以确保流式传输正常工作

    Args:
        request: FastAPI 请求对象
        chat_request: 聊天请求，包含用户消息和可选的会话ID

    Returns:
        StreamingResponse: 流式响应对象，使用 text/event-stream 媒体类型
    """
    try:
        # 获取 session_id，优先使用请求体中的，否则从 request.state 获取
        session_id = chat_request.session_id or getattr(request.state, "session_id", "default")

        # 获取 geometry_data
        geometry_data = chat_request.geometry_data or {}

        logger.debug(f"[DEBUG] chat 请求: message={chat_request.message}, session_id={session_id}")

        # 返回流式响应
        return StreamingResponse(
            generate_stream_response(
                user_input=chat_request.message,
                session_id=session_id,
                geometry_data=geometry_data
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
            }
        )

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] chat 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"对话处理失败：{str(e)}")
@router.post('/knowledge-chat')
async def knowledge_chat(
    request: Request,
    chat_request: ChatRequest
):
    """
    地图智能体流式聊天接口

    与地图AI助手进行对话，支持多轮对话和地图操作。
    使用 SSE (Server-Sent Events) 协议实时返回 Agent 的思考过程和响应结果。

    工作流程：
    1. 接收 POST 请求，解析为 ChatRequest 对象
    2. 获取 session_id，优先使用请求体中的，否则从 request.state 获取
    3. 调用 generate_stream_response 生成流式响应
    4. 通过 StreamingResponse 以 SSE 格式返回数据
    5. 设置适当的响应头以确保流式传输正常工作

    Args:
        request: FastAPI 请求对象
        chat_request: 聊天请求，包含用户消息和可选的会话ID

    Returns:
        StreamingResponse: 流式响应对象，使用 text/event-stream 媒体类型
    """
    try:
        # 获取 session_id，优先使用请求体中的，否则从 request.state 获取
        session_id = chat_request.session_id or getattr(request.state, "session_id", "default")

        # 获取 geometry_data
        geometry_data = chat_request.geometry_data or {}

        logger.debug(f"[DEBUG] chat 请求: message={chat_request.message}, session_id={session_id}")

        # 返回流式响应
        return StreamingResponse(
            generate_stream_response(
                user_input=chat_request.message,
                session_id=session_id,
                context=MapAgentContext(
                    system_prompt=KNOWLEDGE_SYSTEM_PROMPT,
                    knowledge_root=r"app\data\Knowledge\tmp"
                ),
                geometry_data=geometry_data
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
            }
        )

    except Exception as e:
        import traceback
        logger.error(f"[ERROR] chat 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"对话处理失败：{str(e)}")
