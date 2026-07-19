#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
StreamEvent - agent.stream 输出的统一事件包装

职责：
    - 把 LangGraph ``agent.stream(...)`` 在不同 ``stream_mode`` 下产出的异构 chunk
      抽象为统一的 ``StreamEvent`` 数据结构
    - 与具体输出渠道（飞书 / 钉钉 / 企微 / 前端 SSE）解耦：渠道消费者只需识别
      ``kind`` 字段分发处理，无需感知 LangGraph 内部 chunk 形态

事件类型（``StreamEvent.kind``）：
    - ``session_start``：流开始（首次 yield，用于 Consumer 创建占位资源）
    - ``text``：LLM token 文本片段（来自 ``messages`` 模式）
    - ``update``：节点状态更新（来自 ``updates`` 模式，含 node_name + node_data）
    - ``interrupt``：HITL 中断（来自 ``__interrupt__`` 多模式检测）
    - ``session_end``：流自然结束
    - ``abort``：用户主动 abort（abort_event.is_set()）

设计原则：
    - 纯数据结构，无业务逻辑
    - 所有字段均为 Optional，``kind`` 字段必填
    - dataclass + slots 提升内存与访问效率

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# 事件类型常量（与 docstring 中列出的 kind 字符串保持一致）
KIND_SESSION_START = "session_start"
KIND_TEXT = "text"
KIND_UPDATE = "update"
KIND_INTERRUPT = "interrupt"
KIND_SESSION_END = "session_end"
KIND_ABORT = "abort"


@dataclass
class StreamEvent:
    """agent.stream 输出的统一事件包装，与渠道解耦。

    Attributes:
        kind: 事件类型，取值为模块级 ``KIND_*`` 常量
            - ``session_start`` / ``text`` / ``update`` / ``interrupt``
            / ``session_end`` / ``abort``
        text: 文本片段，仅在 ``kind == "text"`` 时填充
        node_name: 节点名称，仅在 ``kind == "update"`` 时填充
            （取自 updates 模式 chunk 的 ``data`` 顶层 key；多节点场景取首个）
        node_data: 节点状态更新 dict，仅在 ``kind == "update"`` 时填充
            （原始 ``data`` dict，含 messages / state_updates 等）
        interrupt_requests: 结构化 HITL 中断请求列表，
            仅在 ``kind == "interrupt"`` 时填充。元素为 dict，含
            ``action`` / ``questions`` 等字段，结构与
            ``app/routers/_stream_helper.py::_extract_interrupt_requests``
            输出一致
    """

    kind: str
    text: Optional[str] = None
    node_name: Optional[str] = None
    node_data: Optional[Dict[str, Any]] = None
    interrupt_requests: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def session_start(cls) -> "StreamEvent":
        """构造 ``session_start`` 事件。

        Returns:
            StreamEvent: kind=session_start 的占位事件
        """
        return cls(kind=KIND_SESSION_START)

    @classmethod
    def text_chunk(cls, text: str) -> "StreamEvent":
        """构造 ``text`` 事件。

        Args:
            text: LLM token 文本片段（不可为 None；空串允许但 Consumer 可自行跳过）

        Returns:
            StreamEvent: kind=text 的事件
        """
        return cls(kind=KIND_TEXT, text=text)

    @classmethod
    def update(
        cls,
        node_name: Optional[str],
        node_data: Optional[Dict[str, Any]],
    ) -> "StreamEvent":
        """构造 ``update`` 事件。

        Args:
            node_name: 节点名称（updates 模式 chunk 的 data 顶层 key）
            node_data: 节点状态更新 dict

        Returns:
            StreamEvent: kind=update 的事件
        """
        return cls(kind=KIND_UPDATE, node_name=node_name, node_data=node_data)

    @classmethod
    def interrupt(
        cls, requests: List[Dict[str, Any]]
    ) -> "StreamEvent":
        """构造 ``interrupt`` 事件。

        Args:
            requests: 结构化 HITL 中断请求列表（已通过
                ``_extract_interrupt_requests`` 解析为 dict）

        Returns:
            StreamEvent: kind=interrupt 的事件
        """
        return cls(kind=KIND_INTERRUPT, interrupt_requests=requests)

    @classmethod
    def session_end(cls) -> "StreamEvent":
        """构造 ``session_end`` 事件。

        Returns:
            StreamEvent: kind=session_end 的占位事件
        """
        return cls(kind=KIND_SESSION_END)

    @classmethod
    def abort(cls) -> "StreamEvent":
        """构造 ``abort`` 事件。

        Returns:
            StreamEvent: kind=abort 的占位事件
        """
        return cls(kind=KIND_ABORT)
