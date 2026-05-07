import pytest
from unittest.mock import patch
from app.core.config.settings import (
    LLMSettings,
    VisionLLMSettings,
    WordOutputSettings,
    FileParserSettings,
    Settings,
)


class TestLLMSettings:
    def test_model_type_is_string(self):
        settings = LLMSettings()
        assert isinstance(settings.model_type, str)

    def test_temperature_in_range(self):
        settings = LLMSettings()
        assert 0.0 <= settings.model_temperature <= 2.0

    def test_is_multimodal_is_bool(self):
        settings = LLMSettings()
        assert isinstance(settings.is_multimodal, bool)

    def test_parallel_tool_calls_is_optional_bool(self):
        settings = LLMSettings()
        assert settings.parallel_tool_calls is None or isinstance(settings.parallel_tool_calls, bool)

    def test_ollama_reasoning_is_bool(self):
        settings = LLMSettings()
        assert isinstance(settings.ollama_reasoning, bool)

    def test_ollama_timeout_positive(self):
        settings = LLMSettings()
        assert settings.ollama_timeout >= 1

    def test_parse_parallel_tool_calls_none_string(self):
        assert LLMSettings.parse_parallel_tool_calls("none") is None

    def test_parse_parallel_tool_calls_true_string(self):
        assert LLMSettings.parse_parallel_tool_calls("true") is True
        assert LLMSettings.parse_parallel_tool_calls("1") is True
        assert LLMSettings.parse_parallel_tool_calls("yes") is True
        assert LLMSettings.parse_parallel_tool_calls("on") is True

    def test_parse_parallel_tool_calls_false_string(self):
        assert LLMSettings.parse_parallel_tool_calls("false") is False
        assert LLMSettings.parse_parallel_tool_calls("0") is False

    def test_parse_parallel_tool_calls_none_value(self):
        assert LLMSettings.parse_parallel_tool_calls(None) is None

    def test_parse_parallel_tool_calls_bool_value(self):
        assert LLMSettings.parse_parallel_tool_calls(True) is True
        assert LLMSettings.parse_parallel_tool_calls(False) is False

    def test_parse_bool_true_strings(self):
        for val in ["true", "1", "yes", "on"]:
            assert LLMSettings.parse_bool(val) is True

    def test_parse_bool_false_strings(self):
        assert LLMSettings.parse_bool("false") is False
        assert LLMSettings.parse_bool("0") is False

    def test_parse_bool_actual_bool(self):
        assert LLMSettings.parse_bool(True) is True
        assert LLMSettings.parse_bool(False) is False

    def test_temperature_validation(self):
        settings = LLMSettings(model_temperature=1.5)
        assert settings.model_temperature == 1.5

    def test_ollama_timeout_minimum(self):
        settings = LLMSettings(ollama_timeout=1)
        assert settings.ollama_timeout == 1


class TestVisionLLMSettings:
    def test_model_type_is_string(self):
        settings = VisionLLMSettings()
        assert isinstance(settings.model_type_vision, str)

    def test_temperature_in_range(self):
        settings = VisionLLMSettings()
        assert 0.0 <= settings.model_temperature_vision <= 2.0


class TestWordOutputSettings:
    def test_default_values(self):
        settings = WordOutputSettings()
        assert settings.highlight_color == "FF0000"
        assert settings.output_dir == "app/agents/data/output"


class TestFileParserSettings:
    def test_enabled_is_bool(self):
        settings = FileParserSettings()
        assert isinstance(settings.file_parser_enabled, bool)

    def test_output_format_is_valid(self):
        settings = FileParserSettings()
        assert settings.file_parser_output_format in ("json", "md")

    def test_max_retries_positive(self):
        settings = FileParserSettings()
        assert settings.file_parser_max_retries > 0

    def test_poll_interval_positive(self):
        settings = FileParserSettings()
        assert settings.file_parser_poll_interval > 0

    def test_timeout_positive(self):
        settings = FileParserSettings()
        assert settings.file_parser_timeout > 0

    def test_parse_bool(self):
        assert FileParserSettings.parse_bool("true") is True
        assert FileParserSettings.parse_bool("false") is False

    def test_validate_output_format_json(self):
        assert FileParserSettings.validate_output_format("json") == "json"

    def test_validate_output_format_md(self):
        assert FileParserSettings.validate_output_format("md") == "md"

    def test_validate_output_format_invalid(self):
        with pytest.raises(ValueError, match="must be 'json' or 'md'"):
            FileParserSettings.validate_output_format("xml")


class TestSettings:
    def test_default_composition(self):
        settings = Settings()
        assert isinstance(settings.llm, LLMSettings)
        assert isinstance(settings.vision_llm, VisionLLMSettings)
        assert isinstance(settings.word_output, WordOutputSettings)
        assert isinstance(settings.file_parser, FileParserSettings)

    def test_get_llm_config(self):
        settings = Settings()
        config = settings.get_llm_config()
        assert isinstance(config, dict)
        required_keys = {"model_name", "api_key", "base_url", "model_type", "temperature", "is_multimodal", "parallel_tool_calls", "ollama_reasoning", "ollama_timeout"}
        assert required_keys.issubset(set(config.keys()))

    def test_get_vision_llm_config(self):
        settings = Settings()
        config = settings.get_vision_llm_config()
        assert isinstance(config, dict)
        assert "model_name" in config
        assert "model_type" in config

    def test_get_word_output_config(self):
        settings = Settings()
        config = settings.get_word_output_config()
        assert isinstance(config, dict)
        assert "highlight_color" in config
        assert "output_dir" in config

    def test_get_file_parser_config(self):
        settings = Settings()
        config = settings.get_file_parser_config()
        assert isinstance(config, dict)
        assert "enabled" in config
        assert "server_url" in config
        assert "output_format" in config
