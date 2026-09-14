# -*- coding:utf-8 -*-
"""SystemConfigRegistry 集成测试:验证 settings.py 导入后 22 个组全部注册"""
import pytest


@pytest.fixture(scope="module", autouse=True)
def _ensure_settings_imported():
    """在模块级 fixture 里触发 import,只 import 一次"""
    import app.core.config.settings  # noqa: F401
    import app.features.contract_host_agent.config.ContractLLMSettings  # noqa: F401


def test_all_22_groups_registered():
    """settings.py + ContractLLMSettings 导入后,22 个组全部注册"""
    # 触发注册:清空后用 importlib.reload 重新执行模块级注册代码
    import importlib
    import sys
    from app.core.services.system_config_registry import SystemConfigRegistry
    SystemConfigRegistry.clear()  # 清掉单元测试残留
    # 通过 sys.modules 取真实模块(避免 app.core.config.settings 命名遮蔽)
    settings_mod = sys.modules.get("app.core.config.settings")
    contract_mod = sys.modules.get(
        "app.features.contract_host_agent.config.ContractLLMSettings"
    )
    if settings_mod is None:
        import app.core.config.settings  # noqa: F401
        settings_mod = sys.modules["app.core.config.settings"]
    if contract_mod is None:
        import app.features.contract_host_agent.config.ContractLLMSettings  # noqa: F401
        contract_mod = sys.modules[
            "app.features.contract_host_agent.config.ContractLLMSettings"
        ]
    importlib.reload(settings_mod)
    importlib.reload(contract_mod)

    expected = {
        "llm", "vision_llm", "mcp_sampling", "contract_llm",
        "file_parser",
        "auth_cookie", "auth_bootstrap", "auth_idle", "mfa", "registration_security", "session",
        "cors", "portal_auth", "third_party_executor",
        "sandbox", "task_scheduler",
        "word_output", "demonstration", "mcp_tags", "skills", "devops", "system",
    }
    actual = set(SystemConfigRegistry.all().keys())
    missing = expected - actual
    extra = actual - expected
    assert not missing and not extra, f"missing: {missing}, extra: {extra}"


def test_tabs_distribution():
    """孙 Tab 分布正确"""
    import importlib
    import sys
    from app.core.services.system_config_registry import SystemConfigRegistry
    SystemConfigRegistry.clear()
    settings_mod = sys.modules.get("app.core.config.settings")
    contract_mod = sys.modules.get(
        "app.features.contract_host_agent.config.ContractLLMSettings"
    )
    if settings_mod is None:
        import app.core.config.settings  # noqa: F401
        settings_mod = sys.modules["app.core.config.settings"]
    if contract_mod is None:
        import app.features.contract_host_agent.config.ContractLLMSettings  # noqa: F401
        contract_mod = sys.modules[
            "app.features.contract_host_agent.config.ContractLLMSettings"
        ]
    importlib.reload(settings_mod)
    importlib.reload(contract_mod)

    tabs = {}
    for meta in SystemConfigRegistry.all().values():
        tabs.setdefault(meta.tab, []).append(meta.group_key)
    assert set(tabs.keys()) == {"llm", "file-parser", "security", "network", "sandbox-task", "misc"}
    assert set(tabs["llm"]) == {"llm", "vision_llm", "mcp_sampling", "contract_llm"}
    assert set(tabs["security"]) == {"auth_cookie", "auth_bootstrap", "auth_idle", "mfa", "registration_security", "session"}


def test_sensitive_fields_marked():
    """敏感字段标记正确"""
    import importlib
    import sys
    from app.core.services.system_config_registry import SystemConfigRegistry
    SystemConfigRegistry.clear()
    settings_mod = sys.modules.get("app.core.config.settings")
    contract_mod = sys.modules.get(
        "app.features.contract_host_agent.config.ContractLLMSettings"
    )
    if settings_mod is None:
        import app.core.config.settings  # noqa: F401
        settings_mod = sys.modules["app.core.config.settings"]
    if contract_mod is None:
        import app.features.contract_host_agent.config.ContractLLMSettings  # noqa: F401
        contract_mod = sys.modules[
            "app.features.contract_host_agent.config.ContractLLMSettings"
        ]
    importlib.reload(settings_mod)
    importlib.reload(contract_mod)

    # 至少这 7 个组应有 sensitive_fields
    expected_sensitive = {
        "llm": ["model_api_key"],
        "vision_llm": ["model_api_key_vision"],
        "mcp_sampling": ["mcp_sampling_model_api_key"],
        "contract_llm": ["model_api_key"],
        "auth_bootstrap": ["default_admin_password"],
        "mfa": ["secret_key"],
        "devops": ["credential_key"],
    }
    for group_key, fields in expected_sensitive.items():
        meta = SystemConfigRegistry.get(group_key)
        assert meta.sensitive_fields == fields, \
            f"{group_key} sensitive_fields mismatch: {meta.sensitive_fields} vs {fields}"
