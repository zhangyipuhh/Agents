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
from pathlib import Path
from typing import List, Optional
from fastapi import UploadFile, HTTPException
import aiofiles


class FileTransfer:
    """
    文件传输工具类
    
    提供文件上传、下载、获取和删除的核心功能实现。
    所有文件使用UUID命名存储，确保文件名的唯一性和安全性。
    支持会话隔离，每个会话的文件存储在独立的目录中。
    """
    
    def __init__(self, upload_dir: str = "app/data/upload"):
        """
        初始化文件传输工具
        
        Args:
            upload_dir (str): 文件上传目录的路径，默认为"app/data/upload"
        """
        self.upload_dir = Path(upload_dir)
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """
        确保上传目录存在
        
        如果上传目录不存在，则创建该目录。
        """
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_session_dir(self, session_id: str) -> Path:
        """
        获取会话目录路径
        
        Args:
            session_id (str): 会话ID
            
        Returns:
            Path: 会话目录的完整路径
        """
        session_dir = self.upload_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def _get_file_path(self, file_uuid: str, session_id: str) -> Path:
        """
        根据UUID和会话ID获取文件的完整路径
        
        Args:
            file_uuid (str): 文件的UUID
            session_id (str): 会话ID
            
        Returns:
            Path: 文件的完整路径
        """
        session_dir = self._get_session_dir(session_id)
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
    
    async def upload_files(self, files: List[UploadFile], session_id: str) -> List[dict]:
        """
        批量上传文件
        
        将多个文件上传到指定会话目录，每个文件使用 UUID 命名。
        
        Args:
            files (List[UploadFile]): 要上传的文件列表
            session_id (str): 会话 ID
            
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
                file_path = self._get_file_path(file_uuid_with_ext, session_id)
                
                # 使用 aiofiles 异步保存文件
                async with aiofiles.open(file_path, "wb") as buffer:
                    content = await file.read()
                    await buffer.write(content)
                
                # 获取 UUID（去除扩展名）
                file_uuid = Path(file_uuid_with_ext).stem
                
                # 获取原始文件名（去除扩展名）
                original_filename = Path(file.filename).stem
                
                uploaded_files.append({
                    "id": file_uuid,
                    "filename": original_filename
                })
                
            except Exception as e:
                # 如果上传失败，删除已上传的文件
                for file_info in uploaded_files:
                    await self.delete_file(file_info["id"], session_id)
                raise HTTPException(status_code=500, detail=f"文件上传失败：{str(e)}")
        
        return uploaded_files
    
    async def upload_base64_files(self, files: List[dict], session_id: str) -> List[dict]:
        """
        批量上传 base64 编码的文件
        
        将多个 base64 编码的文件上传到指定会话目录，每个文件使用 UUID 命名。
        
        Args:
            files (List[dict]): 要上传的文件列表，每个元素包含 filename 和 base64_data
            session_id (str): 会话 ID
            
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
                file_path = self._get_file_path(file_uuid_with_ext, session_id)
                
                # 解码 base64 数据
                file_content = base64.b64decode(base64_data)
                
                # 使用 aiofiles 异步保存文件
                async with aiofiles.open(file_path, "wb") as buffer:
                    await buffer.write(file_content)
                
                # 获取 UUID（去除扩展名）
                file_uuid = Path(file_uuid_with_ext).stem
                
                # 获取原始文件名（去除扩展名）
                original_filename = Path(filename).stem
                
                uploaded_files.append({
                    "id": file_uuid,
                    "filename": original_filename
                })
                
            except Exception as e:
                # 如果上传失败，删除已上传的文件
                for file_info in uploaded_files:
                    await self.delete_file(file_info["id"], session_id)
                raise HTTPException(status_code=500, detail=f"Base64 文件上传失败：{str(e)}")
        
        return uploaded_files
    
    def get_file_path(self, file_uuid: str, session_id: str) -> Path:
        """
        通过UUID和会话ID获取文件路径
        
        支持传入带扩展名或不带扩展名的UUID。
        如果传入不带扩展名的UUID，会自动查找匹配的文件。
        
        Args:
            file_uuid (str): 文件的UUID（可以带或不带扩展名）
            session_id (str): 会话ID
            
        Returns:
            Path: 文件的完整路径
            
        Raises:
            HTTPException: 当文件不存在时抛出404错误
        """
        session_dir = self._get_session_dir(session_id)
        file_path = session_dir / file_uuid
        
        if file_path.exists():
            return file_path
        
        # 如果直接查找失败，尝试查找以该UUID开头的文件
        for existing_file in session_dir.iterdir():
            if existing_file.is_file() and existing_file.stem == file_uuid:
                return existing_file
        
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_uuid}")
    
    async def get_file_info(self, file_uuid: str, session_id: str) -> dict:
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
        file_path = self.get_file_path(file_uuid, session_id)
        
        stat = file_path.stat()
        
        return {
            "uuid": file_uuid,
            "filename": file_path.name,
            "size": stat.st_size,
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime
        }
    
    async def delete_file(self, file_uuid: str, session_id: str) -> bool:
        """
        通过UUID和会话ID删除文件
        
        Args:
            file_uuid (str): 文件的UUID
            session_id (str): 会话ID
            
        Returns:
            bool: 删除成功返回True，文件不存在返回False
            
        Raises:
            HTTPException: 当删除过程中发生错误时抛出
        """
        try:
            file_path = self.get_file_path(file_uuid, session_id)
            file_path.unlink()
            return True
        except HTTPException:
            return False
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")
    
    async def delete_files(self, file_uuids: List[str], session_id: str) -> dict:
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
                if await self.delete_file(file_uuid, session_id):
                    results["success"].append(file_uuid)
                else:
                    results["failed"].append({"uuid": file_uuid, "reason": "文件不存在"})
            except HTTPException as e:
                results["failed"].append({"uuid": file_uuid, "reason": str(e.detail)})
        
        return results
    
    async def list_files(self, session_id: str) -> List[dict]:
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
    
    async def delete_session(self, session_id: str) -> bool:
        """
        删除整个会话目录及其所有文件
        
        Args:
            session_id (str): 要删除的会话ID
            
        Returns:
            bool: 删除成功返回True，会话不存在返回False
            
        Raises:
            HTTPException: 当删除过程中发生错误时抛出
        """
        session_dir = self._get_session_dir(session_id)
        
        if not session_dir.exists():
            return False
        
        try:
            for item in session_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    for sub_item in item.iterdir():
                        if sub_item.is_file():
                            sub_item.unlink()
                    item.rmdir()
            session_dir.rmdir()
            return True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")
