import pytest
from unittest.mock import MagicMock
from app.core.format.stream.base import StreamFormatStrategy
from app.core.format.stream.default import DefaultStreamFormatStrategy
from app.core.format.stream.ollama import OllamaStreamFormatStrategy
from app.core.format.stream.context import StreamFormatContext


class TestDefaultStreamFormatStrategy:
    def test_provider_name(self):
        strategy = DefaultStreamFormatStrategy()
        assert strategy.provider_name == "default"

    def test_format_content_with_text(self):
        strategy = DefaultStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = "Hello world"
        result = strategy.format_content(chunk, {})
        assert result == "Hello world"

    def test_format_content_with_empty_content(self):
        strategy = DefaultStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = ""
        result = strategy.format_content(chunk, {})
        assert result is None

    def test_format_content_with_none_content(self):
        strategy = DefaultStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = None
        result = strategy.format_content(chunk, {})
        assert result is None

    def test_format_content_without_content_attr(self):
        strategy = DefaultStreamFormatStrategy()
        chunk = "plain string"
        result = strategy.format_content(chunk, {})
        assert result == "plain string"


class TestOllamaStreamFormatStrategy:
    def test_provider_name(self):
        strategy = OllamaStreamFormatStrategy()
        assert strategy.provider_name == "ollama"

    def test_format_content_plain_text(self):
        strategy = OllamaStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = "Hello"
        chunk.additional_kwargs = {}
        result = strategy.format_content(chunk, {})
        assert result == [{"text": "Hello", "type": "text"}]

    def test_format_content_with_thinking(self):
        strategy = OllamaStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = "Hello"
        chunk.additional_kwargs = {"reasoning_content": "thinking..."}
        result = strategy.format_content(chunk, {})
        assert result == [{"thinking": "thinking...", "type": "thinking", "index": 0}]

    def test_format_content_empty_content_with_thinking(self):
        strategy = OllamaStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = ""
        chunk.additional_kwargs = {"reasoning_content": "deep thought"}
        result = strategy.format_content(chunk, {})
        assert result == [{"thinking": "deep thought", "type": "thinking", "index": 0}]

    def test_format_content_empty_content_no_thinking(self):
        strategy = OllamaStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = ""
        chunk.additional_kwargs = {}
        result = strategy.format_content(chunk, {})
        assert result is None

    def test_format_content_empty_reasoning_content(self):
        strategy = OllamaStreamFormatStrategy()
        chunk = MagicMock()
        chunk.content = "text"
        chunk.additional_kwargs = {"reasoning_content": ""}
        result = strategy.format_content(chunk, {})
        assert result == [{"text": "text", "type": "text"}]


class TestStreamFormatContext:
    def test_default_strategies_registered(self):
        ctx = StreamFormatContext()
        assert "ollama" in ctx.available_providers
        assert "default" in ctx.available_providers

    def test_get_strategy_ollama(self):
        ctx = StreamFormatContext()
        strategy = ctx.get_strategy("ollama")
        assert isinstance(strategy, OllamaStreamFormatStrategy)

    def test_get_strategy_default(self):
        ctx = StreamFormatContext()
        strategy = ctx.get_strategy("default")
        assert isinstance(strategy, DefaultStreamFormatStrategy)

    def test_get_strategy_unknown_returns_none(self):
        ctx = StreamFormatContext()
        strategy = ctx.get_strategy("unknown_provider")
        assert strategy is None

    def test_format_message_uses_correct_strategy(self):
        ctx = StreamFormatContext()
        chunk = MagicMock()
        chunk.content = "test"
        chunk.additional_kwargs = {}
        result = ctx.format_message(chunk, {"ls_provider": "ollama"})
        assert result == [{"text": "test", "type": "text"}]

    def test_format_message_falls_back_to_default(self):
        ctx = StreamFormatContext()
        chunk = MagicMock()
        chunk.content = "test"
        result = ctx.format_message(chunk, {"ls_provider": "unknown"})
        assert result == "test"

    def test_format_message_no_provider_returns_none(self):
        ctx = StreamFormatContext()
        chunk = MagicMock()
        chunk.content = "test"
        result = ctx.format_message(chunk, {})
        assert result is None

    def test_register_custom_strategy(self):
        ctx = StreamFormatContext()

        class CustomStrategy(StreamFormatStrategy):
            @property
            def provider_name(self):
                return "custom"

            def format_content(self, message_chunk, metadata):
                return "custom_result"

        ctx.register_strategy(CustomStrategy())
        assert "custom" in ctx.available_providers
        strategy = ctx.get_strategy("custom")
        assert isinstance(strategy, CustomStrategy)

    def test_available_providers_returns_list(self):
        ctx = StreamFormatContext()
        providers = ctx.available_providers
        assert isinstance(providers, list)
        assert len(providers) >= 2
