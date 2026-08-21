# -*- coding:utf-8 -*-
"""
app/features/contract_host_agent/config/ContractLLMSettings.py 单元测试

覆盖:
- P0 类可导入(存在性)
- P0 模块级单例 contract_llm_settings / contract_llm_config 可用
- P1 默认字段值与设计契约一致
- P1 model_name 为空 → get_config() 整组回退 LLM_CONFIG(返回 dict 引用 copy)
- P1 model_name 仅空白 → 整组回退
- P1 仅设 CONTRACT_LLM_MODEL_NAME → 其他字段从 LLM_CONFIG 回退
- P1 全部 9 字段都设 → 全部生效,不回退
- P1 env 解析: PARALLEL_TOOL_CALLS / IS_MULTIMODAL / OLLAMA_REASONING bool(含 "none" → None)
- P1 env_prefix="CONTRACT_LLM_" 隔离:ContractLLMSettings 字段不响应全局 MODEL_* env
- P1 .env 文件路径独立推导: Path(__file__).resolve().parents[4] / ".env",monkeypatch.chdir 验证 CWD 无关性
- P2 get_config() 始终返回 dict 且包含 9 个关键字段

Date: 2026-08-19
Author: AI Assistant
"""

from pathlib import Path

import pytest


# ============================================================
# P0: 导入/存在性
# ============================================================


def test_contract_llm_settings_importable():
    """
    P0: ContractLLMSettings 可导入(类与模块)。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    assert ContractLLMSettings is not None


def test_module_level_singletons_importable():
    """
    P0: 模块级单例 contract_llm_settings / contract_llm_config 可导入。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        contract_llm_config,
        contract_llm_settings,
    )

    assert contract_llm_settings is not None
    assert isinstance(contract_llm_config, dict)


# ============================================================
# P1: 字段默认值
# ============================================================


def test_default_field_values():
    """
    P1: 默认字段值与设计契约一致(全部空 / False / 0.0 / None / 120 / True)。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    # 通过 _env_file=None 强制不读 .env,只校验 class defaults
    s = ContractLLMSettings(_env_file=None)
    assert s.model_type == ""
    assert s.model_name == ""
    assert s.model_api_key == ""
    assert s.model_api_base == ""
    assert s.model_temperature == 0.0
    assert s.is_multimodal is False
    assert s.parallel_tool_calls is None
    assert s.ollama_reasoning is True
    assert s.ollama_timeout == 120


# ============================================================
# P1: get_config() 回退策略
# ============================================================


def test_get_config_empty_model_name_full_fallback(monkeypatch):
    """
    P1: model_name 为空 → 整组回退到全局 LLM_CONFIG(返回 dict 等价)。

    关键:model_name 为空时不应用专属配置,直接拿全局 LLM_CONFIG 的快照。
    """
    monkeypatch.delenv("CONTRACT_LLM_MODEL_NAME", raising=False)

    from app.core.config.config import LLM_CONFIG
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()
    # 等价于 LLM_CONFIG 的 copy
    assert cfg == dict(LLM_CONFIG)


@pytest.mark.parametrize("whitespace", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_get_config_whitespace_model_name_full_fallback(monkeypatch, whitespace):
    """
    P2: model_name 为纯空白(空格 / tab / 换行 / 混合)→ 整组回退 LLM_CONFIG。
    """
    monkeypatch.setenv("CONTRACT_LLM_MODEL_NAME", whitespace)

    from app.core.config.config import LLM_CONFIG
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()
    assert cfg == dict(LLM_CONFIG)


def test_get_config_model_name_only_falls_back_others(monkeypatch):
    """
    P1: 仅设 CONTRACT_LLM_MODEL_NAME → 凭据类字段(api_key/base_url/model_type)从 LLM_CONFIG 回退。

    注意:温度 / parallel_tool_calls / is_multimodal / ollama_reasoning / ollama_timeout
    不参与凭据类回退,model_name 非空时直接采用 contract 专属值(默认 0.0/None/False/True/120)。
    这与 plan 文档说明的"字段级回退:仅凭据类 4 项回退"契约一致。
    """
    from app.core.config.config import LLM_CONFIG
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    monkeypatch.setenv("CONTRACT_LLM_MODEL_NAME", "qwen3:32b")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_TYPE", "")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_API_KEY", "")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_API_BASE", "")
    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()
    assert cfg["model_name"] == "qwen3:32b"
    # 凭据类 4 项回退 LLM_CONFIG
    assert cfg["model_type"] == LLM_CONFIG["model_type"]
    assert cfg["api_key"] == LLM_CONFIG["api_key"]
    assert cfg["base_url"] == LLM_CONFIG["base_url"]
    # 行为类 5 项不参与回退,使用 contract 专属值(默认)
    assert cfg["temperature"] == 0.0  # 默认值
    assert cfg["parallel_tool_calls"] is None
    assert cfg["is_multimodal"] is False
    assert cfg["ollama_reasoning"] is True
    assert cfg["ollama_timeout"] == 120


def test_get_config_partial_fields_effective_no_full_fallback(monkeypatch):
    """
    P1: 设 model_name + 部分字段(model_type/api_key/base_url)→ 启用专属配置,
    设了的字段独立,其他字段回退 LLM_CONFIG。
    """
    from app.core.config.config import LLM_CONFIG
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    monkeypatch.setenv("CONTRACT_LLM_MODEL_NAME", "qwen3:32b")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_TYPE", "ollama")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_API_KEY", "contract-key")
    # 留空 model_api_base / temperature / 等 → 回退 LLM_CONFIG
    monkeypatch.setenv("CONTRACT_LLM_MODEL_API_BASE", "")
    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()
    assert cfg["model_name"] == "qwen3:32b"
    assert cfg["model_type"] == "ollama"  # 专属生效
    assert cfg["api_key"] == "contract-key"  # 专属生效
    assert cfg["base_url"] == LLM_CONFIG["base_url"]  # 回退


def test_get_config_all_fields_effective_no_fallback(monkeypatch):
    """
    P1: 全部 9 字段都设 → 全部生效,不回退。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    monkeypatch.setenv("CONTRACT_LLM_MODEL_TYPE", "ollama")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_NAME", "qwen3:32b")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_API_KEY", "contract-key")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_API_BASE", "http://contract-host:11434")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_TEMPERATURE", "0.7")
    monkeypatch.setenv("CONTRACT_LLM_IS_MULTIMODAL", "true")
    monkeypatch.setenv("CONTRACT_LLM_PARALLEL_TOOL_CALLS", "false")
    monkeypatch.setenv("CONTRACT_LLM_OLLAMA_REASONING", "false")
    monkeypatch.setenv("CONTRACT_LLM_OLLAMA_TIMEOUT", "60")

    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()
    assert cfg["model_type"] == "ollama"
    assert cfg["model_name"] == "qwen3:32b"
    assert cfg["api_key"] == "contract-key"
    assert cfg["base_url"] == "http://contract-host:11434"
    assert cfg["temperature"] == 0.7
    assert cfg["is_multimodal"] is True
    assert cfg["parallel_tool_calls"] is False
    assert cfg["ollama_reasoning"] is False
    assert cfg["ollama_timeout"] == 60


# ============================================================
# P1: 字段级回退不读全局 parallel_tool_calls（2026-08-20 回归用例）
# ============================================================


def test_contract_parallel_tool_calls_explicit_false_overrides_global_none(monkeypatch):
    """
    P1 反向用例（2026-08-20 新增）:

        当 CONTRACT_LLM_MODEL_NAME 非空（触发字段级回退分支），
        且 CONTRACT_LLM_PARALLEL_TOOL_CALLS 显式设为 false 时，
        合同路由的 parallel_tool_calls 必须为 False，**不读**全局
        ``parallel_tool_calls=none``（否则会得到 None，Ollama 默认启用
        并行工具调用，触发 LangGraph 多 tool 同一 superstep 写
        file_chunk_read_progress 字段的 InvalidUpdateError）。

    场景:
        - 全局 parallel_tool_calls = "none"（None）
        - contract model_name = "qwen3-vl:30b"（非空 → 字段级回退）
        - contract parallel_tool_calls = "false"（显式）

    期望: cfg["parallel_tool_calls"] is False（不是 None）
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    # 模拟生产 .env 当前状态:全局 "none" + 合同 model_name 非空 + contract 显式 false
    monkeypatch.setenv("parallel_tool_calls", "none")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_NAME", "qwen3-vl:30b")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_TYPE", "ollama")
    monkeypatch.setenv("CONTRACT_LLM_PARALLEL_TOOL_CALLS", "false")

    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()

    # 字段级回退分支生效:model_name 非空,走 9 字段 dict,不走整组 LLM_CONFIG 兜底
    assert cfg["model_name"] == "qwen3-vl:30b", "前提:字段级回退分支必须触发"
    # 核心断言:contract 显式 false 不能被全局 "none" 覆盖
    assert cfg["parallel_tool_calls"] is False, (
        f"CONTRACT_LLM_PARALLEL_TOOL_CALLS=false 必须生效,实际为 "
        f"{cfg['parallel_tool_calls']!r};若为 None 表示被全局 'none' 错误覆盖"
    )


# ============================================================
# P1: env 解析(bool / "none" → None / float)
# ============================================================


def test_parallel_tool_calls_string_none_parsed_as_none(monkeypatch):
    """
    P1: PARALLEL_TOOL_CALLS='none' → None;='true' → True;='false' → False。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    monkeypatch.setenv("CONTRACT_LLM_PARALLEL_TOOL_CALLS", "none")
    s = ContractLLMSettings(_env_file=None)
    assert s.parallel_tool_calls is None

    monkeypatch.setenv("CONTRACT_LLM_PARALLEL_TOOL_CALLS", "true")
    s = ContractLLMSettings(_env_file=None)
    assert s.parallel_tool_calls is True

    monkeypatch.setenv("CONTRACT_LLM_PARALLEL_TOOL_CALLS", "false")
    s = ContractLLMSettings(_env_file=None)
    assert s.parallel_tool_calls is False


def test_is_multimodal_and_ollama_reasoning_bool_parsing(monkeypatch):
    """
    P1: IS_MULTIMODAL / OLLAMA_REASONING 支持 true/1/yes/on;非真值 → False。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    for truth in ("true", "1", "yes", "on"):
        monkeypatch.setenv("CONTRACT_LLM_IS_MULTIMODAL", truth)
        monkeypatch.setenv("CONTRACT_LLM_OLLAMA_REASONING", truth)
        s = ContractLLMSettings(_env_file=None)
        assert s.is_multimodal is True, f"truth='{truth}' failed for is_multimodal"
        assert s.ollama_reasoning is True, f"truth='{truth}' failed for ollama_reasoning"

    for falsy in ("false", "0", "no", "off"):
        monkeypatch.setenv("CONTRACT_LLM_IS_MULTIMODAL", falsy)
        monkeypatch.setenv("CONTRACT_LLM_OLLAMA_REASONING", falsy)
        s = ContractLLMSettings(_env_file=None)
        assert s.is_multimodal is False, f"falsy='{falsy}' failed for is_multimodal"
        assert s.ollama_reasoning is False, f"falsy='{falsy}' failed for ollama_reasoning"


# ============================================================
# P1: env_prefix 隔离
# ============================================================


def test_env_prefix_isolation_does_not_consume_global_env(monkeypatch):
    """
    P1: env_prefix='CONTRACT_LLM_' 隔离 - ContractLLMSettings 不读全局 MODEL_* env,
    只读 CONTRACT_LLM_* 系列。

    此测试验证:即便全局 MODEL_TYPE 设了 'global',ContractLLMSettings.model_type
    也读自己的 CONTRACT_LLM_MODEL_TYPE,而非继承全局 MODEL_TYPE。
    """
    monkeypatch.setenv("MODEL_TYPE", "global")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_TYPE", "contract")
    monkeypatch.setenv("CONTRACT_LLM_MODEL_NAME", "qwen3:32b")

    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    s = ContractLLMSettings(_env_file=None)
    # ContractLLMSettings 字段只读 CONTRACT_LLM_* env,不受全局 MODEL_TYPE 影响
    assert s.model_type == "contract"
    assert s.model_name == "qwen3:32b"
    cfg = s.get_config()
    assert cfg["model_type"] == "contract"
    assert cfg["model_name"] == "qwen3:32b"


# ============================================================
# P1: .env 文件路径独立推导
# ============================================================


def test_env_file_path_independent_of_cwd(monkeypatch, tmp_path):
    """
    P1: .env 文件路径独立推导(Path(__file__).resolve().parents[4] / ".env"),
    monkeypatch.chdir 到其他目录不影响路径。
    """
    from app.features.contract_host_agent.config import ContractLLMSettings

    expected = str(Path(ContractLLMSettings.__file__).resolve().parents[4] / ".env")
    assert ContractLLMSettings._ENV_FILE_PATH == expected

    # 切换到无关目录,再访问 _ENV_FILE_PATH,值不变
    monkeypatch.chdir(tmp_path)
    assert ContractLLMSettings._ENV_FILE_PATH == expected


# ============================================================
# P2: get_config() 形状契约
# ============================================================


def test_get_config_returns_dict_with_expected_keys():
    """
    P2: get_config() 始终返回 dict 且包含 9 个关键字段。
    """
    from app.features.contract_host_agent.config.ContractLLMSettings import (
        ContractLLMSettings,
    )

    s = ContractLLMSettings(_env_file=None)
    cfg = s.get_config()
    assert isinstance(cfg, dict)
    expected_keys = {
        "model_name",
        "api_key",
        "base_url",
        "model_type",
        "temperature",
        "is_multimodal",
        "parallel_tool_calls",
        "ollama_reasoning",
        "ollama_timeout",
    }
    assert expected_keys.issubset(cfg.keys())