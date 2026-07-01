# -*- coding:utf-8 -*-
"""
UserDB postgres 分支 JSONB 解码测试模块

针对 2026-07-01 的 GET /api/users 500 bug：postgres 分支返回的
allowed_agents 在 asyncpg 默认配置下被解码为 JSON 字符串而非 list，
导致下游 Pydantic 模型校验失败。

本文件验证 UserDB.list_users / get_user_by_username / get_user_by_id
在 postgres 路径下通过 _coerce_allowed_agents 兜底，能将各种 JSONB
字符串形态（合法 list / 空 list / 非法 JSON / 原生 list）统一规整为
Python list。

测试策略：monkeypatch env AUTH_STORAGE_MODE=postgres，patch
UserDB.is_enabled 绕过 DatabasePool 初始化检查，patch
DatabasePool.fetch / fetchrow 返回 Record-like 对象模拟
asyncpg.Record 的 dict-style 访问。
"""
import asyncio
from unittest.mock import patch

import pytest

from app.shared.utils.auth.user_db import UserDB


def _make_row(**fields):
    """
    构造 asyncpg.Record-like 对象：支持 record['col'] 与 record.get('col')。

    asyncpg.Record 继承 tuple 并实现 __getitem__，但本次测试只需 dict-style
    访问，故动态类即可。

    Args:
        **fields: 字段名到值的映射。

    Returns:
        object: 含 __getitem__ 与 get 方法的轻量对象。
    """

    class _Row:
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def get(self, key, default=None):
            return self._data.get(key, default)

        def keys(self):
            return list(self._data.keys())

        def values(self):
            return list(self._data.values())

    return _Row(fields)


def test_list_users_postgres_jsonb_string_decodes_to_list():
    """
    postgres 返回 allowed_agents 为 JSON 字符串时，list_users 应解码为 list。

    Returns:
        None

    Raises:
        AssertionError: 解码结果不是预期 list 时抛出。
    """
    raw_rows = [
        _make_row(
            id=1, username="admin", role="admin",
            real_name="Admin", phone="", email="", department="", position="",
            allowed_agents='["map_agent", "contract_host"]',
            created_at="2026-07-01", updated_at="2026-07-01",
        ),
    ]

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetch",
                 return_value=raw_rows,
             ):
            users = await UserDB.list_users()
        assert users[0]["allowed_agents"] == ["map_agent", "contract_host"]

    asyncio.run(_run())


def test_list_users_postgres_empty_jsonb_string_returns_empty_list():
    """
    postgres 返回 '[]' 时，list_users 应规整为 []。

    Returns:
        None

    Raises:
        AssertionError: 解码结果非空列表时抛出。
    """
    raw_rows = [
        _make_row(
            id=2, username="u", role="user",
            real_name="", phone="", email="", department="", position="",
            allowed_agents="[]", created_at="2026-07-01", updated_at="2026-07-01",
        ),
    ]

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetch",
                 return_value=raw_rows,
             ):
            users = await UserDB.list_users()
        assert users[0]["allowed_agents"] == []

    asyncio.run(_run())


def test_list_users_postgres_invalid_jsonb_returns_empty_list():
    """
    防御性兜底：异常 JSON 字符串不抛错，规整为 []。

    Returns:
        None

    Raises:
        AssertionError: 抛异常或返回非空时抛出。
    """
    raw_rows = [
        _make_row(
            id=3, username="u", role="user",
            real_name="", phone="", email="", department="", position="",
            allowed_agents="not-json", created_at="2026-07-01", updated_at="2026-07-01",
        ),
    ]

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetch",
                 return_value=raw_rows,
             ):
            users = await UserDB.list_users()
        assert users[0]["allowed_agents"] == []

    asyncio.run(_run())


def test_list_users_postgres_native_list_passes_through():
    """
    codec 已生效（asyncpg 直接返回 list）时，原样透传。

    Returns:
        None

    Raises:
        AssertionError: list 内容被改写时抛出。
    """
    raw_rows = [
        _make_row(
            id=4, username="u", role="user",
            real_name="", phone="", email="", department="", position="",
            allowed_agents=["a", "b"], created_at="2026-07-01", updated_at="2026-07-01",
        ),
    ]

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetch",
                 return_value=raw_rows,
             ):
            users = await UserDB.list_users()
        assert users[0]["allowed_agents"] == ["a", "b"]

    asyncio.run(_run())


def test_get_user_by_username_postgres_jsonb_decoded():
    """
    postgres 单行查询：allowed_agents JSON 字符串应解码为 list。

    Returns:
        None

    Raises:
        AssertionError: 解码结果不符时抛出。
    """
    raw = _make_row(
        id=5, username="u", password_hash="x", role="user",
        real_name="", phone="", email="", department="", position="",
        allowed_agents='["agent1"]', created_at="2026-07-01", updated_at="2026-07-01",
    )

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetchrow",
                 return_value=raw,
             ):
            user = await UserDB.get_user_by_username("u")
        assert user is not None
        assert user["allowed_agents"] == ["agent1"]

    asyncio.run(_run())


def test_get_user_by_id_postgres_jsonb_decoded():
    """
    postgres 单行查询（按 id）：allowed_agents JSON 字符串应解码为 list。

    Returns:
        None

    Raises:
        AssertionError: 解码结果不符时抛出。
    """
    raw = _make_row(
        id=6, username="u", password_hash="x", role="user",
        real_name="", phone="", email="", department="", position="",
        allowed_agents='["x"]', created_at="2026-07-01", updated_at="2026-07-01",
    )

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetchrow",
                 return_value=raw,
             ):
            user = await UserDB.get_user_by_id(6)
        assert user is not None
        assert user["allowed_agents"] == ["x"]

    asyncio.run(_run())


def test_get_user_by_username_postgres_not_found_returns_none():
    """
    postgres 单行查询无结果时返回 None（兜底 Record 路径不抛错）。

    Returns:
        None

    Raises:
        AssertionError: 返回非 None 时抛出。
    """

    async def _run():
        with patch.object(UserDB, "is_enabled", return_value=True), \
             patch(
                 "app.shared.utils.auth.user_db.DatabasePool.fetchrow",
                 return_value=None,
             ):
            user = await UserDB.get_user_by_username("missing")
        assert user is None

    asyncio.run(_run())