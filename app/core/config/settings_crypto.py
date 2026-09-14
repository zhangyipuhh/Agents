# -*- coding:utf-8 -*-
"""基本设置 Fernet 加解密与脱敏工具

职责:
- get_master_fernet: 从 SETTINGS_SECRET_KEY 环境变量构造 Fernet 单例
- encrypt_value: 加密字符串,返回值带 'fernet:' 前缀
- decrypt_value: 解密 'fernet:' 前缀字符串;非前缀值原样返回(向后兼容)
- mask_value: 脱敏为 '****' 或 '****<后4位>'
- is_encrypted: 判断是否已加密

异常:
- RuntimeError: SETTINGS_SECRET_KEY 缺失或非法(fail-loud)
"""
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_FERNET_PREFIX = "fernet:"


@lru_cache(maxsize=1)
def get_master_fernet() -> Fernet:
    """从 SETTINGS_SECRET_KEY 构造 Fernet 单例

    Returns:
        Fernet: 加解密实例

    Raises:
        RuntimeError: 环境变量缺失或非法
    """
    key = os.getenv("SETTINGS_SECRET_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "SETTINGS_SECRET_KEY 未配置;请生成后填入 .env "
            "(python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")"
        )
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise RuntimeError(f"SETTINGS_SECRET_KEY 非法: {exc}") from exc


def encrypt_value(plain: str) -> str:
    """加密字符串,返回 'fernet:' 前缀密文

    Args:
        plain: 明文字符串;空串原样返回

    Returns:
        str: 'fernet:<base64>' 或 空串
    """
    if not plain:
        return ""
    token = get_master_fernet().encrypt(plain.encode("utf-8"))
    return _FERNET_PREFIX + token.decode("ascii")


def decrypt_value(value: str) -> str:
    """解密 'fernet:' 前缀字符串;非前缀值原样返回

    Args:
        value: 待解密字符串

    Returns:
        str: 解密后明文,或原值

    Raises:
        RuntimeError: 密文非法或密钥不匹配
    """
    if not value:
        return ""
    if not value.startswith(_FERNET_PREFIX):
        return value
    token = value[len(_FERNET_PREFIX):]
    try:
        plain_bytes = get_master_fernet().decrypt(token.encode("ascii"))
        return plain_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("SETTINGS_SECRET_KEY 与密文不匹配,解密失败") from exc


def is_encrypted(value: str) -> bool:
    """判断字符串是否带 'fernet:' 前缀"""
    return bool(value) and value.startswith(_FERNET_PREFIX)


def mask_value(value: str) -> str:
    """脱敏

    规则:
    - 空串 → 空串
    - 已加密(fernet: 前缀) → '****'
    - 长度 <= 4 → '****'
    - 长度 > 4 → '****' + 后 4 位

    Args:
        value: 原始值

    Returns:
        str: 脱敏后值
    """
    if not value:
        return ""
    if is_encrypted(value):
        return "****"
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]
