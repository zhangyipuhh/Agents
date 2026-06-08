# -*- coding:utf-8 -*-
"""
验证码测试模块

测试 app.shared.utils.auth.captcha 中 CaptchaManager 的
生成、验证正确性、验证错误性以及过期逻辑。
"""
import time
from unittest.mock import patch

import pytest

from app.shared.utils.auth.captcha import CaptchaManager


@pytest.fixture(autouse=True)
def reset_captcha_cache():
    """
    每个测试前清空验证码内存缓存。

    Returns:
        None
    """
    CaptchaManager._cache.clear()
    yield
    CaptchaManager._cache.clear()


def test_generate_returns_tuple():
    """
    测试 generate 返回 (key, base64_image) 元组，且图片为 base64 PNG 格式。

    注意：conftest 中全局 mock 了 generate，返回固定的测试用 key 和图片。

    Returns:
        None

    Raises:
        AssertionError: 返回值格式不正确时抛出。
    """
    key, image = CaptchaManager.generate()
    assert isinstance(key, str)
    assert isinstance(image, str)
    assert image.startswith("data:image/png;base64,")
    assert len(key) > 0


def test_verify_correct_code():
    """
    测试输入正确验证码时 verify 返回 True，且不区分大小写。

    由于 generate 被全局 mock，这里直接向 _cache 写入测试数据。
    注意 verify 内部使用 pop 消耗 key，因此大小写测试需使用不同 key。

    Returns:
        None

    Raises:
        AssertionError: 正确验证码被判定为错误时抛出。
    """
    CaptchaManager._cache["test_key_1"] = {
        "code": "ABCD",
        "created_at": time.time(),
    }
    assert CaptchaManager.verify("test_key_1", "ABCD") is True

    CaptchaManager._cache["test_key_2"] = {
        "code": "ABCD",
        "created_at": time.time(),
    }
    assert CaptchaManager.verify("test_key_2", "abcd") is True  # 不区分大小写


def test_verify_wrong_code():
    """
    测试输入错误验证码时 verify 返回 False。

    Returns:
        None

    Raises:
        AssertionError: 错误验证码被判定为正确时抛出。
    """
    CaptchaManager._cache["test_key"] = {
        "code": "ABCD",
        "created_at": time.time(),
    }
    assert CaptchaManager.verify("test_key", "WXYZ") is False
    assert CaptchaManager.verify("test_key", "1234") is False


def test_verify_expired_code():
    """
    测试过期验证码 verify 返回 False（mock time.time 使验证码超过 300 秒有效期）。

    Returns:
        None

    Raises:
        AssertionError: 过期验证码仍被验证通过时抛出。
    """
    CaptchaManager._cache["test_key"] = {
        "code": "ABCD",
        "created_at": time.time(),
    }
    with patch("time.time", return_value=time.time() + 400):
        assert CaptchaManager.verify("test_key", "ABCD") is False


def test_verify_nonexistent_key():
    """
    测试验证不存在的 key 返回 False。

    Returns:
        None

    Raises:
        AssertionError: 不存在的 key 被验证通过时抛出。
    """
    assert CaptchaManager.verify("nonexistent-key", "ABCD") is False
