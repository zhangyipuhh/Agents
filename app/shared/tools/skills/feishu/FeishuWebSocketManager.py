# -*- coding:utf-8 -*-
"""
FeishuWebSocketManager - 飞书 WebSocket 多实例编排器

设计目的（2026-09-03 落地）

- 多应用下 WS 必须支持监听多个 agent,不同应用接的是不一样智能体
- 遍历 ``notification_channels WHERE enabled=TRUE AND channel_type='feishu'``，
  每条渠道启动独立的 ``FeishuWebSocketService`` 实例(独立后台线程 / 独立
  ``lark.Client`` / 独立 ``agent_name`` / 独立 ``receiver_username``)
- 零应用时 INFO log skip,**不 fail-loud**(用户硬约束「WS 启动无 DB 应用时
  跳过即可」)
- 各实例**完全隔离**:一个应用断开 / 异常不影响其他应用

session_id 命名空间

- 原约定 ``feishu:p2p:{open_id}`` / ``feishu:group:{chat_id}:{open_id}``
- 新约定 ``feishu:{channel_id}:p2p:{open_id}`` / ``feishu:{channel_id}:group:{chat_id}:{open_id}``
  让 sessions 表按 channel 隔离;前端按 receiver_username 可看到该 channel 全部 session
- ``channel_id`` 在 ``start_one_channel`` 时注入 ``FeishuWebSocketService._channel_id`` 字段

依赖

- ``app.core.config.settings.settings`` 不再读 ``.env`` 飞书字段
- ``app.shared.utils.notification.NotificationConfigService`` 提供凭证与默认应用解析
- ``app.shared.tools.skills.feishu.FeishuWebSocketService.FeishuWebSocketService`` 每实例一个
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import lark_oapi as lark

from app.shared.utils.notification import NotificationConfigService
from app.shared.utils.notification.notification_config_service import (
    SUPPORTED_CHANNEL_TYPES,
)


logger = logging.getLogger(__name__)


def _resolve_lark_log_level(level_str: str) -> int:
    """把字符串日志级别映射为 lark.LogLevel 枚举值；未识别默认 INFO。"""
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


class FeishuWebSocketManager:
    """飞书 WebSocket 多实例编排器。

    Attributes:
        services: ``channel_id -> FeishuWebSocketService`` 实例映射。
    """

    def __init__(self, notification_service: NotificationConfigService) -> None:
        """初始化编排器。

        参数:
            notification_service: ``NotificationConfigService`` 实例。
        """
        self._notification_service = notification_service
        self.services: Dict[int, Any] = {}

    async def start_all(
        self,
        agent_config_service: Any,
        user_lookup: Any = None,
    ) -> int:
        """遍历 ``notification_channels`` 启动所有 enabled 飞书渠道实例。

        参数:
            agent_config_service: AgentConfigService 实例（用于 build_agent_instance）。
            user_lookup: ``UserDB.get_user_by_username`` 函数（避免直接 import 触发循环）。

        返回:
            int: 启动的实例数。
        """
        if "feishu" not in SUPPORTED_CHANNEL_TYPES:
            logger.warning(
                "[feishu_ws_manager] channel_type='feishu' 未在 SUPPORTED_CHANNEL_TYPES 白名单,跳过"
            )
            return 0

        try:
            channels = await self._notification_service.list_channels(
                channel_type="feishu",
                enabled_only=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[feishu_ws_manager] list_channels failed: %s", type(exc).__name__
            )
            return 0

        if not channels:
            logger.info(
                "[lifespan] FeishuWebSocketManager skipped: 数据库无 enabled=TRUE 的飞书渠道,跳过 WS 启动"
            )
            return 0

        # 动态 import 避免循环依赖
        from app.shared.tools.skills.feishu.FeishuWebSocketService import (
            FeishuWebSocketService,
        )

        started = 0
        loop = asyncio.get_event_loop()
        for ch in channels:
            channel_id = ch["id"]
            try:
                # 用 service._get_channel_internal 拿含加密字段原文的 config
                internal = await self._notification_service._get_channel_internal(channel_id)  # noqa: SLF001
                if internal is None:
                    logger.warning(
                        "[feishu_ws_manager] channel_id=%s 已不存在,跳过", channel_id
                    )
                    continue
                cfg = internal["config"]
                app_id_enc = cfg.get("app_id_encrypted")
                app_secret_enc = cfg.get("app_secret_encrypted")
                if not app_id_enc or not app_secret_enc:
                    logger.warning(
                        "[feishu_ws_manager] channel_id=%s 凭证为空,跳过启动",
                        channel_id,
                    )
                    continue
                try:
                    app_id = self._notification_service.decrypt_field(app_id_enc)
                    app_secret = self._notification_service.decrypt_field(app_secret_enc)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[feishu_ws_manager] channel_id=%s 凭证解密失败: %s",
                        channel_id, exc,
                    )
                    continue
                log_level_str = cfg.get("log_level", "INFO")
                agent_name = cfg.get("agent_name", "")
                receiver_username = cfg.get("receiver_username", "")
                if not agent_name or not receiver_username:
                    logger.warning(
                        "[feishu_ws_manager] channel_id=%s 缺 agent_name 或 receiver_username,跳过",
                        channel_id,
                    )
                    continue
                # 解析 receiver user_id
                receiver_user_id: Optional[int] = None
                if user_lookup is not None:
                    try:
                        receiver_row = await user_lookup(receiver_username)
                        if receiver_row is None:
                            logger.warning(
                                "[feishu_ws_manager] channel_id=%s receiver_username=%r 不存在,跳过",
                                channel_id, receiver_username,
                            )
                            continue
                        receiver_user_id = receiver_row["id"]
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "[feishu_ws_manager] channel_id=%s 解析 receiver 失败: %s",
                            channel_id, exc,
                        )
                        continue

                # 构造 lark.Client(每实例独立)
                client = (
                    lark.Client.builder()
                    .app_id(app_id)
                    .app_secret(app_secret)
                    .log_level(_resolve_lark_log_level(log_level_str))
                    .build()
                )

                ws_service = FeishuWebSocketService(
                    lark_client=client,
                    agent_config_service=agent_config_service,
                    agent_name=agent_name,
                    receiver_user_id=receiver_user_id,
                    receiver_username=receiver_username,
                    log_level=log_level_str,
                )
                # 注入 channel_id,让 _build_session_id 加 channel 命名空间
                ws_service._channel_id = channel_id  # noqa: SLF001
                ws_service.set_event_loop(loop)
                await ws_service.start_async()
                self.services[channel_id] = ws_service
                started += 1
                logger.info(
                    "[feishu_ws_manager] 已启动 channel_id=%s (name=%s, agent=%s, receiver=%s)",
                    channel_id, ch.get("name"), agent_name, receiver_username,
                )
            except Exception as exc:  # noqa: BLE001 - 单实例失败不影响其他
                logger.warning(
                    "[feishu_ws_manager] channel_id=%s 启动失败: %s",
                    channel_id, exc, exc_info=True,
                )

        logger.info(
            "[lifespan] FeishuWebSocketManager started %d instance(s)", started
        )
        return started

    async def stop_all(self) -> None:
        """停止所有实例。"""
        for channel_id, service in list(self.services.items()):
            try:
                service.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[feishu_ws_manager] stop channel_id=%s failed: %s",
                    channel_id, exc,
                )
        self.services.clear()
        logger.info("[lifespan] FeishuWebSocketManager stopped all instances")

    def restart_channel(self, channel_id: int) -> bool:
        """重启某个渠道实例（异步调用方应自行 await）。

        本期作为占位 API 暴露,不实现真正的热重启(避免与 WS 多线程交互产生
        竞态);未来在 UI 保存 channel 后可调此方法。返回 False 提示未实现。

        Returns:
            bool: 始终 False(占位)。
        """
        logger.warning(
            "[feishu_ws_manager] restart_channel(channel_id=%s) 本期未实现,需重启服务",
            channel_id,
        )
        return False
