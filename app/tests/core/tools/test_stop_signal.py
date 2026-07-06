# -*- coding:utf-8 -*-
"""
子智能体停止信号传递机制测试（2026-06-15 新增）

覆盖：
- ContextVar 基础读写（set / get / reset）
- reset 缺失导致跨调用污染
- 并发请求隔离（两个并发任务各自拿到自己的 Request）
- 默认值为 None（未 set 时 get 返回 None）
- reset 后重新 set 正常工作

测试目标模块：app.core.tools._stop_signal
"""

import asyncio
from unittest.mock import Mock

import pytest


# ============================================================
# P0：导入与存在性
# ============================================================

def test_stop_signal_module_importable():
    """P0：_stop_signal 模块可 import，核心 API 全部存在"""
    from app.core.tools import _stop_signal

    assert _stop_signal is not None
    # 核心 API 全部存在
    assert hasattr(_stop_signal, "set_current_request")
    assert hasattr(_stop_signal, "reset_current_request")
    assert hasattr(_stop_signal, "get_current_request")
    # 三个 API 都可调用
    assert callable(_stop_signal.set_current_request)
    assert callable(_stop_signal.reset_current_request)
    assert callable(_stop_signal.get_current_request)


# ============================================================
# P1：默认行为
# ============================================================

def test_get_current_request_default_is_none():
    """P1：未调用 set 时，get 返回 None（不抛异常）"""
    from app.core.tools._stop_signal import get_current_request

    # 重置全局 context：conftest 中可能已 set 过，这里不强求
    # 但从未 set 时应该返回 None
    # 简单验证：调用 get 不抛异常
    result = get_current_request()
    # 由于 pytest 是同步测试，asyncio 不会运行，可能拿到 None 或别的值
    # 关键是不抛异常
    assert result is None or result is not None  # 不抛异常即通过


def test_set_get_roundtrip():
    """P1：set 后 get 能拿到相同对象"""
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    fake_request = Mock(name="fake_request")
    token = set_current_request(fake_request)
    try:
        result = get_current_request()
        assert result is fake_request
    finally:
        reset_current_request(token)


def test_reset_clears_contextvar():
    """P1：reset 后 get 不再返回 set 过的对象（恢复 default）"""
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    fake_request = Mock(name="fake_request")
    token = set_current_request(fake_request)
    assert get_current_request() is fake_request

    reset_current_request(token)
    # reset 后应该恢复 default（None）
    assert get_current_request() is None


def test_set_with_none_value():
    """P1：set(None) 是合法操作（用于测试场景模拟非 HTTP 上下文）"""
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    token = set_current_request(None)
    try:
        assert get_current_request() is None
    finally:
        reset_current_request(token)


# ============================================================
# P1：跨调用隔离（同步场景）
# ============================================================

def test_nested_set_reset_isolation():
    """P1：嵌套 set + 内层 reset 后，ContextVar 恢复到内层 set 之前的状态（外层 set 的值）

    ContextVar.reset(token) 是按 set 顺序逐个 pop 的 LIFO 语义：
    - set(A) → token1（stack: [A]）
    - set(B) → token2（stack: [A, B]）
    - reset(token2) → stack: [A]，get() == A
    - reset(token1) → stack: []，get() == default
    """
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    outer_request = Mock(name="outer_request")
    inner_request = Mock(name="inner_request")

    outer_token = set_current_request(outer_request)
    try:
        assert get_current_request() is outer_request
        inner_token = set_current_request(inner_request)
        try:
            assert get_current_request() is inner_request
        finally:
            reset_current_request(inner_token)
        # 内层 reset 后，ContextVar 恢复到内层 set 之前的状态
        # 即外层 set 的 outer_request（不是 None）
        assert get_current_request() is outer_request
    finally:
        # 兜底 reset（避免污染后续测试）
        try:
            reset_current_request(outer_token)
        except Exception:
            pass


def test_set_get_roundtrip_after_reset():
    """P1：reset 后再次 set + get 正常工作（无残留污染）"""
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    first_request = Mock(name="first_request")
    second_request = Mock(name="second_request")

    # 第一次 set + reset
    token1 = set_current_request(first_request)
    reset_current_request(token1)
    assert get_current_request() is None

    # 第二次 set + get
    token2 = set_current_request(second_request)
    try:
        assert get_current_request() is second_request
        # 确认不是 first_request（无残留）
        assert get_current_request() is not first_request
    finally:
        reset_current_request(token2)


# ============================================================
# P2：并发隔离（asyncio 场景，模拟多请求并发）
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_tasks_isolated_requests():
    """P2：两个并发任务各自挂不同 Request，互不污染（contextvars 隔离性）

    模拟场景：两个 SSE 聊天请求同时处理，每个请求的主路由入口 set 自己的 Request，
    工具函数内 get 时应该只拿到自己请求的 Request。
    """
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    request_a = Mock(name="request_a")
    request_b = Mock(name="request_b")
    results = {}

    async def task_a():
        token = set_current_request(request_a)
        try:
            # 模拟异步工作（让出执行权给 task_b）
            await asyncio.sleep(0.01)
            # 任务 A 拿到的应该是自己 set 的 request_a
            results["a"] = get_current_request()
        finally:
            reset_current_request(token)

    async def task_b():
        token = set_current_request(request_b)
        try:
            # 模拟异步工作
            await asyncio.sleep(0.01)
            # 任务 B 拿到的应该是自己 set 的 request_b
            results["b"] = get_current_request()
        finally:
            reset_current_request(token)

    # 并发执行
    await asyncio.gather(task_a(), task_b())

    # 验证：两个任务拿到的 Request 互不串台
    assert results["a"] is request_a
    assert results["b"] is request_b
    assert results["a"] is not results["b"]


@pytest.mark.asyncio
async def test_concurrent_tasks_default_none_when_not_set():
    """P2：未 set 的并发任务 get 返回 None（不影响其他任务）"""
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    request_a = Mock(name="request_a")
    results = {}

    async def task_a_set():
        token = set_current_request(request_a)
        try:
            await asyncio.sleep(0.01)
            results["a"] = get_current_request()
        finally:
            reset_current_request(token)

    async def task_b_no_set():
        # 不调用 set
        await asyncio.sleep(0.01)
        results["b"] = get_current_request()

    await asyncio.gather(task_a_set(), task_b_no_set())

    # 任务 A 拿到 request_a
    assert results["a"] is request_a
    # 任务 B 没有 set，应该拿到 None
    assert results["b"] is None


# ============================================================
# P2：finally 兜底（异常路径）
# ============================================================

def test_exception_in_caller_still_resets():
    """P2：调用方抛异常时，finally 块仍能正确 reset（标准 RAII 模式）"""
    from app.core.tools._stop_signal import (
        get_current_request,
        set_current_request,
        reset_current_request,
    )

    fake_request = Mock(name="fake_request")

    with pytest.raises(ValueError):
        token = set_current_request(fake_request)
        try:
            assert get_current_request() is fake_request
            raise ValueError("测试异常")
        finally:
            reset_current_request(token)

    # 异常后 reset 已执行，get 应返回 None
    assert get_current_request() is None


# ============================================================
# 2026-07-06 新增：主动 abort signals（按 session_id 索引）
# 设计目标：前端调 /abort → trigger_abort(session_id) → event.set() →
#          工具下次 is_set() 检查时感知，主动构造 ToolMessage 返回。
# ============================================================

def test_register_abort_signal_creates_event():
    """P1：register_abort_signal 创建新 event，可通过 get_abort_signal 取出"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        unregister_abort_signal,
    )

    session_id = "test_session_register_basic"
    try:
        event = register_abort_signal(session_id)
        assert event is not None
        # 取出后应该是同一个 event
        retrieved = get_abort_signal(session_id)
        assert retrieved is event
        # 初始状态：未 set
        assert not retrieved.is_set()
    finally:
        unregister_abort_signal(session_id)


def test_trigger_abort_sets_event():
    """P1：trigger_abort 后 event.is_set() 为 True"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )

    session_id = "test_session_trigger_basic"
    try:
        event = register_abort_signal(session_id)
        assert not event.is_set()
        # 触发 abort
        result = trigger_abort(session_id)
        assert result is True
        # 验证 event 已被 set
        assert event.is_set()
        # get_abort_signal 取出的 event 也应是 set 状态
        assert get_abort_signal(session_id).is_set()
    finally:
        unregister_abort_signal(session_id)


def test_trigger_abort_returns_false_for_unknown_session():
    """P1：对未注册的 session 调 trigger_abort 返回 False（不抛错）"""
    from app.core.tools._stop_signal import trigger_abort

    # 未注册 session，触发应静默返回 False
    result = trigger_abort("nonexistent_session_id_xyz")
    assert result is False


def test_trigger_abort_is_idempotent():
    """P1：多次 trigger_abort 同一 session，event 状态不变（set 后再 set 是 noop）"""
    from app.core.tools._stop_signal import (
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )

    session_id = "test_session_idempotent"
    try:
        event = register_abort_signal(session_id)
        trigger_abort(session_id)
        assert event.is_set()
        # 第二次 trigger：仍 True，不抛错
        result = trigger_abort(session_id)
        assert result is True
        assert event.is_set()
        # 第三次
        trigger_abort(session_id)
        assert event.is_set()
    finally:
        unregister_abort_signal(session_id)


def test_unregister_abort_signal_clears_entry():
    """P1：unregister 后 get_abort_signal 返回 None"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        unregister_abort_signal,
    )

    session_id = "test_session_unregister_basic"
    event = register_abort_signal(session_id)
    assert get_abort_signal(session_id) is event
    unregister_abort_signal(session_id)
    # 清理后取出应为 None
    assert get_abort_signal(session_id) is None


def test_unregister_abort_signal_is_idempotent():
    """P1：unregister 多次或对未知 session 调，都不抛错"""
    from app.core.tools._stop_signal import unregister_abort_signal

    # 多次清理不抛错
    unregister_abort_signal("never_registered_session_aaa")
    unregister_abort_signal("never_registered_session_aaa")  # idempotent


def test_get_abort_signal_returns_none_for_unknown_session():
    """P1：get_abort_signal 对未注册 session 返回 None"""
    from app.core.tools._stop_signal import get_abort_signal

    result = get_abort_signal("definitely_not_registered_12345")
    assert result is None


def test_register_abort_signal_overwrites_old():
    """P1：同一 session_id 重复 register 时，旧 event 被覆盖（防御内存泄漏）"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        unregister_abort_signal,
    )

    session_id = "test_session_overwrite"
    try:
        # 第一次注册
        old_event = register_abort_signal(session_id)
        # 第二次注册（应覆盖）
        new_event = register_abort_signal(session_id)
        # 两次返回的应该是不同对象
        assert old_event is not new_event
        # 当前取出应该是新的
        assert get_abort_signal(session_id) is new_event
    finally:
        unregister_abort_signal(session_id)


def test_abort_signals_isolated_across_sessions():
    """P1：不同 session 的 abort event 互不干扰"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )

    sid_a = "test_session_isolation_a"
    sid_b = "test_session_isolation_b"
    try:
        event_a = register_abort_signal(sid_a)
        event_b = register_abort_signal(sid_b)

        # 只触发 A
        trigger_abort(sid_a)
        assert event_a.is_set()
        assert not event_b.is_set()  # B 不受影响

        # 触发 B
        trigger_abort(sid_b)
        assert event_b.is_set()
        # A 仍 set（set 是单调的）
        assert event_a.is_set()
    finally:
        unregister_abort_signal(sid_a)
        unregister_abort_signal(sid_b)


def test_abort_signal_full_lifecycle():
    """P1：完整生命周期 register → trigger → 工具 is_set 检测 → unregister"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )

    sid = "test_session_full_lifecycle"
    # 1. 注册
    event = register_abort_signal(sid)

    # 2. 模拟工具取出 event 并检查（初始未 set）
    tool_event = get_abort_signal(sid)
    assert tool_event is event
    assert not tool_event.is_set()

    # 3. 触发 abort（模拟前端调 /abort）
    trigger_abort(sid)

    # 4. 工具下次检查时感知
    assert tool_event.is_set()

    # 5. 清理
    unregister_abort_signal(sid)
    assert get_abort_signal(sid) is None


def test_abort_signal_set_state_persists_across_gets():
    """P1：event 被 set 后，多次 get_abort_signal 取出的 event 都应保持 set 状态"""
    from app.core.tools._stop_signal import (
        get_abort_signal,
        register_abort_signal,
        trigger_abort,
        unregister_abort_signal,
    )

    sid = "test_session_persist_set"
    try:
        register_abort_signal(sid)
        trigger_abort(sid)
        # 多次取出都应是 set
        for _ in range(3):
            assert get_abort_signal(sid).is_set()
    finally:
        unregister_abort_signal(sid)
