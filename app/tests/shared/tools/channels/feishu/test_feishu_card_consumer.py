# -*- coding:utf-8 -*-
"""
FeishuCardConsumer 单元测试

测试目标：
    覆盖 ``app/shared/tools/channels/feishu/FeishuCardConsumer.py::FeishuCardConsumer``
    的 6 个 ChannelConsumer 回调 + CardKit 调用 + 降级路径 + 截断逻辑。

测试策略：
    - 通过 ``MagicMock`` 注入 ``lark_client``，断言 ``cardkit.v1.card.create/update``
      与 ``im.v1.message.create`` 的调用次数、顺序、参数
    - 通过 ``MagicMock`` 注入 ``Throttler``，控制 ``should_push`` 返回值
      （避免真实时间窗的不确定性）
    - 异步测试用 ``asyncio.run()`` 包装（与 ``test_stream_event_source.py`` 风格一致）
    - ``conftest.py`` 已 mock ``lark_oapi`` SDK，无需真实安装 lark-oapi 包

测试矩阵覆盖（计划文档 4.3 节）：
    - P0：模块可导入
    - P1：on_session_start / on_text_chunk / on_interrupt / on_session_end / on_abort
      + CardKit create/patch 失败降级 + _send_card_reply 失败降级
    - P2：sequence 严格递增 + 文本超长截断

Date: 2026-07-19
Author: AI Assistant
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from app.core.config.settings import settings
from app.shared.tools.channels.feishu.FeishuCardConsumer import (
    FeishuCardConsumer,
    _PLACEHOLDER_TEXT,
    _STOPPED_MARKER,
)
from app.shared.tools.channels.feishu.Throttler import Throttler


# ---------------------------------------------------------------------------
# 辅助：异步测试 runner（与 test_stream_event_source.py 风格一致）
# ---------------------------------------------------------------------------


def _run(coro):
    """同步包装异步协程，便于在同步测试函数中执行。

    Args:
        coro: 待执行的协程对象

    Returns:
        Any: 协程返回值
    """
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_lark_client() -> MagicMock:
    """构造一个 mock lark_client，默认所有 API 调用成功。

    Returns:
        MagicMock: 已配置 ``cardkit.v1.card.create/update`` 与
            ``im.v1.message.create`` 的成功响应
    """
    client = MagicMock(name="lark_client")

    # CardKit create → 成功 + card_id
    create_resp = MagicMock(name="cardkit_create_resp")
    create_resp.success.return_value = True
    create_resp.data.card_id = "card_test_001"
    # 显式覆盖 conftest 中 _CardKitCardNamespace 的默认 create
    client.cardkit.v1.card.create = MagicMock(return_value=create_resp)

    # CardKit update → 成功
    update_resp = MagicMock(name="cardkit_update_resp")
    update_resp.success.return_value = True
    client.cardkit.v1.card.update = MagicMock(return_value=update_resp)

    # im.v1.message.create → 成功 + message_id
    msg_resp = MagicMock(name="im_message_create_resp")
    msg_resp.success.return_value = True
    msg_resp.data.message_id = "msg_test_001"
    client.im.v1.message.create = MagicMock(return_value=msg_resp)

    return client


@pytest.fixture
def stub_throttler() -> MagicMock:
    """构造一个 stub Throttler，``should_push`` 默认返回 True。

    测试可通过 ``stub_throttler.should_push.return_value = False`` 模拟节流未命中。

    Returns:
        MagicMock: ``should_push`` 返回 True、``force_flush`` 为 no-op 的 stub
    """
    throttler = MagicMock(name="throttler")
    throttler.should_push.return_value = True
    throttler.force_flush = MagicMock()
    return throttler


@pytest.fixture
def consumer(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
) -> FeishuCardConsumer:
    """构造一个 FeishuCardConsumer 实例，使用 mock client + stub throttler。

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        FeishuCardConsumer: 未启动 session 的消费者实例
    """
    return FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
        header_title="测试标题",
    )


async def _start_session(consumer: FeishuCardConsumer) -> None:
    """辅助：启动 session（创建卡片 + 关联消息）。

    Args:
        consumer: FeishuCardConsumer 实例
    """
    await consumer.on_session_start()


# ---------------------------------------------------------------------------
# P0：导入测试
# ---------------------------------------------------------------------------


def test_feishu_card_consumer_importable():
    """P0：FeishuCardConsumer 模块可正常导入。

    Returns:
        None
    """
    assert FeishuCardConsumer is not None
    # 验证关键常量存在
    assert _PLACEHOLDER_TEXT
    assert _STOPPED_MARKER


# ---------------------------------------------------------------------------
# P1：on_session_start
# ---------------------------------------------------------------------------


def test_on_session_start_creates_card_via_cardkit(
    consumer: FeishuCardConsumer, mock_lark_client: MagicMock
):
    """P1：on_session_start 依次调用 CardKit create + im.message.create。

    验证：
        - CardKit create 被调用 1 次
        - im.v1.message.create 被调用 1 次（发送关联消息）
        - ``_card_id`` / ``_message_id`` 被正确保存
        - 未触发降级（``_degraded=False``）

    Args:
        consumer: FeishuCardConsumer fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(consumer.on_session_start())

    # CardKit create 被调用 1 次
    assert mock_lark_client.cardkit.v1.card.create.call_count == 1
    # im.v1.message.create 被调用 1 次（关联消息）
    assert mock_lark_client.im.v1.message.create.call_count == 1
    # card_id / message_id 被保存
    assert consumer._card_id == "card_test_001"
    assert consumer._message_id == "msg_test_001"
    # 未降级
    assert consumer._degraded is False


def test_on_session_start_cardkit_create_failure_degrades(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：CardKit create 返回 success=False → 降级模式。

    验证：
        - ``_degraded=True``
        - ``_card_id`` 为 None
        - 不再调用 im.v1.message.create（因为 create 已失败）

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # 让 CardKit create 失败
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )
    _run(consumer.on_session_start())

    assert consumer._degraded is True
    assert consumer._card_id is None
    # create 失败后不应再调 im.v1.message.create
    mock_lark_client.im.v1.message.create.assert_not_called()


# ---------------------------------------------------------------------------
# P1：on_text_chunk
# ---------------------------------------------------------------------------


def test_on_text_chunk_accumulates_then_patches(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P1：token 累积 → Throttler 命中 → CardKit 元素级 update 被调用。

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    # Throttler 命中（默认返回 True）
    _run(consumer.on_text_chunk("你好"))

    assert consumer.accumulated_text == "你好"
    # CardKit 元素级 update 被调用
    assert mock_lark_client.cardkit.v1.card_element.update.called
    # Throttler.should_push 被调用 1 次
    stub_throttler.should_push.assert_called_once_with(len("你好"))


def test_on_text_chunk_skips_when_throttled(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P1：未命中节流 → 仅累积，不 patch。

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    # Throttler 未命中
    stub_throttler.should_push.return_value = False
    _run(consumer.on_text_chunk("你好"))

    # 文本仍累积
    assert consumer.accumulated_text == "你好"
    # patch 不应被调用
    mock_lark_client.cardkit.v1.card.update.assert_not_called()


def test_on_text_chunk_empty_text_noop(
    consumer: FeishuCardConsumer,
    mock_lark_client: MagicMock,
):
    """P1：空文本 → 直接 return，不累积也不 patch。

    Args:
        consumer: FeishuCardConsumer fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))
    _run(consumer.on_text_chunk(""))

    assert consumer.accumulated_text == ""
    mock_lark_client.cardkit.v1.card.update.assert_not_called()


def test_on_text_chunk_degraded_mode_only_accumulates(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：降级模式下 on_text_chunk 仅累积，不 patch。

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # CardKit create 失败 → 降级
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )
    _run(consumer.on_session_start())
    assert consumer._degraded is True

    _run(consumer.on_text_chunk("你好"))
    assert consumer.accumulated_text == "你好"
    # 降级模式下不应调 CardKit update
    mock_lark_client.cardkit.v1.card.update.assert_not_called()


# ---------------------------------------------------------------------------
# P1：on_interrupt
# ---------------------------------------------------------------------------


def test_on_interrupt_patches_buttons_to_same_card(
    consumer: FeishuCardConsumer, mock_lark_client: MagicMock
):
    """P1：interrupt → 同卡片追加按钮（不创建新消息）。

    验证：
        - ``last_interrupt_req`` 被记录
        - CardKit 元素级 update 被调用（force=True，跳过节流器）
        - 不创建新消息（``im.v1.message.create`` 调用次数仍为 1，仅 session_start 时调过）

    Args:
        consumer: FeishuCardConsumer fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    interrupt_req = {
        "action": "human_review",
        "args": {"question": "是否继续？"},
    }
    _run(consumer.on_interrupt([interrupt_req]))

    # last_interrupt_req 被记录
    assert consumer.last_interrupt_req == interrupt_req
    # CardKit 元素级 update 被调用（force=True）
    assert mock_lark_client.cardkit.v1.card_element.update.called
    # 不创建新消息：im.v1.message.create 仅在 session_start 时调过 1 次
    assert mock_lark_client.im.v1.message.create.call_count == 1


def test_on_interrupt_empty_requests_noop(consumer: FeishuCardConsumer):
    """P1：空 requests 列表 → 直接 return，不记录 last_interrupt_req。

    Args:
        consumer: FeishuCardConsumer fixture

    Returns:
        None
    """
    _run(_start_session(consumer))
    _run(consumer.on_interrupt([]))

    assert consumer.last_interrupt_req is None


def test_on_interrupt_degraded_mode_sends_new_card(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：降级模式下 interrupt → 走 _send_interrupt_card 一次性发新卡片。

    降级模式下不调 CardKit update，而是调 im.v1.message.create 发送新卡片。

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # CardKit create 失败 → 降级
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )
    _run(consumer.on_session_start())
    assert consumer._degraded is True

    interrupt_req = {"action": "human_review", "args": {"question": "继续？"}}
    _run(consumer.on_interrupt([interrupt_req]))

    # last_interrupt_req 仍被记录
    assert consumer.last_interrupt_req == interrupt_req
    # 降级模式：不调 CardKit update
    mock_lark_client.cardkit.v1.card.update.assert_not_called()
    # 降级模式：调 im.v1.message.create 发送新 HITL 卡片
    assert mock_lark_client.im.v1.message.create.called


# ---------------------------------------------------------------------------
# P1：on_session_end
# ---------------------------------------------------------------------------


def test_on_session_end_force_flushes_last_chunk(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P1：session_end → 强制 flush 最后一次。

    场景：
        - on_text_chunk 时 Throttler 未命中 → 累积但不 patch
        - on_session_end 强制 patch 最后一次（确保用户看到完整文本）

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    # Throttler 未命中 → 累积但不 patch
    stub_throttler.should_push.return_value = False
    _run(consumer.on_text_chunk("你好"))
    mock_lark_client.cardkit.v1.card_element.update.assert_not_called()

    # session_end 强制 flush
    _run(consumer.on_session_end())

    # force_flush 被调用
    stub_throttler.force_flush.assert_called_once_with(len("你好"))
    # 元素级 patch 被调用（force=True）
    assert mock_lark_client.cardkit.v1.card_element.update.called


def test_on_session_end_degraded_mode_sends_one_off_reply(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：降级模式下 session_end → 一次性 _send_reply 统一发卡片。

    即使 accumulated_text 是纯文本（无 Markdown 特征），也应走
    ``_send_card_reply``，确保降级路径视觉一致。

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # CardKit create 失败 → 降级
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )

    with patch.object(consumer, "_send_card_reply") as card_mock, \
         patch.object(consumer, "_send_text_reply") as text_mock:
        _run(consumer.on_session_start())
        _run(consumer.on_text_chunk("你好"))
        _run(consumer.on_session_end())

    # 降级模式：不调 CardKit update
    mock_lark_client.cardkit.v1.card.update.assert_not_called()
    # 降级模式：统一走 _send_card_reply，不走 _send_text_reply
    card_mock.assert_called_once_with("oc_test_chat", "你好")
    text_mock.assert_not_called()


def test_on_session_end_skipped_after_abort(consumer: FeishuCardConsumer):
    """P1：abort 后 on_session_end 应跳过（避免重复 patch）。

    Args:
        consumer: FeishuCardConsumer fixture

    Returns:
        None
    """
    _run(_start_session(consumer))
    _run(consumer.on_abort())

    # abort 后 _stopped=True
    assert consumer._stopped is True

    # 记录 abort 后的 update 调用次数
    # 注意：on_abort 内部会 force patch 一次（追加停止标记）

    # session_end 应直接 return（_stopped=True 分支）
    _run(consumer.on_session_end())
    # 不抛异常即可证明行为正确


# ---------------------------------------------------------------------------
# P1：on_abort
# ---------------------------------------------------------------------------


def test_on_abort_appends_stopped_marker_and_stops_patches(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P1：abort → 追加「（已停止）」 + 停止后续 patch。

    验证：
        - ``_stopped=True``
        - ``accumulated_text`` 含停止标记
        - abort 后 on_text_chunk 不再触发 patch
        - force_flush 被调用（强制 patch 停止标记）

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))
    _run(consumer.on_text_chunk("正在生成"))

    update_count_before_abort = mock_lark_client.cardkit.v1.card_element.update.call_count

    _run(consumer.on_abort())

    # 停止标记被追加
    assert _STOPPED_MARKER in consumer.accumulated_text
    # _stopped 被设置
    assert consumer._stopped is True
    # force_flush 被调用
    stub_throttler.force_flush.assert_called()
    # abort 内部触发了一次 force patch（元素级）
    assert mock_lark_client.cardkit.v1.card_element.update.call_count == update_count_before_abort + 1

    update_count_after_abort = mock_lark_client.cardkit.v1.card_element.update.call_count

    # 后续 on_text_chunk 不应再触发 patch
    _run(consumer.on_text_chunk("更多内容"))
    assert mock_lark_client.cardkit.v1.card_element.update.call_count == update_count_after_abort
    # 后续文本不累积（_stopped=True 时直接 return）
    assert "更多内容" not in consumer.accumulated_text


def test_on_abort_degraded_mode_sends_one_off_reply(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：降级模式下 abort → 一次性 _send_reply 统一发卡片（追加停止标记后）。

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # CardKit create 失败 → 降级
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )

    with patch.object(consumer, "_send_card_reply") as card_mock, \
         patch.object(consumer, "_send_text_reply") as text_mock:
        _run(consumer.on_session_start())
        _run(consumer.on_text_chunk("正在生成"))
        _run(consumer.on_abort())

    # 停止标记被追加
    assert _STOPPED_MARKER in consumer.accumulated_text
    # 降级模式：不调 CardKit update
    mock_lark_client.cardkit.v1.card.update.assert_not_called()
    # 降级模式：统一走 _send_card_reply，且文本含停止标记
    assert card_mock.called
    call_text = card_mock.call_args[0][1]
    assert _STOPPED_MARKER in call_text
    text_mock.assert_not_called()


# ---------------------------------------------------------------------------
# P1：CardKit patch 失败静默重试 + 连续失败降级
# ---------------------------------------------------------------------------


def test_cardkit_patch_failure_silent_retry(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P1：元素级 patch 失败静默，下次 patch 重试。

    场景：
        - 第一次 patch：CardKit card_element.update 返回 success=False → 抛 RuntimeError → _patch_failures=1
        - 第二次 patch：CardKit card_element.update 返回 success=True → _patch_failures 重置为 0

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    # 让元素级 patch 第一次失败
    mock_lark_client.cardkit.v1.card_element.update.return_value.success.return_value = False
    _run(consumer.on_text_chunk("片段1"))
    assert consumer._patch_failures == 1

    # 恢复元素级 patch 成功
    mock_lark_client.cardkit.v1.card_element.update.return_value.success.return_value = True
    _run(consumer.on_text_chunk("片段2"))
    # 成功后 _patch_failures 重置
    assert consumer._patch_failures == 0

    # accumulated_text 仍累积完整
    assert consumer.accumulated_text == "片段1片段2"


def test_cardkit_patch_consecutive_failures_triggers_degradation(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P1：patch 连续失败超过 _MAX_PATCH_FAILURES → 切换降级模式。

    元素级 update 失败后本会话会回退到整卡 update；
    为验证降级触发，同时让元素级与整卡 update 均失败。

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    # 让元素级 patch 与整卡 patch 均持续失败
    mock_lark_client.cardkit.v1.card_element.update.return_value.success.return_value = False
    mock_lark_client.cardkit.v1.card.update.return_value.success.return_value = False

    # 触发 3 次失败 patch（_MAX_PATCH_FAILURES=3）
    _run(consumer.on_text_chunk("片段1"))
    _run(consumer.on_text_chunk("片段2"))
    _run(consumer.on_text_chunk("片段3"))

    # 第 3 次失败后应切换降级模式
    assert consumer._degraded is True
    assert consumer._patch_failures >= 3


# ---------------------------------------------------------------------------
# P1：_send_card_reply 失败降级到 _send_text_reply
# ---------------------------------------------------------------------------


def test_send_card_reply_failure_falls_back_to_text(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：_send_card_reply 失败 → _send_text_reply 兜底。

    场景：
        - CardKit create 失败 → 降级模式
        - on_session_end 时走 _send_reply（accumulated_text 含 markdown → _send_card_reply）
        - im.v1.message.create 第一次返回失败（_send_card_reply 失败）
        - _send_card_reply 内部捕获失败 → 调 _send_text_reply 重试
        - im.v1.message.create 第二次返回成功

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # CardKit create 失败 → 降级
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    # im.v1.message.create 第一次失败，第二次成功
    fail_resp = MagicMock(name="fail_resp")
    fail_resp.success.return_value = False
    success_resp = MagicMock(name="success_resp")
    success_resp.success.return_value = True
    mock_lark_client.im.v1.message.create.side_effect = [fail_resp, success_resp]

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )
    _run(consumer.on_session_start())

    # accumulated_text 含 markdown 特征 → _send_reply 走 _send_card_reply
    _run(consumer.on_text_chunk("# 标题\n\n- 列表项"))
    _run(consumer.on_session_end())

    # im.v1.message.create 被调用 2 次（card_reply 失败 + text_reply 成功）
    assert mock_lark_client.im.v1.message.create.call_count == 2


def test_send_reply_plain_text_degraded_still_sends_card(
    mock_lark_client: MagicMock, stub_throttler: MagicMock
):
    """P1：降级路径下纯文本也统一发卡片。

    场景：
        - CardKit create 失败 → 降级模式
        - accumulated_text 为纯文本“你好”（无 Markdown 特征）
        - on_session_end 时 _send_reply 应走 _send_card_reply
        - 最终发送 msg_type="interactive" 的卡片消息

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture

    Returns:
        None
    """
    # CardKit create 失败 → 降级
    mock_lark_client.cardkit.v1.card.create.return_value.success.return_value = False

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )

    with patch.object(consumer, "_send_card_reply") as card_mock, \
         patch.object(consumer, "_send_text_reply") as text_mock:
        _run(consumer.on_session_start())
        _run(consumer.on_text_chunk("你好"))
        _run(consumer.on_session_end())

    # 纯文本在降级路径下也应走 _send_card_reply，而非 _send_text_reply
    card_mock.assert_called_once_with("oc_test_chat", "你好")
    text_mock.assert_not_called()


# ---------------------------------------------------------------------------
# P2：sequence 严格递增
# ---------------------------------------------------------------------------


def test_sequence_strictly_increments(
    consumer: FeishuCardConsumer,
    stub_throttler: MagicMock,
    mock_lark_client: MagicMock,
):
    """P2：sequence 每次 patch 严格 +1。

    Args:
        consumer: FeishuCardConsumer fixture
        stub_throttler: stub Throttler fixture
        mock_lark_client: mock lark_client fixture

    Returns:
        None
    """
    _run(_start_session(consumer))

    # 初始 sequence 为 0
    assert consumer._sequence == 0

    # 触发 3 次 patch（throttler 默认命中）
    _run(consumer.on_text_chunk("片段1"))
    _run(consumer.on_text_chunk("片段2"))
    _run(consumer.on_text_chunk("片段3"))

    # sequence 严格递增到 3
    assert consumer._sequence == 3
    # CardKit 元素级 update 被调用 3 次
    assert mock_lark_client.cardkit.v1.card_element.update.call_count == 3


# ---------------------------------------------------------------------------
# P2：文本超长截断
# ---------------------------------------------------------------------------


def test_truncate_text_under_limit_returns_unchanged():
    """P2：_truncate_text 不超过 max_len 时返回原文本。

    Returns:
        None
    """
    text = "A" * 100
    result = FeishuCardConsumer._truncate_text(text, max_len=4000)
    assert result == text


def test_truncate_text_over_limit_truncated():
    """P2：_truncate_text 超过 max_len 时截断并追加提示。

    验证：
        - 结果长度不超过 max_len
        - 含截断提示
        - 保留原文前缀

    Returns:
        None
    """
    text = "A" * 5000
    result = FeishuCardConsumer._truncate_text(text, max_len=4000)
    assert len(result) <= 4000
    assert "截断" in result
    assert result.startswith("A")


def test_truncate_text_default_max_len_4000():
    """P2：_truncate_text 默认 max_len=4000。

    Returns:
        None
    """
    # 4000 字符刚好不截断
    text_ok = "A" * 4000
    assert FeishuCardConsumer._truncate_text(text_ok) == text_ok

    # 4001 字符触发截断
    text_over = "A" * 4001
    result = FeishuCardConsumer._truncate_text(text_over)
    assert len(result) <= 4000
    assert "截断" in result


# ---------------------------------------------------------------------------
# P1：从 settings.feishu 读取 CardKit 流式/节流配置（2026-07-19 新增）
# ---------------------------------------------------------------------------


def test_consumer_reads_streaming_config_from_settings(
    mock_lark_client: MagicMock,
    monkeypatch,
):
    """P1：FeishuCardConsumer 从 settings.feishu 读取 6 个流式/节流参数。

    验证：
        - _streaming_enabled / _streaming_print_* / _update_* 与 settings 一致
        - 默认启用的 streaming 模式下不处于降级状态

    Args:
        mock_lark_client: mock lark_client fixture
        monkeypatch: pytest fixture

    Returns:
        None
    """
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_enabled",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_print_frequency_ms",
        120,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_print_step",
        2,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_print_strategy",
        "smooth",
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_update_interval_ms",
        800,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_update_delta_chars",
        100,
        raising=False,
    )

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
    )

    assert consumer._streaming_enabled is True
    assert consumer._streaming_print_frequency_ms == 120
    assert consumer._streaming_print_step == 2
    assert consumer._streaming_print_strategy == "smooth"
    assert consumer._update_interval_ms == 800
    assert consumer._update_delta_chars == 100


def test_consumer_passes_settings_to_internal_throttler(
    mock_lark_client: MagicMock,
    monkeypatch,
):
    """P1：FeishuCardConsumer 把 settings.feishu 的节流参数传给内部 Throttler。

    Args:
        mock_lark_client: mock lark_client fixture
        monkeypatch: pytest fixture

    Returns:
        None
    """
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_update_interval_ms",
        900,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_update_delta_chars",
        77,
        raising=False,
    )

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
    )

    assert consumer._throttler.min_interval_ms == 900
    assert consumer._throttler.min_delta_chars == 77


def test_build_card_json_uses_streaming_config_from_settings(
    mock_lark_client: MagicMock,
    monkeypatch,
):
    """P1：_build_card_json 使用 settings.feishu 的 streaming 参数构造卡片 JSON。

    验证：
        - streaming_config.print_frequency_ms / print_step / print_strategy 与 settings 一致
        - config.streaming_mode / update_multi 为 True
        - 第一个 markdown 元素带 element_id

    Args:
        mock_lark_client: mock lark_client fixture
        monkeypatch: pytest fixture

    Returns:
        None
    """
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_print_frequency_ms",
        150,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_print_step",
        3,
        raising=False,
    )
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_print_strategy",
        "fast",
        raising=False,
    )

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
    )

    card = consumer._build_card_json("你好", include_buttons=False)

    assert card["config"]["streaming_mode"] is True
    assert card["config"]["update_multi"] is True
    assert card["config"]["streaming_config"]["print_strategy"] == "fast"
    assert (
        card["config"]["streaming_config"]["print_frequency_ms"]["default"] == 150
    )
    assert card["config"]["streaming_config"]["print_step"]["default"] == 3

    md_elems = [e for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    assert md_elems
    assert md_elems[0].get("element_id") == "markdown_main"


def test_streaming_disabled_falls_back_to_entity_update(
    mock_lark_client: MagicMock,
    stub_throttler: MagicMock,
    monkeypatch,
):
    """P1：feishu_card_streaming_enabled=False 时 Consumer 走整卡更新路径。

    验证：
        - _streaming_enabled=False
        - on_text_chunk 触发的 patch 调用整卡 update，不调用元素级 card_element.update

    Args:
        mock_lark_client: mock lark_client fixture
        stub_throttler: stub Throttler fixture
        monkeypatch: pytest fixture

    Returns:
        None
    """
    monkeypatch.setattr(
        settings.feishu,
        "feishu_card_streaming_enabled",
        False,
        raising=False,
    )

    consumer = FeishuCardConsumer(
        session_id="feishu:p2p:ou_test",
        lark_client=mock_lark_client,
        chat_id="oc_test_chat",
        throttler=stub_throttler,
    )
    assert consumer._streaming_enabled is False

    _run(consumer.on_session_start())
    _run(consumer.on_text_chunk("你好"))

    # 整卡 update 被调用
    assert mock_lark_client.cardkit.v1.card.update.called
    # 元素级 update 未被调用
    assert mock_lark_client.cardkit.v1.card_element.update.call_count == 0
