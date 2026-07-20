#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuCardConsumer - 飞书渠道 CardKit 同卡片流式消费者

职责：
    - 实现 ``ChannelConsumer`` 6 个回调，把 ``StreamEvent`` 翻译为 CardKit patch
    - ``on_session_start``：创建 CardKit 卡片实体 + 发送关联消息（占位「🤖 AI 正在思考…」）
    - ``on_text_chunk``：累积 token → 节流判断 → patch 同一张卡片
    - ``on_interrupt``：HITL 中断 → 同卡片 elements 末尾追加按钮（上下文连贯）
    - ``on_session_end``：强制 flush 最后一次（节流器 ``force_flush``）
    - ``on_abort``：卡片末尾追加「（已停止）」 + 停止后续 patch

降级路径（鲁棒性优先）：
    - CardKit create 失败 → ``_degraded=True`` → ``on_text_chunk`` / ``on_interrupt``
      改走一次性 ``_send_card_reply`` / ``_send_interrupt_card``
    - CardKit patch 失败 → 静默记日志，下次 patch 重试；连续多次失败可降级
    - ``_send_card_reply`` 失败 → 降级 ``_send_text_reply``

设计依据：
    - 飞书官方约束：CardKit update 单卡片 10 QPS / 秒（global 50 QPS）；
      时间窗 600 ms 节流（≈1.6 QPS）远低于限频
    - 卡片 30 KB 上限 → 沿用 ``MarkdownToCardConverter._MAX_CARD_TEXT_LEN=4000`` 字符截断
    - sequence 严格递增（飞书要求）

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from app.core.config.settings import settings
from app.shared.tools.channels.base import ChannelConsumer
from app.shared.tools.channels.feishu.Throttler import Throttler
from app.shared.tools.skills.feishu.InterruptToCardConverter import (
    InterruptToCardConverter,
)
from app.shared.tools.skills.feishu.MarkdownToCardConverter import (
    MarkdownToCardConverter,
)

logger = logging.getLogger(__name__)


# CardKit 流式卡片默认占位文案
_PLACEHOLDER_TEXT = "🤖 AI 正在思考…"
# abort 后追加的停止标记
_STOPPED_MARKER = "\n\n_（已停止）_"
# CardKit patch 连续失败上限，超过后降级为一次性发送
_MAX_PATCH_FAILURES = 3
# 元素级流式更新使用的主文本元素 ID（与 MarkdownToCardConverter 默认值一致）
_STREAMING_ELEMENT_ID = "markdown_main"


class FeishuCardConsumer(ChannelConsumer):
    """飞书渠道 Consumer — CardKit 同卡片流式 + HITL 同卡片按钮。

    Attributes:
        session_id: 会话 ID（LangGraph thread_id，形如 ``feishu:p2p:ou_xxx``）
        accumulated_text: 本会话累积的 LLM token 文本（基类维护）
        last_interrupt_req: 最后一次 HITL 中断请求（基类维护）
        _lark_client: 已配置好的 lark.Client 实例
        _chat_id: 飞书 chat_id（patch 目标消息所属会话）
        _throttler: 时间窗 + 字符增量双条件节流器
        _markdown_converter: Markdown → 卡片 JSON 转换器（复用现有 converter）
        _header_title: 卡片头部标题
        _card_id: CardKit 卡片实体 ID（on_session_start 创建后填充）
        _message_id: 关联消息 ID（on_session_start 发送后填充）
        _sequence: patch 序号（严格递增）
        _lock: 单卡片 asyncio.Lock，串行 patch 避免并发竞态
        _degraded: CardKit 失败 → 降级一次性发送
        _interrupt_buttons: 累积的 HITL 按钮 elements（追加到卡片末尾）
        _stopped: abort 后置 True，停止后续 patch
        _patch_failures: patch 连续失败计数
    """

    def __init__(
        self,
        *,
        session_id: str,
        lark_client: lark.Client,
        chat_id: str,
        throttler: Optional[Throttler] = None,
        markdown_converter: Optional[MarkdownToCardConverter] = None,
        header_title: str = "🤖 AI 智能体回复",
        **ctx: Any,
    ) -> None:
        """初始化飞书 CardKit 消费者。

        Args:
            session_id: 会话 ID（LangGraph thread_id）
            lark_client: 已配置好的 lark.Client 实例
            chat_id: 飞书 chat_id（patch 目标消息所属会话）
            throttler: 节流器实例；``None`` 时内部创建默认 Throttler()
            markdown_converter: Markdown 转换器；``None`` 时使用类静态方法
            header_title: 卡片头部标题
            **ctx: 兼容 ChannelRegistry.resolve 透传的额外上下文（忽略）
        """
        super().__init__(session_id=session_id)
        self._lark_client = lark_client
        self._chat_id = chat_id
        self._markdown_converter = markdown_converter
        self._header_title = header_title

        # 从统一配置读取流式/节流参数
        feishu_cfg = settings.feishu
        self._streaming_enabled = bool(feishu_cfg.feishu_card_streaming_enabled)
        self._streaming_print_frequency_ms = int(
            feishu_cfg.feishu_card_streaming_print_frequency_ms
        )
        self._streaming_print_step = int(feishu_cfg.feishu_card_streaming_print_step)
        self._streaming_print_strategy = str(
            feishu_cfg.feishu_card_streaming_print_strategy
        )
        self._update_interval_ms = int(feishu_cfg.feishu_card_update_interval_ms)
        self._update_delta_chars = int(feishu_cfg.feishu_card_update_delta_chars)

        self._throttler = (
            throttler
            if throttler is not None
            else Throttler(
                min_interval_ms=self._update_interval_ms,
                min_delta_chars=self._update_delta_chars,
            )
        )

        self._card_id: Optional[str] = None
        self._message_id: Optional[str] = None
        self._sequence: int = 0
        self._lock = asyncio.Lock()
        self._degraded: bool = False
        self._interrupt_buttons: List[Dict[str, Any]] = []
        self._stopped: bool = False
        self._patch_failures: int = 0
        # 元素级更新失败后是否回退到整卡更新
        self._entity_fallback: bool = False

    # ------------------------------------------------------------------ #
    # ChannelConsumer 接口实现                                            #
    # ------------------------------------------------------------------ #

    async def on_session_start(self) -> None:
        """流开始：创建 CardKit 卡片实体 + 发送关联消息（占位文案）。

        失败 → ``self._degraded = True``，后续 ``on_text_chunk`` 改为一次性发送。
        """
        try:
            card_id = await self._create_cardkit_entity(_PLACEHOLDER_TEXT)
            if not card_id:
                logger.warning(
                    "[FeishuCardConsumer] CardKit create 返回空 card_id，"
                    "降级为一次性发送模式 session_id=%s",
                    self.session_id,
                )
                self._degraded = True
                return
            self._card_id = card_id

            message_id = await self._send_cardkit_message(card_id)
            if not message_id:
                logger.warning(
                    "[FeishuCardConsumer] CardKit 关联消息发送失败，"
                    "降级为一次性发送模式 session_id=%s",
                    self.session_id,
                )
                self._degraded = True
                return
            self._message_id = message_id

            logger.info(
                "[FeishuCardConsumer] 卡片创建成功 session_id=%s card_id=%s message_id=%s",
                self.session_id, self._card_id, self._message_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] on_session_start 异常，降级为一次性发送: %s",
                e,
            )
            self._degraded = True

    async def on_text_chunk(self, text: str) -> None:
        """累积 token → 节流判断 → patch。

        - ``self._degraded=True`` → 全部累积，不在 patch（最后由
          ``on_session_end`` 一次性 ``_send_card_reply``）
        - ``self._stopped=True`` → 直接 return（abort 后丢弃后续 token）
        - 否则累积到 ``self.accumulated_text``，节流器命中时 patch 同一张卡片
        """
        if not text:
            return
        if self._stopped:
            return
        # 累积文本（无论是否 patch，都要保持完整）
        self.accumulated_text += text

        if self._degraded:
            # 降级模式：仅累积，不 patch（on_session_end 时一次性发）
            return

        # 节流判断
        if not self._throttler.should_push(len(self.accumulated_text)):
            return

        await self._patch_card_safe()

    async def on_node_update(
        self, node_name: str, node_data: Dict[str, Any]
    ) -> None:
        """节点状态更新回调（飞书侧目前不消费，仅 debug 日志）。

        未来可在此处更新进度指示器（如"正在调用工具 X"）。

        Args:
            node_name: 节点名称
            node_data: 节点状态更新 dict
        """
        logger.debug(
            "[FeishuCardConsumer] node_update session_id=%s node=%s",
            self.session_id, node_name,
        )

    async def on_interrupt(self, requests: List[Dict[str, Any]]) -> None:
        """HITL 中断：把 interrupt requests 转按钮，追加到当前卡片 elements 末尾。

        - 若已 ``_degraded`` → 走 ``_send_interrupt_card`` 一次性发按钮卡片（保留兼容）
        - 否则把按钮 elements 追加到 ``self._interrupt_buttons``，
          立即 patch 同一张卡片（让用户看到按钮就地出现）
        - 记录首个 ``action`` 类型的请求到 ``self.last_interrupt_req``（供
          ``FeishuWebSocketService._call_agent`` 回取）

        Args:
            requests: 结构化 HITL 中断请求列表
        """
        if not requests:
            return
        # 取首个 action 类型的请求作为 last_interrupt_req
        for req in requests:
            if isinstance(req, dict) and req.get("action"):
                self.last_interrupt_req = req
                break

        if self._degraded:
            # 降级模式：一次性发新卡片（不复用 CardKit 卡片）
            if self.last_interrupt_req:
                await self._send_interrupt_card(
                    self._chat_id, self.last_interrupt_req, self.session_id
                )
            return

        # 同卡片追加按钮：构造按钮 elements 并 patch
        if self.last_interrupt_req:
            buttons_elements = self._build_interrupt_elements(
                self.last_interrupt_req
            )
            self._interrupt_buttons.extend(buttons_elements)
            # 立即 patch 让按钮出现（不经过节流器，HITL 优先级高）
            await self._patch_card_safe(force=True)

    async def on_session_end(self) -> None:
        """流自然结束：强制 flush 最后一次（节流器 force_flush）。

        - ``_degraded=True`` → 走一次性 ``_send_card_reply``
        - ``_stopped=True`` → 已在 ``on_abort`` patch 过停止标记，跳过
        - 否则强制 patch 最后一次（确保用户看到完整文本），并关闭 streaming 模式
        """
        if self._stopped:
            # abort 已处理过最终 patch，不重复
            return
        if self._degraded:
            # 降级模式：一次性发送完整回复
            if self.accumulated_text:
                await self._send_reply(self._chat_id, self.accumulated_text)
            return
        # 正常模式：强制 flush 最后一次 patch
        self._throttler.force_flush(len(self.accumulated_text))
        if self.accumulated_text:
            await self._patch_card_safe(force=True)
        # 流式更新结束后必须显式关闭 streaming 模式
        await self._close_streaming_mode()

    async def on_abort(self) -> None:
        """abort：卡片末尾追加「（已停止）」 → 设置 ``_stopped=True`` → flush。

        - ``_degraded=True`` → 走一次性 ``_send_reply``（追加停止标记后）
        - 否则 patch 同卡片末尾的停止标记，并设置 ``_stopped=True`` 阻止后续 patch
        """
        self._stopped = True
        self.accumulated_text += _STOPPED_MARKER

        if self._degraded:
            if self.accumulated_text:
                await self._send_reply(self._chat_id, self.accumulated_text)
            return
        # 强制 patch 让停止标记立即出现
        self._throttler.force_flush(len(self.accumulated_text))
        await self._patch_card_safe(force=True)
        # abort 后同样需要关闭 streaming 模式
        await self._close_streaming_mode()

    # ------------------------------------------------------------------ #
    # CardKit 调用                                                       #
    # ------------------------------------------------------------------ #

    async def _create_cardkit_entity(self, placeholder: str) -> Optional[str]:
        """创建 CardKit 卡片实体，返回 ``card_id``。

        Args:
            placeholder: 占位文案（如「🤖 AI 正在思考…」）

        Returns:
            str: ``card_id``；失败返回 ``None``
        """
        card_payload = self._build_card_json(placeholder, include_buttons=False)
        try:
            from lark_oapi.api.cardkit.v1 import (
                CreateCardRequest,
                CreateCardRequestBody,
            )
        except ImportError as e:
            logger.warning(
                "[FeishuCardConsumer] lark_oapi.api.cardkit.v1 不可用: %s", e
            )
            return None

        try:
            req = (
                CreateCardRequest.builder()
                .request_body(
                    CreateCardRequestBody.builder()
                    .type("card_json")
                    .data(json.dumps(card_payload, ensure_ascii=False))
                    .build()
                )
                .build()
            )
            resp = self._lark_client.cardkit.v1.card.create(req)
            code = getattr(resp, "code", None)
            msg = getattr(resp, "msg", None)
            if resp.success() and resp.data and getattr(resp.data, "card_id", None):
                card_id = resp.data.card_id
                logger.info(
                    "[FeishuCardConsumer] CardKit create 成功 session_id=%s card_id=%s code=%s msg=%s",
                    self.session_id, card_id, code, msg,
                )
                return card_id
            logger.error(
                "[FeishuCardConsumer] CardKit create 失败 session_id=%s code=%s msg=%s",
                self.session_id, code, msg,
            )
            return None
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] CardKit create 异常 session_id=%s: %s",
                self.session_id, e,
            )
            return None

    async def _send_cardkit_message(self, card_id: str) -> Optional[str]:
        """发送关联卡片消息，返回 ``message_id``。

        Args:
            card_id: CardKit 卡片实体 ID

        Returns:
            str: ``message_id``；失败返回 ``None``
        """
        try:
            content = json.dumps(
                {
                    "type": "template",
                    "data": {
                        "template_id": card_id,
                        "template_version_name": "1.0.0",
                    },
                },
                ensure_ascii=False,
            )
            req = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(self._chat_id)
                    .msg_type("interactive")
                    .content(content)
                    .uuid(str(uuid.uuid4()))
                    .build()
                )
                .build()
            )
            resp = self._lark_client.im.v1.message.create(req)
            code = getattr(resp, "code", None)
            msg = getattr(resp, "msg", None)
            if resp.success() and resp.data and getattr(resp.data, "message_id", None):
                message_id = resp.data.message_id
                logger.info(
                    "[FeishuCardConsumer] CardKit 关联消息发送成功 session_id=%s card_id=%s message_id=%s code=%s msg=%s",
                    self.session_id, card_id, message_id, code, msg,
                )
                return message_id
            logger.error(
                "[FeishuCardConsumer] CardKit 关联消息发送失败 session_id=%s card_id=%s code=%s msg=%s",
                self.session_id, card_id, code, msg,
            )
            return None
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] CardKit 关联消息发送异常 session_id=%s: %s",
                self.session_id, e,
            )
            return None

    async def _patch_card_safe(self, *, force: bool = False) -> None:
        """线程安全地 patch 当前卡片。

        使用 ``self._lock`` 串行化 patch 调用，避免并发竞态。
        优先使用 CardKit 元素级流式更新（更轻量、更可靠）；失败时回退到整卡更新；
        连续失败超过 ``_MAX_PATCH_FAILURES`` → 切换降级模式。

        Args:
            force: ``True`` 表示强制 patch（跳过节流器，用于 HITL / abort / end）
        """
        if not self._card_id:
            return
        async with self._lock:
            try:
                if self._streaming_enabled and not self._entity_fallback:
                    await self._patch_cardkit_text()
                else:
                    await self._patch_cardkit_entity()
                self._patch_failures = 0  # 成功则重置计数
                self._entity_fallback = False  # 成功后重置 fallback 标记
            except Exception as e:  # noqa: BLE001
                self._patch_failures += 1
                logger.warning(
                    "[FeishuCardConsumer] patch 失败 %s 次 session_id=%s: %s",
                    self._patch_failures, self.session_id, e,
                )
                if self._streaming_enabled and not self._entity_fallback:
                    # 元素级更新失败：本次先回退到整卡更新，下次重试
                    logger.info(
                        "[FeishuCardConsumer] 元素级更新失败，回退到整卡更新 session_id=%s",
                        self.session_id,
                    )
                    self._entity_fallback = True
                elif self._patch_failures >= _MAX_PATCH_FAILURES:
                    logger.warning(
                        "[FeishuCardConsumer] patch 连续失败 %s 次，切换降级模式",
                        self._patch_failures,
                    )
                    self._degraded = True

    async def _patch_cardkit_text(self) -> None:
        """调用 CardKit 元素级更新 API 更新主文本元素。

        比整卡更新更轻量，专为流式文本设计。失败时抛出异常，由
        ``_patch_card_safe`` 捕获并决定是否回退到整卡更新。

        Raises:
            Exception: patch 失败时抛出
        """
        if not self._card_id:
            return
        self._sequence += 1
        try:
            from lark_oapi.api.cardkit.v1 import (
                UpdateCardElementRequest,
                UpdateCardElementRequestBody,
            )
        except ImportError as e:
            raise RuntimeError(
                f"lark_oapi.api.cardkit.v1 不可用: {e}"
            ) from e

        content = self.accumulated_text or _PLACEHOLDER_TEXT
        element = json.dumps(
            {
                "element_id": _STREAMING_ELEMENT_ID,
                "tag": "markdown",
                "content": content,
            },
            ensure_ascii=False,
        )
        req = (
            UpdateCardElementRequest.builder()
            .card_id(self._card_id)
            .element_id(_STREAMING_ELEMENT_ID)
            .request_body(
                UpdateCardElementRequestBody.builder()
                .uuid(str(uuid.uuid4()))
                .sequence(self._sequence)
                .element(element)
                .build()
            )
            .build()
        )
        resp = self._lark_client.cardkit.v1.card_element.update(req)
        code = getattr(resp, "code", None)
        msg = getattr(resp, "msg", None)
        if resp.success():
            logger.info(
                "[FeishuCardConsumer] CardKit 元素级 update 成功 session_id=%s card_id=%s sequence=%s code=%s msg=%s content_len=%s",
                self.session_id, self._card_id, self._sequence, code, msg, len(content),
            )
            return
        raise RuntimeError(
            f"CardKit 元素级 update 失败 code={code} msg={msg}"
        )

    async def _patch_cardkit_entity(self) -> None:
        """调用 CardKit update API patch 当前卡片（整卡更新，fallback）。

        Raises:
            Exception: patch 失败时抛出（由 ``_patch_card_safe`` 捕获）
        """
        if not self._card_id:
            return
        # 构造 patch payload（包含累积文本 + 累积按钮）
        card_payload = self._build_card_json(
            self.accumulated_text or _PLACEHOLDER_TEXT,
            include_buttons=True,
        )
        # sequence 严格递增
        self._sequence += 1
        try:
            from lark_oapi.api.cardkit.v1 import (
                Card,
                UpdateCardRequest,
                UpdateCardRequestBody,
            )
        except ImportError as e:
            raise RuntimeError(
                f"lark_oapi.api.cardkit.v1 不可用: {e}"
            ) from e

        req = (
            UpdateCardRequest.builder()
            .card_id(self._card_id)
            .request_body(
                UpdateCardRequestBody.builder()
                .card(
                    Card.builder()
                    .type("card_json")
                    .data(json.dumps(card_payload, ensure_ascii=False))
                    .build()
                )
                .sequence(self._sequence)
                .build()
            )
            .build()
        )
        resp = self._lark_client.cardkit.v1.card.update(req)
        code = getattr(resp, "code", None)
        msg = getattr(resp, "msg", None)
        if resp.success():
            logger.info(
                "[FeishuCardConsumer] CardKit 整卡 update 成功 session_id=%s card_id=%s sequence=%s code=%s msg=%s content_len=%s",
                self.session_id, self._card_id, self._sequence, code, msg,
                len(self.accumulated_text or _PLACEHOLDER_TEXT),
            )
            return
        raise RuntimeError(
            f"CardKit 整卡 update 失败 code={code} msg={msg}"
        )

    # ------------------------------------------------------------------ #
    # 卡片 JSON 构造                                                     #
    # ------------------------------------------------------------------ #

    def _build_card_json(
        self, text: str, include_buttons: bool = False
    ) -> Dict[str, Any]:
        """构造飞书卡片 JSON（schema 2.0，含 streaming 配置）。

        复用 ``MarkdownToCardConverter.to_streaming_card_json`` 生成 body elements，
        若 ``include_buttons=True`` 则把 ``self._interrupt_buttons`` 追加到末尾。

        Args:
            text: 卡片正文文本（markdown 或纯文本）
            include_buttons: 是否追加 HITL 按钮 elements

        Returns:
            dict: 飞书卡片 JSON（schema 2.0，含 streaming_mode 配置）
        """
        # 复用现有 converter 生成基础 elements（带 element_id 与 streaming_config）
        if self._markdown_converter is not None:
            card = self._markdown_converter.to_streaming_card_json(
                text,
                header_title=self._header_title,
                element_id=_STREAMING_ELEMENT_ID,
                print_frequency_ms=self._streaming_print_frequency_ms,
                print_step=self._streaming_print_step,
                print_strategy=self._streaming_print_strategy,
            )
        else:
            card = MarkdownToCardConverter.to_streaming_card_json(
                text,
                header_title=self._header_title,
                element_id=_STREAMING_ELEMENT_ID,
                print_frequency_ms=self._streaming_print_frequency_ms,
                print_step=self._streaming_print_step,
                print_strategy=self._streaming_print_strategy,
            )

        if include_buttons and self._interrupt_buttons:
            body = card.setdefault("body", {})
            elements = body.setdefault("elements", [])
            # 在文本与按钮之间加分隔线
            if elements and elements[-1].get("tag") != "hr":
                elements.append({"tag": "hr"})
            elements.extend(self._interrupt_buttons)
        return card

    async def _close_streaming_mode(self) -> None:
        """关闭 CardKit 卡片的 streaming 模式。

        飞书要求基于 JSON 开启 streaming 的卡片在流式更新结束后调用
        Update Card Configuration API 将 ``streaming_mode`` 置为 ``false``。
        失败仅记录日志，不影响主流程。
        """
        if not self._card_id:
            return
        self._sequence += 1
        try:
            from lark_oapi.api.cardkit.v1 import (
                SettingsCardRequest,
                SettingsCardRequestBody,
            )
        except ImportError as e:
            logger.warning(
                "[FeishuCardConsumer] 关闭 streaming 模式失败（SDK 不可用）session_id=%s: %s",
                self.session_id, e,
            )
            return

        settings_payload = json.dumps(
            {"config": {"streaming_mode": False, "update_multi": True}},
            ensure_ascii=False,
        )
        try:
            req = (
                SettingsCardRequest.builder()
                .card_id(self._card_id)
                .request_body(
                    SettingsCardRequestBody.builder()
                    .uuid(str(uuid.uuid4()))
                    .sequence(self._sequence)
                    .settings(settings_payload)
                    .build()
                )
                .build()
            )
            resp = self._lark_client.cardkit.v1.card.settings(req)
            code = getattr(resp, "code", None)
            msg = getattr(resp, "msg", None)
            if resp.success():
                logger.info(
                    "[FeishuCardConsumer] streaming 模式关闭成功 session_id=%s card_id=%s sequence=%s code=%s msg=%s",
                    self.session_id, self._card_id, self._sequence, code, msg,
                )
            else:
                logger.warning(
                    "[FeishuCardConsumer] streaming 模式关闭失败 session_id=%s card_id=%s code=%s msg=%s",
                    self.session_id, self._card_id, code, msg,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] streaming 模式关闭异常 session_id=%s: %s",
                self.session_id, e,
            )

    def _build_interrupt_elements(
        self, interrupt_request: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """从 interrupt 请求构造按钮 elements。

        复用 ``InterruptToCardConverter.to_interactive_card`` 生成完整卡片 JSON，
        然后从中提取 ``action`` elements（按钮组）作为追加元素。

        Args:
            interrupt_request: 结构化 interrupt 请求 dict

        Returns:
            list[dict]: 按钮 elements 列表（可追加到 body.elements 末尾）
        """
        try:
            full_card = InterruptToCardConverter.to_interactive_card(
                interrupt_request, self.session_id, self._chat_id
            )
            body = full_card.get("body", {}) if isinstance(full_card, dict) else {}
            elements = body.get("elements", []) if isinstance(body, dict) else []
            # 只取 action 类型的 elements（按钮组），跳过 markdown 题目块（已在主卡片文本中）
            return [
                e for e in elements
                if isinstance(e, dict) and e.get("tag") == "action"
            ]
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] 构造 HITL 按钮失败: %s", e
            )
            return []

    # ------------------------------------------------------------------ #
    # 降级路径：一次性发送（CardKit 失败时兜底）                            #
    # ------------------------------------------------------------------ #

    async def _send_reply(self, chat_id: str, text: str) -> None:
        """降级路径：统一把回复包装成卡片一次性发送。

        与 ``FeishuWebSocketService._send_reply`` 同构。
        不再根据文本是否含 Markdown 特征分支，避免不同内容导致视觉不一致。
        ``_send_card_reply`` 内部会在卡片 API 失败时再降级为纯文本，保证可达性。

        Args:
            chat_id: 飞书 chat_id
            text: 回复文本
        """
        if not text:
            return
        logger.info(
            "[FeishuCardConsumer] 降级路径统一发卡片 session_id=%s text_len=%s",
            self.session_id, len(text),
        )
        await self._send_card_reply(chat_id, text)

    async def _send_text_reply(self, chat_id: str, text: str) -> None:
        """降级路径：通过飞书 Open API 发送纯文本回复。

        Args:
            chat_id: 飞书 chat_id
            text: 回复文本
        """
        truncated = self._truncate_text(text)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": truncated}, ensure_ascii=False))
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        try:
            resp = self._lark_client.im.v1.message.create(request)
            code = getattr(resp, "code", None)
            msg = getattr(resp, "msg", None)
            if resp.success():
                logger.info(
                    "[FeishuCardConsumer] 降级文本回复成功 chat_id=%s code=%s msg=%s",
                    chat_id, code, msg,
                )
            else:
                logger.error(
                    "[FeishuCardConsumer] 降级文本回复失败 chat_id=%s code=%s msg=%s",
                    chat_id, code, msg,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] 降级文本回复异常 chat_id=%s: %s", chat_id, e
            )

    async def _send_card_reply(self, chat_id: str, text: str) -> None:
        """降级路径：通过飞书 Open API 发送交互式卡片（Markdown → 卡片 JSON）。

        失败时再降级到 ``_send_text_reply`` 保证可达性。

        Args:
            chat_id: 飞书 chat_id
            text: 含 Markdown 的回复文本
        """
        card = MarkdownToCardConverter.to_card_json(text)
        content_str = json.dumps(card, ensure_ascii=False)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(content_str)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        try:
            resp = self._lark_client.im.v1.message.create(request)
            code = getattr(resp, "code", None)
            msg = getattr(resp, "msg", None)
            if resp.success():
                logger.info(
                    "[FeishuCardConsumer] 降级卡片回复成功 chat_id=%s code=%s msg=%s",
                    chat_id, code, msg,
                )
            else:
                logger.error(
                    "[FeishuCardConsumer] 降级卡片回复失败 chat_id=%s code=%s msg=%s，"
                    "再降级文本。卡片JSON=%s",
                    chat_id, code, msg, content_str[:500],
                )
                await self._send_text_reply(chat_id, text)
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] 降级卡片回复异常 chat_id=%s，再降级文本: %s",
                chat_id, e,
            )
            await self._send_text_reply(chat_id, text)

    async def _send_interrupt_card(
        self,
        chat_id: str,
        interrupt_request: Dict[str, Any],
        session_id: str,
    ) -> None:
        """降级路径：发送 HITL 带按钮交互式卡片（一次性新卡片）。

        与 ``FeishuWebSocketService._send_interrupt_card`` 同构。

        Args:
            chat_id: 飞书 chat_id
            interrupt_request: 结构化 interrupt 请求
            session_id: LangGraph thread_id（嵌入按钮 value）
        """
        card = InterruptToCardConverter.to_interactive_card(
            interrupt_request, session_id, chat_id
        )
        content_str = json.dumps(card, ensure_ascii=False)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(content_str)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        try:
            resp = self._lark_client.im.v1.message.create(request)
            code = getattr(resp, "code", None)
            msg = getattr(resp, "msg", None)
            if resp.success():
                logger.info(
                    "[FeishuCardConsumer] 降级 HITL 卡片发送成功 chat_id=%s session_id=%s code=%s msg=%s",
                    chat_id, session_id, code, msg,
                )
            else:
                logger.error(
                    "[FeishuCardConsumer] 降级 HITL 卡片发送失败 chat_id=%s session_id=%s code=%s msg=%s",
                    chat_id, session_id, code, msg,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "[FeishuCardConsumer] 降级 HITL 卡片发送异常 chat_id=%s session_id=%s: %s",
                chat_id, session_id, e,
            )

    # ------------------------------------------------------------------ #
    # 辅助                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _truncate_text(text: str, max_len: int = 4000) -> str:
        """截断超长文本。

        Args:
            text: 原始文本
            max_len: 最大字符数（默认 4000）

        Returns:
            str: 截断后的文本（不超过 max_len 字符 + 截断提示）
        """
        hint = "\n...(内容过长已截断)"
        if len(text) <= max_len:
            return text
        keep = max_len - len(hint)
        return text[:keep] + hint

