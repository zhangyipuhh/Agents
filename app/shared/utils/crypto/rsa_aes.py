# -*- coding:utf-8 -*-
"""
RSA-OAEP + AES-256-GCM 混合加解密工具（2026-08-03 新增）。

设计动机：
    - RSA 只能加密小数据块（RSA-2048 单次最多加密 245 字节），无法直接加密请求体。
    - 行业标准做法是用 RSA 加密 AES 会话密钥 + AES 加密实际数据（GCM 提供认证加密）。

算法选择：
    - RSA-2048，OAEP padding，SHA-256 MGF1
    - AES-256-GCM（带 16 字节认证标签，防篡改）
    - IV 长度 12 字节（``os.urandom`` 随机）
    - 会话密钥 32 字节（``os.urandom`` 随机）

传输 payload 结构（明文 → 密文）::

    {
        "algorithm": "RSA-OAEP+AES-256-GCM",
        "key_version": "v1",
        "encrypted_key": "<base64>",   # RSA-OAEP 加密的 32 字节 AES key
        "iv": "<base64>",              # 12 字节
        "ciphertext": "<base64>",      # AES-GCM 密文
        "tag": "<base64>",             # 16 字节 GCM tag
    }

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ALGORITHM_TAG: str = "RSA-OAEP+AES-256-GCM"
KEY_VERSION: str = "v1"
AES_KEY_BYTES: int = 32  # AES-256
GCM_IV_BYTES: int = 12   # GCM 推荐 12 字节
GCM_TAG_BYTES: int = 16  # GCM tag 固定 16 字节
RSA_KEY_BITS: int = 2048


class RSAEncryptError(Exception):
    """RSA / AES 加解密失败统一异常。"""


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _b64e(raw: bytes) -> str:
    """bytes → base64 字符串（不带换行）。

    Args:
        raw: 原始字节

    Returns:
        str: base64 编码
    """
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    """base64 字符串 → bytes（容错 strip / 换行）。

    Args:
        text: base64 字符串

    Returns:
        bytes: 原始字节

    Raises:
        RSAEncryptError: 解码失败时抛出
    """
    try:
        return base64.b64decode(text.strip(), validate=False)
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"base64 解码失败: {exc}") from exc


def _load_public_key(pem: str):
    """解析 PEM 格式 RSA 公钥。

    Args:
        pem: 公钥 PEM 字符串

    Returns:
        RSAPublicKey: cryptography 公钥对象

    Raises:
        RSAEncryptError: 解析失败时抛出
    """
    try:
        return serialization.load_pem_public_key(pem.encode("ascii"))
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"RSA 公钥解析失败: {exc}") from exc


def _load_private_key(pem: str):
    """解析 PEM 格式 RSA 私钥（用于单元测试 / 接收方参考实现）。

    Args:
        pem: 私钥 PEM 字符串

    Returns:
        RSAPrivateKey: cryptography 私钥对象

    Raises:
        RSAEncryptError: 解析失败时抛出
    """
    try:
        return serialization.load_pem_private_key(
            pem.encode("ascii"), password=None
        )
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"RSA 私钥解析失败: {exc}") from exc


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def generate_rsa_keypair_pem() -> Dict[str, str]:
    """生成 RSA-2048 密钥对并返回 PEM 字符串。

    用于开发 / 单元测试 / 给第三方分发公钥时使用。
    生产环境请通过 ``openssl genrsa`` 离线生成并妥善保管。

    Returns:
        Dict[str, str]: ``{"private_key_pem": "...", "public_key_pem": "..."}``
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=RSA_KEY_BITS
    )
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return {"private_key_pem": private_pem, "public_key_pem": public_pem}


def encrypt_body(
    plaintext: Dict[str, Any],
    recipient_public_key_pem: str,
    *,
    key_version: str = KEY_VERSION,
) -> Dict[str, str]:
    """加密请求体（RSA-OAEP 加密 AES key + AES-GCM 加密 body）。

    Args:
        plaintext: 待加密的 dict（会被 ``json.dumps`` 序列化）
        recipient_public_key_pem: 接收方 RSA 公钥 PEM
        key_version: 密钥版本标签，写入 payload 便于接收方多版本兼容

    Returns:
        Dict[str, str]: 传输 payload（``algorithm`` / ``key_version`` /
            ``encrypted_key`` / ``iv`` / ``ciphertext`` / ``tag`` 全为字符串）

    Raises:
        RSAEncryptError: 序列化 / 加密失败时抛出
    """
    try:
        body_bytes = json.dumps(plaintext, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RSAEncryptError(f"请求体 JSON 序列化失败: {exc}") from exc

    # 1. 生成临时 AES 会话密钥 + IV
    aes_key = os.urandom(AES_KEY_BYTES)
    iv = os.urandom(GCM_IV_BYTES)

    # 2. 用 AES-GCM 加密 body
    try:
        aesgcm = AESGCM(aes_key)
        ct_with_tag = aesgcm.encrypt(iv, body_bytes, None)
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"AES-GCM 加密失败: {exc}") from exc
    # cryptography 的 AESGCM 返回 ciphertext || tag (16 字节)；拆分便于接收方按字段校验
    ciphertext, tag = ct_with_tag[:-GCM_TAG_BYTES], ct_with_tag[-GCM_TAG_BYTES:]

    # 3. 用 RSA-OAEP 加密 AES key
    pub = _load_public_key(recipient_public_key_pem)
    try:
        encrypted_key = pub.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"RSA-OAEP 加密失败: {exc}") from exc

    return {
        "algorithm": ALGORITHM_TAG,
        "key_version": key_version,
        "encrypted_key": _b64e(encrypted_key),
        "iv": _b64e(iv),
        "ciphertext": _b64e(ciphertext),
        "tag": _b64e(tag),
    }


def decrypt_body(payload: Dict[str, Any], private_key_pem: str) -> Dict[str, Any]:
    """解密 ``encrypt_body`` 的输出（接收方参考实现 / 测试用）。

    生产环境由第三方实现解密；本函数用于：
      - 单元测试 roundtrip
      - 自建 mock 第三方时复用

    Args:
        payload: 加密后的 dict
        private_key_pem: 本方 RSA 私钥 PEM

    Returns:
        Dict[str, Any]: 解密后的明文 dict

    Raises:
        RSAEncryptError: 任何加解密 / 解析失败时抛出
    """
    for key in ("encrypted_key", "iv", "ciphertext", "tag"):
        if key not in payload or not isinstance(payload[key], str):
            raise RSAEncryptError(f"payload 缺少字段: {key}")

    encrypted_key = _b64d(payload["encrypted_key"])
    iv = _b64d(payload["iv"])
    ciphertext = _b64d(payload["ciphertext"])
    tag = _b64d(payload["tag"])

    if len(iv) != GCM_IV_BYTES:
        raise RSAEncryptError(f"IV 长度非法: {len(iv)} (期望 {GCM_IV_BYTES})")
    if len(tag) != GCM_TAG_BYTES:
        raise RSAEncryptError(f"GCM tag 长度非法: {len(tag)} (期望 {GCM_TAG_BYTES})")

    priv = _load_private_key(private_key_pem)
    try:
        aes_key = priv.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"RSA-OAEP 解密失败: {exc}") from exc

    try:
        aesgcm = AESGCM(aes_key)
        plaintext_bytes = aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"AES-GCM 解密失败（密文被篡改？）: {exc}") from exc

    try:
        return json.loads(plaintext_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RSAEncryptError(f"明文 JSON 解析失败: {exc}") from exc