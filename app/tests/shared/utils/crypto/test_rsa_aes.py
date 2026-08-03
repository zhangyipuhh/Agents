# -*- coding:utf-8 -*-
"""
RSA-OAEP + AES-256-GCM 加解密单元测试（2026-08-03 新增）。

覆盖目标：
    - ``encrypt_body`` / ``decrypt_body`` roundtrip 一致
    - 篡改密文 / 篡改 tag → 抛 ``RSAEncryptError``
    - 错误 PEM 解析 → 抛 ``RSAEncryptError``
    - ``generate_rsa_keypair_pem`` 返回可解析 PEM 字符串

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations

import base64
import json

import pytest

from app.shared.utils.crypto.rsa_aes import (
    RSAEncryptError,
    decrypt_body,
    encrypt_body,
    generate_rsa_keypair_pem,
)


@pytest.fixture(scope="module")
def rsa_keys() -> dict:
    """生成一对 RSA-2048 密钥（PEM）。"""
    return generate_rsa_keypair_pem()


# ---------------------------------------------------------------------------
# 1. roundtrip
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(rsa_keys: dict) -> None:
    """``encrypt_body`` → ``decrypt_body`` 应返回原始 dict。"""
    plaintext = {
        "command": "echo hello",
        "wrapped_command": "/bin/bash -c 'echo hello'",
        "business_name": "alpha",
        "timeout": 30,
        "platform": "linux",
        "request_id": "uuid-xxx",
        "issued_at": "2026-08-03T00:00:00+00:00",
    }
    encrypted = encrypt_body(
        plaintext, rsa_keys["public_key_pem"]
    )
    # 字段齐
    for k in (
        "algorithm",
        "key_version",
        "encrypted_key",
        "iv",
        "ciphertext",
        "tag",
    ):
        assert k in encrypted
    # algorithm 标签
    assert encrypted["algorithm"] == "RSA-OAEP+AES-256-GCM"
    # base64 可解
    base64.b64decode(encrypted["encrypted_key"])
    base64.b64decode(encrypted["iv"])
    base64.b64decode(encrypted["ciphertext"])
    base64.b64decode(encrypted["tag"])

    decrypted = decrypt_body(encrypted, rsa_keys["private_key_pem"])
    assert decrypted == plaintext


def test_encrypt_produces_different_ciphertext_each_call(
    rsa_keys: dict,
) -> None:
    """同一明文两次加密应得到不同密文（AES key + IV 都是随机）。"""
    plaintext = {"a": 1}
    a = encrypt_body(plaintext, rsa_keys["public_key_pem"])
    b = encrypt_body(plaintext, rsa_keys["public_key_pem"])
    assert a["ciphertext"] != b["ciphertext"]
    assert a["encrypted_key"] != b["encrypted_key"]


# ---------------------------------------------------------------------------
# 2. 篡改 / 错误密钥
# ---------------------------------------------------------------------------


def test_decrypt_with_wrong_key_raises(rsa_keys: dict) -> None:
    """用错误私钥解密应抛 ``RSAEncryptError``。"""
    plaintext = {"x": 1}
    encrypted = encrypt_body(plaintext, rsa_keys["public_key_pem"])
    other = generate_rsa_keypair_pem()
    with pytest.raises(RSAEncryptError):
        decrypt_body(encrypted, other["private_key_pem"])


def test_decrypt_tampered_ciphertext_raises(rsa_keys: dict) -> None:
    """篡改 ciphertext → GCM tag 校验失败 → 抛 ``RSAEncryptError``。"""
    plaintext = {"secret": "value"}
    encrypted = encrypt_body(plaintext, rsa_keys["public_key_pem"])
    # 翻转一个 base64 字符（保证仍是合法 base64 长度但内容错）
    raw = bytearray(base64.b64decode(encrypted["ciphertext"]))
    raw[0] ^= 0xFF
    encrypted["ciphertext"] = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(RSAEncryptError):
        decrypt_body(encrypted, rsa_keys["private_key_pem"])


def test_decrypt_tampered_tag_raises(rsa_keys: dict) -> None:
    """篡改 tag → GCM 校验失败 → 抛 ``RSAEncryptError``。"""
    plaintext = {"secret": "value"}
    encrypted = encrypt_body(plaintext, rsa_keys["public_key_pem"])
    raw_tag = bytearray(base64.b64decode(encrypted["tag"]))
    raw_tag[0] ^= 0xFF
    encrypted["tag"] = base64.b64encode(bytes(raw_tag)).decode("ascii")
    with pytest.raises(RSAEncryptError):
        decrypt_body(encrypted, rsa_keys["private_key_pem"])


def test_decrypt_missing_field_raises(rsa_keys: dict) -> None:
    """payload 缺少必填字段 → 抛 ``RSAEncryptError``。"""
    with pytest.raises(RSAEncryptError):
        decrypt_body({"encrypted_key": "abcd"}, rsa_keys["private_key_pem"])


def test_encrypt_with_invalid_pem_raises() -> None:
    """错误 PEM → 抛 ``RSAEncryptError``。"""
    with pytest.raises(RSAEncryptError):
        encrypt_body({"a": 1}, "not-a-pem")


def test_decrypt_with_invalid_base64_raises(rsa_keys: dict) -> None:
    """payload 中含非法 base64 → 抛 ``RSAEncryptError``。"""
    bad = {
        "algorithm": "RSA-OAEP+AES-256-GCM",
        "key_version": "v1",
        "encrypted_key": "$$$not-base64$$$",
        "iv": "abcd",
        "ciphertext": "abcd",
        "tag": "abcd",
    }
    with pytest.raises(RSAEncryptError):
        decrypt_body(bad, rsa_keys["private_key_pem"])


# ---------------------------------------------------------------------------
# 3. 密钥生成
# ---------------------------------------------------------------------------


def test_generate_rsa_keypair_pem_format() -> None:
    """生成的密钥应为合法 PEM，且能被 cryptography 解析。"""
    keys = generate_rsa_keypair_pem()
    assert keys["private_key_pem"].startswith("-----BEGIN PRIVATE KEY-----")
    assert keys["public_key_pem"].startswith("-----BEGIN PUBLIC KEY-----")
    # roundtrip 一次确保能用
    plaintext = {"k": "v"}
    enc = encrypt_body(plaintext, keys["public_key_pem"])
    dec = decrypt_body(enc, keys["private_key_pem"])
    assert dec == plaintext


def test_decrypt_handles_unicode_payload(rsa_keys: dict) -> None:
    """明文含中文 / emoji 时 roundtrip 正常。"""
    plaintext = {"name": "张三", "emoji": "🚀"}
    enc = encrypt_body(plaintext, rsa_keys["public_key_pem"])
    dec = decrypt_body(enc, rsa_keys["private_key_pem"])
    assert dec == plaintext