#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture
def mock_llm_config():
    return {
        "model_type": "openai",
        "model_name": "gpt-4",
        "api_key": "test-api-key",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.0,
        "is_multimodal": False,
        "parallel_tool_calls": None,
        "ollama_reasoning": True,
        "ollama_timeout": 120,
    }


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.bind_tools = MagicMock(return_value=model)
    model.bind = MagicMock(return_value=model)
    model.ainvoke = AsyncMock()
    return model


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.put = MagicMock()
    store.get = MagicMock(return_value=None)
    store.search = MagicMock(return_value=[])
    return store


@pytest.fixture
def mock_checkpointer():
    checkpointer = MagicMock()
    return checkpointer
