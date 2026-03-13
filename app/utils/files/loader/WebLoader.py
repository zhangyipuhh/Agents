#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
WebLoader 模块

提供网页内容加载功能，基于 web_untils.py 的 web_parser 函数进行封装，
支持延迟加载、多种提取类型（正文/表格/列表/完整页面）等扩展功能。

Date: 2026-03-13
Author: 张镒谱
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from langchain_core.documents import Document

import sys
sys.path.append(str(Path(__file__).parent.parent))
from web_untils import web_parser


class WebLoader:
    """
    网页内容加载器

    对 web_untils.py 的 web_parser 函数进行封装，提供更友好的 API 和额外功能。
    支持智能提取正文、表格、列表或完整页面内容。

    Attributes:
        url: 要加载的网页 URL
        extract_type: 提取类型，可选 "article", "table", "list", "full"
        max_length: 最大返回字符数，防止超出模型上下文限制
        include_links: 是否在正文中保留超链接
    """

    def __init__(
        self,
        url: str,
        extract_type: str = "article",
        max_length: Optional[int] = 8000,
        include_links: bool = False
    ):
        """
        初始化 WebLoader

        Args:
            url: 要加载的网页 URL，支持带/不带协议
            extract_type: 提取类型，可选 "article"(正文), "table"(表格), "list"(列表), "full"(完整页面)
            max_length: 最大返回字符数，防止 token 超限，默认 8000
            include_links: 是否在正文中保留超链接（转为 Markdown 格式），默认 False
        """
        self.url = url
        self.extract_type = extract_type
        self.max_length = max_length
        self.include_links = include_links
        self._documents: Optional[List[Document]] = None

    def _parse(self) -> List[Document]:
        """
        调用 web_parser 解析网页内容

        Returns:
            List[Document]: Document 对象列表
        """
        return web_parser(
            url=self.url,
            extract_type=self.extract_type,
            max_length=self.max_length,
            include_links=self.include_links
        )

    def load(self) -> List[Document]:
        """
        加载网页内容

        根据初始化参数调用 web_parser 解析网页，返回 Document 对象列表。

        Returns:
            List[Document]: Document 对象列表
        """
        if self._documents is None:
            self._documents = self._parse()
        return self._documents

    def lazy_load(self) -> List[Document]:
        """
        延迟加载网页内容

        与 load 方法类似，但使用 lazy_load 模式，适合处理大页面。
        当前实现与 load 相同，后续可优化为真正的生成器模式。

        Returns:
            List[Document]: Document 对象列表
        """
        return self.load()

    def load_with_type(
        self,
        extract_type: str,
        max_length: Optional[int] = None,
        include_links: Optional[bool] = None
    ) -> List[Document]:
        """
        使用指定参数加载网页内容

        Args:
            extract_type: 提取类型，可选 "article", "table", "list", "full"
            max_length: 最大返回字符数，默认使用初始化时的值
            include_links: 是否保留超链接，默认使用初始化时的值

        Returns:
            List[Document]: Document 对象列表
        """
        _max_length = max_length if max_length is not None else self.max_length
        _include_links = include_links if include_links is not None else self.include_links

        return web_parser(
            url=self.url,
            extract_type=extract_type,
            max_length=_max_length,
            include_links=_include_links
        )

    def load_article(
        self,
        max_length: Optional[int] = None,
        include_links: bool = False
    ) -> List[Document]:
        """
        智能提取网页正文内容

        Args:
            max_length: 最大返回字符数，默认使用初始化时的值
            include_links: 是否保留超链接

        Returns:
            List[Document]: Document 对象列表
        """
        return self.load_with_type(
            extract_type="article",
            max_length=max_length,
            include_links=include_links
        )

    def load_tables(self, max_length: Optional[int] = None) -> List[Document]:
        """
        提取网页中的表格内容

        Args:
            max_length: 最大返回字符数，默认使用初始化时的值

        Returns:
            List[Document]: Document 对象列表
        """
        return self.load_with_type(
            extract_type="table",
            max_length=max_length,
            include_links=False
        )

    def load_lists(self, max_length: Optional[int] = None) -> List[Document]:
        """
        提取网页中的列表内容

        Args:
            max_length: 最大返回字符数，默认使用初始化时的值

        Returns:
            List[Document]: Document 对象列表
        """
        return self.load_with_type(
            extract_type="list",
            max_length=max_length,
            include_links=False
        )

    def load_full(self, max_length: Optional[int] = None) -> List[Document]:
        """
        提取完整网页内容

        Args:
            max_length: 最大返回字符数，默认使用初始化时的值

        Returns:
            List[Document]: Document 对象列表
        """
        return self.load_with_type(
            extract_type="full",
            max_length=max_length,
            include_links=False
        )

    @property
    def is_valid_url(self) -> bool:
        """
        检查 URL 是否有效

        Returns:
            bool: URL 有效返回 True，否则返回 False
        """
        if not self.url or not isinstance(self.url, str):
            return False
        url = self.url.strip()
        return url.startswith(('http://', 'https://')) or '.' in url


if __name__ == "__main__":
    # 测试代码
    # 方式1: 使用默认参数加载网页正文
    loader = WebLoader("https://docs.langchain.org.cn/oss/python/integrations/document_loaders/microsoft_word")
    if loader.is_valid_url:
        documents = loader.load()
        print("加载网页正文:")
        for doc in documents:
            print(f"Content: {doc.page_content[:500]}...")
            print(f"Metadata: {doc.metadata}")
            print("-" * 50)

    # 方式2: 使用特定方法加载表格
    print("\n加载网页表格:")
    table_docs = loader.load_tables()
    for doc in table_docs:
        print(f"Content: {doc.page_content[:500]}...")
        print(f"Metadata: {doc.metadata}")
        print("-" * 50)

    # 方式3: 使用自定义参数加载
    print("\n使用自定义参数加载:")
    custom_loader = WebLoader(
        url="https://docs.langchain.org.cn/oss/python/integrations/document_loaders/microsoft_word",
        extract_type="full",
        max_length=4000,
        include_links=True
    )
    custom_docs = custom_loader.load()
    for doc in custom_docs:
        print(f"Content: {doc.page_content[:500]}...")
        print(f"Metadata: {doc.metadata}")
        print("-" * 50)
