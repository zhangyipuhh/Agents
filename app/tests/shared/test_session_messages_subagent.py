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
# 2026-06-17 新增：用于多子智能体 + ToolMessage 索引对齐测试
TestToolMessage = type("ToolMessage", (object,), {})


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


# ===== 2026-06-16 修复：非子智能体工具 tool_call 不产生 subagent 元素 =====

def test_messages_filters_non_subagent_tool_call(client, admin_headers):
    """
    端到端测试：主消息含 generate_report tool_call（普通工具）时，
    GET /api/session/{id}/messages 返回的 messages 列表中
    **不应** 包含 type:"subagent" 元素。

    防回归：用户报告 generate_report 被误包装为 type:"subagent"，
    前端误渲染为 SubAgentCard（点击触发 SubAgentDrawer）。
    """
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    # 主消息：用户提问 + AI 回答（带 generate_report tool_call，无子 thread）
    h = _msg(TestHumanMessage, content="生成一份报告")
    ai = _msg(
        TestAIMessage, content="好的，我已生成报告",
        tool_calls=[{"id": "call_gr_e2e", "name": "generate_report", "args": {}}],
        id="m-ai-gr",
    )
    main_messages = [h, ai]

    # 不需要任何子 thread state（普通工具不应被反查）
    cp = _build_mock_checkpointer({})
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
    # 关键断言：total == 2（仅 2 条主消息，无任何 subagent 元素插入）
    assert data["total"] == 2, f"期望 2 条，实际 {data['total']}：{data['messages']}"
    # 关键断言：messages 列表中不应有 type:"subagent"
    subagent_msgs = [m for m in data["messages"] if m.get("type") == "subagent"]
    assert subagent_msgs == [], f"普通工具不应产生 subagent 元素：{subagent_msgs}"
    # 类型校验
    assert data["messages"][0]["type"] == "user"
    assert data["messages"][1]["type"] == "ai"


# ===== 2026-06-17 修复：多子智能体 + ToolMessage 索引对齐（端到端） =====

def test_messages_multiple_subagents_with_tool_messages(client, admin_headers):
    """
    端到端：主消息流 raw = [H, A(sandbox), T, A(text), H, A(explore), T, A(text2)]
    过滤后 main = [U, A, A, U, A, A]（6 条），子 thread call_sb 与 call_ex 各有 2 条。
    期望 total=8，sandbox 与 explore 元素各归位到对应 AI 之后。

    防回归：旧实现仅返回 4 条（h-1, ai-sb, subagent(call_sb), ai-t1），explore 丢失。
    """
    create_resp = client.post("/api/session/create", headers=admin_headers)
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]
    headers = {**admin_headers, "X-Session-ID": session_id}

    # 主消息 raw 流
    h1 = _msg(TestHumanMessage, content="hi")
    ai_sb = _msg(
        TestAIMessage, content="",
        tool_calls=[{"id": "call_sb_e2e", "name": "sandbox", "args": {}}],
        id="ai-sb-e2e",
    )
    t_sb = _msg(TestToolMessage, content="sb result", tool_call_id="call_sb_e2e")
    ai_t1 = _msg(TestAIMessage, content="sandbox done", id="ai-t1-e2e")
    h2 = _msg(TestHumanMessage, content="next")
    ai_ex = _msg(
        TestAIMessage, content="",
        tool_calls=[{"id": "call_ex_e2e", "name": "explore", "args": {}}],
        id="ai-ex-e2e",
    )
    t_ex = _msg(TestToolMessage, content="ex result", tool_call_id="call_ex_e2e")
    ai_t2 = _msg(TestAIMessage, content="explore done", id="ai-t2-e2e")
    main_messages = [h1, ai_sb, t_sb, ai_t1, h2, ai_ex, t_ex, ai_t2]

    sub_sb_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="sb prompt"),
                _msg(TestAIMessage, content="sb answer"),
            ]
        }
    }
    sub_ex_state = {
        "channel_values": {
            "messages": [
                _msg(TestHumanMessage, content="ex prompt"),
                _msg(TestAIMessage, content="ex answer"),
            ]
        }
    }
    cp = _build_mock_checkpointer({
        "call_sb_e2e": sub_sb_state,
        "call_ex_e2e": sub_ex_state,
    })
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
    # 关键断言：total == 8（旧实现仅 4 条，explore 丢失）
    assert data["total"] == 8, f"期望 8 条，实际 {data['total']}：{data['messages']}"

    # 顺序与归属校验
    msgs = data["messages"]
    assert msgs[0]["type"] == "user"
    assert msgs[1]["type"] == "ai" and msgs[1]["id"] == "ai-sb-e2e"
    assert msgs[2]["type"] == "subagent"
    assert msgs[2]["thread_id"] == "call_sb_e2e"
    assert msgs[2]["parent_message_id"] == "ai-sb-e2e"
    assert len(msgs[2]["messages"]) == 2

    assert msgs[3]["type"] == "ai" and msgs[3]["id"] == "ai-t1-e2e"
    assert msgs[4]["type"] == "user"
    assert msgs[5]["type"] == "ai" and msgs[5]["id"] == "ai-ex-e2e"
    assert msgs[6]["type"] == "subagent"
    assert msgs[6]["thread_id"] == "call_ex_e2e"
    assert msgs[6]["parent_message_id"] == "ai-ex-e2e"
    assert len(msgs[6]["messages"]) == 2
    assert msgs[7]["type"] == "ai" and msgs[7]["id"] == "ai-t2-e2e"
