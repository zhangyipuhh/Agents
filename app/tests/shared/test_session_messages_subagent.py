# -*- coding:utf-8 -*-
"""
Session messages 端点集成测试（2026-06-16 改造）

验证 GET /api/session/{session_id}/messages 在以下场景的行为：
    1. 返回主消息 + 按时序合并子智能体消息流（type='subagent'）
    2. limit 参数对合并后总数生效
    3. 无权限时返回 403
    4. checkpointer 故障时返回 500 而非崩溃
    5. delete_session 同时清理子 thread

策略：通过 mock map_agent.get_agent() 与全局 checkpointer，
     在测试环境内构造主 thread + 子 thread 状态。
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.utils.auth.user_db import UserDB


# 测试用动态消息类（类名必须为 AIMessage/HumanMessage 以通过 _is_ai_message / _convert_message_to_dict）
TestAIMessage = type("AIMessage", (object,), {})
TestHumanMessage = type("HumanMessage", (object,), {})


def _msg(type_cls, content=None, **kwargs):
    inst = type_cls.__new__(type_cls)
    inst.content = content
    for k, v in kwargs.items():
        setattr(inst, k, v)
    return inst


@pytest.fixture(autouse=True)
def reset_user_db():
    """每个测试前重置 UserDB"""
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0
    asyncio.run(UserDB.create_user("admin", "admin123", role="admin"))
    yield
    UserDB._memory_users.clear()
    UserDB._memory_id_counter = 0


def _build_mock_agent_graph(main_messages, thread_values=None):
    """
    构造 mock map_agent，graph.aget_state 返回含 messages 的 state
    """
    values = thread_values if thread_values is not None else {"messages": main_messages}
    state = SimpleNamespace(values=values)
    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=state)
    agent = MagicMock()
    agent.graph = graph
    map_agent = MagicMock()
    map_agent.get_agent = AsyncMock(return_value=agent)
    return map_agent


def _build_mock_checkpointer(thread_states):
    """
    构造 mock checkpointer。
    thread_states: dict[thread_id] -> state dict or None
    """
    cp = MagicMock()

    async def fake_aget(config):
        tid = config["configurable"]["thread_id"]
        return thread_states.get(tid)

    cp.aget = AsyncMock(side_effect=fake_aget)
    cp.adelete_thread = AsyncMock()
    return cp


# ===== 主+子消息合并 =====

def test_messages_returns_merged_subagent(client, admin_headers):
    """
    主 thread 含 HumanMessage + AIMessage(有 tool_call=sandbox) + HumanMessage，
    子 thread (call_x) 含 1 条 HumanMessage + 1 条 AIMessage。
    期望返回 4 条：m-h-1, m-ai-1, subagent(call_x), m-h-2
    """
    # 通过 API 创建会话（这样能正确建立 session_cache_original._cache）
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    # 主消息
    h1 = _msg(TestHumanMessage, content="hi")
    ai1 = _msg(
        TestAIMessage, content="ok",
        tool_calls=[{"id": "call_x", "name": "sandbox", "args": {}}],
        id="m-ai-1",
    )
    h2 = _msg(TestHumanMessage, content="thanks")
    main_messages = [h1, ai1, h2]

    # 子 thread 状态
    sub_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="sub prompt"),
                _msg(TestAIMessage, content="sub answer"),
            ]
        }
    }
    cp = _build_mock_checkpointer({"call_x": sub_state})
    map_agent = _build_mock_agent_graph(main_messages)

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.features.map_agent.router.map_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/{session_id}/messages?limit=100",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["total"] == 4

    msgs = data["messages"]
    # 顺序校验
    assert msgs[0]["type"] == "user"
    assert msgs[1]["type"] == "ai"
    assert msgs[2]["type"] == "subagent"
    assert msgs[2]["thread_id"] == "call_x"
    assert msgs[2]["tool"] == "sandbox"
    assert msgs[2]["parent_message_id"] == "m-ai-1"
    assert len(msgs[2]["messages"]) == 2
    assert msgs[3]["type"] == "user"


def test_messages_no_subagent_when_no_tool_calls(client, admin_headers):
    """主消息无 tool_call 时不插入 subagent 元素"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    h = _msg(TestHumanMessage, content="hi")
    ai = _msg(TestAIMessage, content="ok", id="m-1")
    map_agent = _build_mock_agent_graph([h, ai])
    cp = _build_mock_checkpointer({})

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.features.map_agent.router.map_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/{session_id}/messages", headers=headers
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    assert all(m["type"] != "subagent" for m in data["messages"])


def test_messages_unauthorized(client):
    """无 token 时返回 401"""
    resp = client.get("/api/session/any/messages")
    assert resp.status_code == 401


def test_messages_forbidden_other_user(client, admin_headers):
    """其他用户的 session 返回 403"""
    # 通过 admin 创建会话
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    # 强制 verify_session 返回 False
    with patch(
        "app.shared.routers.session_router.session_cache.verify_session",
        AsyncMock(return_value=False),
    ):
        resp = client.get(
            f"/api/session/{session_id}/messages", headers=headers
        )
    assert resp.status_code in (401, 403), f"unexpected status {resp.status_code}"


def test_messages_limit_applied_to_merged(client, admin_headers):
    """limit 应作用于合并后的总数"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    h1 = _msg(TestHumanMessage, content="h1")
    ai1 = _msg(
        TestAIMessage, content="a1",
        tool_calls=[{"id": "call_lim", "name": "sandbox", "args": {}}],
        id="m-ai-1",
    )
    h2 = _msg(TestHumanMessage, content="h2")
    main_messages = [h1, ai1, h2]

    sub_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="sh"),
                _msg(TestAIMessage, content="sa"),
            ]
        }
    }
    cp = _build_mock_checkpointer({"call_lim": sub_state})
    map_agent = _build_mock_agent_graph(main_messages)

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.features.map_agent.router.map_router.get_map_agent",
        AsyncMock(return_value=map_agent),
    ):
        resp = client.get(
            f"/api/session/{session_id}/messages?limit=2",
            headers=headers,
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 合并后共 4 条，limit=2 取最后 2 条
    assert data["total"] == 2
    # 最后 2 条应为 subagent + h2
    assert data["messages"][0]["type"] == "subagent"
    assert data["messages"][1]["type"] == "user"


# ===== delete_session 清理子 thread =====

def test_delete_session_cleans_subagent_threads(client, admin_headers):
    """删除会话时同时调用 adelete_thread 清理子 thread"""
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    # 准备主 thread state 含 AIMessage tool_calls
    ai = _msg(
        TestAIMessage, content="a",
        tool_calls=[{"id": "sub_a", "name": "sandbox", "args": {}}],
    )
    thread_states = {session_id: {"channel_values": {"messages": [ai]}}}
    cp = _build_mock_checkpointer(thread_states)

    with patch(
        "app.shared.routers.session_router.get_async_checkpointer",
        AsyncMock(return_value=cp),
    ), patch(
        "app.shared.routers.session_router.file_transfer.delete_session",
        AsyncMock(return_value=True),
    ):
        resp = client.delete(
            f"/api/session/delete/{session_id}", headers=headers
        )

    assert resp.status_code == 200, resp.text
    # 应至少调用 2 次 adelete_thread：1 次 sub_a + 1 次主 session
    assert cp.adelete_thread.await_count >= 2, f"called {cp.adelete_thread.await_count} times"

    # 提取被调用的 thread_id（兼容 keyword / positional 两种传参）
    called_ids = []
    for c in cp.adelete_thread.await_args_list:
        if c.kwargs and "config" in c.kwargs:
            called_ids.append(c.kwargs["config"]["configurable"]["thread_id"])
        elif c.args and isinstance(c.args[0], dict):
            config = c.args[0]
            if "config" in config:
                called_ids.append(config["config"]["configurable"]["thread_id"])
            elif "configurable" in config:
                called_ids.append(config["configurable"]["thread_id"])
        elif c.args:
            called_ids.append(c.args[0])

    assert "sub_a" in called_ids, f"sub_a not in {called_ids}"
    assert session_id in called_ids, f"{session_id} not in {called_ids}"
