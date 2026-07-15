#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOps 密钥诊断模块（2026-07-15 新增）

职责：
    - 仅做「settings.devops.credential_key 是否可用」的诊断,不做初始化决策
    - 从 ``app.core.config.settings.settings.devops`` 读（统一配置入口）
    - 返回结构化诊断结果,供 lifespan / router 区分 3 类失败原因：
        1. ``missing``        —— settings.devops.credential_key 完全为空
        2. ``misspelled``     —— settings 里读不到,但进程环境里有相近键
                                 （说明用户配在了 shell 而不是 .env）
        3. ``invalid_fernet`` —— 值非空但 Fernet 校验失败

设计原则：
    - 纯函数,不持有状态
    - 不在日志/返回值里打印密钥内容,只回显长度与前缀前 4 字符指纹
    - 由调用方统一映射到 5xx / warning

典型用法（lifespan）：
    diag = diagnose_credential_key()
    if not diag.ok:
        logging.warning("[lifespan] DevOpsServerService skipped: %s", diag.reason)
        # diag.hint 已含可执行提示
        return  # 不挂 app.state,router 会 500 with diag.hint
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from difflib import get_close_matches
from typing import List, Optional

from cryptography.fernet import Fernet


# 期望的环境变量名(全大写,严格匹配)
EXPECTED_ENV_KEY = "DEVOPS_CREDENTIAL_KEY"

# 拼写接近检测词表(运维常见错拼)
_KEYWORD_LIBRARY: List[str] = [
    "DEVOPS_CREDENTIAL_KEY",
    "DEVOPS_CRED_KEY",
    "DEVOPS_FERNET_KEY",
    "DEVOPS_SERVER_CREDENTIAL_KEY",
    "DEVOPS_ENCRYPTION_KEY",
    "EVOPS_CREDENTIAL_KEY",  # 漏字母 D 的高频错拼
    "DEVOPS_CREDENTIALKEY",
]


@dataclass(frozen=True)
class CredentialDiagnosis:
    """DEVOPS_CREDENTIAL_KEY 诊断结果。

    Attributes:
        ok: True 表示密钥可用,False 表示有任一异常
        reason: 失败原因分类标识(missing / misspelled / invalid_fernet)
        hint: 给运维的可执行提示,包含期望键名与当前实际值长度(如有)
        matched_key: 若 ok=True,回显真正命中的环境变量名(用于日志)
        fingerprint: 密钥的前 4 字符指纹(用于日志,绝不打印全值)
    """

    ok: bool
    reason: str = ""
    hint: str = ""
    matched_key: Optional[str] = None
    fingerprint: str = ""


def diagnose_credential_key() -> CredentialDiagnosis:
    """诊断 ``settings.devops.credential_key`` 是否可用。

    Returns:
        CredentialDiagnosis: 结构化诊断结果。``ok=True`` 表示可继续初始化
            ``DevOpsServerService``;``ok=False`` 时 ``hint`` 给出可执行的下一步。

    Notes:
        - 从统一入口 ``app.core.config.settings.settings.devops.credential_key``
          读取;延迟导入 settings 避免循环依赖(settings → 本模块)。
        - 缺失时,扫一遍进程环境变量,挑出含 ``DEVOPS`` / ``CREDENTIAL`` /
          ``FERNET`` 的键,给出拼写接近提示(常见情况:用户把密钥写到了
          shell 环境而非 .env,或拼写错)。
        - Fernet 非法时,只回显长度与前 4 字符指纹,不打印全值。
    """
    # 延迟导入 settings:避免模块加载循环(settings 与 server.py 之间的链路)
    from app.core.config.settings import settings as _app_settings

    raw = (_app_settings.devops.credential_key or "").strip()

    # 1) 完全缺失
    if not raw:
        similar = _find_similar_env_keys()
        # 区分"完全没配" vs "配了但 settings 读不到(env 里有精确键名)"
        exact_in_env = EXPECTED_ENV_KEY in os.environ
        if exact_in_env:
            return CredentialDiagnosis(
                ok=False,
                reason="settings_unread",
                hint=(
                    f"shell 环境里有 {EXPECTED_ENV_KEY},但 settings.devops"
                    f".credential_key 为空。DevOpsSettings 已声明 env_prefix="
                    f"'DEVOPS_'(2026-07-15 修复),正常情况下应能自动读取环境"
                    f"变量;此分支触发说明 settings 单例被显式传入空值覆盖,"
                    f"或 .env 文件路径/编码异常导致未加载。临时绕过:启动前"
                    f" `export {EXPECTED_ENV_KEY}=<密钥>`(直接读 os.environ)。"
                    f"DevOpsServerService 不会初始化,admin API 将返回 500。"
                ),
            )
        if similar:
            return CredentialDiagnosis(
                ok=False,
                reason="misspelled",
                hint=(
                    f"settings.devops.credential_key 为空,且进程环境里发现"
                    f"了相近键 {similar!r}。可能原因:(a) 配置写到了 shell 环"
                    f"境但应用以非交互模式启动未继承;(b) 拼写错(注意全大写 + "
                    f"下划线,大小写不敏感但字符必须完全匹配)。请在 .env 中以 "
                    f"{EXPECTED_ENV_KEY}=<Fernet.generate_key() 的输出> 形式追加。"
                ),
            )
        return CredentialDiagnosis(
            ok=False,
            reason="missing",
            hint=(
                f"settings.devops.credential_key 为空;DevOpsServerService 不会"
                f"初始化,admin API 将返回 500。请在 .env 末尾追加: "
                f"{EXPECTED_ENV_KEY}=<Fernet.generate_key() 的输出> "
                f"(44 字节 url-safe base64)。"
            ),
        )

    # 2) Fernet 合法性校验
    try:
        Fernet(raw.encode("ascii"))
    except (ValueError, TypeError) as exc:
        return CredentialDiagnosis(
            ok=False,
            reason="invalid_fernet",
            hint=(
                f"settings.devops.credential_key 不是合法 Fernet 密钥 "
                f"(长度={len(raw)},前 4 字符={raw[:4]!r});合法密钥必须由 "
                f"Fernet.generate_key() 生成(44 字节 url-safe base64)。原因:{exc!r}"
            ),
            matched_key=EXPECTED_ENV_KEY,
            fingerprint=raw[:4],
        )

    # 3) 通过
    return CredentialDiagnosis(
        ok=True,
        matched_key=EXPECTED_ENV_KEY,
        fingerprint=raw[:4],
    )


def _find_similar_env_keys() -> List[str]:
    """在进程环境里找与期望键名接近的键,用于拼写纠错。

    Returns:
        List[str]: 命中的相近键名(已去重),最多 5 个。
        即使期望键名精确存在,也会保留作为对照(运维可见)。
    """
    candidates: List[str] = []
    needle = EXPECTED_ENV_KEY
    for k in os.environ.keys():
        up = k.upper()
        if "DEVOPS" in up or "EVOPS" in up or "CREDENTIAL" in up or "FERNET" in up:
            candidates.append(k)
    # 再叠加常见错拼词表
    candidates.extend(_KEYWORD_LIBRARY)
    # difflib 过滤:编辑距离 <= 3 且长度差 <= 2
    close = get_close_matches(needle, candidates, n=5, cutoff=0.6)
    # 不过滤 needle 自身——即使精确匹配,运维也需要看到「我配了哪个键」
    # 保持顺序,去重
    seen: set = set()
    out: List[str] = []
    for c in close:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out