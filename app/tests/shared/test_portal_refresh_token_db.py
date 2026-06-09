# -*- coding:utf-8 -*-
"""
Portal Refresh Token 数据库测试模块

测试 app.shared.utils.auth.portal_refresh_token_db 在 memory 模式下的
token 哈希存储、验证、删除和查询逻辑。
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from app.shared.utils.auth.portal_refresh_token_db import PortalRefreshTokenDB


@pytest.fixture(autouse=True)
def reset_portal_token_db():
    """
    每个测试前清空 PortalRefreshTokenDB 内存存储。

    Yields:
        None
    """
    PortalRefreshTokenDB._memory_tokens.clear()
    yield
    PortalRefreshTokenDB._memory_tokens.clear()


def test_store_token_deletes_old():
    """
    测试同一用户多次 store_token 后只有一条记录。

    Returns:
        None

    Raises:
        AssertionError: 旧记录未被删除或新记录未存储时抛出。
    """
    now = datetime.utcnow()
    hash1 = PortalRefreshTokenDB.hash_token("token-old")
    hash2 = PortalRefreshTokenDB.hash_token("token-new")

    asyncio.run(PortalRefreshTokenDB.store_token(hash1, 1, "alice", now + timedelta(hours=1)))
    assert len(PortalRefreshTokenDB._memory_tokens) == 1
    assert hash1 in PortalRefreshTokenDB._memory_tokens

    asyncio.run(PortalRefreshTokenDB.store_token(hash2, 1, "alice", now + timedelta(hours=2)))
    # 旧记录应被物理删除，只剩新记录
    assert len(PortalRefreshTokenDB._memory_tokens) == 1
    assert hash1 not in PortalRefreshTokenDB._memory_tokens
    assert hash2 in PortalRefreshTokenDB._memory_tokens


def test_delete_token_removes_record():
    """
    测试 delete_token 物理删除后 verify_token 返回 None。

    Returns:
        None

    Raises:
        AssertionError: 删除后仍能验证通过时抛出。
    """
    now = datetime.utcnow()
    token_hash = PortalRefreshTokenDB.hash_token("token-to-delete")

    asyncio.run(PortalRefreshTokenDB.store_token(token_hash, 1, "alice", now + timedelta(hours=1)))
    assert asyncio.run(PortalRefreshTokenDB.verify_token(token_hash)) is not None

    deleted = asyncio.run(PortalRefreshTokenDB.delete_token(token_hash))
    assert deleted is True
    assert asyncio.run(PortalRefreshTokenDB.verify_token(token_hash)) is None
    assert len(PortalRefreshTokenDB._memory_tokens) == 0


def test_delete_user_tokens_removes_all():
    """
    测试 delete_user_tokens 后该用户记录全部消失。

    Returns:
        None

    Raises:
        AssertionError: 删除后仍存在该用户记录时抛出。
    """
    now = datetime.utcnow()
    hash1 = PortalRefreshTokenDB.hash_token("user1-token1")
    hash2 = PortalRefreshTokenDB.hash_token("user2-token1")

    asyncio.run(PortalRefreshTokenDB.store_token(hash1, 1, "alice", now + timedelta(hours=1)))
    asyncio.run(PortalRefreshTokenDB.store_token(hash2, 2, "bob", now + timedelta(hours=1)))
    assert len(PortalRefreshTokenDB._memory_tokens) == 2

    deleted_count = asyncio.run(PortalRefreshTokenDB.delete_user_tokens(1))
    assert deleted_count == 1
    assert asyncio.run(PortalRefreshTokenDB.verify_token(hash1)) is None
    assert asyncio.run(PortalRefreshTokenDB.verify_token(hash2)) is not None
    assert len(PortalRefreshTokenDB._memory_tokens) == 1


def test_get_users_with_valid_tokens():
    """
    测试 get_users_with_valid_tokens 只返回持有未过期 token 的用户。

    Returns:
        None

    Raises:
        AssertionError: 查询结果包含过期用户或遗漏有效用户时抛出。
    """
    now = datetime.utcnow()
    hash1 = PortalRefreshTokenDB.hash_token("valid-user1")
    hash2 = PortalRefreshTokenDB.hash_token("valid-user2")
    hash3 = PortalRefreshTokenDB.hash_token("expired-user1")
    hash4 = PortalRefreshTokenDB.hash_token("deleted-user1")

    asyncio.run(PortalRefreshTokenDB.store_token(hash1, 1, "alice", now + timedelta(hours=1)))
    asyncio.run(PortalRefreshTokenDB.store_token(hash2, 2, "bob", now + timedelta(hours=1)))
    asyncio.run(PortalRefreshTokenDB.store_token(hash3, 3, "carol", now - timedelta(hours=1)))
    asyncio.run(PortalRefreshTokenDB.store_token(hash4, 4, "dave", now + timedelta(hours=1)))
    asyncio.run(PortalRefreshTokenDB.delete_token(hash4))

    users = asyncio.run(PortalRefreshTokenDB.get_users_with_valid_tokens())
    user_map = {u['user_id']: u['username'] for u in users}
    assert user_map == {1: "alice", 2: "bob"}
