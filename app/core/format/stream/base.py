"""
流式响应格式化策略基类

定义所有 Provider 格式化策略的抽象接口。

Date: 2026-04-23
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class StreamFormatStrategy(ABC):
    """
    流式响应格式化策略抽象基类
    
    所有具体的 Provider 格式化策略都需要继承此类并实现相应的方法。
    """

    @abstractmethod
    def format_content(
        self, 
        message_chunk: Any, 
        metadata: dict
    ) -> Optional[Any]:
        """
        格式化消息内容
        
        根据 Provider 的特定逻辑处理消息内容。
        
        Args:
            message_chunk: 消息块
            metadata: 元数据字典，包含 provider 信息等
            
        Returns:
            格式化后的内容，如果应该跳过则返回 None
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        获取 Provider 名称
        
        Returns:
            Provider 的标识名称
        """
        pass
