"""
流式响应格式化模块

使用策略模式处理不同 LLM Provider 的输出格式。

主要功能：
- 统一的消息格式化接口
- 支持不同 Provider 的特定处理逻辑
- 便于扩展新的 Provider

当前支持的 Provider：
- ollama: OllamaStreamFormatStrategy
- 其他: DefaultStreamFormatStrategy

Date: 2026-04-23
"""

from app.core.format.stream.base import StreamFormatStrategy
from app.core.format.stream.ollama import OllamaStreamFormatStrategy
from app.core.format.stream.default import DefaultStreamFormatStrategy
from app.core.format.stream.context import StreamFormatContext, stream_format_context

__all__ = [
    'StreamFormatStrategy',
    'OllamaStreamFormatStrategy',
    'DefaultStreamFormatStrategy',
    'StreamFormatContext',
    'stream_format_context',
]
