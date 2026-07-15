#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuClient - 飞书 lark-oapi 客户端公共工厂

职责：
    - 从全局 settings.feishu 读取 app_id / app_secret / log_level
    - 构造并缓存 lark.Client 单例（避免每次调用都重建）
    - 提供 get_lark_client() 公共入口供所有飞书工具复用

依赖：
    - app.core.config.settings.settings.feishu
    - lark_oapi as lark
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import lark_oapi as lark

from app.core.config.settings import settings

logger = logging.getLogger(__name__)

# 模块级单例缓存（线程安全）
_client_lock = threading.Lock()
_client_instance: Optional[lark.Client] = None


def _resolve_log_level(level_str: str) -> int:
    """将字符串日志级别映射为 lark.LogLevel 枚举值。

    Args:
        level_str: 日志级别字符串（DEBUG / INFO / WARNING / ERROR）

    Returns:
        int: lark.LogLevel 枚举值；未识别时默认 INFO
    """
    mapping = {
        "DEBUG": lark.LogLevel.DEBUG,
        "INFO": lark.LogLevel.INFO,
        "WARNING": lark.LogLevel.WARNING,
        "ERROR": lark.LogLevel.ERROR,
    }
    return mapping.get((level_str or "").upper(), lark.LogLevel.INFO)


def get_lark_client() -> lark.Client:
    """获取飞书 lark-oapi 客户端单例。

    首次调用时从 settings.feishu 读取 app_id / app_secret / log_level 构造 client，
    后续调用返回缓存实例（线程安全，双重检查锁定）。

    Returns:
        lark.Client: 已配置好的飞书客户端

    Raises:
        RuntimeError: 当 feishu_app_id 或 feishu_app_secret 未配置时抛出
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    with _client_lock:
        if _client_instance is not None:  # double-check
            return _client_instance

        app_id = settings.feishu.feishu_app_id
        app_secret = settings.feishu.feishu_app_secret
        if not app_id or not app_secret:
            raise RuntimeError(
                "飞书应用凭证未配置：请在 .env 中设置 feishu_app_id 与 feishu_app_secret"
            )

        log_level = _resolve_log_level(settings.feishu.feishu_log_level)
        _client_instance = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(log_level)
            .build()
        )
        logger.info(
            "飞书 lark client 已初始化（app_id=%s, log_level=%s）", app_id, log_level
        )
        return _client_instance


def reset_lark_client() -> None:
    """重置客户端缓存（仅供测试使用）。

    清空单例后，下次调用 get_lark_client() 会重新读取 settings 并构造新 client。
    """
    global _client_instance
    with _client_lock:
        _client_instance = None
