import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.core.agent.agent import Agent, _get_mime_type_from_base64, get_agent
from app.core.agent.AgentConfig import AgentConfig


class TestGetMimeTypeFromBase64:
    def test_jpeg(self):
        assert _get_mime_type_from_base64("/9j/abc") == "image/jpeg"

    def test_png(self):
        assert _get_mime_type_from_base64("iVBORw0KGgo") == "image/png"

    def test_gif(self):
        assert _get_mime_type_from_base64("R0lGOD") == "image/gif"

    def test_webp(self):
        assert _get_mime_type_from_base64("UklGR") == "image/webp"

    def test_unknown_defaults_to_jpeg(self):
        assert _get_mime_type_from_base64("unknown") == "image/jpeg"

    def test_empty_string_defaults_to_jpeg(self):
        assert _get_mime_type_from_base64("") == "image/jpeg"


class TestAgentInit:
    @patch("app.core.agent.agent.LLM_CONFIG", {"model_type": "openai", "model_name": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1", "is_multimodal": False, "parallel_tool_calls": None})
    def test_init_stores_config_values(self):
        config = AgentConfig(
            model_type="openai",
            model_name="gpt-4",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            temperature=0.5,
            system_prompt="Test prompt",
        )
        agent = Agent(config=config)
        assert agent._model_type == "openai"
        assert agent._model_name == "gpt-4"
        assert agent._api_key == "test-key"
        assert agent._base_url == "https://api.openai.com/v1"
        assert agent._temperature == 0.5
        assert agent.system_prompt == "Test prompt"

    def test_init_uses_llm_config_defaults_when_not_provided(self):
        from app.core.agent.agent import LLM_CONFIG
        config = AgentConfig()
        agent = Agent(config=config)
        assert agent._model_type == LLM_CONFIG["model_type"]
        assert agent._model_name == LLM_CONFIG["model_name"]


class TestAgentShouldContinue:
    @patch("app.core.agent.agent.LLM_CONFIG", {"model_type": "openai", "model_name": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1", "is_multimodal": False, "parallel_tool_calls": None})
    def test_returns_tools_when_tool_calls_present(self):
        config = AgentConfig()
        agent = Agent(config=config)
        ai_msg = AIMessage(content="", tool_calls=[{"name": "test_tool", "args": {}, "id": "1"}])
        state = {"messages": [ai_msg]}
        assert agent._should_continue(state) == "tools"

    @patch("app.core.agent.agent.LLM_CONFIG", {"model_type": "openai", "model_name": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1", "is_multimodal": False, "parallel_tool_calls": None})
    def test_returns_end_when_no_tool_calls(self):
        config = AgentConfig()
        agent = Agent(config=config)
        ai_msg = AIMessage(content="Hello")
        state = {"messages": [ai_msg]}
        assert agent._should_continue(state) == "end"

    @patch("app.core.agent.agent.LLM_CONFIG", {"model_type": "openai", "model_name": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1", "is_multimodal": False, "parallel_tool_calls": None})
    def test_returns_end_when_empty_messages(self):
        config = AgentConfig()
        agent = Agent(config=config)
        state = {"messages": []}
        assert agent._should_continue(state) == "end"

    @patch("app.core.agent.agent.LLM_CONFIG", {"model_type": "openai", "model_name": "gpt-4", "api_key": "test", "base_url": "https://api.openai.com/v1", "is_multimodal": False, "parallel_tool_calls": None})
    def test_returns_end_when_no_messages_key(self):
        config = AgentConfig()
        agent = Agent(config=config)
        state = {}
        assert agent._should_continue(state) == "end"
