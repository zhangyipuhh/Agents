#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
JSONLoader 模块

提供 JSON 文件加载功能，基于 langchain 的 JSONLoader 进行封装，
支持延迟加载、文件存在性检查等扩展功能。

Date: 2026-03-12
Author: 张镒谱
"""

from pathlib import Path
from typing import Optional, List, Any
from langchain_community.document_loaders import JSONLoader as LangChainJSONLoader
from langchain_core.documents import Document


class JSONLoader:
    """
    JSON 文件加载器
    
    对 langchain 的 JSONLoader 进行封装，提供更友好的 API 和额外功能。
    使用延迟加载模式优化性能，只有在实际调用 load 方法时才创建底层加载器。
    
    Attributes:
        file_path: 要加载的 JSON 文件路径
        jq_schema: JSON 路径表达式，用于提取需要的内容
        text_content: 是否将内容作为文本返回，默认为 True
    """
    
    def __init__(
        self,
        file_path: str,
        jq_schema: str = ".[]",
        text_content: bool = False
    ):
        """
        初始化 JSONLoader
        
        Args:
            file_path: 要加载的 JSON 文件路径，支持相对路径和绝对路径
            jq_schema: JSON 路径表达式，用于提取需要的内容，默认为 ".[]"
            text_content: 是否将内容作为文本返回，默认为 True
        """
        self.file_path = Path(file_path)
        self.jq_schema = jq_schema
        self.text_content = text_content
        self._loader: Optional[LangChainJSONLoader] = None

    def _get_loader(self) -> LangChainJSONLoader:
        """
        获取底层的 langchain JSONLoader 实例
        
        使用延迟加载模式，只有在首次调用时才创建加载器实例，
        避免不必要的资源占用。
        
        Returns:
            LangChainJSONLoader: 底层的 langchain 加载器实例
        """
        if self._loader is None:
            self._loader = LangChainJSONLoader(
                file_path=str(self.file_path),
                jq_schema=self.jq_schema,
                text_content=self.text_content
            )
        return self._loader

    def load(self) -> List[Document]:
        """
        加载 JSON 文件内容
        
        调用底层 langchain 加载器的 load 方法，将 JSON 文件内容
        转换为 Document 对象列表。
        
        Returns:
            List[Document]: Document 对象列表，每个 Document 代表 JSON 的一部分
        """
        return self._get_loader().load()

    def lazy_load(self) -> List[Document]:
        """
        延迟加载 JSON 文件内容
        
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
    loader = JSONLoader("D:\DocumentLoader\JSONLoader.json")
    documents = loader.load()
    if documents:
        print(documents)
