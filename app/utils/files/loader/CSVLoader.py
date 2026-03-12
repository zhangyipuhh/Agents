#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
CSVLoader 模块

提供 CSV 文件加载功能，基于 langchain 的 CSVLoader 进行封装，
支持延迟加载、文件存在性检查等扩展功能。

Date: 2026-03-12
Author: 张镒谱
"""

from pathlib import Path
from typing import Optional, List
import chardet
from langchain_community.document_loaders import CSVLoader as LangChainCSVLoader
from langchain_core.documents import Document


class CSVLoader:
    """
    CSV 文件加载器
    
    对 langchain 的 CSVLoader 进行封装，提供更友好的 API 和额外功能。
    使用延迟加载模式优化性能，只有在实际调用 load 方法时才创建底层加载器。
    
    Attributes:
        file_path: 要加载的 CSV 文件路径
        encoding: 文件编码格式，默认为 utf-8
    """
    
    def __init__(self, file_path: str, encoding: str = "utf-8", source_encoding: Optional[str] = None):
        """
        初始化 CSVLoader
        
        Args:
            file_path: 要加载的 CSV 文件路径，支持相对路径和绝对路径
            encoding: 文件编码格式，默认为 utf-8
            source_encoding: 源文件编码，用于更精确的编码检测，默认为 None
        """
        self.file_path = Path(file_path)
        self.encoding = encoding
        self.source_encoding = source_encoding
        self._loader: Optional[LangChainCSVLoader] = None

    def _detect_encoding(self) -> str:
        """
        自动检测文件编码
        
        使用 chardet 库检测文件编码，如果检测失败则返回默认编码。
        
        Returns:
            str: 检测到的编码格式
        """
        with open(self.file_path, "rb") as f:
            raw_data = f.read(10000)
            result = chardet.detect(raw_data)
            detected = result.get("encoding")
            if detected:
                return detected
        return self.encoding

    def _get_loader(self) -> LangChainCSVLoader:
        """
        获取底层的 langchain CSVLoader 实例
        
        使用延迟加载模式，只有在首次调用时才创建加载器实例，
        避免不必要的资源占用。
        
        Returns:
            LangChainCSVLoader: 底层的 langchain 加载器实例
        """
        if self._loader is None:
            kwargs = {}
            if self.source_encoding:
                kwargs["source_encoding"] = self.source_encoding
            else:
                kwargs["encoding"] = self._detect_encoding()
            self._loader = LangChainCSVLoader(
                str(self.file_path),
                **kwargs
            )
        return self._loader

    def load(self) -> List[Document]:
        """
        加载 CSV 文件内容
        
        调用底层 langchain 加载器的 load 方法，将 CSV 文件内容
        转换为 Document 对象列表。
        
        Returns:
            List[Document]: Document 对象列表，每个 Document 代表文件中的一行
        """
        return self._get_loader().load()

    def lazy_load(self) -> List[Document]:
        """
        延迟加载 CSV 文件内容
        
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
    loader = CSVLoader("D:\DocumentLoader\CSVLoader.csv")
    documents = loader.load()
    print(documents)