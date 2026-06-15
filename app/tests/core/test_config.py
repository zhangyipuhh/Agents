# -*- coding:utf-8 -*-
"""
测试 app.core.config.settings 配置模块

验证 LLMSettings 默认值、字段校验器以及 Settings 聚合配置访问器行为。
"""

import pytest
from app.core.config.settings import LLMSettings, Settings


def test_llm_settings_default_values(monkeypatch):
    """
    测试 LLMSettings 各字段默认值。

    参数:
        monkeypatch: pytest 内置 fixture，用于清除可能影响默认值的环境变量

    Returns:
        None
    """
    # 清除可能覆盖默认值的环境变量
    for key in [
        "MODEL_TYPE", "MODEL_NAME", "MODEL_API_KEY", "MODEL_API_BASE",
        "MODEL_TEMPERATURE", "IS_MULTIMODAL", "PARALLEL_TOOL_CALLS",
        "OLLAMA_REASONING", "OLLAMA_TIMEOUT",
    ]:
        monkeypatch.delenv(key, raising=False)
    llm = LLMSettings()
    assert llm.model_type == "openai"
    assert llm.model_name == ""
    assert llm.model_api_key == ""
    assert llm.model_api_base == ""
    assert llm.model_temperature == 0.0
    assert llm.is_multimodal is False
    assert llm.parallel_tool_calls is None
    assert llm.ollama_reasoning is True
    assert llm.ollama_timeout == 120


def test_llm_settings_parallel_tool_calls_validator():
    """
    测试 parallel_tool_calls 字段校验器将字符串正确转换为 bool 或 None。

    参数:
        输入字符串或布尔值

    返回值:
        None

    异常:
        AssertionError: 校验结果不符合预期时抛出
    """
    llm = LLMSettings(parallel_tool_calls="none")
    assert llm.parallel_tool_calls is None

    llm = LLMSettings(parallel_tool_calls="true")
    assert llm.parallel_tool_calls is True

    llm = LLMSettings(parallel_tool_calls="false")
    assert llm.parallel_tool_calls is False

    llm = LLMSettings(parallel_tool_calls="1")
    assert llm.parallel_tool_calls is True

    llm = LLMSettings(parallel_tool_calls="0")
    assert llm.parallel_tool_calls is False

    llm = LLMSettings(parallel_tool_calls=True)
    assert llm.parallel_tool_calls is True

    llm = LLMSettings(parallel_tool_calls=None)
    assert llm.parallel_tool_calls is None


def test_llm_settings_is_multimodal_validator():
    """
    测试 is_multimodal 字段校验器将字符串正确解析为布尔值。

    参数:
        输入字符串或布尔值

    返回值:
        None

    异常:
        AssertionError: 校验结果不符合预期时抛出
    """
    llm = LLMSettings(is_multimodal="true")
    assert llm.is_multimodal is True

    llm = LLMSettings(is_multimodal="false")
    assert llm.is_multimodal is False

    llm = LLMSettings(is_multimodal="1")
    assert llm.is_multimodal is True

    llm = LLMSettings(is_multimodal="0")
    assert llm.is_multimodal is False

    llm = LLMSettings(is_multimodal=False)
    assert llm.is_multimodal is False


def test_settings_get_llm_config_returns_dict_with_key_fields():
    """
    测试 Settings.get_llm_config() 返回包含关键字段的字典。

    Returns:
        None

    异常:
        AssertionError: 返回字典缺失关键字段时抛出
    """
    settings = Settings()
    config = settings.get_llm_config()
    assert isinstance(config, dict)
    assert "model_name" in config
    assert "api_key" in config
    assert "base_url" in config
    assert "model_type" in config
    assert "temperature" in config
    assert "is_multimodal" in config
    assert "parallel_tool_calls" in config
    assert "ollama_reasoning" in config
    assert "ollama_timeout" in config
