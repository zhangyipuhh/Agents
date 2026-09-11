# -*- coding:utf-8 -*-
"""
FeishuWebSocketManager - 飞书 WebSocket 多实例编排器

设计目的（2026-09-03 落地，2026-09-07 收敛，2026-09-10 热加载）

- 多应用下 WS 必须支持监听多个 agent,不同应用接的是不一样智能体
- 遍历 ``notification_channels WHERE enabled=TRUE AND channel_type='feishu'``，
  每条渠道启动独立的 ``FeishuWebSocketService`` 实例(独立后台线程 / 独立
  ``lark.Client``)
- channel 绑定智能体：WS 实例从 ``channel.config.agent_name`` 派生;
  接收账号从 ``channel.config.receiver_username`` 读,空时兜底
  ``settings.feishu_ws_receiver_username``
- 零应用时 INFO log skip,**不 fail-loud**(用户硬约束「WS 启动无 DB 应用时
  跳过即可」)
- 各实例**完全隔离**:一个应用断开 / 异常不影响其他应用
- **保存即生效（2026-09-10 热加载）**：``apply_channel_change(channel_id)``
  在渠道新增 / 更新 / 启停 / 删除后被 notification_router 调用,先停旧实例再按
  DB 最新状态决定是否重启,无需重启服务。

已知限制（存量,2026-09-10 记录）

- lark SDK 把 event loop 缓存在 ``lark_oapi.ws.client`` 模块级全局变量,多实例
  线程共享该全局。热启动某渠道会重新 patch 全局,其他运行中实例恰好在同一
  毫秒级窗口断线重连时可能受影响。``FeishuWebSocketService._WS_START_LOCK``
  已把「patch → 首次 connect」窗口串行化压到最小;彻底隔离需每渠道独立模块
  副本或进程级隔离,留作后续演进。

session_id 命名空间

- 原约定 ``feishu:p2p:{open_id}`` / ``feishu:group:{chat_id}:{open_id}``
- 新约定 ``feishu:{channel_id}:p2p:{open_id}`` / ``feishu:{channel_id}:group:{chat_id}:{open_id}``
  让 sessions 表按 channel 隔离;前端按 receiver_username 可看到该 channel 全部 session
- ``channel_id`` 在 ``_start_one_channel`` 时注入 ``FeishuWebSocketService._channel_id`` 字段

依赖

- ``app.core.config.settings.settings.feishu_ws_receiver_username``
  作为 channel.receiver_username 为空时的兜底
- ``app.shared.utils.notification.NotificationConfigService`` 提供凭证解析
- ``app.shared.tools.skills.feishu.FeishuWebSocketService.FeishuWebSocketService`` 每实例一个
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import lark_oapi as lark

from app.core.config.settings import settings as app_settings
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
        # 2026-09-10 新增：热加载操作串行锁（asyncio 级别），
        # 防止同一渠道并发 apply / start_all 与 apply 交叉导致实例泄漏
        self._ops_lock = asyncio.Lock()

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

        started = 0
        loop = asyncio.get_event_loop()
        for ch in channels:
            svc = await self._start_one_channel(
                ch, agent_config_service, user_lookup, loop
            )
            if svc is not None:
                started += 1

        logger.info(
            "[lifespan] FeishuWebSocketManager started %d instance(s)", started
        )
        return started

    async def _start_one_channel(
        self,
        ch: Dict[str, Any],
        agent_config_service: Any,
        user_lookup: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> Optional[Any]:
        """启动单个飞书渠道 WS 实例（start_all 与热加载共用）。

        参数:
            ch: 渠道行（至少含 ``id`` / ``name``；config 会经
                ``_get_channel_internal`` 重读含加密字段原文）。
            agent_config_service: AgentConfigService 实例。
            user_lookup: ``UserDB.get_user_by_username`` 函数；None 时跳过
                receiver 解析（receiver_user_id=None）。
            loop: FastAPI 主事件循环（注入 service 供消息协程回投）。

        返回:
            Optional[FeishuWebSocketService]: 启动成功返回实例（已登记到
            ``self.services``）；任一步骤失败返回 None（不向上抛，单实例失败
            不影响其他渠道）。
        """
        # 动态 import 避免循环依赖
        from app.shared.tools.skills.feishu.FeishuWebSocketService import (
            FeishuWebSocketService,
        )

        channel_id = ch["id"]
        try:
            # 用 service._get_channel_internal 拿含加密字段原文的 config
            internal = await self._notification_service._get_channel_internal(channel_id)  # noqa: SLF001
            if internal is None:
                logger.warning(
                    "[feishu_ws_manager] channel_id=%s 已不存在,跳过", channel_id
                )
                return None
            cfg = internal["config"]
            app_id_enc = cfg.get("app_id_encrypted")
            app_secret_enc = cfg.get("app_secret_encrypted")
            if not app_id_enc or not app_secret_enc:
                logger.warning(
                    "[feishu_ws_manager] channel_id=%s 凭证为空,跳过启动",
                    channel_id,
                )
                return None
            try:
                app_id = self._notification_service.decrypt_field(app_id_enc)
                app_secret = self._notification_service.decrypt_field(app_secret_enc)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[feishu_ws_manager] channel_id=%s 凭证解密失败: %s",
                    channel_id, exc,
                )
                return None
            log_level_str = cfg.get("log_level", "INFO")
            # 2026-09-07 第二轮：channel 重新绑智能体——从 channel.config.agent_name 读
            # 接收账号从 channel.config.receiver_username 读，若为空兜底 settings.feishu_ws_receiver_username
            agent_name = cfg.get("agent_name", "").strip()
            receiver_username = cfg.get("receiver_username", "").strip() or \
                app_settings.feishu.feishu_ws_receiver_username
            if not agent_name or not receiver_username:
                logger.warning(
                    "[feishu_ws_manager] channel_id=%s 缺 agent_name 或 receiver_username,跳过",
                    channel_id,
                )
                return None
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
                        return None
                    receiver_user_id = receiver_row["id"]
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[feishu_ws_manager] channel_id=%s 解析 receiver 失败: %s",
                        channel_id, exc,
                    )
                    return None

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
            logger.info(
                "[feishu_ws_manager] 已启动 channel_id=%s (name=%s, agent=%s, receiver=%s)",
                channel_id, ch.get("name"), agent_name, receiver_username,
            )
            return ws_service
        except Exception as exc:  # noqa: BLE001 - 单实例失败不影响其他
            logger.warning(
                "[feishu_ws_manager] channel_id=%s 启动失败: %s",
                channel_id, exc, exc_info=True,
            )
            return None

    async def apply_channel_change(
        self,
        channel_id: int,
        agent_config_service: Any = None,
        user_lookup: Any = None,
    ) -> bool:
        """热加载单个渠道（保存即生效入口，由 notification_router 调用）。

        语义：先停掉该渠道现有实例（若有）→ 重读 DB 最新行 →
        行存在且 ``enabled=True`` 且 ``channel_type='feishu'`` 则重新启动；
        行已删除 / 已禁用 / 非飞书渠道则保持停止。

        参数:
            channel_id: 变更的渠道 ID。
            agent_config_service: AgentConfigService 实例。
            user_lookup: ``UserDB.get_user_by_username`` 函数。

        返回:
            bool: True=该渠道最终处于运行态;False=已停止 / 启动失败。
        """
        async with self._ops_lock:
            # 1. 停旧实例（优雅断开连接 + 回收线程）
            old = self.services.pop(channel_id, None)
            if old is not None:
                try:
                    old.shutdown()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[feishu_ws_manager] channel_id=%s 停止旧实例异常: %s",
                        channel_id, exc,
                    )

            # 2. 读 DB 最新状态
            try:
                internal = await self._notification_service._get_channel_internal(channel_id)  # noqa: SLF001
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[feishu_ws_manager] apply 读取 channel_id=%s 失败: %s",
                    channel_id, exc,
                )
                return False

            if (
                internal is None
                or not internal.get("enabled")
                or internal.get("channel_type") != "feishu"
            ):
                logger.info(
                    "[feishu_ws_manager] channel_id=%s 已删除/禁用,实例保持停止",
                    channel_id,
                )
                return False

            # 3. 按最新配置重启
            loop = asyncio.get_event_loop()
            svc = await self._start_one_channel(
                internal, agent_config_service, user_lookup, loop
            )
            return svc is not None

    async def stop_all(self) -> None:
        """停止所有实例（lifespan 关停用，仅置标志快速返回）。"""
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

    async def restart_channel(
        self,
        channel_id: int,
        agent_config_service: Any = None,
        user_lookup: Any = None,
    ) -> bool:
        """重启某个渠道实例（2026-09-10 起实现为热加载委托）。

        参数:
            channel_id: 渠道 ID。
            agent_config_service: AgentConfigService 实例。
            user_lookup: ``UserDB.get_user_by_username`` 函数。

        返回:
            bool: 重启后该渠道是否处于运行态。
        """
        return await self.apply_channel_change(
            channel_id,
            agent_config_service=agent_config_service,
            user_lookup=user_lookup,
        )
