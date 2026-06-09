# -*- coding:utf-8 -*-
"""
Refresh Token 数据库测试模块

测试 app.shared.utils.auth.refresh_token_db 在 memory 模式下的
token 哈希存储、验证和删除逻辑。
"""
import asyncio
from datetime import datetime, timedelta

import pytest

from app.shared.utils.auth.refresh_token_db import RefreshTokenDB


@pytest.fixture(autouse=True)
def reset_token_db():
    """
    每个测试前清空 RefreshTokenDB 内存存储。

    Returns:
        None
    """
    RefreshTokenDB._memory_tokens.clear()
    yield
    RefreshTokenDB._memory_tokens.clear()


def test_hash_token():
    """
    测试 hash_token 对相同输入生成一致的 SHA256 哈希值。

    Returns:
        None

    Raises:
        AssertionError: 哈希值不一致或格式不正确时抛出。
    """
    hash1 = RefreshTokenDB.hash_token("same")
    hash2 = RefreshTokenDB.hash_token("same")
    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 64  # SHA256 十六进制长度为 64


def test_store_and_verify_token():
    """
    测试存储 token 后能够成功验证并返回正确的 user_id。

    Returns:
        None

    Raises:
        AssertionError: 验证失败或返回的 user_id 不正确时抛出。
    """
    token = "my-refresh-token"
    token_hash = RefreshTokenDB.hash_token(token)
    expires = datetime.utcnow() + timedelta(hours=1)
    asyncio.run(RefreshTokenDB.store_token(token_hash, 1, expires))

    result = asyncio.run(RefreshTokenDB.verify_token(token_hash))
    assert result is not None
    assert result["user_id"] == 1


def test_verify_expired_token():
    """
    测试已过期的 token 验证返回 None。

    Returns:
        None

    Raises:
        AssertionError: 过期 token 仍被验证通过时抛出。
    """
    token = "expired-token"
    token_hash = RefreshTokenDB.hash_token(token)
    expires = datetime.utcnow() - timedelta(hours=1)
    asyncio.run(RefreshTokenDB.store_token(token_hash, 1, expires))

    result = asyncio.run(RefreshTokenDB.verify_token(token_hash))
    assert result is None


def test_delete_token():
    """
    测试删除指定 token 后再次验证返回 None。

    Returns:
        None

    Raises:
        AssertionError: 删除失败或删除后仍能验证通过时抛出。
    """
    token = "token-to-delete"
    token_hash = RefreshTokenDB.hash_token(token)
    expires = datetime.utcnow() + timedelta(hours=1)
    asyncio.run(RefreshTokenDB.store_token(token_hash, 1, expires))

    assert asyncio.run(RefreshTokenDB.delete_token(token_hash)) is True
    assert asyncio.run(RefreshTokenDB.verify_token(token_hash)) is None


def test_delete_user_tokens():
    """
    测试删除用户的所有 token 后，该用户的所有 token 均无法验证。

    Returns:
        None

    Raises:
        AssertionError: 删除后仍存在可验证的 token 时抛出。
    """
    expires = datetime.utcnow() + timedelta(hours=1)
    hash1 = RefreshTokenDB.hash_token("token-1")
    hash2 = RefreshTokenDB.hash_token("token-2")
    hash3 = RefreshTokenDB.hash_token("token-3")

    asyncio.run(RefreshTokenDB.store_token(hash1, 1, expires))
    asyncio.run(RefreshTokenDB.store_token(hash2, 1, expires))
    asyncio.run(RefreshTokenDB.store_token(hash3, 2, expires))

    deleted_count = asyncio.run(RefreshTokenDB.delete_user_tokens(1))
    assert deleted_count == 2
    assert asyncio.run(RefreshTokenDB.verify_token(hash1)) is None
    assert asyncio.run(RefreshTokenDB.verify_token(hash2)) is None
    assert asyncio.run(RefreshTokenDB.verify_token(hash3)) is not None


def test_cleanup_expired():
    """
    测试清理过期 token 只删除已过期条目，保留未过期条目。

    Returns:
        None

    Raises:
        AssertionError: 清理数量不正确或未过期 token 被误删时抛出。
    """
    now = datetime.utcnow()
    hash1 = RefreshTokenDB.hash_token("valid-token")
    hash2 = RefreshTokenDB.hash_token("expired-token")

    asyncio.run(RefreshTokenDB.store_token(hash1, 1, now + timedelta(hours=1)))
    asyncio.run(RefreshTokenDB.store_token(hash2, 1, now - timedelta(hours=1)))

    cleaned = asyncio.run(RefreshTokenDB.cleanup_expired())
    assert cleaned == 1
    assert asyncio.run(RefreshTokenDB.verify_token(hash1)) is not None
    assert asyncio.run(RefreshTokenDB.verify_token(hash2)) is None


class TestHasValidToken:
    """测试 has_valid_token 方法"""

    def test_has_valid_token_importable(self):
        """
        验证 has_valid_token 方法可调用
        """
        assert hasattr(RefreshTokenDB, 'has_valid_token')
        assert callable(RefreshTokenDB.has_valid_token)

    def test_has_valid_token_returns_true_when_exists(self, monkeypatch):
        """
        测试场景：用户存在未过期的 refresh_token

        参数:
            monkeypatch: pytest monkeypatch fixture

        预期结果:
            返回 True
        """
        from unittest.mock import AsyncMock

        mock_fetchrow = AsyncMock(return_value={'exists': 1})
        monkeypatch.setattr(
            'app.shared.utils.auth.refresh_token_db.DatabasePool.fetchrow',
            mock_fetchrow
        )
        monkeypatch.setattr(
            'app.shared.utils.auth.refresh_token_db.DatabasePool.is_enabled',
            lambda: True
        )

        result = asyncio.run(RefreshTokenDB.has_valid_token(1))
        assert result is True
        mock_fetchrow.assert_called_once()

    def test_has_valid_token_returns_false_when_not_exists(self, monkeypatch):
        """
        测试场景：用户不存在有效的 refresh_token（被踢后）

        参数:
            monkeypatch: pytest monkeypatch fixture

        预期结果:
            返回 False
        """
        from unittest.mock import AsyncMock

        mock_fetchrow = AsyncMock(return_value=None)
        monkeypatch.setattr(
            'app.shared.utils.auth.refresh_token_db.DatabasePool.fetchrow',
            mock_fetchrow
        )
        monkeypatch.setattr(
            'app.shared.utils.auth.refresh_token_db.DatabasePool.is_enabled',
            lambda: True
        )

        result = asyncio.run(RefreshTokenDB.has_valid_token(1))
        assert result is False

    def test_has_valid_token_memory_mode(self, monkeypatch):
        """
        测试场景：memory 模式下用户存在有效 token

        参数:
            monkeypatch: pytest monkeypatch fixture

        预期结果:
            返回 True
        """
        from datetime import timedelta

        monkeypatch.setattr(
            'app.shared.utils.auth.refresh_token_db.DatabasePool.is_enabled',
            lambda: False
        )
        # 清理内存缓存
        RefreshTokenDB._memory_tokens.clear()
        RefreshTokenDB._memory_tokens['hash1'] = {
            'user_id': 1,
            'expires_at': datetime.utcnow() + timedelta(hours=1)
        }

        result = asyncio.run(RefreshTokenDB.has_valid_token(1))
        assert result is True

        # 清理
        RefreshTokenDB._memory_tokens.clear()
