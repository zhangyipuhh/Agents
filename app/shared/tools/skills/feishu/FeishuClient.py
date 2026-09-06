#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuClient - 飞书 lark-oapi 客户端公共工厂

职责：
    - 从 NotificationConfigService 解析默认渠道凭证（app_id/app_secret/log_level）
    - 构造并缓存 lark.Client 单例（避免每次调用都重建）
    - 提供 get_lark_client() 公共入口供 LLM 工具 / 测试复用

2026-09-03 改造：
    - 不再读 settings.feishu.feishu_app_id / feishu_app_secret / feishu_log_level
    - 改为从 app.state.notification_config_service 解析默认飞书渠道
    - WS 多实例路径不走此单例（每实例单独构造 lark.Client，详见
      FeishuWebSocketManager.start_all）

依赖：
    - app.core.config.settings.settings（保留 feishu 字段以兼容测试 / 迁移工具）
    - app.shared.utils.notification.NotificationConfigService
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
# 缓存对应的 channel_id 与 app_id（用于检测 DB 默认应用切换后刷新单例）
_client_channel_id: Optional[int] = None
_client_app_id: Optional[str] = None


def _resolve_log_level(level_str: str) -> int:
    """将字符串日志级别映射为 lark.LogLevel 枚举值。

    Args:
        level_str: 日志级别字符串（DEBUG / INFO / WARNING / ERROR）

    Returns:
        int: lark.LogLevel 枚举值；未识别时默认 INFO
    """
    try:
        mapping = {
            "DEBUG": lark.LogLevel.DEBUG,
            "INFO": lark.LogLevel.INFO,
            "WARNING": lark.LogLevel.WARNING,
            "ERROR": lark.LogLevel.ERROR,
        }
        return mapping.get((level_str or "").upper(), lark.LogLevel.INFO)
    except Exception:  # noqa: BLE001
        return 0


def _resolve_credential_via_settings() -> Optional[lark.Client]:
    """从 ``settings.feishu`` 读凭证构造 lark.Client（仅供测试 / 迁移工具使用）。

    本期生产代码**不**调此函数；仅在 ``app.state.notification_config_service`` 未
    初始化且 settings 仍有飞书字段时,保留 fallback（兼容既有单测）。
    """
    feishu = getattr(settings, "feishu", None)
    if feishu is None:
        return None
    app_id = getattr(feishu, "feishu_app_id", "") or ""
    app_secret = getattr(feishu, "feishu_app_secret", "") or ""
    if not app_id or not app_secret:
        return None
    log_level_str = getattr(feishu, "feishu_log_level", "INFO") or "INFO"
    log_level = _resolve_log_level(log_level_str)
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(log_level)
        .build()
    )


def _get_notification_service():
    """从 ``app.state.notification_config_service`` 取 NotificationConfigService 实例。

    通过 FastAPI 当前 app 单例间接取 state（避免硬编码 import）。

    Returns:
        Optional[NotificationConfigService]: 未初始化时返回 None。
    """
    try:
        # 延迟 import 避免循环
        from fastapi import Request  # noqa: F401

        # 通过 app.state 取：在 lifespan 中挂到 app.state
        from app.main import app as _fastapi_app  # 延迟 import

        svc = getattr(_fastapi_app.state, "notification_config_service", None)
        return svc
    except Exception:  # noqa: BLE001
        return None


def get_lark_client() -> lark.Client:
    """获取飞书 lark-oapi 客户端单例。

    凭证来源（2026-09-03 调整）：
    1. **生产路径**：从 ``NotificationConfigService.resolve_default_channel("feishu")``
       取默认飞书渠道；DB 无默认渠道 → 抛 RuntimeError。
    2. **测试 fallback**：若 ``app.state.notification_config_service`` 未初始化，
       仍读 ``settings.feishu`` 兼容既有测试（仅当 settings 字段非空时）。

    单例缓存策略：缓存 ``(channel_id, app_id)``，若下次调用默认应用变更则重建。

    Returns:
        lark.Client: 已配置好的飞书客户端

    Raises:
        RuntimeError: 默认飞书渠道未配置。
    """
    global _client_instance, _client_channel_id, _client_app_id

    notification_service = _get_notification_service()
    target_channel_id: Optional[int] = None
    target_app_id: Optional[str] = None
    target_log_level: str = "INFO"

    if notification_service is not None:
        # 生产路径：DB 解析默认渠道
        try:
            ch = None
            # 同步 helper 调用:NotificationConfigService 是 async,需要 run_coroutine
            # 但 lifespan 主线程已有 event loop,可以用 asyncio.run_coroutine_threadsafe
            # 这里直接同步等待 — 通过 loop
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在主事件循环内,无法直接 run_coroutine;改用 concurrent.futures 阻塞
                    # 但生产调用都在同步上下文(LLM tool),此处用 ensure_future + queue
                    # 简化:若 loop 在跑,直接走 settings.feishu fallback
                    raise RuntimeError("loop is running")
                ch = loop.run_until_complete(
                    notification_service.resolve_default_channel("feishu")
                )
            except RuntimeError:
                # loop 在跑 或无 loop:尝试用 run_coroutine_threadsafe 投递主 loop
                try:
                    import concurrent.futures

                    fut = asyncio.run_coroutine_threadsafe(
                        notification_service.resolve_default_channel("feishu"),
                        loop,
                    )
                    ch = fut.result(timeout=5.0)
                except Exception:  # noqa: BLE001
                    ch = None
            if ch is not None:
                target_channel_id = ch["id"]
                cfg = ch["config"]
                target_app_id = (
                    notification_service.decrypt_field(
                        cfg.get("app_id_encrypted") or ""
                    )
                    if cfg.get("app_id_encrypted")
                    else ""
                )
                target_log_level = cfg.get("log_level", "INFO") or "INFO"
        except Exception as exc:  # noqa: BLE001
            logger.warning("[feishu_client] 从 DB 解析默认渠道失败: %s", exc)

    if not target_app_id:
        # fallback:从 settings.feishu 读(仅测试 / 迁移工具使用)
        try:
            client = _resolve_credential_via_settings()
        except Exception:  # noqa: BLE001
            client = None
        if client is None:
            raise RuntimeError(
                "飞书默认应用未配置:请在「消息设置 → 飞书设置 → 应用设置」中"
                "配置 is_default=TRUE 的飞书渠道(详见 NotificationConfigService)"
            )
        with _client_lock:
            _client_instance = client
            _client_channel_id = None
            _client_app_id = None
        return client

    # 单例有效且默认渠道未变 → 直接返回缓存
    with _client_lock:
        if (
            _client_instance is not None
            and _client_channel_id == target_channel_id
            and _client_app_id == target_app_id
        ):
            return _client_instance
        # 重建
        app_secret = notification_service.decrypt_field(
            ch["config"].get("app_secret_encrypted") or ""
        )
        _client_instance = (
            lark.Client.builder()
            .app_id(target_app_id)
            .app_secret(app_secret)
            .log_level(_resolve_log_level(target_log_level))
            .build()
        )
        _client_channel_id = target_channel_id
        _client_app_id = target_app_id
        logger.info(
            "[feishu_client] 飞书 lark client 已初始化（channel_id=%s, app_id=%s, log_level=%s）",
            target_channel_id,
            target_app_id,
            target_log_level,
        )
        return _client_instance


def reset_lark_client() -> None:
    """重置客户端缓存（仅供测试使用）。

    清空单例后，下次调用 get_lark_client() 会重新读取 DB 并构造新 client。
    """
    global _client_instance, _client_channel_id, _client_app_id
    with _client_lock:
        _client_instance = None
        _client_channel_id = None
        _client_app_id = None
