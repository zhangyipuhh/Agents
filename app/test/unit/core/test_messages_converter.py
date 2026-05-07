import pytest
from app.core.messages.converter import (
    MessageContentConverter,
    extract_message_content,
    extract_text,
    extract_full,
)
from langchain_core.messages import AIMessage


class TestMessageContentConverterToString:
    def test_string_content(self):
        assert MessageContentConverter.to_string("Hello") == "Hello"

    def test_list_with_text_type(self):
        content = [{"type": "text", "text": "Hello world"}]
        assert MessageContentConverter.to_string(content) == "Hello world"

    def test_list_with_thinking_excluded_by_default(self):
        content = [
            {"type": "thinking", "thinking": "I think..."},
            {"type": "text", "text": "Hello"},
        ]
        result = MessageContentConverter.to_string(content, include_thinking=False)
        assert "I think..." not in result
        assert "Hello" in result

    def test_list_with_thinking_included(self):
        content = [
            {"type": "thinking", "thinking": "I think..."},
            {"type": "text", "text": "Hello"},
        ]
        result = MessageContentConverter.to_string(content, include_thinking=True)
        assert "[思考]: I think..." in result
        assert "Hello" in result

    def test_list_with_image_url(self):
        content = [{"type": "image_url", "url": "https://example.com/img.png"}]
        result = MessageContentConverter.to_string(content)
        assert "[图片]" in result

    def test_list_with_tool_use(self):
        content = [{"type": "tool_use", "name": "search", "input": {"q": "test"}}]
        result = MessageContentConverter.to_string(content)
        assert "[工具调用]: search" in result

    def test_list_with_tool_result(self):
        content = [{"type": "tool_result", "content": "result data"}]
        result = MessageContentConverter.to_string(content)
        assert "[工具结果]: result data" in result

    def test_list_with_unknown_type_has_text(self):
        content = [{"type": "custom", "text": "custom text"}]
        result = MessageContentConverter.to_string(content)
        assert "custom text" in result

    def test_list_with_unknown_type_has_content(self):
        content = [{"type": "custom", "content": "custom content"}]
        result = MessageContentConverter.to_string(content)
        assert "custom content" in result

    def test_list_with_string_items(self):
        content = ["Hello", "World"]
        result = MessageContentConverter.to_string(content)
        assert "Hello" in result
        assert "World" in result

    def test_empty_thinking_not_included(self):
        content = [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": "Hello"},
        ]
        result = MessageContentConverter.to_string(content, include_thinking=True)
        assert "[思考]:" not in result
        assert "Hello" in result

    def test_custom_thinking_prefix(self):
        content = [{"type": "thinking", "thinking": "deep thought"}]
        result = MessageContentConverter.to_string(
            content, include_thinking=True, thinking_prefix="[THINK]: "
        )
        assert "[THINK]: deep thought" in result

    def test_numeric_content(self):
        assert MessageContentConverter.to_string(42) == "42"


class TestMessageContentConverterExtractText:
    def test_extracts_text_only(self):
        content = [
            {"type": "thinking", "thinking": "I think..."},
            {"type": "text", "text": "Hello"},
        ]
        result = MessageContentConverter.extract_text(content)
        assert "I think..." not in result
        assert "Hello" in result


class TestMessageContentConverterExtractFull:
    def test_extracts_text_and_thinking(self):
        content = [
            {"type": "thinking", "thinking": "I think..."},
            {"type": "text", "text": "Hello"},
        ]
        result = MessageContentConverter.extract_full(content)
        assert "[思考]: I think..." in result
        assert "Hello" in result


class TestExtractMessageContent:
    def test_from_ai_message(self):
        msg = AIMessage(content="Hello AI")
        result = extract_message_content(msg)
        assert result == "Hello AI"

    def test_from_ai_message_with_thinking(self):
        msg = AIMessage(content=[{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Hi"}])
        result = extract_message_content(msg, include_thinking=True)
        assert "[思考]: hmm" in result
        assert "Hi" in result


class TestExtractText:
    def test_from_ai_message(self):
        msg = AIMessage(content="Hello")
        result = extract_text(msg)
        assert result == "Hello"


class TestExtractFull:
    def test_from_ai_message(self):
        msg = AIMessage(content=[{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Hi"}])
        result = extract_full(msg)
        assert "[思考]: hmm" in result
        assert "Hi" in result
