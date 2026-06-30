import json
import logging
import tempfile
import asyncio
import aiofiles
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from pydantic import BaseModel
from requests import RequestException

from app.core.config.config import FILE_PARSER_CONFIG
from app.shared.utils.files.DocumentLoader import DocumentLoader
from app.shared.utils.files.file_parser_client import FileParserClient
from app.shared.utils.files.attachment_db import AttachmentDB
from app.shared.utils.files.session_path_manager import (
    get_session_upload_dir,
    get_session_tmp_upload_dir,
)
# 2026-06-30 新增：项目路由支持
from app.shared.utils.files.project_path_manager import (
    get_project_upload_dir,
    get_project_tmp_upload_dir,
)
from app.shared.utils.project.project_db import ProjectDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/core', tags=['Core File Upload'])

CHUNKS_DIR = Path("data/upload_chunks")


class UploadedFileInfo(BaseModel):
    filename: str
    stored_path: str
    file_type: str


class CoreFileUploadResponse(BaseModel):
    files: List[UploadedFileInfo]
    count: int
    parser_mode: str


@router.post('/uploadfile', response_model=CoreFileUploadResponse)
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...)
):
    """批量上传文件并解析为 Markdown。

    路径规则（2026-06-30 改造）：
        - 有 project_id（项目文件夹）→ data/project/{project_uuid}/
        - 无 project_id（不使用文件夹 / 默认）→ data/upload/{yyyy}/{mm}/{dd}/{session_id}/

    原文件保留在对应目录，解析结果统一保存为 .md 文件到对应的 tmp 目录。

    Args:
        request: FastAPI 请求对象，用于获取 session_id 与 project_id（中间件注入）。
        files: 上传文件列表。

    Returns:
        CoreFileUploadResponse: 包含解析后的 md 文件信息、数量及解析模式。

    Raises:
        HTTPException: 解析服务不可用、文件类型不支持或上传失败时抛出。
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        project_id = getattr(request.state, "project_id", None)

        # 2026-06-30 新增：项目目录路由
        if project_id:
            # 先确保项目在内存中（启动时已加载）；若 DB 模式且未初始化，兜底查一次
            project = ProjectDB._memory_cache.get(project_id)
            if not project and ProjectDB.is_enabled():
                # DB 未命中内存（如重启后首请求）；用 username 校验后回填
                username = getattr(request.state, "username", None)
                user = None
                if username:
                    from app.shared.utils.auth.user_db import UserDB
                    user = await UserDB.get_user_by_username(username)
                project = await ProjectDB.get_project_by_id(
                    project_id,
                    user_id=user['id'] if user else None,
                )
                if project:
                    with ProjectDB._lock:
                        ProjectDB._memory_cache[project_id] = project
            if not project:
                raise HTTPException(status_code=404, detail=f"项目不存在: project_id={project_id}")
            project_uuid = project['uuid']
            session_upload_dir = get_project_upload_dir(project_uuid, create=True)
            session_tmp_dir = get_project_tmp_upload_dir(project_uuid, create=True)
        else:
            session_upload_dir = get_session_upload_dir(session_id, create=True)
            session_tmp_dir = get_session_tmp_upload_dir(session_id, create=True)

        parser_enabled = FILE_PARSER_CONFIG.get("enabled", False)
        parser_mode = "remote" if parser_enabled else "local"
        uploaded_files = []

        for file in files:
            original_stem = Path(file.filename).stem
            original_suffix = Path(file.filename).suffix

            content = await file.read()

            # 保留原文件到对应目录
            original_path = session_upload_dir / f"{original_stem}{original_suffix}"
            async with aiofiles.open(original_path, "wb") as f:
                await f.write(content)

            if parser_enabled:
                client = FileParserClient(
                    server_url=FILE_PARSER_CONFIG["server_url"],
                    max_retries=FILE_PARSER_CONFIG["max_retries"],
                    poll_interval=FILE_PARSER_CONFIG["poll_interval"],
                    timeout=FILE_PARSER_CONFIG["timeout"],
                )
                try:
                    result_path = await asyncio.to_thread(
                        client.parse,
                        file_path=str(original_path),
                        output_dir=str(session_tmp_dir),
                        api_url=FILE_PARSER_CONFIG["api_url"],
                        output_format="md",
                    )
                except RequestException as e:
                    raise HTTPException(status_code=503, detail=f"远程解析服务不可用: {str(e)}")
                except (ValueError, RuntimeError) as e:
                    raise HTTPException(status_code=503, detail=f"远程解析服务错误: {str(e)}")
                except TimeoutError as e:
                    raise HTTPException(status_code=503, detail=f"远程解析服务超时: {str(e)}")

                uploaded_files.append(UploadedFileInfo(
                    filename=file.filename,
                    stored_path=result_path,
                    file_type="md",
                ))
            else:
                try:
                    loader = DocumentLoader(path=str(original_path))
                    docs = await asyncio.to_thread(loader.load)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"不支持的文件类型: {str(e)}")

                text_content = "\n".join([doc.page_content for doc in docs])
                output_path = session_tmp_dir / f"{original_stem}.md"

                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write(text_content)

                uploaded_files.append(UploadedFileInfo(
                    filename=file.filename,
                    stored_path=str(output_path),
                    file_type="md",
                ))

            # 记录附件元数据（携带 project_id 用于聚合查询）
            await _record_attachment(
                session_id=session_id,
                file_info=UploadedFileInfo(
                    filename=file.filename,
                    stored_path=str(session_tmp_dir / f"{original_stem}.md") if not parser_enabled else result_path,
                    file_type="md",
                ),
                project_id=project_id,
            )

        return CoreFileUploadResponse(
            files=uploaded_files,
            count=len(uploaded_files),
            parser_mode=parser_mode,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


class ChunkUploadResponse(BaseModel):
    file_id: str
    chunk_index: int
    received: bool


class MergeChunksRequest(BaseModel):
    file_id: str
    filename: str
    total_chunks: int


@router.post('/upload-chunk', response_model=ChunkUploadResponse)
async def upload_chunk(
    chunk: UploadFile = File(...),
    file_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...)
):
    try:
        chunk_dir = CHUNKS_DIR / file_id
        chunk_dir.mkdir(parents=True, exist_ok=True)

        chunk_path = chunk_dir / f"chunk_{chunk_index}"
        content = await chunk.read()
        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(content)

        return ChunkUploadResponse(
            file_id=file_id,
            chunk_index=chunk_index,
            received=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分片上传失败: {str(e)}")


@router.post('/merge-chunks', response_model=CoreFileUploadResponse)
async def merge_chunks(request: Request, merge_request: MergeChunksRequest):
    """合并分片并解析为 Markdown。

    路径规则（2026-06-30 改造）：
        - 有 project_id（项目文件夹）→ data/project/{project_uuid}/
        - 无 project_id（不使用文件夹 / 默认）→ data/upload/{yyyy}/{mm}/{dd}/{session_id}/

    Args:
        request: FastAPI 请求对象，用于获取 session_id 与 project_id。
        merge_request: 分片合并请求，包含 file_id、filename、total_chunks。

    Returns:
        CoreFileUploadResponse: 包含解析后的 md 文件信息、数量及解析模式。

    Raises:
        HTTPException: 分片缺失、解析服务不可用、文件类型不支持或合并失败时抛出。
    """
    try:
        session_id = getattr(request.state, "session_id", "default")
        project_id = getattr(request.state, "project_id", None)

        # 2026-06-30 新增：项目目录路由
        if project_id:
            project = ProjectDB._memory_cache.get(project_id)
            if not project and ProjectDB.is_enabled():
                username = getattr(request.state, "username", None)
                user = None
                if username:
                    from app.shared.utils.auth.user_db import UserDB
                    user = await UserDB.get_user_by_username(username)
                project = await ProjectDB.get_project_by_id(
                    project_id,
                    user_id=user['id'] if user else None,
                )
                if project:
                    with ProjectDB._lock:
                        ProjectDB._memory_cache[project_id] = project
            if not project:
                raise HTTPException(status_code=404, detail=f"项目不存在: project_id={project_id}")
            project_uuid = project['uuid']
            session_upload_dir = get_project_upload_dir(project_uuid, create=True)
            session_tmp_dir = get_project_tmp_upload_dir(project_uuid, create=True)
        else:
            session_upload_dir = get_session_upload_dir(session_id, create=True)
            session_tmp_dir = get_session_tmp_upload_dir(session_id, create=True)

        chunk_dir = CHUNKS_DIR / merge_request.file_id
        if not chunk_dir.exists():
            raise HTTPException(status_code=404, detail=f"分片目录不存在: {merge_request.file_id}")

        original_stem = Path(merge_request.filename).stem
        original_suffix = Path(merge_request.filename).suffix

        merged_file = tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix)
        merged_path = Path(merged_file.name)
        merged_file.close()

        try:
            async with aiofiles.open(merged_path, "wb") as out_f:
                for i in range(merge_request.total_chunks):
                    chunk_path = chunk_dir / f"chunk_{i}"
                    if not chunk_path.exists():
                        raise HTTPException(
                            status_code=400,
                            detail=f"分片缺失: chunk_{i}"
                        )
                    async with aiofiles.open(chunk_path, "rb") as in_f:
                        content = await in_f.read()
                        await out_f.write(content)

            shutil.rmtree(chunk_dir, ignore_errors=True)

            # 将合并后的原文件保留到日期化 session 目录
            original_path = session_upload_dir / f"{original_stem}{original_suffix}"
            async with aiofiles.open(original_path, "wb") as f:
                async with aiofiles.open(merged_path, "rb") as in_f:
                    content = await in_f.read()
                await f.write(content)

            parser_enabled = FILE_PARSER_CONFIG.get("enabled", False)
            parser_mode = "remote" if parser_enabled else "local"

            if parser_enabled:
                client = FileParserClient(
                    server_url=FILE_PARSER_CONFIG["server_url"],
                    max_retries=FILE_PARSER_CONFIG["max_retries"],
                    poll_interval=FILE_PARSER_CONFIG["poll_interval"],
                    timeout=FILE_PARSER_CONFIG["timeout"],
                )
                try:
                    result_path = await asyncio.to_thread(
                        client.parse,
                        file_path=str(original_path),
                        output_dir=str(session_tmp_dir),
                        api_url=FILE_PARSER_CONFIG["api_url"],
                        output_format="md",
                    )
                except RequestException as e:
                    raise HTTPException(status_code=503, detail=f"远程解析服务不可用: {str(e)}")
                except (ValueError, RuntimeError) as e:
                    raise HTTPException(status_code=503, detail=f"远程解析服务错误: {str(e)}")
                except TimeoutError as e:
                    raise HTTPException(status_code=503, detail=f"远程解析服务超时: {str(e)}")

                uploaded_files = [UploadedFileInfo(
                    filename=merge_request.filename,
                    stored_path=result_path,
                    file_type="md",
                )]
            else:
                try:
                    loader = DocumentLoader(path=str(original_path))
                    docs = await asyncio.to_thread(loader.load)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"不支持的文件类型: {str(e)}")

                text_content = "\n".join([doc.page_content for doc in docs])
                output_path = session_tmp_dir / f"{original_stem}.md"

                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write(text_content)

                uploaded_files = [UploadedFileInfo(
                    filename=merge_request.filename,
                    stored_path=str(output_path),
                    file_type="md",
                )]

            # 记录附件信息到数据库（携带 project_id 用于聚合查询）
            for f in uploaded_files:
                await _record_attachment(
                    session_id=session_id,
                    file_info=f,
                    file_id=merge_request.file_id,
                    project_id=project_id,
                )

            return CoreFileUploadResponse(
                files=uploaded_files,
                count=len(uploaded_files),
                parser_mode=parser_mode,
            )
        finally:
            merged_path.unlink(missing_ok=True)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合并分片失败: {str(e)}")


async def _record_attachment(
    session_id: str,
    file_info: UploadedFileInfo,
    file_id: str = None,
    project_id: Optional[int] = None,
):
    """记录附件信息到数据库

    在文件上传成功后调用，将附件元数据写入 attachments 表。
    2026-06-30 改造：携带 project_id 用于按项目聚合查询。

    Args:
        session_id: 会话 ID
        file_info: 上传文件信息
        file_id: 上传时的 file_id
        project_id: 所属项目 ID（None = 不使用文件夹 / 默认）
    """
    try:
        import mimetypes
        mime_type = mimetypes.guess_type(file_info.filename)[0]
        # 从存储路径获取文件大小
        stored_path = Path(file_info.stored_path)
        file_size = stored_path.stat().st_size if stored_path.exists() else 0

        await AttachmentDB.add_attachment(
            session_id=session_id,
            file_name=file_info.filename,
            stored_path=file_info.stored_path,
            file_type=file_info.file_type,
            file_size=file_size,
            mime_type=mime_type,
            file_id=file_id,
            project_id=project_id,
        )
    except Exception as e:
        logger.warning(f"记录附件信息失败: {e}")
