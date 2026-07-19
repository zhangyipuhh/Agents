#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ChannelConsumer - 渠道消费者抽象基类

职责：
    - 定义所有输出渠道（飞书 / 钉钉 / 企微 / Slack / ...）的统一接口
    - 由 ``StreamEventSource`` 产出的 ``StreamEvent`` 序列驱动，Consumer 负责
      把事件翻译为具体渠道的渲染动作（CardKit patch / 钉钉卡片 update / ...）
    - 维护本会话内累积的回复文本与最后一次 HITL 中断请求，供调用方
      （如 ``FeishuWebSocketService._call_agent``）回取

接口契约（6 个回调方法）：
    - ``on_session_start``：流开始（Consumer 可创建占位资源，如 CardKit 卡片实体）
    - ``on_text_chunk``：LLM token 文本片段（Consumer 自行决定节流 / 累积策略）
    - ``on_node_update``：节点状态更新（含 tools 节点完成等信号）
    - ``on_interrupt``：HITL 中断（Consumer 在同卡片追加按钮 / 发新卡片）
    - ``on_session_end``：流自然结束（Consumer 强制 flush 最后一次更新）
    - ``on_abort``：用户主动 abort（Consumer 在卡片末尾追加停止标记）

设计原则：
    - 抽象基类仅声明接口，不实现业务逻辑
    - 子类必须实现全部 6 个抽象方法
    - 公共状态（``accumulated_text`` / ``last_interrupt_req``）放基类，
      避免每个子类重复维护

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ChannelConsumer(ABC):
    """渠道消费者抽象接口 — 任何输出渠道（飞书 / 钉钉 / 企微）实现此接口。

    Attributes:
        session_id: 会话 ID（LangGraph thread_id，也用作渠道前缀路由 key）
        accumulated_text: 本会话累积的 LLM token 文本（流结束时即完整回复）
        last_interrupt_req: 最后一次 HITL 中断请求（``StreamEvent.interrupt_requests``
            的首个元素；非 HITL 场景为 ``None``）
    """

    def __init__(self, *, session_id: str, **ctx: Any) -> None:
        """初始化渠道消费者。

        Args:
            session_id: 会话 ID（LangGraph thread_id）
            **ctx: 渠道特定上下文（如飞书 ``lark_client`` / ``chat_id`` / ``throttler``）。
                基类不解释这些字段，由子类自行取用。
        """
        self.session_id: str = session_id
        self.accumulated_text: str = ""
        self.last_interrupt_req: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # 抽象接口（子类必须实现）                                              #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def on_session_start(self) -> None:
        """流开始回调。

        Consumer 可在此处创建占位资源（如飞书 CardKit 卡片实体 + 关联消息）。
        若创建失败，Consumer 应自行切换到降级路径（如一次性发送）。
        """
        raise NotImplementedError

    @abstractmethod
    async def on_text_chunk(self, text: str) -> None:
        """LLM token 文本片段回调。

        Consumer 应累积文本并按节流策略推送更新到渠道。

        Args:
            text: LLM token 文本片段（非空字符串；空串由调用方过滤）
        """
        raise NotImplementedError

    @abstractmethod
    async def on_node_update(
        self, node_name: str, node_data: Dict[str, Any]
    ) -> None:
        """节点状态更新回调。

        Consumer 可在此处更新进度指示器（如"正在调用工具 X"）。
        飞书侧目前主要消费 ``tools`` 节点完成信号。

        Args:
            node_name: 节点名称（updates 模式 chunk 的 data 顶层 key）
            node_data: 节点状态更新 dict（含 messages / state_updates 等）
        """
        raise NotImplementedError

    @abstractmethod
    async def on_interrupt(self, requests: List[Dict[str, Any]]) -> None:
        """HITL 中断回调。

        Consumer 应把 interrupt 请求转按钮追加到当前卡片（同卡片就地追加，
        避免上下文割裂），或降级为新卡片。基类不强制实现方式。

        Args:
            requests: 结构化 HITL 中断请求列表（来自
                ``StreamEvent.interrupt_requests``，元素为 dict，含
                ``action`` / ``questions`` 等字段）
        """
        raise NotImplementedError

    @abstractmethod
    async def on_session_end(self) -> None:
        """流自然结束回调。

        Consumer 应强制 flush 最后一次更新（节流器 ``force_flush``），
        保证用户看到完整的最终回复。
        """
        raise NotImplementedError

    @abstractmethod
    async def on_abort(self) -> None:
        """用户主动 abort 回调。

        Consumer 应在卡片末尾追加停止标记（如飞书「（已停止）」），
        并设置内部 ``_stopped`` 标志停止后续 patch。
        """
        raise NotImplementedError
