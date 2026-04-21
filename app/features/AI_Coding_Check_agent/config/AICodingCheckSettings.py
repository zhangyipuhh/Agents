#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AICodingCheckAgent 配置模块

使用 Pydantic BaseSettings 管理 AICodingCheckAgent 专用配置，从 .env 文件加载。

Date: 2026-04-21
Author: 张镒谱
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AICodingCheckSettings(BaseSettings):
    """
    AICodingCheckAgent 专用配置

    从环境变量加载 AICodingCheckAgent 相关的配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",                    # 指定 .env 文件路径
        env_file_encoding="utf-8",          # .env 文件编码格式
        case_sensitive=False,               # 环境变量名不区分大小写，便于配置
        extra="ignore",                     # 忽略 .env 中未定义的字段，避免报错
        protected_namespaces=("settings_",),  # 保护命名空间前缀，防止与 Pydantic 内部方法冲突
    )

    model_type: str = Field(default="deepseek", description="模型类型")
    """模型类型标识，用于区分不同的 LLM 提供商，如 deepseek、openai 等"""

    model_name: str = Field(default="deepseek-chat", description="模型名称")
    """模型名称，对应 LLM 提供商的具体模型标识，如 deepseek-chat、gpt-4 等"""

    deepseek_api_key: str = Field(default="", description="DeepSeek API Key")
    """DeepSeek API 密钥，用于鉴权调用 DeepSeek 模型接口"""

    model_base_url: str = Field(default="", description="API 地址")
    """模型 API 基础地址，支持自定义代理或私有部署的 API 端点"""

    model_temperature: float = Field(default=0, ge=0.0, le=2.0, description="温度参数")
    """模型温度参数，控制输出随机性；0 表示确定性输出，值越大输出越随机"""

    model_max_tokens: int = Field(default=2000, description="最大 token 数")
    """单次请求最大生成 token 数，限制模型输出长度"""

    model_timeout: int = Field(default=60, description="请求超时（秒）")
    """模型请求超时时间（秒），超过该时间未响应则抛出超时异常"""

    model_retry_times: int = Field(default=3, description="重试次数")
    """模型请求失败后的最大重试次数，提高调用可靠性"""


# 创建全局配置单例，模块加载时自动从 .env 文件读取配置
ai_coding_check_settings = AICodingCheckSettings()
