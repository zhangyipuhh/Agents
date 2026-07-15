# -*- coding:utf-8 -*-
"""
DevOps 密钥诊断单元测试（2026-07-15 新增）

目标：
    - 覆盖 ``app.core.config.devops_diagnostics.diagnose_credential_key`` 三类失败分支
    - 不依赖任何生产 lifespan / DB / Fernet，仅测试纯函数逻辑
    - 通过 ``monkeypatch`` 修改 ``settings.devops.credential_key`` 与
      ``os.environ`` 模拟不同输入，避免污染全局

被测对象：
    - diagnose_credential_key() -> CredentialDiagnosis
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


# 复用合法 Fernet 密钥（44 字节 url-safe base64）
VALID_FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture
def reset_devops_credential(monkeypatch):
    """每个用例前后重置 settings.devops.credential_key 与进程环境，避免污染。

    注意：pydantic v2 的 BaseSettings 自定义 __getattr__,会拦截对未知属性的访问,
    因此测试中必须把 settings 单例绑定到本地变量再 monkeypatch,
    不能 ``monkeypatch.setattr(_settings_module, "settings", ...)``。

    Yields:
        monkeypatch: pytest 内建 fixture
    """
    from app.core.config.settings import DevOpsSettings, settings as _app_settings

    # 重置 DevOpsSettings 字段:直接给 settings 单例的 devops 子 settings 重新赋值
    fresh = DevOpsSettings(credential_key="")
    monkeypatch.setattr(_app_settings, "devops", fresh)
    # 清空环境里可能干扰的键
    for k in ("DEVOPS_CREDENTIAL_KEY", "EVOPS_CREDENTIAL_KEY", "DEVOPS_FERNET_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch
    # 用例结束后恢复默认 .env 读到的 devops,避免污染后续用例
    monkeypatch.setattr(_app_settings, "devops", DevOpsSettings())


def test_diagnose_missing_when_no_env_and_empty_settings(reset_devops_credential):
    """完全缺失分支：settings 为空 + 进程环境无精确键 → hint 提示用户配置。"""
    from app.core.config.devops_diagnostics import diagnose_credential_key

    diag = diagnose_credential_key()
    assert diag.ok is False
    # 允许 missing / misspelled / settings_unread 任一种:只要 hint 提示用户该改哪个键即可
    assert diag.reason in ("missing", "misspelled", "settings_unread")
    assert "DEVOPS_CREDENTIAL_KEY" in diag.hint


def test_diagnose_misspelled_when_env_has_similar_key(reset_devops_credential, monkeypatch):
    """拼写接近分支：settings 为空，但环境里有 EVOPS_CREDENTIAL_KEY（漏字母 D）→ misspelled。"""
    from app.core.config.devops_diagnostics import diagnose_credential_key

    # 模拟运维把密钥配到 shell 而非 .env,且拼写错
    monkeypatch.setenv("EVOPS_CREDENTIAL_KEY", VALID_FERNET_KEY)
    diag = diagnose_credential_key()
    assert diag.ok is False
    assert diag.reason == "misspelled"
    # hint 应该提到相近键
    assert "EVOPS_CREDENTIAL_KEY" in diag.hint
    assert "DEVOPS_CREDENTIAL_KEY" in diag.hint


def test_diagnose_invalid_fernet_returns_invalid_fernet_reason(reset_devops_credential):
    """Fernet 非法分支：settings 有值但不是合法密钥 → invalid_fernet + 指纹不打印全值。"""
    from app.core.config.settings import DevOpsSettings, settings as _app_settings
    from app.core.config.devops_diagnostics import diagnose_credential_key

    bad_key = "not-a-real-fernet-key-1234567890"
    _app_settings.devops = DevOpsSettings(credential_key=bad_key)
    diag = diagnose_credential_key()
    assert diag.ok is False
    assert diag.reason == "invalid_fernet"
    # 不打印全值,只显示长度+前 4 字符
    assert bad_key not in diag.hint
    assert f"长度={len(bad_key)}" in diag.hint
    assert "前 4 字符='not-'" in diag.hint


def test_diagnose_ok_returns_true_with_fingerprint(reset_devops_credential):
    """正常路径：settings 有合法 Fernet 密钥 → ok=True + 指纹只露前 4 字符。"""
    from app.core.config.settings import DevOpsSettings, settings as _app_settings
    from app.core.config.devops_diagnostics import diagnose_credential_key

    _app_settings.devops = DevOpsSettings(credential_key=VALID_FERNET_KEY)
    diag = diagnose_credential_key()
    assert diag.ok is True
    assert diag.reason == ""
    assert diag.matched_key == "DEVOPS_CREDENTIAL_KEY"
    assert diag.fingerprint == VALID_FERNET_KEY[:4]
    # 指纹不应包含完整密钥
    assert VALID_FERNET_KEY not in diag.fingerprint


def test_diagnose_strips_whitespace(reset_devops_credential):
    """首尾空白应被忽略：'   ' → 视为空 → ok=False 且 hint 提示用户。"""
    from app.core.config.settings import DevOpsSettings, settings as _app_settings
    from app.core.config.devops_diagnostics import diagnose_credential_key

    _app_settings.devops = DevOpsSettings(credential_key="   ")
    diag = diagnose_credential_key()
    assert diag.ok is False
    assert diag.reason in ("missing", "misspelled", "settings_unread")
    assert "DEVOPS_CREDENTIAL_KEY" in diag.hint


def test_diagnose_credential_diagnosis_is_frozen_dataclass():
    """CredentialDiagnosis 是 frozen dataclass，避免外部修改。"""
    from app.core.config.devops_diagnostics import CredentialDiagnosis

    d = CredentialDiagnosis(ok=True, fingerprint="abcd")
    with pytest.raises(Exception):
        # frozen=True 不允许赋值
        d.ok = False  # type: ignore[misc]


def test_diagnose_ok_path_does_not_leak_full_key_in_hint(reset_devops_credential):
    """通过路径 hint 为空 → 不存在密钥泄漏路径。"""
    from app.core.config.settings import DevOpsSettings, settings as _app_settings
    from app.core.config.devops_diagnostics import diagnose_credential_key

    _app_settings.devops = DevOpsSettings(credential_key=VALID_FERNET_KEY)
    diag = diagnose_credential_key()
    assert diag.ok is True
    assert diag.hint == ""
    # 指纹只露前 4 字符
    assert diag.fingerprint == VALID_FERNET_KEY[:4]
    assert len(diag.fingerprint) < len(VALID_FERNET_KEY)


def test_diagnose_settings_unread_when_exact_env_key_present(reset_devops_credential, monkeypatch):
    """settings_unread 分支：settings 为空,但 shell 环境里有精确键名(用户当前场景)。"""
    from app.core.config.devops_diagnostics import diagnose_credential_key

    # 用户 .env 已配,启动时被 shell 继承 → os.environ 里有这个键
    monkeypatch.setenv("DEVOPS_CREDENTIAL_KEY", VALID_FERNET_KEY)
    diag = diagnose_credential_key()
    assert diag.ok is False
    assert diag.reason == "settings_unread"
    # hint 必须提到嵌套 BaseSettings 这个根因
    assert "嵌套 BaseSettings" in diag.hint or "BaseSettings" in diag.hint
    # 必须给出临时绕过方式
    assert "export" in diag.hint or "os.environ" in diag.hint