#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同路由专属 LLM 配置（2026-08-19 新增）

设计动机:
    合同审批子系统（contract_host_agent / contract_document_agent / contract_approval_agent）
    需要使用独立于全局 LLM_CONFIG 的专属模型配置，本类按"子智能体维度隔离"原则
    放在合同 host 智能体 config/ 目录下，过渡设计,不污染 app/core/config/。

回退策略（双层）:
    1. model_name == "" 时,整组回退到全局 LLM_CONFIG(向后兼容,默认行为)
    2. model_name != "" 时,字段级回退(空字段回退全局,非空字段独立生效)

环境变量命名:
    全部以 CONTRACT_LLM_ 前缀(env_prefix),与全局 LLMSettings 无前缀、VisionLLMSettings
    model_*_vision 后缀形成命名层次;同前缀下 9 项字段一一对应 LLMSettings 9 字段,
    保证契约一致性。

文件路径:
    env_file 路径独立推导(Path(__file__).resolve().parents[4] / ".env"),
    不引用 app/core/config/settings.py::_ENV_FILE_PATH,完全独立。

延迟依赖:
    get_config() 内部运行时 read 核心 LLM_CONFIG(来自 app.core.config.config),
    仅作为回退数据源,不修改任何核心代码。

Date: 2026-08-19
Author: 张镒谱
"""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根 .env 绝对路径(本文件独立推导,不依赖 app/core/config/settings.py)
# app/features/contract_host_agent/config/ -> 4 层上推到项目根
_ENV_FILE_PATH = str(Path(__file__).resolve().parents[4] / ".env")


class ContractLLMSettings(BaseSettings):
    """
    合同路由专属 LLM 配置类

    从环境变量加载合同子智能体专属的 LLM 相关配置(env 前缀 CONTRACT_LLM_)，
    支持覆盖全局 LLM_CONFIG(LLMSettings)。

    关键开关:
        model_name 非空时启用专属配置;空时整组回退全局 LLM_CONFIG。

    Attributes:
        model_type: 模型类型,如 "openai" / "deepseek" / "ollama" 等(env: CONTRACT_LLM_MODEL_TYPE)
        model_name: 模型名称,如 "gpt-4" / "deepseek-chat" / "qwen3:32b" 等(env: CONTRACT_LLM_MODEL_NAME)
        model_api_key: API 密钥,用于访问远程模型服务(env: CONTRACT_LLM_MODEL_API_KEY)
        model_api_base: API 基础 URL,指定模型服务的地址(env: CONTRACT_LLM_MODEL_API_BASE)
        model_temperature: 模型温度参数,控制生成多样性(env: CONTRACT_LLM_MODEL_TEMPERATURE)
        is_multimodal: 是否多模态模型(env: CONTRACT_LLM_IS_MULTIMODAL)
        parallel_tool_calls: 是否启用并行工具调用(None 表示不传参)(env: CONTRACT_LLM_PARALLEL_TOOL_CALLS)
        ollama_reasoning: Ollama 是否启用推理(env: CONTRACT_LLM_OLLAMA_REASONING)
        ollama_timeout: Ollama 请求超时秒数(env: CONTRACT_LLM_OLLAMA_TIMEOUT)
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATH,
        env_file_encoding="utf-8",
        env_prefix="CONTRACT_LLM_",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    model_type: str = Field(
        default="",
        description="合同路由专属模型类型,如 'openai' / 'deepseek' / 'ollama';env: CONTRACT_LLM_MODEL_TYPE",
    )
    model_name: str = Field(
        default="",
        description=(
            "合同路由专属模型名称,如 'gpt-4' / 'deepseek-chat' / 'qwen3:32b';"
            "非空时启用专属配置(关键开关);env: CONTRACT_LLM_MODEL_NAME"
        ),
    )
    model_api_key: str = Field(
        default="",
        description="合同路由专属 API 密钥;env: CONTRACT_LLM_MODEL_API_KEY",
    )
    model_api_base: str = Field(
        default="",
        description="合同路由专属 API 基础 URL;env: CONTRACT_LLM_MODEL_API_BASE",
    )
    model_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="合同路由专属温度参数,控制生成多样性,取值 0-2;env: CONTRACT_LLM_MODEL_TEMPERATURE",
    )
    is_multimodal: bool = Field(
        default=False,
        description="合同路由专属多模态开关;env: CONTRACT_LLM_IS_MULTIMODAL",
    )
    parallel_tool_calls: Optional[bool] = Field(
        default=None,
        description="合同路由专属并行工具调用开关,None 表示不传参;env: CONTRACT_LLM_PARALLEL_TOOL_CALLS",
    )
    ollama_reasoning: Optional[bool] = Field(
        default=True,
        description="合同路由专属 Ollama 推理开关;env: CONTRACT_LLM_OLLAMA_REASONING",
    )
    ollama_timeout: int = Field(
        default=120,
        ge=1,
        description="合同路由专属 Ollama 请求超时秒数;env: CONTRACT_LLM_OLLAMA_TIMEOUT",
    )

    @field_validator("parallel_tool_calls", mode="before")
    @classmethod
    def _parse_parallel_tool_calls(cls, value):
        """
        将字符串转换为布尔值,None 表示不传参

        支持 "none" -> None、 "true"/"1"/"yes"/"on" -> True、 "false"/"0"/"no"/"off" -> False。
        与全局 LLMSettings 同款逻辑,完全内联,不依赖核心代码。

        Args:
            value: 输入值(字符串 / None / 布尔)

        Returns:
            Optional[bool]: 转换后的布尔值或 None
        """
        if value is None:
            return None
        if isinstance(value, str):
            if value.lower() == "none":
                return None
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    @field_validator("is_multimodal", "ollama_reasoning", mode="before")
    @classmethod
    def _parse_bool(cls, value):
        """
        将字符串转换为布尔值

        与全局 LLMSettings 同款逻辑,完全内联。

        Args:
            value: 输入值(字符串或布尔)

        Returns:
            bool: 转换后的布尔值
        """
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    def get_config(self) -> dict:
        """
        获取合同路由 LLM 配置字典;空字段自动回退全局 LLM_CONFIG

        回退策略(双层):
            - model_name 为空或仅空白时,整组回退到全局 LLM_CONFIG(向后兼容)
            - model_name 非空且非纯空白时,字段级回退(空字段回退全局,非空字段独立生效)

        Returns:
            dict: 合同路由 LLM 配置字典,包含 9 个字段:
                model_name / api_key / base_url / model_type / temperature /
                is_multimodal / parallel_tool_calls / ollama_reasoning / ollama_timeout
        """
        # 延迟导入核心 LLM_CONFIG(运行时 read-only,不修改核心代码)
        from app.core.config.config import LLM_CONFIG

        # model_name 为空 / 仅空白 → 整组回退
        if not (self.model_name and self.model_name.strip()):
            return dict(LLM_CONFIG)

        return {
            "model_name": self.model_name,
            "api_key": self.model_api_key or LLM_CONFIG["api_key"],
            "base_url": self.model_api_base or LLM_CONFIG["base_url"],
            "model_type": self.model_type or LLM_CONFIG["model_type"],
            "temperature": self.model_temperature,
            "is_multimodal": self.is_multimodal,
            "parallel_tool_calls": self.parallel_tool_calls,
            "ollama_reasoning": self.ollama_reasoning,
            "ollama_timeout": self.ollama_timeout,
        }


# 模块级单例(路由层导入使用)
contract_llm_settings = ContractLLMSettings()
contract_llm_config = contract_llm_settings.get_config()


if __name__ == "__main__":
    # 冒烟测试入口:python -m app.features.contract_host_agent.config.ContractLLMSettings
    print("ContractLLMSettings 实例字段:")
    print(contract_llm_settings.model_dump())
    print("\nget_config() 输出(已应用回退策略):")
    print(contract_llm_config)