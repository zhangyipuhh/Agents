#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
app.shared.tools.channels.feishu - 飞书渠道包

导入本包即自动把 ``FeishuCardConsumer`` 注册到 ``channel_registry``，
按 ``"feishu"`` 前缀匹配所有 ``feishu:p2p:*`` / ``feishu:group:*`` 形式的 session_id。

使用方式（lifespan 启动阶段）：
    import app.shared.tools.channels.feishu  # noqa: F401

注册后运行时通过：
    from app.shared.tools.channels.registry import channel_registry
    consumer = channel_registry.resolve(session_id, lark_client=..., chat_id=...)
"""
from app.shared.tools.channels.feishu.FeishuCardConsumer import FeishuCardConsumer
from app.shared.tools.channels.registry import channel_registry

# 一次性注册：飞书前缀匹配 feishu:p2p:* / feishu:group:* 等所有形式
# 重复注册会抛 ValueError，由 lifespan try/except 兜底（避免重复 import 时崩溃）
try:
    channel_registry.register("feishu", FeishuCardConsumer)
except ValueError:
    # 已注册（如热重载场景），跳过
    pass

__all__ = ["FeishuCardConsumer"]
