#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuEndpointResolver - 飞书工具公共 Endpoint 解析模块

职责：
    - 从 LangChain ``ToolRuntime.state.agent_name`` 拿当前智能体名
    - 调 ``NotificationConfigService.resolve_agent_feishu_endpoint`` 一次性
      解析 channel + target + 明文凭证 + chat_id
    - 用 Endpoint dataclass 封装返回值，供所有飞书工具复用
    - 提供 ``build_lark_client(endpoint)`` 构造临时 ``lark.Client``

设计目标（2026-09-11）：
    - **复用**：未来新增 ``send_feishu_document`` / ``send_feishu_image`` /
      ``upload_feishu_doc`` 等飞书工具时，只需 import 本模块，无需重复实现
      DB 查询 + 凭证解密 + client 构造逻辑。
    - **异步直达**：工具与 service 均为 async，直接 ``await`` 调用，
      不做同步桥接。

公共 API：
    - ``Endpoint`` : dataclass，封装一次解析的全部结果
    - ``resolve_current_endpoint(runtime)`` : 主入口，失败返回 ``None``
    - ``build_lark_client(endpoint)`` : 用明文凭证构造临时 ``lark.Client``
    - 错误文案常量 ``ERROR_*`` : 供各工具统一返回给用户
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# 统一错误文案（供所有飞书工具复用）
# =============================================================================

ERROR_NO_AGENT_NAME = "未识别当前智能体，请检查智能体配置"
ERROR_NO_CHANNEL = (
    "智能体 {agent_name!r} 未绑定飞书渠道，"
    "请到「消息设置 → 飞书设置 → 应用设置」配置"
)
ERROR_NO_TARGET = (
    "飞书渠道 {channel_name!r} 未配置接收群，"
    "请到「消息设置 → 飞书设置 → 发送策略」添加"
)
ERROR_DB_UNAVAILABLE = "通知配置服务未初始化"


# =============================================================================
# Endpoint dataclass
# =============================================================================


@dataclass(frozen=True)
class Endpoint:
    """一次飞书 endpoint 解析的完整结果。

    Attributes:
        channel_id: notification_channels.id
        channel_name: notification_channels.name
        app_id: 明文 app_id（已解密）
        app_secret: 明文 app_secret（已解密）
        log_level: SDK 日志级别（DEBUG / INFO / WARNING / ERROR）
        target_id: notification_targets.id
        target_name: notification_targets.name
        chat_id: 接收方 ID（群 chat_id / 用户 open_id 等）
        chat_type: 接收方类型（chat_id / open_id / user_id / email）
        agent_name: 当前智能体名
    """

    channel_id: int
    channel_name: str
    app_id: str
    app_secret: str
    log_level: str
    target_id: int
    target_name: str
    chat_id: str
    chat_type: str
    agent_name: str


# =============================================================================
# 内部 helpers
# =============================================================================


def _get_notification_service():
    """从 ``app.state.notification_config_service`` 取服务实例（延迟 import）。

    Returns:
        Optional[NotificationConfigService]: 未初始化时返回 None。
    """
    try:
        from app.main import app as _fastapi_app

        return getattr(_fastapi_app.state, "notification_config_service", None)
    except Exception:  # noqa: BLE001
        return None


def _get_agent_name_from_runtime(runtime: Any) -> Optional[str]:
    """从 ``runtime.state`` 安全读取 ``agent_name``（参考 SkillTools._get_agent_name）。

    Args:
        runtime: LangChain ToolRuntime 实例（可能为 None）。

    Returns:
        Optional[str]: agent_name；runtime 缺失 / state 缺失 / 字段为空时返回 None。
    """
    if runtime is None:
        return None
    try:
        state = getattr(runtime, "state", None)
        if state is None:
            return None
        agent_name = state.get("agent_name")
        if not agent_name or not isinstance(agent_name, str):
            return None
        stripped = agent_name.strip()
        return stripped or None
    except Exception:  # noqa: BLE001
        return None


# =============================================================================
# 公共 API
# =============================================================================


async def resolve_current_endpoint(runtime: Any) -> Optional[Endpoint]:
    """从 ``runtime.state.agent_name`` 解析当前智能体的飞书 endpoint。

    流程：
        1. 从 runtime 取 agent_name，缺失返回 None
        2. 取 notification_config_service，未初始化返回 None（WARNING 日志）
        3. 直接 ``await service.resolve_agent_feishu_endpoint``，异常返回 None（WARNING 日志）
        4. dict → Endpoint dataclass

    Args:
        runtime: LangChain ToolRuntime 实例。

    Returns:
        Optional[Endpoint]: 任一环节失败返回 None；
        调用方根据 None 自行决定返回哪种 ERROR_* 文案。
    """
    agent_name = _get_agent_name_from_runtime(runtime)
    if agent_name is None:
        return None
    service = _get_notification_service()
    if service is None:
        logger.warning(
            "[feishu_endpoint_resolver] notification_config_service 未初始化，"
            "无法解析 agent=%s 的飞书端点",
            agent_name,
        )
        return None
    try:
        raw = await service.resolve_agent_feishu_endpoint(agent_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[feishu_endpoint_resolver] resolve_agent_feishu_endpoint 失败 agent=%s err=%s",
            agent_name, type(exc).__name__, exc_info=True,
        )
        return None
    if raw is None:
        return None
    try:
        return Endpoint(
            channel_id=raw["channel_id"],
            channel_name=raw["channel_name"],
            app_id=raw["app_id"],
            app_secret=raw["app_secret"],
            log_level=raw["log_level"],
            target_id=raw["target_id"],
            target_name=raw["target_name"],
            chat_id=raw["chat_id"],
            chat_type=raw["chat_type"],
            agent_name=raw["agent_name"],
        )
    except (KeyError, TypeError) as exc:
        logger.warning(
            "[feishu_endpoint_resolver] service 返回字段缺失 agent=%s err=%s",
            agent_name, exc,
        )
        return None


def build_lark_client(endpoint: Endpoint):
    """用 Endpoint 明文凭证构造临时 ``lark.Client``（不走全局单例）。

    Args:
        endpoint: ``resolve_current_endpoint`` 的返回值。

    Returns:
        lark.Client: 按 endpoint.app_id/app_secret/log_level 构造的新实例。

    Raises:
        ImportError: lark_oapi 未安装时抛出（正常生产环境必装）。
    """
    import lark_oapi as lark

    log_level_map = {
        "DEBUG": lark.LogLevel.DEBUG,
        "INFO": lark.LogLevel.INFO,
        "WARNING": lark.LogLevel.WARNING,
        "ERROR": lark.LogLevel.ERROR,
    }
    log_level = log_level_map.get(
        (endpoint.log_level or "INFO").upper(),
        lark.LogLevel.INFO,
    )
    return (
        lark.Client.builder()
        .app_id(endpoint.app_id)
        .app_secret(endpoint.app_secret)
        .log_level(log_level)
        .build()
    )