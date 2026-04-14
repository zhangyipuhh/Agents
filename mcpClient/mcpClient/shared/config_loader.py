#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
配置加载模块

从 YAML 配置文件加载 MCP 服务器配置。
借鉴 hermes-cli/config.py 实现。

Date: 2026-04-14
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# 默认配置路径
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _interpolate_env_vars(value: Any) -> Any:
    """
    递归解析 ${VAR} 占位符

    Args:
        value: 要解析的值（str, dict, list 或其他）

    Returns:
        解析后的值
    """
    if isinstance(value, str):

        def _replace(m):
            return os.environ.get(m.group(1), m.group(0))

        return re.sub(r"\$\{([^}]+)\}", _replace, value)
    if isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_vars(v) for v in value]
    return value


def load_mcp_config(config_path: Optional[Path] = None) -> Dict[str, dict]:
    """
    从 YAML 文件加载 MCP 服务器配置

    支持 ${ENV_VAR} 环境变量插值。

    Args:
        config_path: 配置文件路径，默认为 config.yaml

    Returns:
        MCP 服务器配置字典 {server_name: config}

    Example:
        config = load_mcp_config()
        for name, cfg in config.items():
            print(f"{name}: {cfg}")
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    if not config_path.exists():
        logger.warning("MCP config file not found: %s", config_path)
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.error("Failed to parse YAML config: %s", e)
        return {}

    servers = raw_config.get("mcp_servers", {})
    if not servers or not isinstance(servers, dict):
        return {}

    result = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        result[name] = _interpolate_env_vars(cfg)

    return result


def get_mcp_servers_from_config(
    config_path: Optional[Path] = None,
) -> Dict[str, dict]:
    """
    获取 MCP 服务器配置的别名函数

    Args:
        config_path: 配置文件路径

    Returns:
        MCP 服务器配置字典
    """
    return load_mcp_config(config_path)
