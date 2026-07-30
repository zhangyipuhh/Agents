# -*- coding:utf-8 -*-
"""统一日志服务公共契约测试。"""
import asyncio
import inspect
import json
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.shared.utils.log_service import (
    LogEvent,
    LogLevel,
    LogResult,
    LogService,
    LogType,
    get_log_service,
    hash_command,
    redact_command,
    redact_metadata,
    reset_log_service,
    set_log_service,
)


def _event(**kwargs):
    """构造测试事件。

    参数:
        **kwargs: 覆盖事件字段。
    返回值:
        LogEvent: 测试事件。
    异常:
        ValidationError: 字段不合法时抛出。
    """
    values = {"action": "login_success", "username": "alice"}
    values.update(kwargs)
    return LogEvent(**values)


def test_log_enums_match_public_contract():
    """枚举值必须严格匹配公共契约。"""
    assert {item.value for item in LogType} == {"auth", "user", "session", "ssh", "system"}
    assert {item.value for item in LogResult} == {"success", "failure", "blocked", "pending", "skipped"}
    assert {item.value for item in LogLevel} == {"info", "warning", "error"}


@pytest.mark.parametrize(
    ("field", "value"),
    [("log_type", "audit"), ("result", "unknown"), ("level", "debug")],
)
def test_log_event_rejects_invalid_enum(field, value):
    """非法枚举不得静默降级。

    参数:
        field: 枚举字段名。
        value: 非法值。
    返回值:
        None。
    异常:
        ValidationError: 构造事件时抛出。
    """
    with pytest.raises(ValidationError):
        LogEvent(action="invalid_enum", **{field: value})


def test_log_event_defaults_and_timestamp_contract():
    """默认事件使用 system/success/info 和 UTC naive 时间。"""
    event = LogEvent(action="unknown_action")
    assert event.log_type == LogType.SYSTEM
    assert event.result == LogResult.SUCCESS
    assert event.level == LogLevel.INFO
    assert event.timestamp.tzinfo is None


def test_log_event_rejects_extra_fields_and_empty_action():
    """空 action 与额外字段均应被拒绝。"""
    with pytest.raises(ValidationError):
        LogEvent(action="")
    with pytest.raises(ValidationError):
        LogEvent(action="x", unexpected=True)


def test_redaction_helpers_do_not_mutate_input():
    """通用脱敏创建深副本且命令辅助函数保持稳定。"""
    source = {"nested": [{"password": "secret", "safe": "ok"}]}
    redacted = redact_metadata(source)
    source["nested"][0]["safe"] = "changed"
    assert redacted == {"nested": [{"password": "***REDACTED***", "safe": "ok"}]}
    command = "mysql -psecret"
    assert redact_command(command) == "mysql -p***REDACTED***"
    assert hash_command(command) == hash_command(command)


@pytest.mark.parametrize(
    ("command", "secret"),
    [
        ("PASSWORD=value", "value"),
        ('PASSWORD="double-value"', "double-value"),
        ("PASSWORD='single-value'", "single-value"),
        ("PASSWORD: colon-value", "colon-value"),
        ("tool --password space-value", "space-value"),
        ('tool --password="double-flag"', "double-flag"),
        ("tool --password='single-flag'", "single-flag"),
        ("mysql -pshort-value", "short-value"),
        ("mysql -p short-space-value", "short-space-value"),
        ("Authorization: Bearer bearer-value", "bearer-value"),
        ("curl https://url-user:url-pass@example.com", "url-user"),
    ],
)
def test_redact_command_replaces_complete_sensitive_values(command, secret):
    """命令脱敏必须覆盖所有约定形态，并统一使用完整占位符。

    参数:
        command: 含敏感值的命令。
        secret: 不得出现在脱敏结果中的敏感片段。
    返回值:
        None。
    异常:
        AssertionError: 敏感片段残留或占位符不正确时抛出。
    """
    redacted = redact_command(command)
    assert secret not in redacted
    assert "***REDACTED***" in redacted


def test_redact_metadata_persists_sensitive_and_command_like_keys_via_emit():
    """真实 emit→queue→flush→query_logs 链路持久化前完成 metadata 脱敏。

    返回值:
        None。
    异常:
        AssertionError: 通用敏感键或命令型键中仍有明文时抛出。
    """
    async def runner():
        service = LogService(memory_only=True, flush_interval_seconds=0.01)
        await service.start()
        metadata = {
            "password": "password-value",
            "token": "token-value",
            "api_key": "api-value",
            "secret": "secret-value",
            "api-key": "dash-api-value",
            "access_key": "access-value",
            "private_key": "private-value",
            "mysql_pwd": "mysql-value",
            "redis_pwd": "redis-value",
            "cookie": "cookie-value",
            "authorization": "Bearer auth-value",
            "intercept_reason": "blocked mysql --password=reason-value",
            "decision": "curl --token decision-value",
            "intercept_code": "PASSWORD=code-value",
        }
        assert service.emit(_event(action="redaction", metadata=metadata)) is True
        await service.stop()
        return (await service.query_logs(action="redaction"))[0]["metadata"]

    persisted = asyncio.run(runner())
    blob = json.dumps(persisted, ensure_ascii=False)
    for secret in (
        "password-value", "token-value", "api-value", "secret-value",
        "dash-api-value", "access-value", "private-value", "mysql-value",
        "redis-value", "cookie-value", "auth-value", "reason-value",
        "decision-value", "code-value",
    ):
        assert secret not in blob
    assert blob.count("***REDACTED***") >= 13


def test_emit_is_only_public_synchronous_entry():
    """emit 是唯一公开同步写入口，不暴露线程专用入口。"""
    assert not inspect.iscoroutinefunction(LogService.emit)
    assert not hasattr(LogService, "emit_threadsafe")


def test_emit_before_start_returns_false():
    """服务未启动时 emit 返回 False。"""
    assert LogService(memory_only=True).emit(_event()) is False


def test_queue_full_callback_logs_error(caplog):
    """队列在调度回调执行时已满应记录错误日志。

    参数:
        caplog: pytest 日志捕获夹具。
    返回值:
        None。
    异常:
        AssertionError: 未按 error 级别记录时抛出。
    """
    service = LogService(memory_only=True)
    service._queue = asyncio.Queue(maxsize=1)
    service._queue.put_nowait(_event(action="existing"))
    service._enqueue_sync(_event(action="dropped"))
    assert any(record.levelname == "ERROR" and "queue full" in record.message for record in caplog.records)


def test_emit_returns_false_when_queue_is_full_at_emit_time():
    """事件循环线程队列满时 emit 返回 False，且拒绝事件不持久化。"""
    service = LogService(memory_only=True)

    async def runner():
        await service.start()
        service._consumer_task.cancel()
        await asyncio.gather(service._consumer_task, return_exceptions=True)
        for index in range(LogService.QUEUE_MAX_SIZE):
            service._queue.put_nowait(_event(action=f"fill-{index}"))
        rejected = service.emit(_event(action="overflow-loop"))
        await service.stop()
        return rejected, await service.query_logs(action="overflow-loop")

    rejected, rows = asyncio.run(runner())
    assert rejected is False
    assert rows == []


def test_emit_returns_false_from_ssh_worker_when_queue_is_full():
    """SSH worker 线程队列满时 emit 返回 False，且拒绝事件不持久化。

    返回值:
        None。
    异常:
        AssertionError: worker 线程误报成功或事件被持久化时抛出。
    """
    service = LogService(memory_only=True)

    async def runner():
        await service.start()
        service._consumer_task.cancel()
        await asyncio.gather(service._consumer_task, return_exceptions=True)
        for index in range(LogService.QUEUE_MAX_SIZE):
            service._queue.put_nowait(_event(action=f"fill-worker-{index}"))
        results = []
        worker = threading.Thread(
            target=lambda: results.append(service.emit(_event(action="overflow-worker")))
        )
        worker.start()
        worker.join()
        await service.stop()
        return results, await service.query_logs(action="overflow-worker")

    results, rows = asyncio.run(runner())
    assert results == [False]
    assert rows == []


def test_emit_reserved_count_released_after_enqueue():
    """入队成功后 ``_reserved_count`` 必须 -1,避免名额泄漏。

    在事件循环线程消费一定数量后,emit 应再次成功,证明预留未泄漏。
    """
    service = LogService(memory_only=True)

    async def runner():
        await service.start()
        # 把队列填满到 QUEUE_MAX_SIZE - 1,留出 1 个名额供 emit 抢占
        for index in range(LogService.QUEUE_MAX_SIZE - 1):
            service._queue.put_nowait(_event(action=f"fill-{index}"))
        # 第一次 emit:应该成功(预留 → 调度 → 入队 → 释放预留)
        assert service.emit(_event(action="burst-1")) is True
        # 等待事件循环线程消费一空
        await asyncio.sleep(0.05)
        # 第二次 emit:队列已部分消费,应再次成功(预留已正确释放)
        assert service.emit(_event(action="burst-2")) is True
        # _reserved_count 在所有 emit 完成且 _enqueue_sync 跑过后应回到 0
        await asyncio.sleep(0.05)
        assert service._reserved_count == 0
        await service.stop()

    asyncio.run(runner())


def test_emit_thread_safety_concurrent_workers():
    """多 worker 线程并发 emit,超容时返回 False,未超容时全部成功。

    验证 ``_reserve_lock`` 串行化预留逻辑,防止「多个 worker 同时通过 qsize
    检查并各自调度」导致实际入队数超 QUEUE_MAX_SIZE。
    """
    service = LogService(memory_only=True)

    async def runner():
        await service.start()
        results = []
        results_lock = threading.Lock()

        def worker(thread_id):
            for index in range(200):
                ok = service.emit(_event(action=f"t{thread_id}-{index}"))
                with results_lock:
                    results.append(ok)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 等消费协程跑一会儿
        await asyncio.sleep(0.5)
        # 关键校验:任何时候 _queue.qsize() 都不应超 QUEUE_MAX_SIZE
        assert service._queue.qsize() <= LogService.QUEUE_MAX_SIZE
        # 预留计数必须回归 0(无泄漏)
        assert service._reserved_count == 0
        # 至少有一些 emit 成功(消费者会持续 flush)
        assert any(results), "预期至少部分 emit 成功"
        await service.stop()

    asyncio.run(runner())


def test_materialized_message_falls_back_to_action():
    """事件未提供 message 时持久化值回退为 action，以满足非空约束。"""
    service = LogService(memory_only=True)
    event = _event(action="no_message")
    assert service._materialize_row(event)[5] == "no_message"
    service._store_memory(event)
    assert service._memory_records[0]["message"] == "no_message"


def test_emit_uses_saved_loop_from_event_loop_thread():
    """事件循环线程调用 emit 也必须经保存 loop 调度。"""
    async def runner():
        service = LogService(memory_only=True)
        await service.start()
        with patch.object(service._loop, "call_soon_threadsafe", wraps=service._loop.call_soon_threadsafe) as call:
            assert service.emit(_event()) is True
            assert call.call_count == 1
        await service.stop()
        assert len(await service.query_logs()) == 1

    asyncio.run(runner())


def test_emit_from_worker_thread_does_not_require_loop_argument():
    """SSH worker 线程直接调用统一 emit，无需传 loop。"""
    async def runner():
        service = LogService(memory_only=True)
        await service.start()
        results = []

        def worker():
            for index in range(5):
                results.append(service.emit(_event(action=f"ssh_{index}", log_type="ssh")))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        await service.stop()
        return results, await service.query_logs(log_type="ssh")

    results, rows = asyncio.run(runner())
    assert results == [True] * 5
    assert {row["action"] for row in rows} == {f"ssh_{index}" for index in range(5)}


def test_emit_snapshots_and_redacts_before_enqueue():
    """入队前生成深复制脱敏事件，后续修改原 metadata 不影响记录。"""
    async def runner():
        service = LogService(memory_only=True, flush_interval_seconds=60)
        await service.start()
        metadata = {
            "nested": {"token": "plain-token", "safe": "before"},
            "command": "mysql -uroot -pplain-password",
        }
        event = _event(action="ssh_command", log_type="ssh", metadata=metadata)
        assert service.emit(event) is True
        metadata["nested"]["safe"] = "after"
        metadata["nested"]["token"] = "changed-token"
        event.metadata["command"] = "changed-command"
        await service.stop()
        return (await service.query_logs())[0]

    row = asyncio.run(runner())
    serialized = json.dumps(row["metadata"], ensure_ascii=False)
    assert row["metadata"]["nested"] == {"token": "***REDACTED***", "safe": "before"}
    assert "plain-token" not in serialized
    assert "plain-password" not in serialized
    assert "changed-command" not in serialized


def test_stop_drains_callbacks_current_batch_and_remaining_queue():
    """stop 等待已调度 enqueue 回调并排空当前批次与剩余队列。"""
    async def runner():
        service = LogService(memory_only=True, batch_size=7, flush_interval_seconds=60)
        await service.start()

        def worker():
            for index in range(25):
                assert service.emit(_event(action=f"drain_{index}")) is True

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        await service.stop()
        return await service.count_logs()

    assert asyncio.run(runner()) == 25


def test_emit_returns_false_when_saved_loop_is_closed():
    """保存的 loop 已关闭时 emit 返回 False。"""
    service = LogService(memory_only=True)

    async def start_only():
        await service.start()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(start_only())
    service._consumer_task.cancel()
    loop.run_until_complete(asyncio.gather(service._consumer_task, return_exceptions=True))
    loop.close()
    assert service.emit(_event()) is False


class _Acquire:
    """模拟 asyncpg acquire 上下文管理器。"""

    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeConnection:
    """记录 PostgreSQL 参数化调用。"""

    def __init__(self):
        self.executemany = AsyncMock(return_value=None)
        self.fetch = AsyncMock(return_value=[{"id": 1, "action": "login_success"}])
        self.fetchval = AsyncMock(return_value=3)
        self.fetchrow = AsyncMock(return_value={"id": 1, "action": "login_success"})


class _FakePool:
    """模拟 asyncpg pool。"""

    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def test_query_methods_are_async():
    """四个查询入口必须全部为异步函数。"""
    for name in ("query_logs", "count_logs", "get_log", "get_correlated_logs"):
        assert inspect.iscoroutinefunction(getattr(LogService, name))


def test_postgres_queries_use_acquire_and_parameterized_fixed_filters():
    """PG 查询通过 acquire/fetch 系列执行全部计划过滤器。"""
    async def runner():
        connection = _FakeConnection()
        service = LogService(db_pool=_FakePool(connection), memory_only=False)
        service._memory_only = False
        filters = {
            "log_type": "auth", "action": "login_success", "result": "success",
            "level": "info", "source": "auth_router", "user_id": 1,
            "username": "alice", "session_id": "s", "request_id": "r",
            "tool_call_id": "t", "correlation_id": "c", "target_type": "user",
            "target_id": "1", "target_name": "Alice",
            "created_from": datetime(2026, 1, 1), "created_to": datetime(2026, 2, 1),
        }
        rows = await service.query_logs(**filters, limit=20, offset=5)
        count = await service.count_logs(**filters)
        one = await service.get_log(1)
        correlated = await service.get_correlated_logs("c")
        return connection, rows, count, one, correlated

    connection, rows, count, one, correlated = asyncio.run(runner())
    assert rows == [{"id": 1, "action": "login_success"}]
    assert count == 3
    assert one["id"] == 1
    assert correlated == [{"id": 1, "action": "login_success"}]
    query_sql, *query_args = connection.fetch.await_args_list[0].args
    assert "log_type = $1" in query_sql
    assert "created_at >= $15" in query_sql
    assert "created_at <= $16" in query_sql
    assert "LIMIT $17 OFFSET $18" in query_sql
    assert query_args[-2:] == [20, 5]
    assert connection.fetchval.await_count == 1
    assert connection.fetchrow.await_count == 1


def test_memory_queries_support_same_filter_contract():
    """memory 查询支持与 PostgreSQL 相同的过滤契约。"""
    async def runner():
        service = LogService(memory_only=True)
        await service.start()
        service.emit(_event(log_type="auth", result="blocked", level="warning", source="auth", user_id=1,
                            session_id="s", request_id="r", tool_call_id="t", correlation_id="c",
                            target_type="user", target_id="1", target_name="Alice",
                            timestamp=datetime(2026, 1, 15)))
        service.emit(_event(action="logout", log_type="auth", timestamp=datetime(2025, 1, 1)))
        await service.stop()
        filters = dict(log_type="auth", action="login_success", result="blocked", level="warning",
                       source="auth", user_id=1, username="alice", session_id="s", request_id="r",
                       tool_call_id="t", correlation_id="c", target_type="user", target_id="1",
                       target_name="Alice", created_from=datetime(2026, 1, 1), created_to=datetime(2026, 2, 1))
        rows = await service.query_logs(**filters)
        return rows, await service.count_logs(**filters), await service.get_log(rows[0]["id"]), await service.get_correlated_logs("c")

    rows, count, one, correlated = asyncio.run(runner())
    assert len(rows) == count == len(correlated) == 1
    assert one == rows[0]


def test_database_batch_insert_remains_parameterized():
    """PostgreSQL 批写保持 executemany 参数化。"""
    async def runner():
        connection = _FakeConnection()
        service = LogService(db_pool=_FakePool(connection), memory_only=False)
        service._memory_only = False
        await service.start()
        assert service.emit(_event(log_type="auth")) is True
        await service.stop()
        return connection

    connection = asyncio.run(runner())
    sql, rows = connection.executemany.await_args.args
    assert "$1" in sql
    assert isinstance(rows, list) and isinstance(rows[0], tuple)


def test_sql_schema_matches_enums_history_and_idempotency():
    """init SQL 的枚举、历史填充、非空约束与幂等语句符合契约。"""
    sql_path = Path(__file__).parents[3] / "migrations" / "init_all_tables.sql"
    sql = sql_path.read_text(encoding="utf-8")
    assert "DO $$" not in sql
    assert "IN ('auth', 'user', 'session', 'ssh', 'system')" in sql
    assert "IN ('success', 'failure', 'blocked', 'pending', 'skipped')" in sql
    assert "IN ('info', 'warning', 'error')" in sql
    for constraint in ("chk_audit_logs_log_type", "chk_audit_logs_result", "chk_audit_logs_level"):
        assert f"DROP CONSTRAINT IF EXISTS {constraint}" in sql
        assert f"ADD CONSTRAINT {constraint}" in sql
    for action in ("login_success", "login_failure", "logout", "admin_update_user", "admin_kick_user", "admin_delete_session"):
        assert action in sql
    assert "ELSE 'system'" in sql
    for field in ("log_type", "result", "level", "source", "message"):
        assert f"ALTER COLUMN {field} SET NOT NULL" in sql
    assert "created_at      TIMESTAMP" in sql


def test_dynamic_audit_schema_executes_full_idempotent_migration():
    """动态 schema 注册必须执行与 init SQL 同步的 ALTER、填充、约束和索引。

    2026-07-29 迁移：``init_audit_log_schema`` 入口由旧
    ``app.shared.utils.auth.audit_log`` 迁到 ``app.shared.utils.log_service``，
    业务侧无旧模块引用；测试同步迁移 patch 点。
    """
    from app.shared.utils.log_service import init_audit_log_schema

    statements = []

    async def capture(sql, *args):
        statements.append(sql)

    with patch("app.shared.utils.log_service.DatabasePool.execute", side_effect=capture):
        asyncio.run(init_audit_log_schema())
    sql = "\n".join(statements)
    assert "ADD COLUMN IF NOT EXISTS log_type" in sql
    assert "ELSE 'system'" in sql
    assert "ALTER COLUMN log_type SET NOT NULL" in sql
    assert "DROP CONSTRAINT IF EXISTS chk_audit_logs_log_type" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at" in sql
    assert "DO $$" not in sql


def test_singleton_contract():
    """全局单例支持设置、获取和重置。"""
    reset_log_service()
    service = LogService(memory_only=True)
    set_log_service(service)
    assert get_log_service() is service
    reset_log_service()
    assert get_log_service() is None
