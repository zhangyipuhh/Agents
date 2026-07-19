#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
app.shared.tools.channels - 多渠道消费者包

包结构：
    channels/
    ├── __init__.py        # 本文件：导出公共 API
    ├── base.py            # ChannelConsumer 抽象基类
    ├── registry.py        # ChannelRegistry 路由注册中心
    └── feishu/            # 飞书渠道实现
        ├── __init__.py    # 注册 FeishuCardConsumer 到 channel_registry
        ├── Throttler.py   # 时间窗 + 字符增量双条件节流器
        └── FeishuCardConsumer.py  # 飞书 CardKit 同卡片流式消费者

使用方式：
    # 在 lifespan 启动阶段导入 feishu 包触发自动注册：
    import app.shared.tools.channels.feishu  # noqa: F401

    # 运行时通过 channel_registry.resolve 拿到 Consumer 实例：
    from app.shared.tools.channels.registry import channel_registry
    consumer = channel_registry.resolve(session_id, **ctx)
"""
from app.shared.tools.channels.base import ChannelConsumer
from app.shared.tools.channels.registry import ChannelRegistry, channel_registry

__all__ = ["ChannelConsumer", "ChannelRegistry", "channel_registry"]