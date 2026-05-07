import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.core.messages.trim import trim_old_tool_messages, trim_messages_with_tool_limit


class TestTrimOldToolMessages:
    def test_no_tool_messages(self):
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        result = trim_old_tool_messages(messages, keep_last_n=2)
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Hi there"

    def test_keep_last_n_tool_messages(self):
        messages = [
            HumanMessage(content="Hello"),
            ToolMessage(content="tool result 1", tool_call_id="1"),
            ToolMessage(content="tool result 2", tool_call_id="2"),
            ToolMessage(content="tool result 3", tool_call_id="3"),
        ]
        result = trim_old_tool_messages(messages, keep_last_n=2)
        assert len(result) == 4
        assert "已被压缩" in result[1].content
        assert result[2].content == "tool result 2"
        assert result[3].content == "tool result 3"

    def test_keep_all_when_fewer_than_n(self):
        messages = [
            ToolMessage(content="tool result 1", tool_call_id="1"),
            ToolMessage(content="tool result 2", tool_call_id="2"),
        ]
        result = trim_old_tool_messages(messages, keep_last_n=5)
        assert len(result) == 2
        assert result[0].content == "tool result 1"
        assert result[1].content == "tool result 2"

    def test_keep_last_1_tool_message(self):
        messages = [
            HumanMessage(content="Hello"),
            ToolMessage(content="old result", tool_call_id="1"),
            ToolMessage(content="new result", tool_call_id="2"),
        ]
        result = trim_old_tool_messages(messages, keep_last_n=1)
        assert len(result) == 3
        assert "已被压缩" in result[1].content
        assert result[2].content == "new result"

    def test_trimmed_message_preserves_tool_call_id(self):
        messages = [
            ToolMessage(content="result", tool_call_id="tc-123", name="search"),
        ]
        result = trim_old_tool_messages(messages, keep_last_n=0)
        assert len(result) == 1
        assert result[0].tool_call_id == "tc-123"

    def test_empty_messages(self):
        result = trim_old_tool_messages([], keep_last_n=2)
        assert result == []

    def test_keep_last_n_zero(self):
        messages = [
            HumanMessage(content="Hello"),
            ToolMessage(content="result", tool_call_id="1"),
        ]
        result = trim_old_tool_messages(messages, keep_last_n=0)
        assert len(result) == 2
        assert "已被压缩" in result[1].content


class TestTrimMessagesWithToolLimit:
    def test_trims_tool_messages_only(self):
        messages = [
            HumanMessage(content="Hello"),
            ToolMessage(content="old result", tool_call_id="1"),
            ToolMessage(content="new result", tool_call_id="2"),
        ]
        result = trim_messages_with_tool_limit(messages, keep_last_n=1)
        assert len(result) == 3
        assert "已被压缩" in result[1].content
        assert result[2].content == "new result"

    def test_no_token_trimming_without_params(self):
        messages = [
            HumanMessage(content="Hello"),
            ToolMessage(content="result", tool_call_id="1"),
        ]
        result = trim_messages_with_tool_limit(messages, keep_last_n=2, max_tokens=None, token_counter=None)
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "result"
