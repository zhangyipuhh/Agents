from typing import Callable, Optional

from ...ZYPAgent import ModelConfig


class ModelHandler:
    def __init__(self):
        self._current_model = "deepseek"
        self._model_configs = {}
        self._on_model_change: Optional[Callable] = None

        self._default_configs = {
            "deepseek": {
                "model_type": "deepseek",
                "model_name": "deepseek-chat",
                "api_key": "",
                "base_url": "https://api.deepseek.com",
                "temperature": 0.0,
            },
            "ollama": {
                "model_type": "ollama",
                "model_name": "llama2",
                "api_key": "",
                "base_url": "http://localhost:11434",
                "temperature": 0.0,
            },
            "openai": {
                "model_type": "openai",
                "model_name": "gpt-4",
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "temperature": 0.0,
            },
        }

        self._model_configs = self._default_configs.copy()

    def set_on_model_change(self, callback: Callable):
        self._on_model_change = callback

    def get_model_list(self) -> list[str]:
        return list(self._default_configs.keys())

    def get_current_model(self) -> str:
        return self._current_model

    def set_current_model(self, model_type: str):
        if model_type in self._model_configs:
            self._current_model = model_type

    def get_config(self, model_type: Optional[str] = None) -> ModelConfig:
        model = model_type or self._current_model
        config = self._model_configs.get(model, self._default_configs.get(model, {}))
        return ModelConfig(
            model_type=config.get("model_type", model),
            model_name=config.get("model_name", ""),
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url", ""),
            temperature=config.get("temperature", 0.0),
        )

    def update_config(self, model_type: str, model_name: str, api_key: str, base_url: str, temperature: float):
        self._model_configs[model_type] = {
            "model_type": model_type,
            "model_name": model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
        }

        if self._on_model_change:
            self._on_model_change(self._current_model, self.get_config())

    def get_default_config(self, model_type: str) -> dict:
        return self._default_configs.get(model_type, {})

    def get_config_form_fields(self, model_type: str) -> list[dict]:
        forms = {
            "deepseek": [
                {"field": "model_name", "label": "模型名称", "default": "deepseek-chat", "type": "text"},
                {"field": "api_key", "label": "API Key", "default": "", "type": "password"},
                {"field": "base_url", "label": "Base URL", "default": "https://api.deepseek.com", "type": "text"},
                {"field": "temperature", "label": "Temperature", "default": 0.0, "type": "float", "min": 0.0, "max": 1.0},
            ],
            "ollama": [
                {"field": "model_name", "label": "模型名称", "default": "llama2", "type": "text"},
                {"field": "base_url", "label": "Base URL", "default": "http://localhost:11434", "type": "text"},
                {"field": "temperature", "label": "Temperature", "default": 0.0, "type": "float", "min": 0.0, "max": 1.0},
            ],
            "openai": [
                {"field": "model_name", "label": "模型名称", "default": "gpt-4", "type": "text"},
                {"field": "api_key", "label": "API Key", "default": "", "type": "password"},
                {"field": "base_url", "label": "Base URL", "default": "https://api.openai.com/v1", "type": "text"},
                {"field": "temperature", "label": "Temperature", "default": 0.0, "type": "float", "min": 0.0, "max": 1.0},
            ],
        }
        return forms.get(model_type, [])
