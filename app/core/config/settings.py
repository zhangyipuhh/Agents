#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
配置管理模块

使用 Pydantic BaseSettings 管理应用配置，自动从 .env 文件加载配置。
支持类型验证、默认值、环境变量覆盖等功能。

Date: 2026-04-07
Author: 张镒谱
"""
from typing import Dict, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcpClient.shared.config_loader import load_mcp_config


class LLMSettings(BaseSettings):
    """
    大语言模型配置
    
    从环境变量加载 LLM 相关配置，支持多种模型服务商。
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)
    )
    
    model_type: str = Field(
        default="openai",
        description="模型类型，如 'openai', 'deepseek', 'ollama' 等"
    )
    model_name: str = Field(
        default="",
        description="模型名称，如 'gpt-4', 'deepseek-chat', 'qwen3-vl:30b' 等"
    )
    model_api_key: str = Field(
        default="",
        description="API 密钥，用于访问远程模型服务"
    )
    model_api_base: str = Field(
        default="",
        description="API 基础 URL，指定模型服务的地址"
    )
    model_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="模型温度参数，控制生成多样性，取值范围 0-2"
    )
    is_multimodal: bool = Field(
        default=False,
        description="是否开启多模态，支持同时处理文本和图片等多模态输入"
    )
    
    @field_validator("is_multimodal", mode="before")
    @classmethod
    def parse_bool(cls, v):
        """将字符串转换为布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)


class VisionLLMSettings(BaseSettings):
    """
    视觉大语言模型配置
    
    专门用于视觉模型的配置，与通用 LLM 配置分离。
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)
    )
    
    model_type_vision: str = Field(
        default="openai",
        description="视觉模型类型"
    )
    model_name_vision: str = Field(
        default="",
        description="视觉模型名称"
    )
    model_api_key_vision: str = Field(
        default="",
        description="视觉模型 API 密钥"
    )
    model_api_base_vision: str = Field(
        default="",
        description="视觉模型 API 基础 URL"
    )
    model_temperature_vision: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="视觉模型温度参数"
    )


class WordOutputSettings(BaseSettings):
    """
    Word 输出配置
    
    管理 Word 文档输出的相关配置。
    """
    highlight_color: str = Field(
        default="FF0000",
        description="高亮颜色，十六进制格式，默认红色"
    )
    output_dir: str = Field(
        default="app/agents/data/output",
        description="输出目录路径"
    )


class MCPSettings(BaseSettings):
    """
    MCP 服务器配置
    
    管理 MCP（Model Context Protocol）服务器相关配置，
    包括配置文件路径和配置加载功能。
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=('settings_',)
    )
    
    mcp_config_path: str = Field(
        default="app/shared/tools/mcp/config.yaml",
        description="MCP 服务器配置文件路径"
    )
    
    def get_mcp_config(self) -> Dict[str, dict]:
        """
        加载并返回 MCP 服务器配置
        
        从 YAML 配置文件加载 MCP 服务器配置，支持环境变量插值。
        
        Returns:
            Dict[str, dict]: MCP 服务器配置字典，键为服务器名称，值为服务器配置
        """
        from pathlib import Path
        
        config_path = Path(self.mcp_config_path)
        return load_mcp_config(config_path)


class Settings(BaseSettings):
    """
    应用总配置
    
    整合所有配置模块，提供统一的配置访问接口。
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    llm: LLMSettings = Field(default_factory=LLMSettings)
    vision_llm: VisionLLMSettings = Field(default_factory=VisionLLMSettings)
    word_output: WordOutputSettings = Field(default_factory=WordOutputSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    
    def get_llm_config(self) -> dict:
        """
        获取 LLM 配置字典
        
        Returns:
            dict: LLM 配置字典，兼容旧代码
        """
        return {
            "model_name": self.llm.model_name,
            "api_key": self.llm.model_api_key,
            "base_url": self.llm.model_api_base,
            "model_type": self.llm.model_type,
            "temperature": self.llm.model_temperature,
            "is_multimodal": self.llm.is_multimodal,
        }
    
    def get_vision_llm_config(self) -> dict:
        """
        获取视觉 LLM 配置字典
        
        Returns:
            dict: 视觉 LLM 配置字典，兼容旧代码
        """
        return {
            "model_name": self.vision_llm.model_name_vision,
            "api_key": self.vision_llm.model_api_key_vision,
            "base_url": self.vision_llm.model_api_base_vision,
            "model_type": self.vision_llm.model_type_vision,
            "temperature": self.vision_llm.model_temperature_vision,
        }
    
    def get_word_output_config(self) -> dict:
        """
        获取 Word 输出配置字典
        
        Returns:
            dict: Word 输出配置字典，兼容旧代码
        """
        return {
            "highlight_color": self.word_output.highlight_color,
            "output_dir": self.word_output.output_dir,
        }


settings = Settings()
