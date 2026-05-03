import json
import logging
import tempfile
import asyncio
import aiofiles
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from pydantic import BaseModel
from requests import RequestException

from app.core.config.config import FILE_PARSER_CONFIG
from app.shared.utils.files.DocumentLoader import DocumentLoader
from app.shared.utils.files.file_parser_client import FileParserClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/core', tags=['Core File Upload'])

UPLOAD_DIR = Path("app/data/upload")


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
    try:
        session_id = getattr(request.state, "session_id", "default")
        session_dir = UPLOAD_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        parser_enabled = FILE_PARSER_CONFIG.get("enabled", False)
        parser_mode = "remote" if parser_enabled else "local"
        uploaded_files = []

        for file in files:
            original_stem = Path(file.filename).stem
            original_suffix = Path(file.filename).suffix

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix)
            tmp_path = tmp_file.name
            tmp_file.close()

            try:
                content = await file.read()
                async with aiofiles.open(tmp_path, "wb") as f:
                    await f.write(content)

                if parser_enabled:
                    source_path = session_dir / f"{original_stem}{original_suffix}"
                    async with aiofiles.open(source_path, "wb") as f:
                        await f.write(content)

                    client = FileParserClient(
                        server_url=FILE_PARSER_CONFIG["server_url"],
                        max_retries=FILE_PARSER_CONFIG["max_retries"],
                        poll_interval=FILE_PARSER_CONFIG["poll_interval"],
                        timeout=FILE_PARSER_CONFIG["timeout"],
                    )
                    try:
                        result_path = await asyncio.to_thread(
                            client.parse,
                            file_path=str(source_path),
                            output_dir=str(session_dir),
                            api_url=FILE_PARSER_CONFIG["api_url"],
                            output_format=FILE_PARSER_CONFIG["output_format"],
                        )
                    except RequestException as e:
                        raise HTTPException(status_code=503, detail=f"远程解析服务不可用: {str(e)}")
                    except (ValueError, RuntimeError) as e:
                        raise HTTPException(status_code=503, detail=f"远程解析服务错误: {str(e)}")
                    except TimeoutError as e:
                        raise HTTPException(status_code=503, detail=f"远程解析服务超时: {str(e)}")
                    finally:
                        source_path.unlink(missing_ok=True)

                    uploaded_files.append(UploadedFileInfo(
                        filename=file.filename,
                        stored_path=result_path,
                        file_type=FILE_PARSER_CONFIG["output_format"],
                    ))
                else:
                    try:
                        loader = DocumentLoader(path=tmp_path)
                        docs = await asyncio.to_thread(loader.load)
                    except ValueError as e:
                        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {str(e)}")

                    text_content = "\n".join([doc.page_content for doc in docs])
                    output_path = session_dir / f"{original_stem}.txt"

                    async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                        await f.write(text_content)

                    uploaded_files.append(UploadedFileInfo(
                        filename=file.filename,
                        stored_path=str(output_path),
                        file_type="txt",
                    ))
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        return CoreFileUploadResponse(
            files=uploaded_files,
            count=len(uploaded_files),
            parser_mode=parser_mode,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")
