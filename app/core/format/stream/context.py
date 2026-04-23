"""
流式响应格式化策略上下文

管理不同的格式化策略并根据 Provider 自动选择合适的策略。

Date: 2026-04-23
"""

from typing import Any, Optional, Dict
from app.core.format.stream.base import StreamFormatStrategy
from app.core.format.stream.ollama import OllamaStreamFormatStrategy
from app.core.format.stream.default import DefaultStreamFormatStrategy


class StreamFormatContext:
    """
    流式格式化策略上下文管理器
    
    负责：
    - 注册和管理不同的策略
    - 根据 provider 名称自动选择合适的策略
    - 提供统一的格式化接口
    """

    def __init__(self):
        """
        初始化上下文，注册所有内置策略
        """
        self._strategies: Dict[str, StreamFormatStrategy] = {}
        self._register_default_strategies()

    def _register_default_strategies(self):
        """
        注册默认的策略
        
        当前注册：
        - ollama: OllamaStreamFormatStrategy
        - default: DefaultStreamFormatStrategy (处理其他 Provider)
        """
        self.register_strategy(OllamaStreamFormatStrategy())
        self.register_strategy(DefaultStreamFormatStrategy())

    def register_strategy(self, strategy: StreamFormatStrategy):
        """
        注册新的策略
        
        Args:
            strategy: 策略实例
        """
        self._strategies[strategy.provider_name] = strategy

    def get_strategy(self, provider_name: str) -> Optional[StreamFormatStrategy]:
        """
        获取指定 Provider 的策略
        
        Args:
            provider_name: Provider 名称
            
        Returns:
            对应的策略实例，如果不存在返回 None
        """
        return self._strategies.get(provider_name)

    def format_message(
        self, 
        message_chunk: Any, 
        metadata: dict
    ) -> Optional[Any]:
        """
        使用合适的策略格式化消息
        
        Args:
            message_chunk: 消息块
            metadata: 元数据字典
            
        Returns:
            格式化后的内容，如果应该跳过则返回 None
        """
        provider_name = metadata.get('ls_provider')
        
        if not provider_name:
            return None
        
        strategy = self.get_strategy(provider_name)
        
        if strategy is None:
            strategy = self.get_strategy('default')
        
        if strategy is None:
            return None
            
        return strategy.format_content(message_chunk, metadata)

    @property
    def available_providers(self) -> list:
        """
        获取所有已注册的 Provider 列表
        
        Returns:
            Provider 名称列表
        """
        return list(self._strategies.keys())


stream_format_context = StreamFormatContext()
