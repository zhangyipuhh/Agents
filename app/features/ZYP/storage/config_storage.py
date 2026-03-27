#!/usr/bin/python
# -*- coding:utf-8 -*-
# Date: 2026-03-27
# Author: 张镒谱

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from ..ZYPAgent import ModelConfig


@dataclass
class AppConfig:
    """
    应用程序配置数据类，用于存储和序列化应用程序的各项配置参数
    """
    default_model_type: str = "deepseek"
    default_model_name: str = "deepseek-chat"
    default_api_key: str = ""
    default_base_url: str = "https://api.deepseek.com"
    default_temperature: float = 0.0
    window_width: int = 120
    window_height: int = 40
    session_storage_path: str = "./data/sessions"

    def to_dict(self) -> dict:
        """
        将AppConfig实例转换为字典格式，用于JSON序列化
        """
        return {
            "default_model_type": self.default_model_type,
            "default_model_name": self.default_model_name,
            "default_api_key": self.default_api_key,
            "default_base_url": self.default_base_url,
            "default_temperature": self.default_temperature,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "session_storage_path": self.session_storage_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """
        从字典数据创建AppConfig实例，提供默认值以确保兼容性
        """
        return cls(
            default_model_type=data.get("default_model_type", "deepseek"),
            default_model_name=data.get("default_model_name", "deepseek-chat"),
            default_api_key=data.get("default_api_key", ""),
            default_base_url=data.get("default_base_url", "https://api.deepseek.com"),
            default_temperature=data.get("default_temperature", 0.0),
            window_width=data.get("window_width", 120),
            window_height=data.get("window_height", 40),
            session_storage_path=data.get("session_storage_path", "./data/sessions"),
        )


class ConfigStorage:
    """
    配置存储类，负责应用程序配置的持久化和加载
    支持从JSON文件读取配置，若文件不存在或格式错误则返回默认配置
    """
    def __init__(self, config_path: str = "./data/config.json"):
        self.config_path = Path(config_path)
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppConfig:
        """
        加载配置文件，若文件不存在则返回默认配置
        捕获JSON解析错误和键缺失错误，确保返回有效的配置对象
        """
        if not self.config_path.exists():
            return AppConfig()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppConfig.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return AppConfig()

    def save(self, config: AppConfig):
        """
        保存配置到JSON文件，使用UTF-8编码和格式化输出
        """
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

    def get_model_config(self) -> ModelConfig:
        """
        从应用配置中提取模型相关配置并转换为ModelConfig对象
        """
        config = self.load()
        return ModelConfig(
            model_type=config.default_model_type,
            model_name=config.default_model_name,
            api_key=config.default_api_key,
            base_url=config.default_base_url,
            temperature=config.default_temperature,
        )

    def save_model_config(self, model_config: ModelConfig):
        """
        将ModelConfig对象更新到应用配置并保存到文件
        """
        config = self.load()
        config.default_model_type = model_config.model_type
        config.default_model_name = model_config.model_name
        config.default_api_key = model_config.api_key
        config.default_base_url = model_config.base_url
        config.default_temperature = model_config.temperature
        self.save(config)
