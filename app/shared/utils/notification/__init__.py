# -*- coding:utf-8 -*-
"""
通知渠道通用工具模块。

承载飞书及未来所有新增通知渠道（钉钉 / 企微 / Slack 等）的凭证与目标管理。
本模块核心契约见 ``memory/misc.md`` 「通知渠道通用表设计原则」章节
（2026-09-03 落地）：

- 所有新渠道共用 ``notification_channels`` + ``notification_targets`` 两张表
- ``channel_type`` / ``target_type`` 字段白名单区分渠道（CHECK 约束）
- 渠道差异一律进 ``config`` JSONB，service 层按 ``channel_type`` 分发
- 邮件老表（``email_*``）永远不动
"""
from app.shared.utils.notification.notification_config_service import (
    NotificationConfigError,
    NotificationConfigNotFoundError,
    NotificationConfigService,
    NotificationConfigValidationError,
)

__all__ = [
    "NotificationConfigService",
    "NotificationConfigError",
    "NotificationConfigNotFoundError",
    "NotificationConfigValidationError",
]
