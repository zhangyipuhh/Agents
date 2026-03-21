#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MarkdownLoader 模块

提供 Markdown 文件加载功能，基于 langchain 的 UnstructuredMarkdownLoader 进行封装，
支持延迟加载、文件存在性检查等扩展功能。

Date: 2026-03-12
Author: 张镒谱
"""

from pathlib import Path
from typing import Optional, List
from langchain_community.document_loaders import UnstructuredMarkdownLoader as LangChainMarkdownLoader
from langchain_core.documents import Document


class MarkdownLoader:
    """
    Markdown 文件加载器
    
    对 langchain 的 UnstructuredMarkdownLoader 进行封装，提供更友好的 API 和额外功能。
    使用延迟加载模式优化性能，只有在实际调用 load 方法时才创建底层加载器。
    
    Attributes:
        file_path: 要加载的 Markdown 文件路径
    """
    
    def __init__(self, file_path: str):
        """
        初始化 MarkdownLoader
        
        Args:
            file_path: 要加载的 Markdown 文件路径，支持相对路径和绝对路径
        """
        self.file_path = Path(file_path)
        self._loader: Optional[LangChainMarkdownLoader] = None

    def _get_loader(self) -> LangChainMarkdownLoader:
        """
        获取底层的 langchain MarkdownLoader 实例
        
        使用延迟加载模式，只有在首次调用时才创建加载器实例，
        避免不必要的资源占用。
        
        Returns:
            LangChainMarkdownLoader: 底层的 langchain 加载器实例
        """
        if self._loader is None:
            self._loader = LangChainMarkdownLoader(
                str(self.file_path),
                mode="elements",
                strategy="fast"
            )
        return self._loader

    def load(self) -> List[Document]:
        """
        加载 Markdown 文件内容
        
        调用底层 langchain 加载器的 load 方法，将 Markdown 文件内容
        转换为 Document 对象列表。
        
        Returns:
            List[Document]: Document 对象列表，每个 Document 代表文件内容的一部分
        """
        return self._get_loader().load()

    def lazy_load(self) -> List[Document]:
        """
        延迟加载 Markdown 文件内容
        
        与 load 方法类似，但使用 lazy_load 模式，适合处理大文件。
        
        Returns:
            List[Document]: Document 对象列表
        """
        return self._get_loader().lazy_load()

    @property
    def exists(self) -> bool:
        """
        检查文件是否存在
        
        Returns:
            bool: 文件存在返回 True，否则返回 False
        """
        return self.file_path.exists()


if __name__ == "__main__":
    loader = MarkdownLoader("D:\DocumentLoader\MarkdownLoader.md")
    documents = loader.load()
    if documents:
        print(documents)
