# -*- coding:utf-8 -*-
"""基本设置 Fernet 加解密与脱敏工具

职责:
- bootstrap_master_key: 首次启动自动生成密钥落盘(避免鸡生蛋死锁)
- get_master_fernet: 从 SETTINGS_SECRET_KEY 环境变量或密钥文件构造 Fernet 单例
- encrypt_value: 加密字符串,返回值带 'fernet:' 前缀
- decrypt_value: 解密 'fernet:' 前缀字符串;非前缀值原样返回(向后兼容)
- mask_value: 脱敏为 '****' 或 '****<后4位>'
- is_encrypted: 判断是否已加密

异常:
- RuntimeError: SETTINGS_SECRET_KEY 非空但非法(fail-loud)
            缺失时不再 fail-loud,而是自动 bootstrap 到 data/secrets/

密钥存储分层策略(2026-09-14 修订):
- 真正的 Fernet 密钥(SETTINGS_SECRET_KEY / MFA_SECRET_KEY / DEVOPS_CREDENTIAL_KEY)
  留在 .env 或密钥文件,永远不入 DB(丢失密钥 = DB 中加密字段全报废)
- 凭据类(model_api_key 等)由 SETTINGS_SECRET_KEY 加密后入 DB
- 配置类(URL / 温度 / 开关)直接明文入 DB
"""
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config.paths import SETTINGS_SECRET_KEY_FILE

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "fernet:"


def _read_key_from_file() -> Optional[str]:
    """从 data/secrets/settings_secret.key 读取已 bootstrap 的密钥。

    Returns:
        Optional[str]: 文件存在且非空返回 key 字符串;否则 None。
    """
    try:
        path = Path(SETTINGS_SECRET_KEY_FILE)
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content or None
    except OSError as exc:
        logger.warning("[settings_crypto] 读取密钥文件失败: %s", exc)
        return None


def bootstrap_master_key() -> str:
    """首次启动自动生成 Fernet 密钥并落盘到 data/secrets/settings_secret.key。

    设计动机:
        解决"用户进 UI 配置敏感字段前必须先生成密钥"的鸡生蛋死锁。
        首次部署 .env 中 SETTINGS_SECRET_KEY 为空 → lifespan 自动 bootstrap,
        同时在 UI 顶栏提示用户"密钥已自动生成,请妥善备份"。

    行为:
        1. 若文件已存在 → 直接读取(防止覆盖已有密钥,避免 DB 中加密字段全报废)
        2. 若文件不存在 → 生成新密钥,写入文件,权限 0600(Windows 上 OSError 容忍)
        3. 写一条醒目的 WARNING 日志,提醒运维备份

    Returns:
        str: 已落盘的密钥字符串(url-safe base64 编码)

    Raises:
        RuntimeError: 无法写入密钥文件(权限/磁盘满)
    """
    existing = _read_key_from_file()
    if existing:
        logger.info(
            "[settings_crypto] 检测到已存在的密钥文件 %s,复用不覆盖",
            SETTINGS_SECRET_KEY_FILE,
        )
        return existing

    new_key = Fernet.generate_key().decode("ascii")
    try:
        path = Path(SETTINGS_SECRET_KEY_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_key, encoding="utf-8")
        # 权限收紧:仅 owner 可读写。Windows 不支持 POSIX 模式,容忍 OSError
        try:
            os.chmod(path, 0o600)
        except (OSError, AttributeError):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"无法写入密钥文件 {SETTINGS_SECRET_KEY_FILE}: {exc}. "
            f"请检查 data/secrets/ 目录权限或手动设置 .env 中的 SETTINGS_SECRET_KEY"
        ) from exc

    logger.warning(
        "[settings_crypto] 首次启动自动生成 Fernet 主密钥并落盘到 %s。"
        "请立即备份此文件;丢失将导致 DB 中所有加密字段(api_key / mfa_secret / "
        "devops_credential 等)无法解密。",
        SETTINGS_SECRET_KEY_FILE,
    )
    return new_key


@lru_cache(maxsize=1)
def get_master_fernet() -> Fernet:
    """从 SETTINGS_SECRET_KEY 或密钥文件构造 Fernet 单例。

    解析优先级(2026-09-14 修订):
        1. 环境变量 SETTINGS_SECRET_KEY 非空 → 用 env 值
        2. env 缺失/空 → 调 bootstrap_master_key() 从 data/secrets/ 读取或生成
        3. env 非空但非法 → RuntimeError fail-loud

    Returns:
        Fernet: 加解密实例

    Raises:
        RuntimeError: SETTINGS_SECRET_KEY 非空但非法(非 Fernet 格式)
    """
    env_key = os.getenv("SETTINGS_SECRET_KEY", "").strip()

    if not env_key:
        # env 缺失/空 → 走 bootstrap(读文件或生成新文件)
        effective_key = bootstrap_master_key()
    else:
        effective_key = env_key

    try:
        return Fernet(effective_key.encode("ascii"))
    except Exception as exc:
        raise RuntimeError(
            f"SETTINGS_SECRET_KEY 非法(非合法 Fernet 格式): {exc}. "
            f"如需重新生成请删除 .env 中 SETTINGS_SECRET_KEY 行(或设为空),"
            f"系统将自动 bootstrap 新密钥到 {SETTINGS_SECRET_KEY_FILE}"
        ) from exc


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
