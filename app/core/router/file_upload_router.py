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

# 2026-07-13 新增：上传文件最大字节数（从 FILE_PARSER_CONFIG['max_file_size_mb'] 计算）。
# 前端校验 + 后端校验共用，前后端不一致时以本值为准。
MAX_FILE_SIZE_MB = FILE_PARSER_CONFIG.get("max_file_size_mb", 3)
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# 2026-07-17 新增：跳过远程 mineru 解析、可直接转 md 的扩展名集合。
# 即使 file_parser_enabled=true，这些后缀也按本地模式处理（原文转 md 写入 tmp）。
_PASSTHROUGH_SUFFIXES = {".md", ".markdown", ".txt"}


def _is_passthrough_suffix(suffix: str) -> bool:
    """判断后缀是否属于无需远程解析、可直接复制为 md 的类型（md/markdown/txt）。

    Args:
        suffix: 文件后缀（如 ".md", ".TXT"）。

    Returns:
        bool: 命中 PASSTHROUGH_SUFFIXES 时返回 True。
    """
    return (suffix or "").lower() in _PASSTHROUGH_SUFFIXES


async def _write_md_passthrough(original_path: Path, output_path: Path) -> None:
    """读取原文件文本，按行拼接后写入 output_path（.md）。

    行为与本地 DocumentLoader 分支完全一致：按 utf-8 解码，失败降级 latin-1，
    避免 UnicodeDecodeError 导致整个上传失败。

    Args:
        original_path: 原文件绝对路径（.md / .txt / .markdown）。
        output_path: 目标 .md 文件绝对路径。
    """
    raw = original_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    # 与本地分支行为对齐：按换行拼接后整段写入（保持原文顺序与空行）。
    content = text
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
        await f.write(content)


class UploadedFileInfo(BaseModel):
    filename: str
    stored_path: str
    file_type: str


class CoreFileUploadResponse(BaseModel):
    files: List[UploadedFileInfo]
    count: int
    parser_mode: str


class AttachmentDeleteRequest(BaseModel):
    """附件批量删除请求模型。"""
    stored_paths: List[str]


class AttachmentDeleteItem(BaseModel):
    """单个附件删除失败明细。"""
    stored_path: str
    reason: str


class AttachmentDeleteResponse(BaseModel):
    """附件批量删除响应模型。"""
    success: List[str]
    failed: List[AttachmentDeleteItem]


class UploadConfigResponse(BaseModel):
    """2026-07-13 新增：上传配置响应，供前端校验使用。"""
    max_file_size_mb: int
    parser_enabled: bool


@router.get('/upload-config', response_model=UploadConfigResponse)
async def get_upload_config():
    """获取上传相关配置（前端启动时调用一次）。

    Returns:
        UploadConfigResponse: 包含最大文件大小（MB）与是否启用远程解析。
    """
    return UploadConfigResponse(
        max_file_size_mb=MAX_FILE_SIZE_MB,
        parser_enabled=FILE_PARSER_CONFIG.get("enabled", False),
    )


@router.post('/uploadfile', response_model=CoreFileUploadResponse)
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...)
):
    """批量上传文件并解析为 Markdown。

    路径规则（2026-06-30 改造）：
        - 有 project_id（项目文件夹）→ data/project/{yyyy}/{mm}/{dd}/{project_uuid}/
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
            relative_path = project['relative_path']
            session_upload_dir = get_project_upload_dir(relative_path, create=True)
            session_tmp_dir = get_project_tmp_upload_dir(relative_path, create=True)
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

            # 2026-07-13 新增：统一大小校验（与 file_parser_enabled 无关）
            if len(content) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE_MB} MB）：{file.filename}",
                )

            # 保留原文件到对应目录
            original_path = session_upload_dir / f"{original_stem}{original_suffix}"
            async with aiofiles.open(original_path, "wb") as f:
                await f.write(content)

            if parser_enabled:
                # 2026-07-17 新增：md / txt / markdown 跳过 mineru 远程解析，直接转 md 写入 tmp。
                # mineru 面向 PDF/图片，md/txt 远程解析会报错，行为对齐本地 DocumentLoader 分支。
                if _is_passthrough_suffix(original_suffix):
                    output_path = session_tmp_dir / f"{original_stem}.md"
                    await _write_md_passthrough(original_path, output_path)
                    result_path = str(output_path)
                else:
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
        - 有 project_id（项目文件夹）→ data/project/{yyyy}/{mm}/{dd}/{project_uuid}/
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
            relative_path = project['relative_path']
            session_upload_dir = get_project_upload_dir(relative_path, create=True)
            session_tmp_dir = get_project_tmp_upload_dir(relative_path, create=True)
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

            # 2026-07-13 新增：合并分片后立即校验总大小（与 file_parser_enabled 无关）
            if merged_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                merged_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE_MB} MB）：{merge_request.filename}",
                )

            # 将合并后的原文件保留到日期化 session 目录
            original_path = session_upload_dir / f"{original_stem}{original_suffix}"
            async with aiofiles.open(original_path, "wb") as f:
                async with aiofiles.open(merged_path, "rb") as in_f:
                    content = await in_f.read()
                await f.write(content)

            parser_enabled = FILE_PARSER_CONFIG.get("enabled", False)
            parser_mode = "remote" if parser_enabled else "local"

            if parser_enabled:
                # 2026-07-17 新增：md / txt / markdown 跳过 mineru 远程解析，直接转 md 写入 tmp。
                # 行为对齐 upload_files() 的对应短路分支。
                if _is_passthrough_suffix(original_suffix):
                    output_path = session_tmp_dir / f"{original_stem}.md"
                    await _write_md_passthrough(original_path, output_path)
                    result_path = str(output_path)
                else:
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


@router.delete('/attachments', response_model=AttachmentDeleteResponse)
async def delete_attachments(request: Request, delete_request: AttachmentDeleteRequest):
    """批量删除附件。

    根据 stored_path 删除对应的 .md 缓存文件、原文件以及 attachments 表记录。
    仅允许删除属于当前 session_id 的附件；若存在 project_id，还需校验项目一致性。

    Args:
        request: FastAPI 请求对象，用于获取 session_id 与 project_id（中间件注入）。
        delete_request: 包含要删除的 stored_path 列表。

    Returns:
        AttachmentDeleteResponse: 包含删除成功与失败的 stored_path 列表。
    """
    session_id = getattr(request.state, "session_id", "default")
    project_id = getattr(request.state, "project_id", None)

    success_paths: List[str] = []
    failed_items: List[AttachmentDeleteItem] = []

    for stored_path in delete_request.stored_paths:
        try:
            attachment = await AttachmentDB.get_attachment_by_stored_path(stored_path, session_id)
            if not attachment:
                failed_items.append(AttachmentDeleteItem(
                    stored_path=stored_path,
                    reason="附件不存在或无权限"
                ))
                continue

            if project_id is not None and attachment.get("project_id") != project_id:
                failed_items.append(AttachmentDeleteItem(
                    stored_path=stored_path,
                    reason="附件不属于当前项目"
                ))
                continue

            md_path = Path(_resolve_project_root()) / stored_path
            if md_path.exists():
                md_path.unlink()

            original_path = _resolve_original_path(md_path)
            if original_path and original_path.exists():
                original_path.unlink()

            await AttachmentDB.delete_attachment_by_stored_path(stored_path, session_id)
            success_paths.append(stored_path)
        except Exception as e:
            failed_items.append(AttachmentDeleteItem(
                stored_path=stored_path,
                reason=f"删除失败: {str(e)}"
            ))

    return AttachmentDeleteResponse(
        success=success_paths,
        failed=failed_items,
    )


def _resolve_original_path(md_path: Path) -> Optional[Path]:
    """根据 .md 缓存绝对路径推导原文件绝对路径。

    推导规则：
        - <root>/data/tmp/upload/...  -> <root>/data/upload/...
        - <root>/data/tmp/project/... -> <root>/data/project/...

    由于 .md 缓存文件的后缀与原文件不同，推导后会优先在目标目录中查找
    与缓存文件 stem 相同的任意文件；找不到时返回以原文件常见后缀猜测的路径。

    Args:
        md_path: .md 缓存文件的绝对路径。

    Returns:
        Optional[Path]: 原文件绝对路径；无法推导时返回 None。
    """
    try:
        parts = md_path.parts
        for i in range(len(parts) - 2):
            if parts[i] == "data" and parts[i + 1] == "tmp":
                if parts[i + 2] == "upload":
                    original_dir_parts = list(parts[:i]) + ["data", "upload"] + list(parts[i + 3:-1])
                    original_stem = Path(parts[-1]).stem
                elif parts[i + 2] == "project":
                    original_dir_parts = list(parts[:i]) + ["data", "project"] + list(parts[i + 3:-1])
                    original_stem = Path(parts[-1]).stem
                else:
                    return None

                original_dir = Path(*original_dir_parts)
                if original_dir.exists():
                    for candidate in original_dir.iterdir():
                        if candidate.is_file() and candidate.stem == original_stem:
                            return candidate

                return None
        return None
    except Exception:
        return None


def _resolve_project_root() -> Path:
    """获取项目根目录绝对路径。

    Returns:
        Path: 项目根目录绝对路径。
    """
    from app.core.config.paths import _PROJECT_ROOT
    return Path(_PROJECT_ROOT)


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
