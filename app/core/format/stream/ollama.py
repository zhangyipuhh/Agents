"""
Ollama Provider 流式响应格式化策略

实现 Ollama Provider 的特定消息格式化逻辑。

Date: 2026-04-23
"""

from typing import Any, Optional
from app.core.format.stream.base import StreamFormatStrategy


class OllamaStreamFormatStrategy(StreamFormatStrategy):
    """
    Ollama Provider 流式格式化策略
    
    处理 Ollama Provider 的特定输出格式：
    - 检查 content 是否为空
    - 处理 reasoning_content (thinking) 的逻辑
    - 返回统一格式的内容
    """

    @property
    def provider_name(self) -> str:
        return 'ollama'

    def format_content(
        self, 
        message_chunk: Any, 
        metadata: dict
    ) -> Optional[Any]:
        """
        格式化 Ollama 消息内容
        
        处理逻辑：
        1. 如果 content 不为空：
           - 检查 reasoning_content 是否存在
           - 如果 reasoning_content 有值，使用 thinking 格式
           - 否则使用普通文本格式
        2. 如果 content 为空：
           - 检查 reasoning_content
           - 如果有 thinking 内容，使用 thinking 格式
        3. 如果都没有，返回 None 跳过
        
        Args:
            message_chunk: 消息块
            metadata: 元数据字典
            
        Returns:
            格式化后的内容或 None
        """
        content = getattr(message_chunk, 'content', str(message_chunk))
        reasoning_content = None

        if content:
            reasoning_content = getattr(message_chunk, 'additional_kwargs', str(message_chunk))
            if not reasoning_content or not reasoning_content.get("reasoning_content"):
                return [{'text': content, 'type': 'text'}]
            else:
                thinking_content = reasoning_content["reasoning_content"]
                if thinking_content:
                    return [{'thinking': thinking_content, 'type': 'thinking', 'index': 0}]
        else:
            reasoning_content = getattr(message_chunk, 'additional_kwargs', str(message_chunk))
            if reasoning_content:
                thinking_content = reasoning_content["reasoning_content"]
                if thinking_content:
                    return [{'thinking': thinking_content, 'type': 'thinking', 'index': 0}]

        return None
