import pytest
from unittest.mock import MagicMock, patch
from app.core.llmcalls.model_factory import ModelFactory


class TestModelFactoryCreateModel:
    @patch.object(ModelFactory, '_model_creators', {
        'deepseek': MagicMock(return_value=MagicMock()),
        'ollama': MagicMock(return_value=MagicMock()),
        'openai': MagicMock(return_value=MagicMock()),
        'anthropic': MagicMock(return_value=MagicMock()),
    })
    def test_create_deepseek_model(self):
        result = ModelFactory.create_model(
            model_type="deepseek",
            model_name="deepseek-chat",
            api_key="test-key",
            temperature=0.5,
            base_url="https://api.deepseek.com",
        )
        ModelFactory._model_creators["deepseek"].assert_called_once_with(
            model_name="deepseek-chat",
            api_key="test-key",
            temperature=0.5,
            base_url="https://api.deepseek.com",
        )

    @patch.object(ModelFactory, '_model_creators', {
        'deepseek': MagicMock(return_value=MagicMock()),
        'ollama': MagicMock(return_value=MagicMock()),
        'openai': MagicMock(return_value=MagicMock()),
        'anthropic': MagicMock(return_value=MagicMock()),
    })
    def test_create_openai_model(self):
        result = ModelFactory.create_model(
            model_type="openai",
            model_name="gpt-4",
            api_key="test-key",
            temperature=0.7,
        )
        ModelFactory._model_creators["openai"].assert_called_once()

    @patch.object(ModelFactory, '_model_creators', {
        'deepseek': MagicMock(return_value=MagicMock()),
        'ollama': MagicMock(return_value=MagicMock()),
        'openai': MagicMock(return_value=MagicMock()),
        'anthropic': MagicMock(return_value=MagicMock()),
    })
    def test_create_ollama_model_with_defaults(self):
        result = ModelFactory.create_model(
            model_type="ollama",
            model_name="llama3",
            api_key="test-key",
        )
        ModelFactory._model_creators["ollama"].assert_called_once_with(
            model_name="llama3",
            api_key="test-key",
            temperature=0,
            base_url=None,
            reasoning=True,
            timeout=120,
        )

    @patch.object(ModelFactory, '_model_creators', {
        'deepseek': MagicMock(return_value=MagicMock()),
        'ollama': MagicMock(return_value=MagicMock()),
        'openai': MagicMock(return_value=MagicMock()),
        'anthropic': MagicMock(return_value=MagicMock()),
    })
    def test_create_ollama_model_with_custom_reasoning(self):
        result = ModelFactory.create_model(
            model_type="ollama",
            model_name="llama3",
            api_key="test-key",
            reasoning=False,
            timeout=60,
        )
        ModelFactory._model_creators["ollama"].assert_called_once_with(
            model_name="llama3",
            api_key="test-key",
            temperature=0,
            base_url=None,
            reasoning=False,
            timeout=60,
        )

    def test_create_model_case_insensitive(self):
        with pytest.raises(ValueError, match="不支持的模型类型"):
            ModelFactory.create_model(
                model_type="UNKNOWN_TYPE",
                model_name="test",
                api_key="test",
            )

    def test_create_model_unsupported_type_raises_error(self):
        with pytest.raises(ValueError) as exc_info:
            ModelFactory.create_model(
                model_type="nonexistent",
                model_name="test",
                api_key="test",
            )
        assert "不支持的模型类型" in str(exc_info.value)
        assert "nonexistent" in str(exc_info.value)


class TestModelFactoryRegisterModelCreator:
    def test_register_new_model_type(self):
        mock_creator = MagicMock()
        original_keys = set(ModelFactory._model_creators.keys())
        ModelFactory.register_model_creator("custom_model", mock_creator)
        assert "custom_model" in ModelFactory._model_creators
        assert ModelFactory._model_creators["custom_model"] == mock_creator
        if "custom_model" not in original_keys:
            del ModelFactory._model_creators["custom_model"]

    def test_register_model_case_insensitive(self):
        mock_creator = MagicMock()
        ModelFactory.register_model_creator("MyModel", mock_creator)
        assert "mymodel" in ModelFactory._model_creators
        if "mymodel" in ModelFactory._model_creators:
            del ModelFactory._model_creators["mymodel"]


class TestModelFactoryGetSupportedModels:
    def test_returns_list(self):
        models = ModelFactory.get_supported_models()
        assert isinstance(models, list)

    def test_includes_known_models(self):
        models = ModelFactory.get_supported_models()
        assert "deepseek" in models
        assert "ollama" in models
        assert "openai" in models
        assert "anthropic" in models

    def test_returns_copy_not_reference(self):
        models1 = ModelFactory.get_supported_models()
        models2 = ModelFactory.get_supported_models()
        assert models1 == models2
        assert models1 is not models2


class TestModelFactoryInit:
    def test_instance_creators_match_class_creators(self):
        factory = ModelFactory()
        assert set(factory._model_creators.keys()) == set(ModelFactory._model_creators.keys())
