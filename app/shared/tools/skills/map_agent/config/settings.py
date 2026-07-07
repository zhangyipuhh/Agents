#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 配置模块

使用 Pydantic BaseSettings 管理 MapAgent 专用配置，从 .env 文件加载。

Date: 2026-04-20
"""

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MapAgentSettings(BaseSettings):
    """
    MapAgent 专用配置

    从环境变量加载 MapAgent 相关的配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    mcp_tags: List[str] = Field(
        default=["map"],
        validation_alias="map_mcp_tags",
        description="MCP 工具标签过滤列表，用于按标签筛选 MCP 工具"
    )

    @field_validator("mcp_tags", mode="before")
    @classmethod
    def parse_mcp_tags(cls, v):
        """将逗号分隔的字符串转换为列表"""
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        return v
