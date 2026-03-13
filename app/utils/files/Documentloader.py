from pathlib import Path
from typing import Union, List, Dict, Optional, Type
from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredPDFLoader,
    UnstructuredWordDocumentLoader,
    CSVLoader,
    JSONLoader,
    UnstructuredHTMLLoader,
    PythonLoader,
)
from langchain_core.documents import Document


class SmartFileLoader:
    """
    智能文件加载器
    - 自动识别文件类型
    - 支持单个文件或批量文件夹
    - 内置常见文件类型映射
    """
    
    # 文件扩展名 → 加载器类 映射表
    LOADER_MAPPING: Dict[str, Type] = {
        # 文本文件
        '.txt': TextLoader,
        '.md': UnstructuredMarkdownLoader,
        '.markdown': UnstructuredMarkdownLoader,
        
        # 文档
        '.pdf': UnstructuredPDFLoader,
        '.docx': UnstructuredWordDocumentLoader,
        '.doc': UnstructuredWordDocumentLoader,
        
        # 数据文件
        '.csv': CSVLoader,
        '.json': JSONLoader,
        
        # 网页
        '.html': UnstructuredHTMLLoader,
        '.htm': UnstructuredHTMLLoader,
        
        # 代码文件
        '.py': PythonLoader,
    }
    
    # 各加载器的默认参数
    LOADER_KWARGS: Dict[str, Dict] = {
        '.md': {'mode': 'elements', 'strategy': 'fast'},
        '.markdown': {'mode': 'elements', 'strategy': 'fast'},
        '.pdf': {'strategy': 'fast'},
        '.docx': {'strategy': 'fast'},
        '.json': {'jq_schema': '.', 'text_content': False},
    }
    
    def __init__(
        self,
        path: Union[str, Path],
        glob: str = "**/*",
        custom_mapping: Optional[Dict[str, Type]] = None,
        custom_kwargs: Optional[Dict[str, Dict]] = None,
        default_loader: Optional[Type] = TextLoader,
        silent_errors: bool = True,
    ):
        """
        Args:
            path: 文件或文件夹路径
            glob: 批量加载时的匹配规则
            custom_mapping: 自定义文件类型映射（覆盖或扩展默认）
            custom_kwargs: 自定义加载器参数
            default_loader: 未知文件类型使用的默认加载器
            silent_errors: 是否跳过加载失败的文件
        """
        self.path = Path(path)
        self.glob = glob
        self.default_loader = default_loader
        self.silent_errors = silent_errors
        
        # 合并自定义映射
        self.mapping = {**self.LOADER_MAPPING, **(custom_mapping or {})}
        self.kwargs_map = {**self.LOADER_KWARGS, **(custom_kwargs or {})}
    
    def _get_loader_class(self, file_path: Path) -> Type:
        """根据扩展名获取加载器类"""
        ext = file_path.suffix.lower()
        loader_cls = self.mapping.get(ext, self.default_loader)
        
        if ext not in self.mapping:
            print(f"⚠️  未知类型 {ext}，使用默认加载器: {loader_cls.__name__}")
        
        return loader_cls
    
    def _get_loader_kwargs(self, file_path: Path) -> Dict:
        """获取该文件类型的默认参数"""
        ext = file_path.suffix.lower()
        return self.kwargs_map.get(ext, {}).copy()
    
    def _load_single(self, file_path: Path) -> List[Document]:
        """加载单个文件"""
        try:
            loader_cls = self._get_loader_class(file_path)
            kwargs = self._get_loader_kwargs(file_path)
            
            print(f"📄 {file_path.name} → {loader_cls.__name__}")
            
            loader = loader_cls(str(file_path), **kwargs)
            docs = loader.load()
            
            # 统一添加元数据
            for doc in docs:
                doc.metadata.update({
                    'file_type': file_path.suffix.lower(),
                    'loader_used': loader_cls.__name__,
                })
            
            return docs
            
        except Exception as e:
            if self.silent_errors:
                print(f"❌ 跳过 {file_path}: {e}")
                return []
            raise
    
    def load(self) -> List[Document]:
        """智能加载：文件则单个，文件夹则批量"""
        
        # 单个文件
        if self.path.is_file():
            return self._load_single(self.path)
        
        # 文件夹：收集所有支持的文件
        elif self.path.is_dir():
            all_docs = []
            
            # 遍历所有匹配文件
            for file_path in self.path.glob(self.glob):
                if not file_path.is_file():
                    continue
                
                # 检查是否支持该类型
                ext = file_path.suffix.lower()
                if ext not in self.mapping and self.default_loader is None:
                    print(f"⏭️  跳过不支持类型: {file_path}")
                    continue
                
                docs = self._load_single(file_path)
                all_docs.extend(docs)
            
            print(f"\n✅ 总计: {len(all_docs)} 个文档片段")
            return all_docs
        
        else:
            raise FileNotFoundError(f"路径不存在: {self.path}")


# ========== 使用示例 ==========

# 示例1：加载单个 PDF
loader = SmartFileLoader("./docs/report.pdf")
docs = loader.load()

# 示例2：加载单个 Markdown（自动用最佳参数）
loader = SmartFileLoader("./docs/readme.md")
docs = loader.load()  # 自动使用 mode="elements"

# 示例3：批量加载混合类型文件夹
loader = SmartFileLoader(
    path="./docs/",
    glob="**/*",  # 所有文件
)
docs = loader.load()
# 输出：
# 📄 readme.md → UnstructuredMarkdownLoader
# 📄 report.pdf → UnstructuredPDFLoader  
# 📄 data.csv → CSVLoader
# 📄 config.json → JSONLoader
# ✅ 总计: 156 个文档片段

# 示例4：自定义映射和参数
loader = SmartFileLoader(
    path="./docs/",
    glob="**/*.xyz",  # 自定义扩展名
    custom_mapping={
        '.xyz': MyCustomLoader,  # 添加新类型
        '.md': MyMarkdownLoader,  # 覆盖默认
    },
    custom_kwargs={
        '.xyz': {'encoding': 'utf-16'},
        '.md': {'mode': 'single'},  # 覆盖默认参数
    }
)