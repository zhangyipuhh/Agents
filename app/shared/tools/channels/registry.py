#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ChannelRegistry - 渠道消费者注册中心

职责：
    - 按 ``session_id`` 前缀路由到对应的 ``ChannelConsumer`` 子类
    - 在 lifespan 启动阶段一次性 ``register(...)`` 注册各渠道
    - 运行时 ``resolve(session_id, **ctx)`` 按 session_id 前缀匹配（最长前缀优先）
      实例化对应 Consumer

session_id 前缀约定（与 ``FeishuWebSocketService._build_session_id`` 输出对齐）：
    - ``feishu:p2p:{open_id}`` → FeishuCardConsumer
    - ``feishu:group:{chat_id}:{open_id}`` → FeishuCardConsumer
    - ``dingtalk:xxx`` → DingTalkCardConsumer（未来扩展）
    - ``wecom:xxx`` → WeComCardConsumer（未来扩展）

设计原则：
    - 模块级全局单例 ``channel_registry``，整个进程共享
    - 重复注册同一前缀抛 ``ValueError``，避免静默覆盖
    - ``resolve`` 未命中时抛 ``ValueError``，调用方需保证 session_id 前缀已注册
    - 实例化时透传 ``**ctx`` 给 Consumer 构造函数（飞书侧含
      ``lark_client`` / ``chat_id`` / ``throttler`` 等）

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

from typing import Any, List, Tuple, Type

from app.shared.tools.channels.base import ChannelConsumer


class ChannelRegistry:
    """按 session_id 前缀路由到 ``ChannelConsumer``。"""

    def __init__(self) -> None:
        """初始化空注册表。"""
        # 按 (prefix, consumer_cls) 二元组存储；resolve 时按 prefix 长度降序匹配
        self._registry: List[Tuple[str, Type[ChannelConsumer]]] = []

    def register(
        self, prefix: str, consumer_cls: Type[ChannelConsumer]
    ) -> None:
        """注册渠道 — lifespan 阶段一次性调用。

        Args:
            prefix: session_id 前缀（如 ``"feishu"``，匹配 ``feishu:p2p:xxx`` /
                ``feishu:group:xxx`` 等所有以 ``"feishu"`` 开头的 session_id）
            consumer_cls: ``ChannelConsumer`` 子类（非实例）

        Raises:
            ValueError: 同一前缀重复注册（避免静默覆盖）
        """
        if not prefix:
            raise ValueError("ChannelRegistry.register: prefix 不能为空")
        if not isinstance(prefix, str):
            raise TypeError(
                "ChannelRegistry.register: prefix 必须是 str"
            )
        # 检查重复注册（精确匹配 prefix）
        for existing_prefix, _ in self._registry:
            if existing_prefix == prefix:
                raise ValueError(
                    f"ChannelRegistry.register: 前缀 {prefix!r} 已注册，禁止重复注册"
                )
        self._registry.append((prefix, consumer_cls))
        # 按 prefix 长度降序排序，保证最长前缀优先匹配
        self._registry.sort(key=lambda x: len(x[0]), reverse=True)

    def resolve(self, session_id: str, **ctx: Any) -> ChannelConsumer:
        """按 session_id 前缀匹配（最长前缀优先），实例化对应 Consumer。

        Args:
            session_id: 会话 ID（LangGraph thread_id，如 ``feishu:p2p:ou_xxx``）
            **ctx: 透传给 Consumer 构造函数的渠道上下文（飞书侧含
                ``lark_client`` / ``chat_id`` / ``throttler`` 等）

        Returns:
            ChannelConsumer: 实例化后的 Consumer（持有本 session 的状态）

        Raises:
            ValueError: session_id 未命中任何已注册前缀
        """
        if not session_id:
            raise ValueError("ChannelRegistry.resolve: session_id 不能为空")
        # 最长前缀优先匹配（register 时已按长度降序排序）
        for prefix, consumer_cls in self._registry:
            if session_id.startswith(prefix):
                return consumer_cls(session_id=session_id, **ctx)
        raise ValueError(
            f"ChannelRegistry.resolve: session_id {session_id!r} 未命中任何已注册渠道前缀，"
            f"已注册前缀: {[p for p, _ in self._registry]}"
        )

    def list_prefixes(self) -> List[str]:
        """列出所有已注册前缀（调试用）。

        Returns:
            list[str]: 已注册前缀列表（按注册顺序）
        """
        return [prefix for prefix, _ in self._registry]

    def clear(self) -> None:
        """清空注册表（仅测试用）。

        生产代码不应调用此方法；lifespan 阶段注册后整个进程共享一份注册表。
        """
        self._registry.clear()


# 模块级全局单例
channel_registry = ChannelRegistry()


