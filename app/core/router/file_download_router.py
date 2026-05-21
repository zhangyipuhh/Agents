import io
import logging
import mimetypes
import re
import time
import zipfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from app.core.config.config import DEMONSTRATION_CONFIG
logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/core/download', tags=['Core File Download'])

DOWNLOAD_DIR = Path("app/data/download")

CHUNK_SIZE = 64 * 1024


class DownloadableFileInfo(BaseModel):
    name: str
    path: str
    size: int
    modified_time: float
    is_dir: bool


class FileListResponse(BaseModel):
    files: List[DownloadableFileInfo]
    count: int


class BatchDownloadRequest(BaseModel):
    paths: List[str] = Field(..., min_length=1)
    zip_filename: Optional[str] = None


class MultipleChoiceFileInfo(BaseModel):
    name: str
    path: str
    size: int


class MultipleChoiceResponse(BaseModel):
    message: str
    files: List[MultipleChoiceFileInfo]


def _safe_path(base_dir: Path, relative_path: str) -> Path:
    resolved = (base_dir / relative_path).resolve()
    if not str(resolved).startswith(str(base_dir.resolve())):
        raise HTTPException(status_code=400, detail="非法路径")
    return resolved


def _get_session_dir(request: Request) -> Path:
    session_id = getattr(request.state, "session_id", "default")
    session_dir = DOWNLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _detect_content_type(file_path: Path) -> str:
    content_type, _ = mimetypes.guess_type(str(file_path))
    return content_type or "application/octet-stream"


def _make_content_disposition(filename: str) -> str:
    """生成 RFC 5987 格式的 Content-Disposition 头，支持中文文件名"""
    try:
        filename.encode('ascii')
        return f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        encoded = quote(filename, safe='')
        return f"attachment; filename*=UTF-8''{encoded}"


async def _file_iterator(file_path: Path, start: int = 0, end: Optional[int] = None):
    async with aiofiles.open(file_path, "rb") as f:
        await f.seek(start)
        remaining = (end - start + 1) if end is not None else None
        while remaining is None or remaining > 0:
            read_size = min(CHUNK_SIZE, remaining) if remaining else CHUNK_SIZE
            data = await f.read(read_size)
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data


def _parse_range_header(range_header: str, file_size: int):
    match = re.match(r'^bytes=(\d*)-(\d*)$', range_header)
    if not match:
        raise HTTPException(status_code=416, detail="无效的 Range 请求")

    start_str, end_str = match.groups()

    if start_str == "" and end_str == "":
        raise HTTPException(status_code=416, detail="无效的 Range 请求")

    if start_str == "":
        suffix_length = int(end_str)
        start = max(0, file_size - suffix_length)
        end = file_size - 1
    elif end_str == "":
        start = int(start_str)
        end = file_size - 1
    else:
        start = int(start_str)
        end = min(int(end_str), file_size - 1)

    if start > end or start >= file_size:
        raise HTTPException(status_code=416, detail="Range 超出文件范围")

    return start, end


@router.get('/file')
async def download_file(
    request: Request,
    path: str = Query(..., description="相对于 session 下载目录的文件路径"),
    filename: Optional[str] = Query(None, description="自定义下载文件名"),
):
    try:
        logger.info(f"[DEBUG] 原始 path 参数: {path!r}")
        path = unquote(path)
        logger.info(f"[DEBUG] 解码后 path: {path!r}")
        session_dir = _get_session_dir(request)
        logger.info(f"[DEBUG] session_dir: {session_dir}")
        file_path = _safe_path(session_dir, path)
        logger.info(f"[DEBUG] 初始 file_path: {file_path}")

        if DEMONSTRATION_CONFIG["demonstration_report_enabled"]:
            file_path = Path("app/data/demonstration/download", path)
            logger.info(f"[DEBUG] 演示模式 file_path: {file_path}")
        logger.info(f"[DEBUG] 最终 file_path: {file_path}, exists={file_path.exists()}, is_file={file_path.is_file() if file_path.exists() else 'N/A'}")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

        file_size = file_path.stat().st_size
        content_type = _detect_content_type(file_path)
        download_name = filename or file_path.name

        range_header = request.headers.get("range")

        if range_header:
            start, end = _parse_range_header(range_header, file_size)
            content_length = end - start + 1

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Disposition": _make_content_disposition(download_name),
            }

            return StreamingResponse(
                _file_iterator(file_path, start, end),
                status_code=206,
                media_type=content_type,
                headers=headers,
            )

        headers = {
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": _make_content_disposition(download_name),
        }

        return StreamingResponse(
            _file_iterator(file_path),
            media_type=content_type,
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[ERROR] 下载文件时发生异常: {type(e).__name__}: {e}")
        logger.error(f"[ERROR] 异常堆栈:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {type(e).__name__}: {e}")


@router.get('/by-name')
async def download_by_name(
    request: Request,
    name: str = Query(..., description="文件名（支持模糊匹配）"),
    exact: bool = Query(False, description="是否精确匹配"),
):
    session_dir = _get_session_dir(request)

    if not session_dir.exists():
        raise HTTPException(status_code=404, detail=f"未找到匹配文件: {name}")

    matched_files = []
    for f in session_dir.rglob("*"):
        if f.is_file():
            if exact:
                if f.name == name:
                    matched_files.append(f)
            else:
                if name in f.name:
                    matched_files.append(f)

    if not matched_files:
        raise HTTPException(status_code=404, detail=f"未找到匹配文件: {name}")

    if len(matched_files) > 1:
        candidates = [
            MultipleChoiceFileInfo(
                name=f.name,
                path=str(f.relative_to(session_dir)),
                size=f.stat().st_size,
            )
            for f in matched_files
        ]
        return JSONResponse(
            status_code=300,
            content=MultipleChoiceResponse(
                message=f"找到 {len(matched_files)} 个匹配文件，请指定具体路径",
                files=candidates,
            ).model_dump(),
        )

    file_path = matched_files[0]
    file_size = file_path.stat().st_size
    content_type = _detect_content_type(file_path)

    headers = {
        "Content-Length": str(file_size),
        "Accept-Ranges": "bytes",
        "Content-Disposition": _make_content_disposition(file_path.name),
    }

    return StreamingResponse(
        _file_iterator(file_path),
        media_type=content_type,
        headers=headers,
    )


@router.post('/batch')
async def batch_download(
    request: Request,
    batch_request: BatchDownloadRequest,
):
    session_dir = _get_session_dir(request)

    not_found = []
    valid_files = []

    for rel_path in batch_request.paths:
        file_path = _safe_path(session_dir, rel_path)
        if not file_path.exists() or not file_path.is_file():
            not_found.append(rel_path)
        else:
            valid_files.append((rel_path, file_path))

    if not_found:
        raise HTTPException(
            status_code=404,
            detail=f"以下文件不存在: {', '.join(not_found)}",
        )

    zip_filename = batch_request.zip_filename or f"download_{int(time.time())}.zip"

    async def _zip_iterator():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path, file_path in valid_files:
                zf.write(file_path, arcname=Path(rel_path).name)
        buffer.seek(0)
        while True:
            chunk = buffer.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk

    zip_size = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, file_path in valid_files:
            zf.write(file_path, arcname=Path(rel_path).name)
    zip_size = buffer.tell()

    headers = {
        "Content-Length": str(zip_size),
        "Content-Disposition": _make_content_disposition(zip_filename),
    }

    buffer.seek(0)

    return StreamingResponse(
        _sync_stream_from_buffer(buffer),
        media_type="application/zip",
        headers=headers,
    )


def _sync_stream_from_buffer(buffer: io.BytesIO):
    while True:
        chunk = buffer.read(CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


@router.get('/list', response_model=FileListResponse)
async def list_downloadable_files(
    request: Request,
    subdir: Optional[str] = Query(None, description="子目录路径"),
    recursive: bool = Query(False, description="是否递归列出子目录"),
):
    session_dir = _get_session_dir(request)

    target_dir = session_dir
    if subdir:
        target_dir = _safe_path(session_dir, subdir)

    if not target_dir.exists():
        return FileListResponse(files=[], count=0)

    files = []
    pattern = "**/*" if recursive else "*"
    for f in target_dir.glob(pattern):
        if f.is_file():
            stat = f.stat()
            files.append(
                DownloadableFileInfo(
                    name=f.name,
                    path=str(f.relative_to(session_dir)),
                    size=stat.st_size,
                    modified_time=stat.st_mtime,
                    is_dir=False,
                )
            )

    return FileListResponse(files=files, count=len(files))
