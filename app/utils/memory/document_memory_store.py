#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文档长期记忆存储模块

本模块提供了基于 LangGraph InMemoryStore 的文档长期记忆存储功能。
用于在智能体工作流中缓存合同、成交确认书、会议纪要等文档的解析结果。

Date: 2026-03-05
Author: AI Assistant
"""
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from langgraph.store.memory import InMemoryStore


class DocumentMemoryStore:
    """基于 LangGraph Store 的文档长期记忆存储类"""

    def __init__(self):
        """初始化 InMemoryStore 实例"""
        # 创建内存存储实例，用于在内存中保存文档数据
        self.store = InMemoryStore()
        # 定义命名空间，用于区分不同类型的存储数据
        self.namespace = "audit_documents"

    def save_document(
        self,
        session_id: str,
        file_id: str,
        file_type: str,
        content: Dict[str, Any],
        file_name: str = ""
    ) -> bool:
        """
        保存文档解析结果到长期记忆

        Args:
            session_id: 会话 ID，用于标识不同的会话
            file_id: 文件 ID，用于唯一标识文档
            file_type: 文档类型 (contract | transaction | meeting)
            content: 解析后的文档内容
            file_name: 文件名

        Returns:
            bool: 保存是否成功
        """
        # 根据会话 ID 从存储中获取会话数据
        session_data = self.store.get(self.namespace, session_id)

        # 如果会话数据不存在，初始化一个空的会话数据结构
        if not session_data:
            session_data = {"files": []}

        # 查找是否已存在相同 file_id 的文档
        existing_file = next((f for f in session_data["files"] if f["file_id"] == file_id), None)

        # 如果文档已存在，更新现有文档的信息
        if existing_file:
            existing_file.update({
                "file_type": file_type,
                "content": content,
                "file_name": file_name,
                "created_at": datetime.now().isoformat()  # 更新创建时间
            })
        # 如果文档不存在，创建新的文档记录并添加到文件列表
        else:
            new_file = {
                "file_id": file_id,
                "file_type": file_type,
                "content": content,
                "file_name": file_name,
                "created_at": datetime.now().isoformat()  # 记录创建时间
            }
            session_data["files"].append(new_file)

        # 将更新后的会话数据保存回存储
        self.store.put(self.namespace, session_id, session_data)
        return True

    def get_documents_by_type(
        self,
        session_id: str,
        file_type: str
    ) -> List[Dict[str, Any]]:
        """
        根据文档类型获取记忆

        Args:
            session_id: 会话 ID
            file_type: 文档类型

        Returns:
            指定类型的文档记忆列表
        """
        # 根据会话 ID 获取会话数据
        session_data = self.store.get(self.namespace, session_id)

        # 如果会话数据不存在，返回空列表
        if not session_data:
            return []

        # 使用列表推导式过滤出指定类型的文档
        docs = [
            file
            for file in session_data["files"]
            if file.get("file_type") == file_type
        ]

        return docs

    def get_all_documents(
        self,
        session_id: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取 session 的所有文档

        Args:
            session_id: 会话 ID

        Returns:
            包含 contract_data、transaction_data、meeting_data 的字典
        """
        # 根据会话 ID 获取会话数据
        session_data = self.store.get(self.namespace, session_id)

        # 初始化三种文档类型的存储结构
        documents = {
            "contract_data": [],      # 合同数据
            "transaction_data": [],   # 成交确认书数据
            "meeting_data": []        # 会议纪要数据
        }

        # 如果会话数据存在，按文档类型分类存储
        if session_data:
            for file in session_data["files"]:
                file_type = file.get("file_type")
                # 根据文档类型将文档添加到对应的列表中
                if file_type == "contract":
                    documents["contract_data"].append(file)
                elif file_type == "transaction":
                    documents["transaction_data"].append(file)
                elif file_type == "meeting":
                    documents["meeting_data"].append(file)

        return documents

    def get_document_by_id(
        self,
        session_id: str,
        file_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        根据 file_id 获取指定文档

        Args:
            session_id: 会话 ID
            file_id: 文件 ID

        Returns:
            文档记忆，如果不存在则返回 None
        """
        # 根据会话 ID 获取会话数据
        session_data = self.store.get(self.namespace, session_id)

        # 如果会话数据不存在，返回 None
        if not session_data:
            return None

        # 遍历文件列表，查找匹配 file_id 的文档
        for file in session_data["files"]:
            if file.get("file_id") == file_id:
                return file

        # 未找到匹配的文档，返回 None
        return None

    def delete_document(
        self,
        session_id: str,
        file_id: str
    ) -> bool:
        """
        删除指定文档记忆

        Args:
            session_id: 会话 ID
            file_id: 文件 ID

        Returns:
            删除是否成功
        """
        # 根据会话 ID 获取会话数据
        session_data = self.store.get(self.namespace, session_id)

        # 如果会话数据不存在，返回删除失败
        if not session_data:
            return False

        # 记录删除前的文件数量
        original_length = len(session_data["files"])
        # 使用列表推导式过滤掉要删除的文档
        session_data["files"] = [
            file for file in session_data["files"]
            if file.get("file_id") != file_id
        ]

        # 如果文件数量减少了，说明成功删除了文档
        if len(session_data["files"]) < original_length:
            # 更新存储中的会话数据
            self.store.put(self.namespace, session_id, session_data)
            return True

        # 未找到要删除的文档，返回失败
        return False

    def clear_session(
        self,
        session_id: str
    ) -> bool:
        """
        清空 session 的所有文档记忆

        Args:
            session_id: 会话 ID

        Returns:
            清空是否成功
        """
        try:
            # 删除整个会话的数据
            self.store.delete(self.namespace, session_id)
            return True
        except Exception:
            # 发生异常时返回失败
            return False


# 创建全局单例实例，供其他模块直接导入使用
document_memory_store = DocumentMemoryStore()
