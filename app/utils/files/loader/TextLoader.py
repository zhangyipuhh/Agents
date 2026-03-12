#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
TextLoader 模块

提供文本文件加载功能，基于 langchain 的 TextLoader 进行封装，
支持延迟加载、文件存在性检查等扩展功能。

Date: 2026-03-12
Author: 张镒谱
"""

from pathlib import Path
from typing import Optional, List
from langchain_community.document_loaders import TextLoader as LangChainTextLoader
from langchain_core.documents import Document


class TextLoader:
    """
    文本文件加载器
    
    对 langchain 的 TextLoader 进行封装，提供更友好的 API 和额外功能。
    使用延迟加载模式优化性能，只有在实际调用 load 方法时才创建底层加载器。
    
    Attributes:
        file_path: 要加载的文本文件路径
        encoding: 文件编码格式，默认为 utf-8
    """
    
    def __init__(self, file_path: str, encoding: str = "utf-8"):
        """
        初始化 TextLoader
        
        Args:
            file_path: 要加载的文本文件路径，支持相对路径和绝对路径
            encoding: 文件编码格式，默认为 utf-8
        """
        self.file_path = Path(file_path)
        self.encoding = encoding
        self._loader: Optional[LangChainTextLoader] = None

    def _get_loader(self) -> LangChainTextLoader:
        """
        获取底层的 langchain TextLoader 实例
        
        使用延迟加载模式，只有在首次调用时才创建加载器实例，
        避免不必要的资源占用。
        
        Returns:
            LangChainTextLoader: 底层的 langchain 加载器实例
        """
        # 检查是否已创建加载器，避免重复创建
        if self._loader is None:
            self._loader = LangChainTextLoader(
                str(self.file_path),
                encoding=self.encoding
            )
        return self._loader

    def load(self) -> List[Document]:
        """
        加载文本文件内容
        
        调用底层 langchain 加载器的 load 方法，将文本文件内容
        转换为 Document 对象列表。
        
        Returns:
            List[Document]: Document 对象列表，每个 Document 代表文件内容的一部分
        """
        return self._get_loader().load()

    def lazy_load(self) -> List[Document]:
        """
        延迟加载文本文件内容
        
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
    loader = TextLoader("D:\DocumentLoader\TextLoader.txt")
    documents = loader.load()
    print(documents)
