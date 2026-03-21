#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocumentLoader 模块

通用文件加载工具，支持多种文件类型的智能加载。
- 支持单个文件或批量文件夹加载
- 自动识别文件类型并选择对应的加载器
- 支持配置化参数传递
- 内置常见文件类型映射

Date: 2026-03-13
Author: 张镠谱
"""

from pathlib import Path
from typing import Union, List, Dict, Optional, Type, Any, Callable
from langchain_core.documents import Document

from app.shared.utils.files.loader.TextLoader import TextLoader
from app.shared.utils.files.loader.CSVLoader import CSVLoader
from app.shared.utils.files.loader.JSONLoader import JSONLoader
from app.shared.utils.files.loader.MarkdownLoader import MarkdownLoader
from app.shared.utils.files.loader.PDFLoader import PDFLoader
from app.shared.utils.files.loader.WebLoader import WebLoader
from app.shared.utils.files.loader.WordLoader import WordLoader


class DocumentLoader:
    """
    通用文件加载器

    智能识别文件类型，自动选择对应的加载器进行加载。
    支持单个文件或批量文件夹加载，支持自定义配置参数。

    Attributes:
        path: 文件或文件夹路径
        glob: 批量加载时的匹配规则
        silent_errors: 是否跳过加载失败的文件
    """

    # 文件扩展名 → 加载器类 映射表
    LOADER_MAPPING: Dict[str, Type] = {
        # 文本文件
        '.txt': TextLoader,
        '.md': MarkdownLoader,
        '.markdown': MarkdownLoader,

        # 文档
        '.pdf': PDFLoader,
        '.docx': WordLoader,
        '.doc': WordLoader,

        # 数据文件
        '.csv': CSVLoader,
        '.json': JSONLoader,
    }

    # 各加载器的默认参数配置
    LOADER_DEFAULT_KWARGS: Dict[str, Dict[str, Any]] = {
        '.txt': {'encoding': 'utf-8'},
        '.csv': {'encoding': 'utf-8'},
        '.json': {'jq_schema': '.[]', 'text_content': False},
        '.docx': {'load_method': 'default'},
        '.doc': {'load_method': 'default'},
    }

    def __init__(
        self,
        path: Union[str, Path],
        glob: str = "**/*",
        silent_errors: bool = True,
        custom_mapping: Optional[Dict[str, Type]] = None,
        custom_kwargs: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """
        初始化 DocumentLoader

        Args:
            path: 文件或文件夹路径，支持相对路径和绝对路径
            glob: 批量加载时的匹配规则，默认为 "**/*"（所有文件）
            silent_errors: 是否跳过加载失败的文件，默认为 True
            custom_mapping: 自定义文件类型映射（覆盖或扩展默认）
            custom_kwargs: 自定义加载器参数（覆盖或扩展默认）
        """
        self.path = Path(path)
        self.glob = glob
        self.silent_errors = silent_errors

        # 合并自定义映射
        self.mapping = {**self.LOADER_MAPPING, **(custom_mapping or {})}
        self.kwargs_map = {**self.LOADER_DEFAULT_KWARGS, **(custom_kwargs or {})}

    def _get_loader_class(self, file_path: Path) -> Optional[Type]:
        """
        根据文件扩展名获取加载器类

        Args:
            file_path: 文件路径

        Returns:
            Optional[Type]: 加载器类，如果不支持则返回 None
        """
        ext = file_path.suffix.lower()
        return self.mapping.get(ext)

    def _get_loader_kwargs(self, file_path: Path) -> Dict[str, Any]:
        """
        获取该文件类型的默认参数

        Args:
            file_path: 文件路径

        Returns:
            Dict[str, Any]: 加载器参数字典
        """
        ext = file_path.suffix.lower()
        return self.kwargs_map.get(ext, {}).copy()

    def _load_single(self, file_path: Path, **override_kwargs) -> List[Document]:
        """
        加载单个文件

        Args:
            file_path: 文件路径
            **override_kwargs: 覆盖默认参数的额外参数

        Returns:
            List[Document]: Document 对象列表
        """
        try:
            loader_cls = self._get_loader_class(file_path)

            if loader_cls is None:
                if self.silent_errors:
                    print(f"⏭️  跳过不支持的文件类型: {file_path}")
                    return []
                raise ValueError(f"不支持的文件类型: {file_path.suffix}")

            # 获取默认参数并合并覆盖参数
            kwargs = self._get_loader_kwargs(file_path)
            kwargs.update(override_kwargs)

            print(f"📄 {file_path.name} → {loader_cls.__name__}")

            # 创建加载器实例并加载
            loader = loader_cls(str(file_path), **kwargs)
            docs = loader.load()

            # 统一添加元数据
            for doc in docs:
                doc.metadata.update({
                    'source': str(file_path),
                    'file_type': file_path.suffix.lower(),
                    'loader_used': loader_cls.__name__,
                })

            return docs

        except Exception as e:
            if self.silent_errors:
                print(f"❌ 跳过 {file_path}: {e}")
                return []
            raise

    def load(self, **override_kwargs) -> List[Document]:
        """
        智能加载文件

        - 如果是文件则单个加载
        - 如果是文件夹则批量加载

        Args:
            **override_kwargs: 覆盖默认参数的额外参数

        Returns:
            List[Document]: Document 对象列表

        Raises:
            FileNotFoundError: 路径不存在时抛出
        """
        # 单个文件
        if self.path.is_file():
            return self._load_single(self.path, **override_kwargs)

        # 文件夹：收集所有支持的文件
        elif self.path.is_dir():
            all_docs = []

            for file_path in self.path.glob(self.glob):
                if not file_path.is_file():
                    continue

                # 检查是否支持该类型
                ext = file_path.suffix.lower()
                if ext not in self.mapping:
                    print(f"⏭️  跳过不支持类型: {file_path}")
                    continue

                docs = self._load_single(file_path, **override_kwargs)
                all_docs.extend(docs)

            print(f"\n✅ 总计: {len(all_docs)} 个文档片段")
            return all_docs

        else:
            raise FileNotFoundError(f"路径不存在: {self.path}")

    def load_with_config(
        self,
        file_type: str,
        **kwargs
    ) -> List[Document]:
        """
        使用指定配置加载当前路径的文件

        Args:
            file_type: 文件扩展名（如 '.txt', '.pdf' 等）
            **kwargs: 传递给加载器的参数

        Returns:
            List[Document]: Document 对象列表
        """
        if self.path.is_file():
            return self._load_single(self.path, **kwargs)
        elif self.path.is_dir():
            # 针对特定类型过滤
            all_docs = []
            for file_path in self.path.glob(self.glob):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() != file_type.lower():
                    continue
                docs = self._load_single(file_path, **kwargs)
                all_docs.extend(docs)
            return all_docs
        else:
            raise FileNotFoundError(f"路径不存在: {self.path}")

    @classmethod
    def load_url(
        cls,
        url: str,
        extract_type: str = "article",
        max_length: Optional[int] = 8000,
        include_links: bool = False
    ) -> List[Document]:
        """
        加载网页内容

        类方法，直接加载指定 URL 的网页内容。

        Args:
            url: 网页 URL
            extract_type: 提取类型，可选 "article", "table", "list", "full"
            max_length: 最大返回字符数
            include_links: 是否保留超链接

        Returns:
            List[Document]: Document 对象列表
        """
        loader = WebLoader(
            url=url,
            extract_type=extract_type,
            max_length=max_length,
            include_links=include_links
        )
        return loader.load()


# ========== 使用示例 ==========

if __name__ == "__main__":
    # 测试文件路径数组（来自各 loader 的测试地址）
    test_files = [
        r"D:\DocumentLoader\TextLoader.txt",
        r"D:\DocumentLoader\MarkdownLoader.md",
        r"D:\DocumentLoader\PdfLoader.pdf",
        r"D:\DocumentLoader\WordLoader.docx",
        r"D:\DocumentLoader\CSVLoader.csv",
        r"D:\DocumentLoader\JSONLoader.json",
    ]

    for file_path in test_files:
        print(f"\n{'='*60}")
        print(f"📂 正在加载: {file_path}")
        print(f"{'='*60}")

        try:
            loader = DocumentLoader(file_path)
            docs = loader.load()

            if docs:
                print(f"\n✅ 成功加载 {len(docs)} 个文档片段:\n")
                for idx, doc in enumerate(docs, 1):
                    print(f"--- 片段 {idx} ---")
                    print(f"内容: {doc.page_content[:500]}{'...' if len(doc.page_content) > 500 else ''}")
                    print(f"元数据: {doc.metadata}")
                    print()
            else:
                print("⚠️  未加载到任何内容")

        except Exception as e:
            print(f"❌ 加载失败: {e}")
