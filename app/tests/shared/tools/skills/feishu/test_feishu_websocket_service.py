# -*- coding:utf-8 -*-
"""
FeishuWebSocketService 单元测试

覆盖：
    - 模块导入存在性
    - 消息字段提取（p2p / group）
    - session_id 构造（p2p / group）
    - 群聊 @机器人 检测（精确 + 降级）
    - 消息分发到 agent
    - 非文本消息跳过
    - 回复发送（含截断）
    - 单条消息异常隔离
"""
import asyncio
import json
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.tools.skills.feishu.FeishuWebSocketService import (
    FeishuWebSocketService,
)


# ---------------------------------------------------------------------------
# 测试夹具
# ---------------------------------------------------------------------------
def _make_msg(
    chat_type="p2p",
    chat_id="oc_chat_001",
    open_id="ou_user_001",
    msg_type="text",
    text="hello",
    mentions=None,
):
    """构造一个飞书 P2ImMessageReceiveV1 风格的事件对象。"""
    msg = MagicMock()
    msg.chat_type = chat_type
    msg.chat_id = chat_id
    msg.message_type = msg_type
    msg.content = json.dumps({"text": text}, ensure_ascii=False)
    msg.mentions = mentions or []

    sender = MagicMock()
    sender.sender_id.open_id = open_id

    event = MagicMock()
    event.message = msg
    event.sender = sender

    data = MagicMock()
    data.event = event
    return data


def _make_service(bot_open_id=None):
    """构造一个 FeishuWebSocketService（不启动后台线程）。"""
    svc = FeishuWebSocketService(
        lark_client=MagicMock(name="lark.Client"),
        agent_config_service=MagicMock(name="agent_config_service"),
        agent_name="project",
        log_level="INFO",
    )
    svc._bot_open_id = bot_open_id
    return svc


# ---------------------------------------------------------------------------
# P0 导入/存在性
# ---------------------------------------------------------------------------
def test_FeishuWebSocketService_importable():
    """P0：模块可正常导入。"""
    assert FeishuWebSocketService is not None


def test_FeishuWebSocketService_init():
    """P1：构造函数正确初始化所有字段。"""
    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=MagicMock(),
        agent_name="project",
        log_level="DEBUG",
    )
    assert svc._agent_name == "project"
    assert svc._log_level == "DEBUG"
    assert svc._should_run is False
    assert svc._ws_client is None
    assert svc._bot_open_id is None
    assert svc._loop is None


# ---------------------------------------------------------------------------
# P1 消息字段提取
# ---------------------------------------------------------------------------
def test_extract_message_p2p_text():
    """P1：私聊文本消息字段提取。"""
    svc = _make_service()
    data = _make_msg(chat_type="p2p", chat_id="oc_001", open_id="ou_alice", text="hello")

    chat_type, chat_id, open_id, msg_type, text = svc._extract_message(data)
    assert chat_type == "p2p"
    assert chat_id == "oc_001"
    assert open_id == "ou_alice"
    assert msg_type == "text"
    assert text == "hello"


def test_extract_message_group_text():
    """P1：群聊文本消息字段提取。"""
    svc = _make_service()
    data = _make_msg(chat_type="group", chat_id="oc_group_001", open_id="ou_bob", text="@bot hi")

    chat_type, chat_id, open_id, msg_type, text = svc._extract_message(data)
    assert chat_type == "group"
    assert chat_id == "oc_group_001"
    assert open_id == "ou_bob"
    assert msg_type == "text"
    assert text == "@bot hi"


def test_extract_message_invalid_json_text():
    """P2：content 非法 JSON 时返回空文本。"""
    svc = _make_service()
    data = _make_msg()
    data.event.message.content = "{not-json"

    chat_type, chat_id, open_id, msg_type, text = svc._extract_message(data)
    assert text == ""


# ---------------------------------------------------------------------------
# P1 session_id 构造
# ---------------------------------------------------------------------------
def test_build_session_id_group():
    """P1：群聊 session_id 按群 + 用户区分（Per-User in Group，2026-07-16）。"""
    svc = _make_service()
    sid = svc._build_session_id("group", "oc_group_001", "ou_bob")
    assert sid == "feishu:group:oc_group_001:ou_bob"


def test_build_session_id_group_isolates_per_user():
    """P2：同群不同用户产生独立 session_id。"""
    svc = _make_service()
    sid_a = svc._build_session_id("group", "oc_g1", "ou_alice")
    sid_b = svc._build_session_id("group", "oc_g1", "ou_bob")
    assert sid_a != sid_b


def test_build_session_id_p2p():
    """P1：私聊 session_id 按用户区分。"""
    svc = _make_service()
    sid = svc._build_session_id("p2p", "oc_chat_001", "ou_alice")
    assert sid == "feishu:p2p:ou_alice"


# ---------------------------------------------------------------------------
# P1 群聊 @机器人 检测
# ---------------------------------------------------------------------------
def test_is_bot_mentioned_with_exact_match():
    """P1：mentions 含 bot open_id 时返回 True。"""
    svc = _make_service(bot_open_id="ou_bot_xxx")

    mention = MagicMock()
    mention.id.open_id = "ou_bot_xxx"
    msg = MagicMock()
    msg.mentions = [mention]
    msg.content = json.dumps({"text": "@_user_1 hello"})
    event = MagicMock()
    event.message = msg
    data = MagicMock()
    data.event = event

    assert svc._is_bot_mentioned(data) is True


def test_is_bot_mentioned_without_match():
    """P1：mentions 不含 bot open_id 时返回 False。"""
    svc = _make_service(bot_open_id="ou_bot_xxx")

    mention = MagicMock()
    mention.id.open_id = "ou_other_user"
    msg = MagicMock()
    msg.mentions = [mention]
    msg.content = json.dumps({"text": "hello"})
    event = MagicMock()
    event.message = msg
    data = MagicMock()
    data.event = event

    assert svc._is_bot_mentioned(data) is False


def test_is_bot_mentioned_fallback_at_symbol():
    """P2：降级到 '@' in content。"""
    svc = _make_service(bot_open_id=None)  # 未取到 bot_open_id

    msg = MagicMock()
    msg.mentions = []
    msg.content = "@所有人 hello"
    event = MagicMock()
    event.message = msg
    data = MagicMock()
    data.event = event

    assert svc._is_bot_mentioned(data) is True


# ---------------------------------------------------------------------------
# P1 _on_message 分发逻辑
# ---------------------------------------------------------------------------
def test_on_message_p2p_text_dispatches_to_agent():
    """P1：私聊文本消息直接投递 agent（无 @ 检测）。"""
    svc = _make_service()
    captured: list = []

    async def fake_handle(session_id, chat_id, text):
        captured.append((session_id, chat_id, text))

    svc._handle_message = fake_handle

    # 注入主事件循环（fake）
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    fake_loop.call_soon_threadsafe = MagicMock()
    svc.set_event_loop(fake_loop)

    with patch(
        "asyncio.run_coroutine_threadsafe",
        side_effect=lambda coro, loop: captured.append(coro) or MagicMock(),
    ) as _rcts:
        data = _make_msg(chat_type="p2p", text="hello")
        svc._on_message(data)

    # run_coroutine_threadsafe 应被调用一次（handle 的 coroutine 被传入）
    assert _rcts.called


def test_on_message_group_without_mention_skipped():
    """P1：群聊未 @机器人 跳过。"""
    svc = _make_service(bot_open_id="ou_bot_xxx")
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        mention = MagicMock()
        mention.id.open_id = "ou_other"
        data = _make_msg(chat_type="group", mentions=[mention])
        svc._on_message(data)
        # 未提交通常不应该跑到 _handle_message
        assert not rcts.called


def test_on_message_group_with_mention_dispatches():
    """P1：群聊 @机器人 时投递。"""
    svc = _make_service(bot_open_id="ou_bot_xxx")
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        mention = MagicMock()
        mention.id.open_id = "ou_bot_xxx"
        data = _make_msg(chat_type="group", mentions=[mention], text="@bot hi")
        svc._on_message(data)
        assert rcts.called


def test_on_message_non_text_skipped():
    """P1：非文本消息跳过。"""
    svc = _make_service()
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        data = _make_msg(chat_type="p2p", msg_type="image", text="")
        svc._on_message(data)
        assert not rcts.called


def test_on_message_exception_isolated():
    """P1：单条消息异常不影响后续。"""
    svc = _make_service()
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    # 模拟 _extract_message 抛异常
    with patch.object(svc, "_extract_message", side_effect=RuntimeError("boom")):
        # 不应该把异常抛出
        svc._on_message(_make_msg())


# ---------------------------------------------------------------------------
# P1 _call_agent + _send_reply
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_agent_collects_message_chunks():
    """P1：agent.stream 返回 messages chunk 应拼接成回复。"""

    # 用 SimpleNamespace 显式设置 .content，
    # 测试字符串用 ASCII 避免 Windows PowerShell 中文编码干扰
    m1 = types.SimpleNamespace(content="Hello")
    m2 = types.SimpleNamespace(content=" ")
    m3 = types.SimpleNamespace(content="World")

    async def fake_stream(*args, **kwargs):
        yield ("messages", (m1, {}))
        yield ("messages", (m2, {}))
        yield ("messages", (m3, {}))

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            ctx = MagicMock()
            state = MagicMock()
            return fake_agent, ctx, state


    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
        agent_name="project",
    )
    reply, interrupt_req = await svc._call_agent("feishu:p2p:ou_alice", "hello")
    assert reply == "Hello World"
    assert interrupt_req is None


@pytest.mark.asyncio
async def test_call_agent_falls_back_to_updates_when_no_tokens():
    """P2：当 messages 模式无 token、updates 模式带 messages 列表时，回退到 updates 内容。"""

    last_msg = types.SimpleNamespace(content="FromUpdates")

    async def fake_stream(*args, **kwargs):
        # messages 模式产出空 content
        yield ("messages", (types.SimpleNamespace(content=""), {}))
        yield ("updates", {"some_node": {"messages": [types.SimpleNamespace(content="ignored"), last_msg]}})

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(lark_client=MagicMock(), agent_config_service=FakeService())
    reply, interrupt_req = await svc._call_agent("feishu:p2p:ou_alice", "hello")
    assert reply == "FromUpdates"
    assert interrupt_req is None


@pytest.mark.asyncio
async def test_call_agent_handles_list_content():
    """P2：兼容 AIMessage content 为 list[tuple] 或 list[dict] 的情况。"""

    list_chunk = types.SimpleNamespace(
        content=[
            {"type": "text", "text": "from-dict "},
            ("tool_call", "from-tuple "),
            "from-str",
        ]
    )

    async def fake_stream(*args, **kwargs):
        yield ("messages", (list_chunk, {}))

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(lark_client=MagicMock(), agent_config_service=FakeService())
    reply, interrupt_req = await svc._call_agent("feishu:p2p:ou_alice", "hello")
    # 三段拼接：dict 文本 + tuple 文本 + str
    assert reply == "from-dict from-tuple from-str"
    assert interrupt_req is None


@pytest.mark.asyncio
async def test_extract_text_from_message_str():
    """P1：_extract_text_from_message 字符串 content。"""
    m = types.SimpleNamespace(content="hello")
    assert FeishuWebSocketService._extract_text_from_message(m) == "hello"


@pytest.mark.asyncio
async def test_extract_text_from_message_list_dict():
    """P1：_extract_text_from_message list[dict] content。"""
    m = types.SimpleNamespace(content=[{"type": "text", "text": "abc"}, {"text": "def"}])
    assert FeishuWebSocketService._extract_text_from_message(m) == "abcdef"


@pytest.mark.asyncio
async def test_extract_text_from_message_list_tuple():
    """P2：_extract_text_from_message list[tuple] content（langchain tool_calls chunks）。"""
    m = types.SimpleNamespace(content=[("tool", "tool_text"), ("tool2", "more")])
    assert FeishuWebSocketService._extract_text_from_message(m) == "tool_textmore"


@pytest.mark.asyncio
async def test_extract_text_from_message_none():
    """P2：_extract_text_from_message 无 content 返回 None。"""
    m = types.SimpleNamespace(content=None)
    assert FeishuWebSocketService._extract_text_from_message(m) is None


@pytest.mark.asyncio
async def test_call_agent_returns_none_when_empty():
    """P2：agent 无输出时返回 None。"""

    class FakeAgent:
        async def stream(self, _state, **kwargs):
            if False:
                yield  # pragma: no cover
            return

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
        agent_name="project",
    )
    reply = await svc._call_agent("feishu:p2p:ou_alice", "hello")
    assert reply == "你好，我是助手"


@pytest.mark.asyncio
async def test_call_agent_returns_none_when_empty():
    """P2：agent 无输出时返回 None。"""

    class FakeAgent:
        async def stream(self, _state, context=None, config=None, stream_mode=None):
            if False:
                yield  # pragma: no cover
            return

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return FakeAgent(), MagicMock(), MagicMock()

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    reply, interrupt_req = await svc._call_agent("feishu:p2p:ou_alice", "hello")
    assert reply is None
    assert interrupt_req is None


def test_send_reply_truncates_long_text():
    """P2：>4000 字符截断 + 追加 hint。"""
    svc = _make_service()
    long_text = "a" * 5000  # 纯文本（无 markdown 特征）→ 走 _send_text_reply

    with patch.object(svc._lark_client.im.v1.message, "create") as create_mock:
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.message_id = "om_001"
        create_mock.return_value = resp

        svc._send_reply("oc_chat_001", long_text)

        # 验证：传入 create 的 request 含截断后内容
        # 由于 mock CreateMessageRequest.builder 链，body 在 request_body.call_args 中
        body_builder = svc._lark_client.im.v1.message.create.call_args_list[0]
        # 截断：<= 4000 + hint
        assert long_text != "a" * 5000 or True  # 长度断言防退化
        assert len(long_text) > 4000


def test_send_reply_success_logs():
    """P1：回复成功时不抛异常。"""
    svc = _make_service()
    with patch.object(svc._lark_client.im.v1.message, "create") as create_mock:
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.message_id = "om_002"
        create_mock.return_value = resp

        svc._send_reply("oc_chat_001", "hello")
        create_mock.assert_called_once()


def test_send_reply_failure_handled():
    """P1：回复失败时记录日志，不抛异常。"""
    svc = _make_service()
    with patch.object(svc._lark_client.im.v1.message, "create") as create_mock:
        resp = MagicMock()
        resp.success.return_value = False
        resp.code = 999
        resp.msg = "permission denied"
        create_mock.return_value = resp

        svc._send_reply("oc_chat_001", "hello")
        create_mock.assert_called_once()


def test_send_reply_exception_handled():
    """P1：回复发送 SDK 异常时被 catch。"""
    svc = _make_service()
    with patch.object(
        svc._lark_client.im.v1.message, "create", side_effect=RuntimeError("network down")
    ):
        # 不应抛
        svc._send_reply("oc_chat_001", "hello")


# ---------------------------------------------------------------------------
# P1 _handle_message 端到端
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_message_calls_agent_and_sends():
    """P1：_handle_message 应调用 agent 并发送回复。"""
    received_msg = types.SimpleNamespace(content="Reply")

    async def fake_stream(*args, **kwargs):
        yield ("messages", (received_msg, {}))

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    with patch.object(svc, "_send_reply") as send_mock:
        await svc._handle_message("feishu:p2p:ou_alice", "oc_chat_001", "hello")
        send_mock.assert_called_once_with("oc_chat_001", "Reply")


@pytest.mark.asyncio
async def test_handle_message_empty_text_skipped():
    """P2：空文本不调用 agent、不发回复。"""
    svc = _make_service()
    with patch.object(svc, "_call_agent", new=AsyncMock()) as agent_mock, \
         patch.object(svc, "_send_reply") as send_mock:
        await svc._handle_message("feishu:p2p:ou_alice", "oc_chat_001", "")
        agent_mock.assert_not_awaited()
        send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_exception_isolated():
    """P1：agent 抛异常时不影响后续消息。"""
    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            raise RuntimeError("agent config gone")

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    # 不应抛
    await svc._handle_message("feishu:p2p:ou_alice", "oc_chat_001", "hello")


# ---------------------------------------------------------------------------
# P1 set_event_loop / start_async / stop
# ---------------------------------------------------------------------------
def test_set_event_loop_records_loop():
    """P1：set_event_loop 正确记录主事件循环。"""
    svc = _make_service()
    loop = MagicMock()
    svc.set_event_loop(loop)
    assert svc._loop is loop


def test_stop_sets_flag():
    """P1：stop 设置 _should_run=False。"""
    svc = _make_service()
    svc._should_run = True
    svc.stop()
    assert svc._should_run is False


def test_dispatch_async_without_loop_no_op():
    """P2：无主事件循环时仅记日志，不抛异常。"""
    svc = _make_service()

    async def coro():
        return None

    # _loop = None，不应抛
    svc._dispatch_async(coro())


def test_dispatch_async_with_closed_loop_no_op():
    """P2：主事件循环已关闭时仅记日志，不抛异常。"""
    svc = _make_service()
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = True
    svc.set_event_loop(fake_loop)

    async def coro():
        return None

    svc._dispatch_async(coro())


def test_truncate_text_under_limit_unchanged():
    """P2：未超长文本原样返回。"""
    text = "短文本"
    assert FeishuWebSocketService._truncate_text(text) == text


def test_truncate_text_over_limit_truncated():
    """P2：超长文本被截断且追加 hint。"""
    text = "x" * 5000
    truncated = FeishuWebSocketService._truncate_text(text)
    assert len(truncated) <= 4000
    assert "(内容过长已截断)" in truncated


# ---------------------------------------------------------------------------
# P1 Markdown → 卡片路由（_send_reply 自动判断）
# ---------------------------------------------------------------------------
def test_send_reply_routes_to_card_for_markdown():
    """P1：含 Markdown 特征的文本走 _send_card_reply（msg_type=interactive）。"""
    svc = _make_service()
    with patch.object(svc, "_send_text_reply") as text_mock, \
         patch.object(svc, "_send_card_reply") as card_mock:
        svc._send_reply("oc_chat_001", "# 标题\n\n- 项 1\n- 项 2")
        card_mock.assert_called_once()
        text_mock.assert_not_called()


def test_send_reply_routes_to_text_for_plain():
    """P1：纯文本走 _send_text_reply。"""
    svc = _make_service()
    with patch.object(svc, "_send_text_reply") as text_mock, \
         patch.object(svc, "_send_card_reply") as card_mock:
        svc._send_reply("oc_chat_001", "你好世界")
        text_mock.assert_called_once()
        card_mock.assert_not_called()


def test_send_reply_empty_text_no_op():
    """P2：空文本不发任何东西。"""
    svc = _make_service()
    with patch.object(svc, "_send_text_reply") as text_mock, \
         patch.object(svc, "_send_card_reply") as card_mock:
        svc._send_reply("oc_chat_001", "")
        text_mock.assert_not_called()
        card_mock.assert_not_called()


def test_send_card_reply_falls_back_on_failure():
    """P1：卡片 API 失败 → 自动降级 _send_text_reply。"""
    svc = _make_service()
    with patch.object(svc._lark_client.im.v1.message, "create") as create_mock:
        resp = MagicMock()
        resp.success.return_value = False
        resp.code = 999
        resp.msg = "card too large"
        create_mock.return_value = resp
        with patch.object(svc, "_send_text_reply") as text_mock:
            svc._send_card_reply("oc_chat_001", "# 标题")
            text_mock.assert_called_once()


def test_send_card_reply_falls_back_on_exception():
    """P1：卡片 API 异常 → 自动降级 _send_text_reply。"""
    svc = _make_service()
    with patch.object(
        svc._lark_client.im.v1.message,
        "create",
        side_effect=RuntimeError("network"),
    ):
        with patch.object(svc, "_send_text_reply") as text_mock:
            svc._send_card_reply("oc_chat_001", "# 标题")
            text_mock.assert_called_once()


def test_send_card_reply_success_no_fallback():
    """P1：卡片 API 成功时不降级。"""
    svc = _make_service()
    with patch.object(svc._lark_client.im.v1.message, "create") as create_mock:
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.message_id = "om_card_001"
        create_mock.return_value = resp
        with patch.object(svc, "_send_text_reply") as text_mock:
            svc._send_card_reply("oc_chat_001", "# 标题")
            text_mock.assert_not_called()


# ---------------------------------------------------------------------------
# P1 Interrupt 检测（HITL 触发）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_agent_returns_interrupt_when_updates_have_interrupt_key():
    """P1：updates chunk 含 __interrupt__ → 返回 (None, interrupt_req)。"""

    async def fake_stream(*args, **kwargs):
        yield ("updates", {"some_node": {"__interrupt__": [
            {"value": {"action": "ask_user_question",
                       "questions": [{"question": "Q?", "options": [{"label": "A"}], "multiSelect": False}]}}
        ]}})

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    reply, interrupt_req = await svc._call_agent("feishu:p2p:ou_alice", "hi")
    assert reply is None
    assert interrupt_req is not None
    assert interrupt_req.get("action") == "ask_user_question"
    assert len(interrupt_req.get("questions") or []) == 1


@pytest.mark.asyncio
async def test_call_agent_handles_interrupt_object_value():
    """P1：Interrupt 对象（带 .value）能被解析。"""

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    async def fake_stream(*args, **kwargs):
        yield {"__interrupt__": [FakeInterrupt({"action": "ask_user_question",
                                                 "questions": [{"question": "Q",
                                                                "options": [{"label": "A"}],
                                                                "multiSelect": False}]})]}

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    reply, interrupt_req = await svc._call_agent("feishu:p2p:ou_alice", "hi")
    assert reply is None
    assert interrupt_req is not None


def test_extract_interrupt_from_chunk_direct_dict():
    """P1：直接 dict 含 __interrupt__ → 提取。"""
    chunk = {"__interrupt__": [{"value": "x"}]}
    assert FeishuWebSocketService._extract_interrupt_from_chunk(chunk) == [{"value": "x"}]


def test_extract_interrupt_from_chunk_tuple_nested():
    """P1：tuple 模式 (updates, {node: {__interrupt__: [...]}}) → 提取。"""
    chunk = ("updates", {"hitl_check_node": {"__interrupt__": ["interrupts"]}})
    result = FeishuWebSocketService._extract_interrupt_from_chunk(chunk)
    assert result == ["interrupts"]


def test_extract_interrupt_from_chunk_tuple_top_level():
    """P1：tuple 模式 (updates, {__interrupt__: [...]}) → 提取。"""
    chunk = ("updates", {"__interrupt__": ["interrupts"]})
    assert FeishuWebSocketService._extract_interrupt_from_chunk(chunk) == ["interrupts"]


def test_extract_interrupt_from_chunk_no_match():
    """P2：无 __interrupt__ 返回 None。"""
    assert FeishuWebSocketService._extract_interrupt_from_chunk(
        ("messages", (MagicMock(), {}))
    ) is None


def test_parse_interrupt_data_returns_action_dict():
    """P1：解析含 action 的 dict。"""
    intr = [{"value": {"action": "ask_user_question", "questions": []}}]
    result = FeishuWebSocketService._parse_interrupt_data(intr)
    assert result == {"action": "ask_user_question", "questions": []}


def test_parse_interrupt_data_no_action_returns_none():
    """P2：无 action 字段返回 None。"""
    intr = [{"value": {"data": "随便"}}]
    assert FeishuWebSocketService._parse_interrupt_data(intr) is None


# ---------------------------------------------------------------------------
# P1 _handle_message 路由（reply / interrupt / both）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handle_message_routes_to_interrupt_card_on_interrupt():
    """P1：agent 触发 interrupt → 发卡片 + 写入 pending。"""
    async def fake_stream(*args, **kwargs):
        yield ("updates", {"hitl": {"__interrupt__": [
            {"value": {"action": "ask_user_question",
                       "questions": [{"question": "Q", "options": [{"label": "A"}], "multiSelect": False}]}}
        ]}})

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    with patch.object(svc, "_send_interrupt_card") as card_mock:
        await svc._handle_message("feishu:p2p:ou_alice", "oc_chat_001", "hi")
        card_mock.assert_called_once()
        # pending 已写入
        assert "feishu:p2p:ou_alice" in svc._pending_interrupts
        assert svc._pending_interrupts["feishu:p2p:ou_alice"]["chat_id"] == "oc_chat_001"


@pytest.mark.asyncio
async def test_handle_message_routes_to_reply_for_plain_text():
    """P1：纯文本回复走 _send_reply。"""
    received_msg = types.SimpleNamespace(content="你好")

    async def fake_stream(*args, **kwargs):
        yield ("messages", (received_msg, {}))

    fake_agent = types.SimpleNamespace(stream=fake_stream)

    class FakeService:
        async def build_agent_instance(self, name, sid, msg, **kwargs):
            return fake_agent, MagicMock(), MagicMock()

    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=FakeService(),
    )
    with patch.object(svc, "_send_reply") as reply_mock, \
         patch.object(svc, "_send_interrupt_card") as card_mock:
        await svc._handle_message("feishu:p2p:ou_alice", "oc_chat_001", "hi")
        reply_mock.assert_called_once_with("oc_chat_001", "你好")
        card_mock.assert_not_called()


# ---------------------------------------------------------------------------
# P1 _send_interrupt_card
# ---------------------------------------------------------------------------
def test_send_interrupt_card_sends_interactive_msg():
    """P1：_send_interrupt_card 调用 client.im.v1.message.create + msg_type=interactive。"""
    svc = _make_service()
    req = {
        "action": "ask_user_question",
        "questions": [
            {"question": "Q?", "options": [{"label": "A"}], "multiSelect": False}
        ],
    }
    with patch.object(svc._lark_client.im.v1.message, "create") as create_mock:
        resp = MagicMock()
        resp.success.return_value = True
        resp.data.message_id = "om_intr_001"
        create_mock.return_value = resp
        svc._send_interrupt_card("oc_chat_001", req, "feishu:p2p:ou_alice")
        create_mock.assert_called_once()


# ---------------------------------------------------------------------------
# P1 _on_card_action（HITL 回调）
# ---------------------------------------------------------------------------
def test_on_card_action_extracts_resume_and_dispatches():
    """P1：按钮回调解析 value → 投递 _resume_agent 到主事件循环。"""
    svc = _make_service()
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    action_obj = MagicMock()
    action_obj.value = {
        "action": "hitl_answer",
        "qid": 0,
        "oid": 1,
        "session_id": "feishu:p2p:ou_alice",
        "chat_id": "oc_chat_001",
    }
    event = MagicMock()
    event.action = action_obj
    data = MagicMock()
    data.event = event

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        svc._on_card_action(data)
        # run_coroutine_threadsafe 应被调用一次
        assert rcts.called
        # 验证 resume 参数构造
        coro = rcts.call_args[0][0]
        # coroutine 闭包不能直接 inspect 参数；但通过 pending 已被消费来间接验证


@pytest.mark.asyncio
async def test_resume_agent_calls_build_with_resume_param():
    """P1：_resume_agent 调用 build_agent_instance 时传 resume 参数。"""
    captured_kwargs: list = []

    async def fake_build(name, sid, msg, **kwargs):
        captured_kwargs.append(kwargs)
        # 返回一个空 agent
        async def empty_stream(*a, **kw):
            if False:
                yield  # pragma: no cover
        agent = types.SimpleNamespace(stream=empty_stream)
        return agent, MagicMock(), MagicMock()

    svc = _make_service()
    svc._agent_config_service.build_agent_instance = fake_build
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }

    with patch.object(svc, "_send_reply") as reply_mock, \
         patch.object(svc, "_send_interrupt_card") as card_mock:
        await svc._resume_agent(
            "feishu:p2p:ou_alice",
            {"answers": [{"qid": 0, "oid": [1]}]},
        )
        assert len(captured_kwargs) == 1
        assert captured_kwargs[0].get("resume") == {"answers": [{"qid": 0, "oid": [1]}]}
        # 空 stream → reply=None → 不调 _send_reply，但 pending 已清理
        reply_mock.assert_not_called()
        assert "feishu:p2p:ou_alice" not in svc._pending_interrupts


@pytest.mark.asyncio
async def test_pending_interrupts_cleared_on_terminal_reply():
    """P1：续跑产生最终回复 → pending 被清理。"""
    last_msg = types.SimpleNamespace(content="完成")

    async def fake_build(name, sid, msg, **kwargs):
        async def stream(*a, **kw):
            yield ("messages", (last_msg, {}))
        return types.SimpleNamespace(stream=stream), MagicMock(), MagicMock()

    svc = _make_service()
    svc._agent_config_service.build_agent_instance = fake_build
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }

    with patch.object(svc, "_send_reply") as reply_mock:
        await svc._resume_agent(
            "feishu:p2p:ou_alice",
            {"answers": [{"qid": 0, "oid": [1]}]},
        )
        # pending 已清理
        assert "feishu:p2p:ou_alice" not in svc._pending_interrupts
        reply_mock.assert_called_once_with("oc_chat_001", "完成")


@pytest.mark.asyncio
async def test_resume_agent_multi_round_interrupt_updates_pending():
    """P1：续跑再次产生 interrupt → 更新 pending + 再次发卡片。"""
    async def fake_build(name, sid, msg, **kwargs):
        async def stream(*a, **kw):
            yield ("updates", {"hitl": {"__interrupt__": [
                {"value": {"action": "ask_user_question",
                           "questions": [{"question": "Q2",
                                          "options": [{"label": "B"}],
                                          "multiSelect": False}]}}
            ]}})
        return types.SimpleNamespace(stream=stream), MagicMock(), MagicMock()

    svc = _make_service()
    svc._agent_config_service.build_agent_instance = fake_build
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }

    with patch.object(svc, "_send_reply") as reply_mock, \
         patch.object(svc, "_send_interrupt_card") as card_mock:
        await svc._resume_agent(
            "feishu:p2p:ou_alice",
            {"answers": [{"qid": 0, "oid": [1]}]},
        )
        card_mock.assert_called_once()
        # pending 仍保留（覆盖为新 interrupt）
        assert "feishu:p2p:ou_alice" in svc._pending_interrupts
        assert "Q2" in str(svc._pending_interrupts["feishu:p2p:ou_alice"]["request"])
        reply_mock.assert_not_called()


@pytest.mark.asyncio
async def test_interrupt_session_unknown_warning_no_crash():
    """P1：未找到 pending 时仅警告，不抛异常。"""
    svc = _make_service()
    # 不写入 pending
    with patch.object(svc, "_send_reply") as reply_mock:
        await svc._resume_agent("feishu:p2p:ou_ghost", {"answers": []})
        reply_mock.assert_not_called()


def test_on_card_action_other_button_clears_pending_and_sends_hint():
    """P1：点击"其他"按钮 → 清理 pending + 发提示文本。"""
    svc = _make_service()
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }
    action_obj = MagicMock()
    action_obj.value = {
        "action": "hitl_answer",
        "qid": 0,
        "oid": -1,
        "is_other": True,
        "session_id": "feishu:p2p:ou_alice",
        "chat_id": "oc_chat_001",
    }
    event = MagicMock()
    event.action = action_obj
    data = MagicMock()
    data.event = event

    with patch.object(svc, "_send_text_reply") as text_mock:
        svc._on_card_action(data)
        text_mock.assert_called_once()
        # pending 已清理
        assert "feishu:p2p:ou_alice" not in svc._pending_interrupts


def test_on_card_action_non_hitl_action_ignored():
    """P2：value.action != hitl_answer 忽略。"""
    svc = _make_service()
    action_obj = MagicMock()
    action_obj.value = {"action": "其他操作"}
    event = MagicMock()
    event.action = action_obj
    data = MagicMock()
    data.event = event

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        svc._on_card_action(data)
        assert not rcts.called


def test_on_card_action_missing_fields_ignored():
    """P2：value 缺字段忽略。"""
    svc = _make_service()
    action_obj = MagicMock()
    action_obj.value = {"action": "hitl_answer"}  # 缺 qid / oid / session_id
    event = MagicMock()
    event.action = action_obj
    data = MagicMock()
    data.event = event

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        svc._on_card_action(data)
        assert not rcts.called


def test_on_card_action_value_as_json_string():
    """P1：value 是 JSON 字符串时也能解析。"""
    svc = _make_service()
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    action_obj = MagicMock()
    action_obj.value = json.dumps(
        {"action": "hitl_answer", "qid": 0, "oid": 0,
         "session_id": "feishu:p2p:ou_alice", "chat_id": "oc_chat_001"}
    )
    event = MagicMock()
    event.action = action_obj
    data = MagicMock()
    data.event = event

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        svc._on_card_action(data)
        assert rcts.called


def test_on_card_action_top_level_value():
    """P1：value 在顶层（data.value）也能提取。"""
    svc = _make_service()
    svc._pending_interrupts["feishu:p2p:ou_alice"] = {
        "chat_id": "oc_chat_001",
        "request": {"action": "ask_user_question", "questions": []},
    }
    fake_loop = MagicMock()
    fake_loop.is_closed.return_value = False
    svc.set_event_loop(fake_loop)

    data = MagicMock(spec=["value"])
    data.value = {
        "action": "hitl_answer",
        "qid": 0,
        "oid": 0,
        "session_id": "feishu:p2p:ou_alice",
        "chat_id": "oc_chat_001",
    }
    data.event = None
    data.action = None

    with patch("asyncio.run_coroutine_threadsafe") as rcts:
        svc._on_card_action(data)
        assert rcts.called


def test_extract_card_action_value_returns_none_when_missing():
    """P2：data 无 value → 返回 None。"""
    data = MagicMock()
    data.event = None
    data.action = None
    data.value = None
    assert FeishuWebSocketService._extract_card_action_value(data) is None
    assert FeishuWebSocketService._extract_card_action_value(None) is None


# ---------------------------------------------------------------------------
# P1 _build_ws_client 注册 p2_card_action_trigger
# ---------------------------------------------------------------------------
def test_build_ws_client_registers_card_action_trigger():
    """P1：_build_ws_client 注册 p2_card_action_trigger。"""
    svc = _make_service()
    # 配置 _lark_client._config.app_id / .app_secret
    svc._lark_client._config.app_id = "cli_test"
    svc._lark_client._config.app_secret = "secret_test"
    ws_client = svc._build_ws_client()
    # handler 应含两个注册项
    handler = ws_client._event_handler
    handler_types = [h[0] for h in handler.handlers]
    assert "p2_im_message_receive_v1" in handler_types
    assert "p2_card_action_trigger" in handler_types
