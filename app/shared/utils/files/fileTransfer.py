#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件传输工具类模块

本模块提供文件上传、下载、获取和删除的功能。
主要功能包括：
- 批量上传文件并使用UUID命名
- 通过UUID下载文件
- 通过UUID获取文件信息
- 通过UUID删除文件
- 支持会话隔离，每个会话的文件存储在独立目录中

Date: 2026/2/6
Author: 张镒谱
"""
import os
import uuid
import base64
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import UploadFile, HTTPException
import aiofiles

from app.shared.utils.files.pdf_untils import PDFProcessor
from app.shared.utils.files.session_path_manager import (
    get_session_upload_dir,
    get_session_tmp_upload_dir,
    remove_session_upload_date,
)


class FileTransfer:
    """
    文件传输工具类

    提供文件上传、下载、获取和删除的核心功能实现。
    所有文件使用UUID命名存储，确保文件名的唯一性和安全性。
    支持会话隔离，每个会话的文件存储在独立的目录中。
    """

    def __init__(self, upload_dir: str = "data/upload"):
        """
        初始化文件传输工具

        Args:
            upload_dir (str): 文件上传目录的路径，默认为"data/upload"
                                   支持相对路径（基于项目根目录）或绝对路径
        """
        upload_path = Path(upload_dir)

        if not upload_path.is_absolute():
            current_file_dir = Path(__file__).parent
            project_root = current_file_dir.parent.parent.parent.parent.parent
            upload_path = project_root / upload_dir

        self.upload_dir = upload_path.resolve()
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """
        确保上传根目录存在

        如果上传目录不存在，则创建该目录。
        """
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self, session_id: str, project_id: int = None) -> Path:
        """
        获取会话目录路径

        目录按日期组织：data/upload/{yyyy}/{mm}/{dd}/{session_id}
        2026-06-30 改造：有 project_id 时走项目目录 data/project/{project_uuid}/

        Args:
            session_id (str): 会话ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            Path: 会话目录的完整路径
        """
        return get_session_upload_dir(session_id, create=True, project_id=project_id)

    def _get_session_tmp_dir(self, session_id: str, project_id: int = None) -> Path:
        """
        获取会话解析缓存目录路径

        目录按日期组织：data/tmp/upload/{yyyy}/{mm}/{dd}/{session_id}
        2026-06-30 改造：有 project_id 时走项目目录 data/tmp/project/{project_uuid}/

        Args:
            session_id (str): 会话ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            Path: 解析缓存目录的完整路径
        """
        return get_session_tmp_upload_dir(session_id, create=True, project_id=project_id)
    
    def _get_file_path(self, file_uuid: str, session_id: str, project_id: int = None) -> Path:
        """
        根据UUID和会话ID获取文件的完整路径
        
        2026-06-30 改造：接受 project_id；走项目目录时按 projects.uuid 路径
        
        Args:
            file_uuid (str): 文件的UUID
            session_id (str): 会话ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID
            
        Returns:
            Path: 文件的完整路径
        """
        session_dir = self._get_session_dir(session_id, project_id=project_id)
        return session_dir / file_uuid
    
    def _get_file_uuid_with_extension(self, original_filename: str) -> str:
        """
        生成带扩展名的UUID文件名

        Args:
            original_filename (str): 原始文件名，用于提取文件扩展名

        Returns:
            str: UUID文件名，保留原始文件的扩展名
        """
        file_extension = Path(original_filename).suffix
        return f"{uuid.uuid4()}{file_extension}"

    def _get_file_type(self, filename: str, file_path: Optional[str] = None) -> str:
        """
        根据文件后缀名判断文件类型

        文件类型分类：
        - doc: 文档类文件（doc, docx, txt, xls, xlsx, ppt, pptx 等）
        - img: 图片类文件（jpg, jpeg, png, gif, bmp, webp, svg 等）
        - scan: 扫描件类文件（tif, tiff, 扫描版pdf）

        Args:
            filename (str): 文件名
            file_path (Optional[str]): 文件路径，用于检测PDF是否为扫描件

        Returns:
            str: 文件类型（doc/img/scan）
        """
        extension = Path(filename).suffix.lower()

        scan_extensions = {'.tif', '.tiff'}
        img_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.raw', '.heic', '.heif'}
        doc_extensions = {'.doc', '.docx', '.txt', '.rtf', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.md', '.html', '.htm', '.xml', '.json', '.yaml', '.yml'}

        # 如果是PDF文件，需要检测是否为扫描件
        if extension == '.pdf':
            if file_path and Path(file_path).exists():
                pdf_processor = PDFProcessor()
                if pdf_processor.is_scanned_pdf(file_path):
                    return 'scan'
            return 'doc'

        if extension in scan_extensions:
            return 'scan'
        elif extension in img_extensions:
            return 'img'
        elif extension in doc_extensions:
            return 'doc'
        else:
            return 'doc'
    
    async def upload_files(self, files: List[UploadFile], session_id: str, project_id: int = None) -> List[dict]:
        """
        批量上传文件

        将多个文件上传到指定会话目录，每个文件使用 UUID 命名。
        2026-06-30 改造：接受 project_id，文件落到项目目录而非 session 目录。

        Args:
            files (List[UploadFile]): 要上传的文件列表
            session_id (str): 会话 ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            List[dict]: 上传成功后的文件信息列表，每个元素包含 id（UUID，无扩展名）和 filename（原始文件名，无扩展名）

        Raises:
            HTTPException: 当上传过程中发生错误时抛出
        """
        uploaded_files = []
        
        for file in files:
            try:
                # 生成 UUID 文件名（带扩展名）
                file_uuid_with_ext = self._get_file_uuid_with_extension(file.filename)
                file_path = self._get_file_path(file_uuid_with_ext, session_id, project_id=project_id)
                
                # 使用 aiofiles 异步保存文件
                async with aiofiles.open(file_path, "wb") as buffer:
                    content = await file.read()
                    await buffer.write(content)
                
                # 获取 UUID（去除扩展名）
                file_uuid = Path(file_uuid_with_ext).stem
                
                # 获取原始文件名（去除扩展名）
                original_filename = Path(file.filename).stem

                # 获取文件类型（传入文件路径以检测PDF是否为扫描件）
                file_type = self._get_file_type(file.filename, str(file_path))

                uploaded_files.append({
                    "id": file_uuid,
                    "filename": original_filename,
                    "file_type": file_type
                })

            except Exception as e:
                # 如果上传失败，删除已上传的文件
                for file_info in uploaded_files:
                    await self.delete_file(file_info["id"], session_id, project_id=project_id)
                raise HTTPException(status_code=500, detail=f"文件上传失败：{str(e)}")
        
        return uploaded_files
    
    async def upload_base64_files(self, files: List[dict], session_id: str, project_id: int = None) -> List[dict]:
        """
        批量上传 base64 编码的文件

        将多个 base64 编码的文件上传到指定会话目录，每个文件使用 UUID 命名。
        文件存储位置: {upload_dir}/{yyyy}/{mm}/{dd}/{session_id}/{uuid}.{ext}
        例如: data/upload/2026/06/19/session_123/550e8400-e29b-41d4-a716-446655440000.pdf

        2026-06-30 改造：接受 project_id，文件落到项目目录而非 session 目录。

        Args:
            files (List[dict]): 要上传的文件列表，每个元素包含 filename 和 base64_data
            session_id (str): 会话 ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            List[dict]: 上传成功后的文件信息列表，每个元素包含 id（UUID，无扩展名）和 filename（原始文件名，无扩展名）

        Raises:
            HTTPException: 当上传或解码过程中发生错误时抛出
        """
        uploaded_files = []

        for file_info in files:
            try:
                filename = file_info["filename"]
                base64_data = file_info["base64_data"]

                # 生成 UUID 文件名（带扩展名）
                file_uuid_with_ext = self._get_file_uuid_with_extension(filename)
                file_path = self._get_file_path(file_uuid_with_ext, session_id, project_id=project_id)

                # 解码 base64 数据
                file_content = base64.b64decode(base64_data)

                # 使用 aiofiles 异步保存文件
                async with aiofiles.open(file_path, "wb") as buffer:
                    await buffer.write(file_content)

                # 获取 UUID（去除扩展名）
                file_uuid = Path(file_uuid_with_ext).stem

                # 获取原始文件名（去除扩展名）
                original_filename = Path(filename).stem

                # 获取文件类型（传入文件路径以检测PDF是否为扫描件）
                file_type = self._get_file_type(filename, str(file_path))

                uploaded_files.append({
                    "id": file_uuid,
                    "filename": original_filename,
                    "file_type": file_type
                })

            except Exception as e:
                # 如果上传失败，删除已上传的文件
                for file_info in uploaded_files:
                    await self.delete_file(file_info["id"], session_id, project_id=project_id)
                raise HTTPException(status_code=500, detail=f"Base64 文件上传失败：{str(e)}")

        return uploaded_files
    
    def get_file_path(self, file_uuid: str, session_id: str, project_id: int = None) -> Path:
        """
        通过UUID和会话ID获取文件路径

        支持传入带扩展名或不带扩展名的UUID。
        如果传入不带扩展名的UUID，会自动查找匹配的文件。

        2026-06-30 改造：接受 project_id；有项目目录时优先查项目目录。

        查找逻辑：
            1. 首先尝试直接查找（假设传入的是带扩展名的完整文件名）
            2. 如果未找到，遍历会话目录，匹配文件名（不含扩展名）等于file_uuid的文件

        Args:
            file_uuid (str): 文件的UUID（可以带或不带扩展名）
            session_id (str): 会话ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            Path: 文件的完整路径

        Raises:
            HTTPException: 当文件不存在时抛出404错误

        Examples:
            >>> # 方式2：传入带扩展名的UUID
            >>> file_path = file_transfer.get_file_path(
            ...     "550e8400-e29b-41d4-a716-446655440000.pdf",
            ...     "session_123"
            ... )
            >>> print(file_path)
            PosixPath('data/upload/session_123/550e8400-e29b-41d4-a716-446655440000.pdf')

            >>> # 方式2：传入带扩展名的UUID
            >>> file_path = file_transfer.get_file_path(
            ...     "550e8400-e29b-41d4-a716-446655440000.pdf",
            ...     "session_123"
            ... )
            >>> print(file_path)
            PosixPath('data/upload/session_123/550e8400-e29b-41d4-a716-446655440000.pdf')

            >>> # 文件不存在的情况
            >>> file_path = file_transfer.get_file_path("not-exist-uuid", "session_123")
            HTTPException: 404 文件不存在: not-exist-uuid
        """
        session_dir = self._get_session_dir(session_id, project_id=project_id)
        file_path = session_dir / file_uuid

        # 首先尝试直接查找（传入的是带扩展名的完整文件名）
        if file_path.exists():
            return file_path

        # 如果直接查找失败，遍历会话目录，匹配文件名（不含扩展名）
        for existing_file in session_dir.iterdir():
            if existing_file.is_file() and existing_file.stem == file_uuid:
                return existing_file

        raise HTTPException(status_code=404, detail=f"文件不存在: {file_uuid}")
    
    async def get_file_info(self, file_uuid: str, session_id: str, project_id: int = None) -> dict:
        """
        通过UUID和会话ID获取文件信息
        
        Args:
            file_uuid (str): 文件的UUID
            session_id (str): 会话ID
            
        Returns:
            dict: 包含文件信息的字典，包括文件名、大小、创建时间等
            
        Raises:
            HTTPException: 当文件不存在时抛出404错误
        """
        file_path = self.get_file_path(file_uuid, session_id, project_id=project_id)
        
        stat = file_path.stat()
        
        return {
            "uuid": file_uuid,
            "filename": file_path.name,
            "size": stat.st_size,
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime
        }

    async def get_file_as_base64(self, file_uuid: str, session_id: str, project_id: int = None) -> dict:
        """
        通过UUID和会话ID获取文件，并返回base64编码的内容

        文件存储位置: {upload_dir}/{yyyy}/{mm}/{dd}/{session_id}/{uuid}.{ext}
        例如: data/upload/2026/06/19/session_123/550e8400-e29b-41d4-a716-446655440000.pdf

        Args:
            file_uuid (str): 文件的UUID（可带或不带扩展名）
            session_id (str): 会话ID

        Returns:
            dict: 包含文件名和base64编码内容的字典
            {
                "filename": "550e8400-e29b-41d4-a716-446655440000.pdf",
                "base64_data": "JVBERi0xLjQKJcOkw7zDtsO..."
            }

        Raises:
            HTTPException: 当文件不存在或读取失败时抛出404/500错误

        Examples:
            >>> result = await file_transfer.get_file_as_base64(
            ...     "550e8400-e29b-41d4-a716-446655440000",
            ...     "session_123"
            ... )
            >>> print(result["filename"])
            550e8400-e29b-41d4-a716-446655440000.pdf
        """
        file_path = self.get_file_path(file_uuid, session_id)

        try:
            async with aiofiles.open(file_path, "rb") as buffer:
                file_content = await buffer.read()

            base64_data = base64.b64encode(file_content).decode("utf-8")

            return {
                "filename": file_path.name,
                "base64_data": base64_data
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"文件读取失败: {str(e)}")

    async def delete_file(self, file_uuid: str, session_id: str, project_id: int = None) -> bool:
        """
        通过UUID和会话ID删除文件

        2026-06-30 改造：接受 project_id；走项目目录时按 projects.uuid 路径。

        Args:
            file_uuid (str): 文件的UUID
            session_id (str): 会话ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            bool: 删除成功返回True，文件不存在返回False

        Raises:
            HTTPException: 当删除过程中发生错误时抛出
        """
        try:
            file_path = self.get_file_path(file_uuid, session_id, project_id=project_id)
            file_path.unlink()
            return True
        except HTTPException:
            return False
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")

    async def delete_files(self, file_uuids: List[str], session_id: str, project_id: int = None) -> dict:
        """
        批量删除文件
        
        Args:
            file_uuids (List[str]): 要删除的文件UUID列表
            session_id (str): 会话ID
            
        Returns:
            dict: 包含删除结果的字典，包括成功和失败的文件列表
        """
        results = {
            "success": [],
            "failed": []
        }
        
        for file_uuid in file_uuids:
            try:
                if await self.delete_file(file_uuid, session_id, project_id=project_id):
                    results["success"].append(file_uuid)
                else:
                    results["failed"].append({"uuid": file_uuid, "reason": "文件不存在"})
            except HTTPException as e:
                results["failed"].append({"uuid": file_uuid, "reason": str(e.detail)})

        return results

    async def list_files(self, session_id: str, project_id: int = None) -> List[dict]:
        """
        列出指定会话的所有已上传文件
        
        Args:
            session_id (str): 会话ID
            
        Returns:
            List[dict]: 包含所有文件信息的列表
        """
        files = []
        session_dir = self._get_session_dir(session_id)
        
        for file_path in session_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "uuid": file_path.name,
                    "filename": file_path.name,
                    "size": stat.st_size,
                    "created_time": stat.st_ctime,
                    "modified_time": stat.st_mtime
                })
        
        return files
    
    async def delete_session(self, session_id: str, project_id: int = None) -> bool:
        """
        删除整个会话目录及其所有文件

        同时删除原文件目录 data/upload/{yyyy}/{mm}/{dd}/{session_id} 与解析缓存目录
        data/tmp/upload/{yyyy}/{mm}/{dd}/{session_id}，并从索引中移除记录。

        2026-06-30 改造：
        - 有 project_id：仅删除项目目录 data/project/{project_uuid}/（不删 session 目录，
          因为多个 session 共享同一项目目录）
        - 无 project_id：保持原行为

        Args:
            session_id (str): 要删除的会话ID
            project_id (Optional[int]): 2026-06-30 新增；项目 ID

        Returns:
            bool: 删除成功返回True，会话不存在返回False

        Raises:
            HTTPException: 当删除过程中发生错误时抛出
        """
        if project_id:
            # 2026-06-30 新增：项目目录清理
            from app.shared.utils.project.project_db import ProjectDB
            from app.shared.utils.files.project_path_manager import (
                get_project_upload_dir,
                get_project_tmp_upload_dir,
            )
            project = ProjectDB._memory_cache.get(project_id)
            if not project and ProjectDB.is_enabled():
                project = await ProjectDB.get_project_by_id(project_id)
            if project:
                project_uuid = project['uuid']
                project_upload = get_project_upload_dir(project_uuid)
                project_tmp = get_project_tmp_upload_dir(project_uuid)
                existed = project_upload.exists() or project_tmp.exists()
                if not existed:
                    return False
                try:
                    if project_upload.exists():
                        shutil.rmtree(project_upload)
                    if project_tmp.exists():
                        shutil.rmtree(project_tmp)
                    return True
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"删除项目目录失败: {str(e)}")
            return False

        session_dir = get_session_upload_dir(session_id)
        tmp_session_dir = get_session_tmp_upload_dir(session_id)

        existed = session_dir.exists() or tmp_session_dir.exists()
        if not existed:
            return False

        try:
            if session_dir.exists():
                shutil.rmtree(session_dir)
            if tmp_session_dir.exists():
                shutil.rmtree(tmp_session_dir)
            remove_session_upload_date(session_id)
            return True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")
