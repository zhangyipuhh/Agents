#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
StreamEventSource - agent.stream 消费循环 + 统一事件产出

职责：
    - 消费 ``agent.stream(...)`` 在 ``stream_mode=["updates", "custom", "messages"]``
      组合模式下产出的异构 chunk
    - 把 chunk 抽象为 ``StreamEvent`` 序列（与渠道解耦），通过 ``events()``
      异步生成器对外输出
    - 复刻 ``app/routers/_stream_helper.py::generate_stream_response`` 的核心
      循环逻辑（HITL 中断多模式检测 / abort_event 监听 / tools 节点完成检测 /
      异常隔离），但**不含 SSE 推送**——SSE 由前端专用 ``_stream_helper`` 负责

设计原则：
    - **不修改** ``_stream_helper.py``（前端 SSE 行为冻结，硬约束）
    - **不感知**任何输出渠道（飞书 / 钉钉 / 企微平等接入）
    - **不向上抛异常**：``agent.stream`` 内部异常仅记日志，以 ``session_end``
      事件收尾（与 ``_stream_helper`` 行为对齐）

事件流时序：
    1. ``session_start``（首次 yield，Consumer 可创建占位资源）
    2. ``text`` / ``update``（多次 yield，按 chunk 到达顺序）
    3. ``interrupt``（HITL 触发时 yield + return，等用户回答后续跑）
       *或* ``abort``（abort_event.is_set() 时 yield + return）
    4. ``session_end``（流自然结束 yield）

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, Optional

# 注意：本模块刻意不 import ``langchain_core.messages.ToolMessage``，因为
# 测试环境 conftest 会把该符号替换为 ``Mock()``，导致 ``isinstance`` 抛
# ``TypeError``。改用 ``_is_tool_message(message_chunk)`` 做类名 duck-typing。
from app.core.agent.stream_event import StreamEvent
from app.core.format.stream import stream_format_context

logger = logging.getLogger(__name__)


class StreamEventSource:
    """消费 ``agent.stream`` 输出，产出 ``StreamEvent`` 序列。

    从 ``_stream_helper`` 抽取核心循环（不含 SSE 推送），所有渠道共用。
    与 ``_stream_helper`` 同构的逻辑：
        - ``stream_mode = ["updates", "custom", "messages"]`` 组合
        - interrupt 多模式检测（dict / tuple / node 嵌套）
        - abort_event 监听（用户主动 abort）
        - tools 节点完成检测（延迟中断语义，飞书侧转换为 abort）
        - 异常隔离（不向外抛）

    Attributes:
        _agent: Agent 实例（需实现 ``stream`` 方法）
        _input_state: 输入状态（AgentState 或 ``Command(resume=...)``）
        _context: AgentContext 实例
        _config: 传给 ``agent.stream`` 的 config dict
            （含 ``configurable.thread_id`` / ``recursion_limit`` 等）
        _abort_event: 可选的 asyncio.Event；外部 ``set()`` 时流以 abort 事件收尾
    """

    def __init__(
        self,
        agent: Any,
        input_state: Any,
        context: Any,
        config: Dict[str, Any],
        abort_event: Optional[asyncio.Event] = None,
    ) -> None:
        """初始化事件源。

        Args:
            agent: Agent 实例（需实现 ``stream`` 方法，签名为
                ``stream(input_state, context, config, stream_mode) -> AsyncGenerator``）
            input_state: 输入状态（AgentState 或 ``Command(resume=...)``）
            context: AgentContext 实例
            config: 传给 ``agent.stream`` 的 config dict
            abort_event: 可选的 abort 信号；外部 ``set()`` 时流以 abort 事件收尾。
                ``None`` 表示不监听 abort（仅靠 stream 自然结束）
        """
        self._agent = agent
        self._input_state = input_state
        self._context = context
        self._config = config
        self._abort_event = abort_event

    async def events(self) -> AsyncIterator[StreamEvent]:
        """异步产出 ``StreamEvent`` 序列。

        Consumer 负责解释事件并推送到对应渠道。事件类型见模块 docstring。

        Yields:
            StreamEvent: 按 ``session_start`` → (``text`` | ``update``)* →
                (``interrupt`` | ``abort`` | ``session_end``) 顺序产出
        """
        # 1. 首次 yield session_start
        yield StreamEvent.session_start()

        try:
            async for chunk in self._agent.stream(
                self._input_state,
                context=self._context,
                config=self._config,
                stream_mode=["updates", "custom", "messages"],
            ):
                # 2. abort_event 检测（用户主动 abort）
                if self._abort_event is not None and self._abort_event.is_set():
                    logger.info(
                        "[StreamEventSource] abort_event 已触发，停止消费 agent.stream"
                    )
                    yield StreamEvent.abort()
                    return

                # 3. HITL 中断检测（多模式兼容，参考 _stream_helper.py:152-176）
                interrupt_data = self._extract_interrupt_data(chunk)
                if interrupt_data is not None:
                    structured_requests = _extract_interrupt_requests(interrupt_data)
                    yield StreamEvent.interrupt(structured_requests)
                    return  # 中断后结束流，等用户回答后续跑

                # 4. 处理组合模式 (mode, data) 元组
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk

                    if mode == "updates":
                        # 4.1 节点状态更新
                        # 取首个 node_name 作为代表（与 _stream_helper 的 langgraph_node 取法一致）
                        node_name = (
                            next(iter(data.keys()), "")
                            if isinstance(data, dict)
                            else ""
                        )
                        yield StreamEvent.update(
                            node_name=node_name or None,
                            node_data=data if isinstance(data, dict) else None,
                        )

                        # 4.2 tools 节点完成检测（飞书侧 abort 语义）
                        # 当 "tools" 节点刚完成且 data 含 ToolMessage → 当前工具/子智能体已完成
                        # 飞书侧若已 abort，可在此处真正中断；非 abort 场景仍正常 yield update
                        if (
                            self._abort_event is not None
                            and self._abort_event.is_set()
                            and isinstance(data, dict)
                            and self._contains_tool_completion(data)
                        ):
                            logger.info(
                                "[StreamEventSource] abort 期间 tools 节点完成，停止消费"
                            )
                            yield StreamEvent.abort()
                            return

                    elif mode == "messages":
                        # 4.3 LLM token 文本片段
                        # data 形如 (message_chunk, metadata)
                        if isinstance(data, tuple) and len(data) == 2:
                            message_chunk, metadata = data
                            # 跳过 ToolMessage（与 _stream_helper:258 一致）
                            # 使用类名 duck-typing 而非 isinstance(message_chunk, ToolMessage)，
                            # 因为测试环境 conftest 会把 langchain_core.messages.ToolMessage
                            # 替换为 Mock()，isinstance 在 Mock 上会抛 TypeError。
                            if _is_tool_message(message_chunk):
                                continue
                            content = stream_format_context.format_message(
                                message_chunk, metadata
                            )
                            if content is None:
                                continue
                            yield StreamEvent.text_chunk(content)
                        # else: data 格式不符合预期，丢弃（不抛错）

                    # mode == "custom"：当前 stream_event_source 不向 Consumer 暴露
                    # custom 事件（飞书侧不消费 subagent thread_id / tool_progress），
                    # 保持与 _stream_helper 一致的"忽略"行为，但避免污染事件流。
                    # 未来如需扩展可在此处 yield StreamEvent.custom(data)。

            # 5. 流自然结束
            yield StreamEvent.session_end()

        except Exception as e:  # noqa: BLE001
            # 异常隔离：与 _stream_helper:284-289 行为对齐
            # 不向上抛，仅记日志并以 session_end 收尾（避免 Consumer 协程被取消）
            logger.exception(
                "[StreamEventSource] agent.stream 调用异常（已隔离，以 session_end 收尾）: %s",
                e,
            )
            yield StreamEvent.session_end()

    # ------------------------------------------------------------------ #
    # 内部辅助：HITL 中断检测                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_interrupt_data(chunk: Any) -> Optional[Any]:
        """从 ``agent.stream`` 的 chunk 中提取 ``__interrupt__`` 数据。

        兼容多种 stream 模式（与 ``_stream_helper.py:155-169`` 同构）：
            1) chunk 直接是 dict 且含 ``__interrupt__``
            2) chunk 是 ``(mode, data)`` 元组，``mode == "updates"`` 且
               ``data`` 直接含 ``__interrupt__``
            3) chunk 是 ``(mode, data)`` 元组，``mode == "updates"`` 且
               ``data`` 的某节点值含 ``__interrupt__``

        Args:
            chunk: ``agent.stream`` 产出的单个 chunk

        Returns:
            interrupt_data: 原始 interrupt 数据（含 Interrupt 对象或 dict），
            未命中返回 ``None``
        """
        # 情况 1：直接 dict 含 __interrupt__
        if isinstance(chunk, dict) and "__interrupt__" in chunk:
            return chunk["__interrupt__"]

        # 情况 2 / 3：组合模式 (mode, data)
        if isinstance(chunk, tuple) and len(chunk) == 2:
            mode, data = chunk
            if mode == "updates" and isinstance(data, dict):
                # 情况 2：data 直接含 __interrupt__
                if "__interrupt__" in data:
                    return data["__interrupt__"]
                # 情况 3：data 的某节点值含 __interrupt__
                for _node_name, node_data in data.items():
                    if (
                        isinstance(node_data, dict)
                        and "__interrupt__" in node_data
                    ):
                        return node_data["__interrupt__"]
        return None

    @staticmethod
    def _contains_tool_completion(node_data: Dict[str, Any]) -> bool:
        """判断 updates 模式的 ``node_data`` 是否含 ``tools`` 节点完成信号。

        与 ``_stream_helper.py:191-205`` 同构：当 ``"tools"`` 节点刚完成时，
        ``node_data`` 形如 ``{"tools": {"messages": [ToolMessage, ...]}}``。
        依赖 LangGraph ToolNode 的"全或无"语义（``asyncio.gather`` 等所有
        ``tool_calls`` 完成才 yield），所以检测到 ``tools`` 节点完成时，
        所有并行的 ``tool_calls`` 都已执行完，ToolMessage 全部写入 state。

        Args:
            node_data: updates 模式 chunk 的 data dict

        Returns:
            bool: ``True`` 表示 ``tools`` 节点完成且含 ToolMessage
        """
        if not isinstance(node_data, dict):
            return False
        tools_update = node_data.get("tools")
        if not isinstance(tools_update, dict):
            return False
        messages_in_update = tools_update.get("messages", [])
        if not isinstance(messages_in_update, list):
            return False
        # 检查是否包含 ToolMessage（兼容 Mock）
        for m in messages_in_update:
            if m is None:
                continue
            if m.__class__.__name__ in (
                "ToolMessage",
                "MockToolMessage",
                "_MockToolMessage",
            ):
                return True
        return False


def _extract_interrupt_requests(interrupt_data: Any) -> list:
    """从 interrupt 数据中提取结构化的请求列表。

    与 ``app/routers/_stream_helper.py::_extract_interrupt_requests`` 同构，
    保证飞书侧与前端 SSE 拿到的 interrupt 结构一致。

    LangGraph 的 ``interrupt()`` 返回的 ``Interrupt`` 对象包含 ``value`` 属性，
    本函数把 ``Interrupt`` 对象解析为 Consumer 可直接使用的结构化字典。

    Args:
        interrupt_data (list): interrupt 数据列表，元素可能是
            ``Interrupt`` 对象（有 ``.value`` 属性）或 dict

    Returns:
        list: 结构化的请求列表，每个元素为 dict
    """
    requests = []
    items = interrupt_data if isinstance(interrupt_data, list) else [interrupt_data]
    for item in items:
        if hasattr(item, "value"):
            # LangGraph Interrupt 对象
            value = item.value
            if isinstance(value, list):
                for req in value:
                    if isinstance(req, dict):
                        requests.append(req)
                    else:
                        requests.append({"data": str(req)})
            elif isinstance(value, dict):
                requests.append(value)
            else:
                requests.append({"data": str(value)})
        elif isinstance(item, dict):
            requests.append(item)
        else:
            requests.append({"data": str(item)})
    return requests


def _is_tool_message(message_chunk: Any) -> bool:
    """判断 ``message_chunk`` 是否为 ToolMessage（duck-typing，兼容 Mock 环境）。

    生产环境直接用 ``isinstance(message_chunk, ToolMessage)`` 即可，但测试
    环境 conftest 把 ``langchain_core.messages.ToolMessage`` 替换为 ``Mock()``
    （非 type），导致 ``isinstance`` 抛 ``TypeError``。本函数改用类名匹配，
    与 ``_stream_helper.py:198`` 的"兼容 Mock"模式一致。

    Args:
        message_chunk: messages 模式 chunk 内的消息对象

    Returns:
        bool: ``True`` 表示该 chunk 是 ToolMessage，调用方应跳过
    """
    if message_chunk is None:
        return False
    cls_name = message_chunk.__class__.__name__
    return cls_name in ("ToolMessage", "MockToolMessage", "_MockToolMessage")
