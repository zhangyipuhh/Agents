#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文档长期记忆存储模块

本模块实现了基于LangGraph Store的文档长期记忆存储，
使用session_id作为key，存储文件类型和fileid的键值对数据。

Date: 2026/3/4
Author: 张镒谱
"""
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from langgraph.store.memory import InMemoryStore
from langgraph.store.base import BaseStore


class DocumentMemoryStore:
    """
    基于 LangGraph Store 的文档长期记忆存储
    """
    
    def __init__(self):
        """
        初始化 InMemoryStore
        """
        self.store = InMemoryStore()
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
            session_id: 会话 ID
            file_id: 文件 ID
            file_type: 文档类型 (contract | transaction | meeting)
            content: 解析后的内容
            file_name: 文件名
            
        Returns:
            bool: 保存是否成功
        """
        # 获取当前 session 的数据
        session_data = self.store.get(self.namespace, session_id)
        
        if not session_data:
            # 如果 session 不存在，创建新的 session 数据
            session_data = {"files": []}
        
        # 检查是否已存在相同 file_id 的文件
        existing_file = next((f for f in session_data["files"] if f["file_id"] == file_id), None)
        
        if existing_file:
            # 更新现有文件
            existing_file.update({
                "file_type": file_type,
                "content": content,
                "file_name": file_name,
                "created_at": datetime.now().isoformat()
            })
        else:
            # 添加新文件
            new_file = {
                "file_id": file_id,
                "file_type": file_type,
                "content": content,
                "file_name": file_name,
                "created_at": datetime.now().isoformat()
            }
            session_data["files"].append(new_file)
        
        # 保存回 store
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
            文档记忆列表
        """
        session_data = self.store.get(self.namespace, session_id)
        
        if not session_data:
            return []
        
        # 过滤指定类型的文档
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
        session_data = self.store.get(self.namespace, session_id)
        
        documents = {
            "contract_data": [],
            "transaction_data": [],
            "meeting_data": []
        }
        
        if session_data:
            for file in session_data["files"]:
                file_type = file.get("file_type")
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
        session_data = self.store.get(self.namespace, session_id)
        
        if not session_data:
            return None
        
        # 查找指定 file_id 的文件
        for file in session_data["files"]:
            if file.get("file_id") == file_id:
                return file
        
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
        session_data = self.store.get(self.namespace, session_id)
        
        if not session_data:
            return False
        
        # 过滤掉要删除的文件
        original_length = len(session_data["files"])
        session_data["files"] = [
            file for file in session_data["files"] 
            if file.get("file_id") != file_id
        ]
        
        # 如果文件被删除，更新 store
        if len(session_data["files"]) < original_length:
            self.store.put(self.namespace, session_id, session_data)
            return True
        
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
            self.store.delete(self.namespace, session_id)
            return True
        except Exception:
            return False
