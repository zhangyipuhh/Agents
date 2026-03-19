"""
ToolChunkResponse 模块

该模块提供工具分块读取响应的标准化数据结构，用于规范文件读取场景下
的工具回复格式，确保回复内容的一致性和可扩展性。

基于 BaseTools.py 中文件读取工具的响应结构设计。

典型响应结构:
{
    "index": int,           # 当前块的索引（从1开始）
    "name": str,            # 文件/块名称
    "content": str,         # 当前块的内容
    "is_last": bool,        # 是否为最后一块
    "next_tool": str|None, # 下一个工具名称（最后一块时为None）
    "next_step": str        # 下一步操作说明
}
"""

from dataclasses import dataclass, asdict
from typing import Optional
import json


@dataclass
class ToolChunkResponse:
    """
    工具分块读取响应类

    该类用于标准化文件读取场景下的回复结构，包含当前块的索引、名称、
    内容以及下一步操作信息。支持序列化为JSON格式。

    Attributes:
        index: 当前块的索引，从1开始编号
        name: 文件或块的名称
        content: 当前块的实际内容
        is_last: 标记当前块是否为文件的最后一块
        next_tool: 下一个要调用的工具名称，如果is_last为True则为None
        next_step: 描述下一步操作的说明文本
    """

    index: int
    name: str
    content: str
    is_last: bool
    next_tool: Optional[str]
    next_step: str

    def to_dict(self) -> dict:
        """
        将响应对象转换为字典格式

        Returns:
            dict: 包含所有字段的字典
        """
        return asdict(self)

    def to_json(self, ensure_ascii: bool = False) -> str:
        """
        将响应对象序列化为JSON字符串

        Args:
            ensure_ascii: 是否强制ASCII编码，默认为False（允许Unicode字符）

        Returns:
            str: JSON格式的字符串
        """
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii)

    @classmethod
    def create(
        cls,
        index: int,
        name: str,
        content: str,
        is_last: bool,
        cache_id: Optional[str] = None
    ) -> "ToolChunkResponse":
        """
        工厂方法：创建分块读取响应对象

        根据当前块的信息自动构建响应，包括判断是否为最后一块，
        并生成相应的next_tool和next_step字段。

        Args:
            index: 当前块的索引，从1开始
            name: 文件或块的名称
            content: 当前块的内容
            is_last: 是否为最后一块
            cache_id: 缓存ID，用于生成next_tool调用参数

        Returns:
            ToolChunkResponse: 新的响应对象实例

        Example:
            >>> response = ToolChunkResponse.create(
            ...     index=1,
            ...     name="document.txt",
            ...     content="文件内容...",
            ...     is_last=False,
            ...     cache_id="abc123"
            ... )
            >>> response.next_tool
            'read_cached_chunk'
            >>> response.next_step
            "继续调用 read_cached_chunk(cache_id='abc123') 读取下一块"
        """
        if is_last:
            next_tool = None
            next_step = "文档读取完毕"
        else:
            next_tool = "read_cached_chunk"
            cache_param = f"cache_id='{cache_id}'" if cache_id else ""
            next_step = f"继续调用 read_cached_chunk({cache_param}) 读取下一块"

        return cls(
            index=index,
            name=name,
            content=content,
            is_last=is_last,
            next_tool=next_tool,
            next_step=next_step
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ToolChunkResponse":
        """
        从字典创建响应对象

        Args:
            data: 包含响应字段的字典

        Returns:
            ToolChunkResponse: 新的响应对象实例
        """
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "ToolChunkResponse":
        """
        从JSON字符串创建响应对象

        Args:
            json_str: JSON格式的字符串

        Returns:
            ToolChunkResponse: 新的响应对象实例
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
