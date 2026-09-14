# -*- coding:utf-8 -*-
"""SystemConfigRegistry 单元测试

测试目标:
- register / get / all / has / clear 基本行为
- 重复注册同 group_key → 抛 ValueError
- GroupMeta 三种来源互斥校验(settings_cls / field_specs 二选一)
"""
import pytest
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from app.core.services.system_config_registry import (
    FieldSpec,
    GroupMeta,
    SystemConfigRegistry,
)


class _DummySettings(BaseSettings):
    """测试用 Settings 子类"""
    foo: str = "default-foo"
    secret: str = "default-secret"


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个用例前后清空注册表,避免用例间污染"""
    SystemConfigRegistry.clear()
    yield
    SystemConfigRegistry.clear()


class TestRegister:
    def test_register_with_settings_cls(self):
        SystemConfigRegistry.register(
            group_key="llm",
            tab="llm",
            label="主模型",
            settings_cls=_DummySettings,
            sensitive_fields=["secret"],
        )
        assert SystemConfigRegistry.has("llm")
        meta = SystemConfigRegistry.get("llm")
        assert meta.group_key == "llm"
        assert meta.tab == "llm"
        assert meta.label == "主模型"
        assert meta.settings_cls is _DummySettings
        assert meta.sensitive_fields == ["secret"]
        assert meta.field_specs is None

    def test_register_with_field_specs(self):
        SystemConfigRegistry.register(
            group_key="session",
            tab="security",
            label="会话",
            field_specs=[
                FieldSpec(
                    name="agent_chat_max_concurrency",
                    field_type=int,
                    default=1,
                    getter=lambda s: s.agent_chat_max_concurrency,
                    setter=lambda s, v: setattr(s, "agent_chat_max_concurrency", v),
                ),
            ],
        )
        meta = SystemConfigRegistry.get("session")
        assert meta.settings_cls is None
        assert len(meta.field_specs) == 1

    def test_register_neither_raises(self):
        """settings_cls 与 field_specs 都缺 → ValueError"""
        with pytest.raises(ValueError, match="settings_cls.*field_specs"):
            SystemConfigRegistry.register(group_key="x", tab="t", label="x")

    def test_register_both_raises(self):
        """settings_cls 与 field_specs 都给 → ValueError"""
        with pytest.raises(ValueError, match="互斥"):
            SystemConfigRegistry.register(
                group_key="x",
                tab="t",
                label="x",
                settings_cls=_DummySettings,
                field_specs=[],
            )

    def test_duplicate_raises(self):
        SystemConfigRegistry.register(
            group_key="llm", tab="t", label="x", settings_cls=_DummySettings
        )
        with pytest.raises(ValueError, match="重复注册"):
            SystemConfigRegistry.register(
                group_key="llm", tab="t", label="y", settings_cls=_DummySettings
            )


class TestGet:
    def test_get_missing_raises_key_error(self):
        with pytest.raises(KeyError):
            SystemConfigRegistry.get("nonexistent")

    def test_all_returns_copy(self):
        SystemConfigRegistry.register(
            group_key="llm", tab="t", label="x", settings_cls=_DummySettings
        )
        all_groups = SystemConfigRegistry.all()
        assert "llm" in all_groups
        all_groups["llm"] = None
        assert SystemConfigRegistry.get("llm") is not None


class TestListByTab:
    def test_list_by_tab(self):
        SystemConfigRegistry.register(
            group_key="llm", tab="llm", label="x", settings_cls=_DummySettings
        )
        SystemConfigRegistry.register(
            group_key="vision_llm", tab="llm", label="y", settings_cls=_DummySettings
        )
        SystemConfigRegistry.register(
            group_key="cors", tab="network", label="z", settings_cls=_DummySettings
        )
        llm_groups = SystemConfigRegistry.list_by_tab("llm")
        assert {g.group_key for g in llm_groups} == {"llm", "vision_llm"}
