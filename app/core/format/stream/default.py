"""
通用 Provider 流式响应格式化策略

处理其他 Provider（非 Ollama）的默认格式化逻辑。

Date: 2026-04-23
"""

from typing import Any, Optional
from app.core.format.stream.base import StreamFormatStrategy


class DefaultStreamFormatStrategy(StreamFormatStrategy):
    """
    通用 Provider 流式格式化策略
    
    处理默认的 Provider 格式化：
    - 直接返回 message_chunk 的 content
    - 如果 content 为空，返回 None 跳过
    """

    @property
    def provider_name(self) -> str:
        return 'default'

    def format_content(
        self, 
        message_chunk: Any, 
        metadata: dict
    ) -> Optional[Any]:
        """
        格式化通用消息内容
        
        处理逻辑：
        1. 获取 message_chunk 的 content
        2. 如果 content 不为空，直接返回
        3. 如果 content 为空，返回 None 跳过
        
        Args:
            message_chunk: 消息块
            metadata: 元数据字典
            
        Returns:
            消息内容或 None
        """
        content = getattr(message_chunk, 'content', str(message_chunk))
        
        if content:
            return content
        
        return None
