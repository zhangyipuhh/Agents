import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.agent.AgentConfig import AgentConfig, AgentState, ExecuteConfig, ConfigurableConfig
from app.core.agent.AgentContext import AgentContext


class TestAgentConfig:
    def test_default_values(self):
        config = AgentConfig()
        assert config.temperature == 0
        assert config.max_tokens == 999999999
        assert config.max_tokens_before_summary == 999999999
        assert config.max_summary_tokens == 999999999
        assert config.checkpointer is None
        assert config.store is None
        assert config.system_prompt is None
        assert config.trim_tool_messages is True
        assert config.keep_last_n_tools == 2
        assert config.IS_MULTIMODAL is False
        assert config.llm_retry_max_attempts == 3
        assert config.tool_retry_max_attempts == 2
        assert config.summarize_retry_max_attempts == 2

    def test_custom_values(self):
        config = AgentConfig(
            model_type="deepseek",
            model_name="deepseek-chat",
            temperature=0.7,
            system_prompt="You are a helpful assistant",
            max_tokens=4096,
        )
        assert config.model_type == "deepseek"
        assert config.model_name == "deepseek-chat"
        assert config.temperature == 0.7
        assert config.system_prompt == "You are a helpful assistant"
        assert config.max_tokens == 4096

    def test_get_tools_returns_tuple(self):
        config = AgentConfig()
        tools, tool_node = config.get_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert tool_node is not None

    def test_get_llm_retry_policy(self):
        config = AgentConfig()
        policy = config.get_llm_retry_policy()
        assert policy.max_attempts == 3
        assert policy.initial_interval == 1.0

    def test_get_tool_retry_policy(self):
        config = AgentConfig()
        policy = config.get_tool_retry_policy()
        assert policy.max_attempts == 2
        assert policy.initial_interval == 0.5

    def test_get_summarize_retry_policy(self):
        config = AgentConfig()
        policy = config.get_summarize_retry_policy()
        assert policy.max_attempts == 2
        assert policy.initial_interval == 1.0

    def test_custom_retry_config(self):
        config = AgentConfig(
            llm_retry_max_attempts=5,
            llm_retry_initial_interval=2.0,
            tool_retry_max_attempts=3,
            tool_retry_initial_interval=1.0,
        )
        llm_policy = config.get_llm_retry_policy()
        assert llm_policy.max_attempts == 5
        assert llm_policy.initial_interval == 2.0

        tool_policy = config.get_tool_retry_policy()
        assert tool_policy.max_attempts == 3
        assert tool_policy.initial_interval == 1.0


class TestAgentState:
    def test_agent_state_is_typed_dict(self):
        assert hasattr(AgentState, "__annotations__")
        assert "error_limit" in AgentState.__annotations__
        assert "limit" in AgentState.__annotations__
        assert "file_chunk_read_progress" in AgentState.__annotations__
        assert "tool_progress" in AgentState.__annotations__
        assert "intermediate_results" in AgentState.__annotations__


class TestExecuteConfig:
    def test_execute_config_structure(self):
        assert hasattr(ExecuteConfig, "__annotations__")
        assert "configurable" in ExecuteConfig.__annotations__
        assert "recursion_limit" in ExecuteConfig.__annotations__


class TestConfigurableConfig:
    def test_configurable_config_structure(self):
        assert hasattr(ConfigurableConfig, "__annotations__")
        assert "thread_id" in ConfigurableConfig.__annotations__
