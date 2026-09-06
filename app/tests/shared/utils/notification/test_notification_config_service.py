# -*- coding:utf-8 -*-
"""
NotificationConfigService 单元测试(2026-09-03 新增)。

测试覆盖：
- P0 导入与构造
- P1 飞书 config 校验必填字段(FAIL-FAST)
- P1 Fernet 加密/解密 roundtrip
- P1 channel CRUD(name 唯一 + is_default 原子切换)
- P1 target CRUD(target_type 必须以 channel_type 开头)
- P1 list_enabled_agents
- P1 resolve_default_channel(is_default 优先 → enabled 第一行)
- P2 send_test_message 失败分支(channel_type 不一致/凭证空)

不在本测试范围(由 router 测试覆盖):HTTP 路由 + ACL
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.utils.notification import (
    NotificationConfigError,
    NotificationConfigNotFoundError,
    NotificationConfigService,
    NotificationConfigValidationError,
)


# =============================================================================
# P0: 导入与构造
# =============================================================================


def test_module_importable():
    """NotificationConfigService 模块可导入。"""
    from app.shared.utils.notification import notification_config_service

    assert hasattr(notification_config_service, "NotificationConfigService")
    assert hasattr(notification_config_service, "FEISHU_REQUIRED_CONFIG_KEYS")
    assert hasattr(notification_config_service, "SUPPORTED_CHANNEL_TYPES")
    assert hasattr(notification_config_service, "SUPPORTED_TARGET_TYPES")


def test_construct_with_empty_credential_key_does_not_raise():
    """credential_key 为空字符串时不抛异常(Fernet 懒加载)。"""
    svc = NotificationConfigService(db=None, credential_key="")
    assert svc._db is None
    assert svc._credential_key == ""


def test_construct_with_invalid_credential_key_does_not_raise_initially():
    """credential_key 非法时构造不报错,首次 _ensure_fernet 才报错。"""
    svc = NotificationConfigService(db=None, credential_key="not-a-valid-fernet-key")
    assert svc._credential_key == "not-a-valid-fernet-key"


def test_ensure_fernet_raises_on_empty_key():
    """credential_key 空 + 触发 encrypt → 抛 NotificationConfigError。"""
    svc = NotificationConfigService(db=None, credential_key="")
    with pytest.raises(NotificationConfigError) as exc_info:
        svc.encrypt_field("hello")
    assert "credential_key 未配置" in str(exc_info.value)


def test_ensure_fernet_raises_on_invalid_key():
    """credential_key 非法 + 触发 encrypt → 抛 NotificationConfigError。"""
    svc = NotificationConfigService(db=None, credential_key="not-a-valid-fernet-key")
    with pytest.raises(NotificationConfigError) as exc_info:
        svc.encrypt_field("hello")
    assert "Fernet base64" in str(exc_info.value)


# =============================================================================
# P1: Fernet 加解密 roundtrip
# =============================================================================


VALID_FERNET_KEY = "Ly_GPItylXtIJiS2qEQ5FjCaBxMhTkJUByS9aoaIFng="  # 与 .env 中相同


def _make_service_with_valid_fernet() -> NotificationConfigService:
    return NotificationConfigService(db=None, credential_key=VALID_FERNET_KEY)


def test_encrypt_decrypt_roundtrip():
    """encrypt_field 后 decrypt_field 应能还原原文。"""
    svc = _make_service_with_valid_fernet()
    encrypted = svc.encrypt_field("my-app-secret-123")
    assert encrypted != "my-app-secret-123"
    decrypted = svc.decrypt_field(encrypted)
    assert decrypted == "my-app-secret-123"


def test_encrypt_empty_string_returns_empty():
    """encrypt_field("") → "" (避免不必要加密)。"""
    svc = _make_service_with_valid_fernet()
    assert svc.encrypt_field("") == ""


def test_decrypt_empty_string_returns_empty():
    """decrypt_field("") → "" (避免 InvalidToken)。"""
    svc = _make_service_with_valid_fernet()
    assert svc.decrypt_field("") == ""


def test_decrypt_invalid_ciphertext_raises():
    """decrypt_field(非 Fernet token) → 抛 NotificationConfigError。"""
    svc = _make_service_with_valid_fernet()
    with pytest.raises(NotificationConfigError) as exc_info:
        svc.decrypt_field("not-a-real-ciphertext")
    assert "解密失败" in str(exc_info.value)


def test_decrypt_feishu_config_decrypts_encrypted_fields():
    """decrypt_feishu_config 返回含 _plain 后缀的明文字段。"""
    svc = _make_service_with_valid_fernet()
    config = {
        "app_id_encrypted": svc.encrypt_field("cli_xxx"),
        "app_secret_encrypted": svc.encrypt_field("secret_yyy"),
        "default_receive_id": "oc_xxx",
    }
    decrypted = svc.decrypt_feishu_config(config)
    assert decrypted["app_id_encrypted_plain"] == "cli_xxx"
    assert decrypted["app_secret_encrypted_plain"] == "secret_yyy"
    assert decrypted["default_receive_id"] == "oc_xxx"
    # 原密文字段保留
    assert "app_id_encrypted" in decrypted


# =============================================================================
# P1: 飞书 config 必填字段校验
# =============================================================================


def test_feishu_config_missing_required_field_raises():
    """飞书 config 缺 app_id_encrypted → 抛 NotificationConfigValidationError。"""
    svc = _make_service_with_valid_fernet()
    config = {
        # 缺 app_id_encrypted
        "app_secret_encrypted": svc.encrypt_field("secret"),
        "default_receive_id": "oc_xxx",
        "default_receive_id_type": "chat_id",
        "log_level": "INFO",
        "agent_name": "project",
        "receiver_username": "admin",
    }
    with pytest.raises(NotificationConfigValidationError) as exc_info:
        svc._validate_config("feishu", config)
    assert "app_id_encrypted" in str(exc_info.value)


def test_feishu_config_all_required_present_passes():
    """飞书 config 全必填字段均存在 → 校验通过。"""
    svc = _make_service_with_valid_fernet()
    config = {
        "app_id_encrypted": svc.encrypt_field("cli_xxx"),
        "app_secret_encrypted": svc.encrypt_field("secret"),
        "default_receive_id": "oc_xxx",
        "default_receive_id_type": "chat_id",
        "log_level": "INFO",
        "agent_name": "project",
        "receiver_username": "admin",
    }
    # 不抛异常
    svc._validate_config("feishu", config)


def test_unsupported_channel_type_raises_in_upsert():
    """upsert_channel 时 channel_type 不在白名单 → 抛 ValidationError。"""
    svc = _make_service_with_valid_fernet()
    with pytest.raises(NotificationConfigValidationError):
        # channel_type 校验在 db 检查之前,ValidationError 先抛
        asyncio.run(svc.upsert_channel(
            channel_type="wechat",  # 不在 SUPPORTED_CHANNEL_TYPES
            name="test",
            display_name="",
            config={},
            enabled=True,
            is_default=False,
            created_by_user_id=1,
        ))


# =============================================================================
# P1: channel CRUD(name 唯一 + is_default 原子切换)
# =============================================================================


def _make_service_with_mock_db() -> tuple:
    """构造带 mock db 的 NotificationConfigService + db 实例。

    mock db 的 fetch / fetchrow / execute / fetchval 都是 AsyncMock,因为
    service 层使用 ``await self._db.fetch(...)`` / ``await self._db.fetchrow(...)``。
    """
    db = MagicMock()
    db.fetch = AsyncMock()
    db.fetchrow = AsyncMock()
    db.execute = AsyncMock()
    db.fetchval = AsyncMock()
    svc = NotificationConfigService(db=db, credential_key=VALID_FERNET_KEY)
    return svc, db


def _valid_feishu_config(svc: NotificationConfigService) -> dict:
    """构造完整飞书 config（含 Fernet 加密字段）。"""
    return {
        "app_id_encrypted": svc.encrypt_field("cli_xxx"),
        "app_secret_encrypted": svc.encrypt_field("secret"),
        "default_receive_id": "oc_xxx",
        "default_receive_id_type": "chat_id",
        "log_level": "INFO",
        "agent_name": "project",
        "receiver_username": "admin",
    }


def test_list_channels_with_db_none_returns_empty():
    """db=None → list_channels 返回空列表(不抛异常)。"""
    svc = NotificationConfigService(db=None, credential_key=VALID_FERNET_KEY)
    result = asyncio.run(svc.list_channels())
    assert result == []


def test_list_channels_filters_by_channel_type():
    """list_channels(channel_type='feishu') 应带参数 SQL 过滤。"""
    svc, db = _make_service_with_mock_db()
    db.fetch = AsyncMock(return_value=[])
    asyncio.run(svc.list_channels(channel_type="feishu", enabled_only=True))
    call_args = db.fetch.call_args
    assert "channel_type = $1" in call_args.args[0]
    assert "enabled = TRUE" in call_args.args[0]
    assert call_args.args[1] == "feishu"


def test_upsert_channel_creates_new_when_not_exists():
    """upsert_channel 不存在同名同 channel_type 行 → INSERT。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        None,  # SELECT existing → None(不存在)
        {"id": 10, "updated_at": "2026-09-03"},  # INSERT RETURNING
    ])
    config = _valid_feishu_config(svc)
    result = asyncio.run(svc.upsert_channel(
        channel_type="feishu",
        name="ops-bot",
        display_name="运维机器人",
        config=config,
        enabled=True,
        is_default=True,
        created_by_user_id=1,
    ))
    assert result["created"] is True
    assert result["id"] == 10
    # is_default=True → 应先 UPDATE 把其它行置 False
    # 断言 execute 被调过至少 1 次,且 sql 包含 is_default = FALSE
    execute_calls = db.execute.call_args_list
    assert len(execute_calls) >= 1, f"execute 未被调用, calls={execute_calls}"
    execute_sqls = [c.args[0] for c in execute_calls]
    assert any("SET is_default = FALSE" in sql for sql in execute_sqls), f"sqls={execute_sqls}"


def test_upsert_channel_updates_existing():
    """upsert_channel 已存在 → UPDATE 不重 INSERT。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        {"id": 5},  # SELECT existing → 已存在
        {"id": 5, "updated_at": "2026-09-03"},  # UPDATE RETURNING
    ])
    config = _valid_feishu_config(svc)
    result = asyncio.run(svc.upsert_channel(
        channel_type="feishu",
        name="ops-bot",
        display_name="运维机器人",
        config=config,
        enabled=True,
        is_default=False,
        created_by_user_id=None,
    ))
    assert result["created"] is False
    assert result["id"] == 5
    # is_default=False → 不调 UPDATE is_default=False 原子切换
    # 仅调 1 次 UPDATE(实际数据 UPDATE),不调 atomic switch
    update_calls = [
        c for c in db.execute.call_args_list
        if "is_default = FALSE" in str(c)
    ]
    assert len(update_calls) == 0


def test_delete_channel_returns_true_on_existing():
    """delete_channel 删除存在行 → 返回 True。"""
    svc, db = _make_service_with_mock_db()
    db.execute = AsyncMock(return_value="DELETE 1")
    result = asyncio.run(svc.delete_channel(1))
    assert result is True


def test_delete_channel_returns_false_on_missing():
    """delete_channel 删除不存在行 → 返回 False。"""
    svc, db = _make_service_with_mock_db()
    db.execute = AsyncMock(return_value="DELETE 0")
    result = asyncio.run(svc.delete_channel(999))
    assert result is False


def test_set_default_channel_atomic_switch():
    """set_default_channel → 先 UPDATE 其它行 is_default=FALSE,再 UPDATE 本行 TRUE。"""
    svc, db = _make_service_with_mock_db()
    db.fetchval = AsyncMock(return_value=10)  # channel_id=10 存在
    db.execute = AsyncMock()
    result = asyncio.run(svc.set_default_channel(10, "feishu"))
    assert result is True
    # 应有 2 次 execute 调用:先批量置 False,再置单行 True
    assert db.execute.call_count == 2
    first_call_sql = db.execute.call_args_list[0].args[0]
    second_call_sql = db.execute.call_args_list[1].args[0]
    assert "SET is_default = FALSE" in first_call_sql
    assert "WHERE channel_type = $1 AND is_default = TRUE" in first_call_sql
    assert "SET is_default = TRUE" in second_call_sql
    assert "WHERE id = $1" in second_call_sql


def test_set_default_channel_returns_false_when_not_exists():
    """set_default_channel 不存在 → 返回 False,不调任何 UPDATE。"""
    svc, db = _make_service_with_mock_db()
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    result = asyncio.run(svc.set_default_channel(999, "feishu"))
    assert result is False
    assert db.execute.call_count == 0


# =============================================================================
# P1: target CRUD
# =============================================================================


def test_upsert_target_rejects_target_type_not_matching_channel_type():
    """upsert_target target_type 不以 channel_type 开头 → ValidationError。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value={"channel_type": "feishu"})
    config = {"chat_id": "oc_xxx", "chat_type": "chat_id"}
    with pytest.raises(NotificationConfigValidationError) as exc_info:
        asyncio.run(svc.upsert_target(
            channel_id=1,
            target_type="dingtalk.group",  # 不以 feishu. 开头
            name="test",
            config=config,
            agent_name="project",
            subject_template="",
            body_template="",
            enabled=True,
            created_by_user_id=1,
        ))
    assert "target_type" in str(exc_info.value)


def test_upsert_target_channel_not_found_raises_notfound():
    """upsert_target channel_id 不存在 → NotFoundError。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value=None)  # channel 不存在
    config = {"chat_id": "oc_xxx", "chat_type": "chat_id"}
    with pytest.raises(NotificationConfigNotFoundError):
        asyncio.run(svc.upsert_target(
            channel_id=999,
            target_type="feishu.chat",
            name="test",
            config=config,
            agent_name="project",
            subject_template="",
            body_template="",
            enabled=True,
            created_by_user_id=1,
        ))


def test_upsert_target_rejects_missing_feishu_required_config():
    """飞书 target config 缺 chat_id → ValidationError。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value={"channel_type": "feishu"})
    config = {"chat_type": "chat_id"}  # 缺 chat_id
    with pytest.raises(NotificationConfigValidationError) as exc_info:
        asyncio.run(svc.upsert_target(
            channel_id=1,
            target_type="feishu.chat",
            name="test",
            config=config,
            agent_name="project",
            subject_template="",
            body_template="",
            enabled=True,
            created_by_user_id=1,
        ))
    assert "chat_id" in str(exc_info.value)


def test_delete_target_returns_true_on_existing():
    """delete_target 删除存在行 → True。"""
    svc, db = _make_service_with_mock_db()
    db.execute = AsyncMock(return_value="DELETE 1")
    result = asyncio.run(svc.delete_target(1))
    assert result is True


# =============================================================================
# P1: list_enabled_agents
# =============================================================================


def test_list_enabled_agents_returns_empty_when_db_none():
    """db=None → 返回空列表。"""
    svc = NotificationConfigService(db=None, credential_key=VALID_FERNET_KEY)
    result = asyncio.run(svc.list_enabled_agents())
    assert result == []


def test_list_enabled_agents_filters_enabled_true():
    """list_enabled_agents 应按 enabled=TRUE 过滤 + 按 sort_order ASC, name ASC 排序。"""
    svc, db = _make_service_with_mock_db()
    db.fetch = AsyncMock(return_value=[
        {"name": "project", "display_name": "Project Bot"},
        {"name": "ops", "display_name": None},  # None display_name → 回落 name
    ])
    result = asyncio.run(svc.list_enabled_agents())
    assert len(result) == 2
    assert result[0]["name"] == "project"
    assert result[0]["display_name"] == "Project Bot"
    assert result[1]["display_name"] == "ops"  # None 回落到 name
    # SQL 检查
    call_sql = db.fetch.call_args.args[0]
    assert "WHERE enabled = TRUE" in call_sql
    assert "ORDER BY sort_order ASC, name ASC" in call_sql


# =============================================================================
# P1: resolve_default_channel
# =============================================================================


def test_resolve_default_channel_prefers_is_default_true():
    """resolve_default_channel 优先 is_default=TRUE 的行。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        {"id": 5, "name": "primary", "channel_type": "feishu",
         "config": {"app_id_encrypted": "x"}, "enabled": True,
         "is_default": True, "created_by_user_id": 1,
         "created_at": None, "updated_at": None},
    ])
    result = asyncio.run(svc.resolve_default_channel("feishu"))
    assert result is not None
    assert result["id"] == 5
    assert result["is_default"] is True
    # SQL 应包含 is_default = TRUE
    assert "is_default = TRUE" in db.fetchrow.call_args_list[0].args[0]


def test_resolve_default_channel_falls_back_to_first_enabled():
    """resolve_default_channel 无 is_default → 取第一行 enabled=TRUE。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        None,  # is_default 查询无结果
        {"id": 8, "name": "first-enabled", "channel_type": "feishu",
         "config": {"app_id_encrypted": "x"}, "enabled": True,
         "is_default": False, "created_by_user_id": 1,
         "created_at": None, "updated_at": None},
    ])
    result = asyncio.run(svc.resolve_default_channel("feishu"))
    assert result is not None
    assert result["id"] == 8


def test_resolve_default_channel_returns_none_when_empty():
    """DB 无任何飞书渠道 → 返回 None。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value=None)
    result = asyncio.run(svc.resolve_default_channel("feishu"))
    assert result is None


# =============================================================================
# P2: send_test_message 失败分支
# =============================================================================


def test_send_test_message_returns_false_when_db_none():
    """db=None → send_test_message 失败返回。"""
    svc = NotificationConfigService(db=None, credential_key=VALID_FERNET_KEY)
    result = asyncio.run(svc.send_test_message(target_id=1, channel_type="feishu", content="hello"))
    assert result["success"] is False
    assert "数据库未初始化" in result["error"]


def test_send_test_message_target_not_found():
    """target_id 不存在 → 返回失败。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value=None)  # get_target 不存在
    result = asyncio.run(svc.send_test_message(target_id=999, channel_type="feishu", content="hi"))
    assert result["success"] is False
    assert "999" in result["error"]


def test_send_test_message_channel_type_mismatch():
    """body.channel_type 与 target.channel.channel_type 不一致 → 返回失败。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "channel_id": 5, "target_type": "feishu.chat",
         "name": "test", "config": {"chat_id": "oc_xxx"},
         "agent_name": "project", "subject_template": "",
         "body_template": "", "enabled": True, "created_by_user_id": 1,
         "created_at": None, "updated_at": None,
         "channel_type": "feishu", "channel_name": "primary"},
        # get_channel_internal 返回 feishu channel
        {"id": 5, "name": "primary", "channel_type": "feishu",
         "config": {"app_id_encrypted": "x", "app_secret_encrypted": "y"},
         "enabled": True, "is_default": True, "created_by_user_id": 1,
         "created_at": None, "updated_at": None},
    ])
    result = asyncio.run(svc.send_test_message(
        target_id=1, channel_type="dingtalk", content="hi"
    ))
    assert result["success"] is False
    assert "不一致" in result["error"]


def test_send_test_message_channel_disabled():
    """channel.enabled=False → 返回失败。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "channel_id": 5, "target_type": "feishu.chat",
         "name": "test", "config": {"chat_id": "oc_xxx"},
         "agent_name": "project", "subject_template": "",
         "body_template": "", "enabled": True, "created_by_user_id": 1,
         "created_at": None, "updated_at": None,
         "channel_type": "feishu", "channel_name": "primary"},
        {"id": 5, "name": "primary", "channel_type": "feishu",
         "config": {"app_id_encrypted": "x", "app_secret_encrypted": "y"},
         "enabled": False, "is_default": False, "created_by_user_id": 1,
         "created_at": None, "updated_at": None},
    ])
    result = asyncio.run(svc.send_test_message(
        target_id=1, channel_type="feishu", content="hi"
    ))
    assert result["success"] is False
    assert "已禁用" in result["error"]


def test_send_test_message_target_missing_chat_id():
    """target.config.chat_id 为空 → 返回失败。"""
    svc, db = _make_service_with_mock_db()
    # 用真实 Fernet 加密的凭证(mock db 提供的 config)
    valid_config = _valid_feishu_config(svc)
    db.fetchrow = AsyncMock(side_effect=[
        {"id": 1, "channel_id": 5, "target_type": "feishu.chat",
         "name": "test", "config": {"chat_id": ""},  # 空 chat_id
         "agent_name": "project", "subject_template": "",
         "body_template": "", "enabled": True, "created_by_user_id": 1,
         "created_at": None, "updated_at": None,
         "channel_type": "feishu", "channel_name": "primary"},
        {"id": 5, "name": "primary", "channel_type": "feishu",
         "config": valid_config,
         "enabled": True, "is_default": True, "created_by_user_id": 1,
         "created_at": None, "updated_at": None},
    ])
    # mock lark_oapi(测试环境无此包);让 _send_feishu_test 不抛 ImportError
    import sys
    import types

    fake_lark = types.ModuleType("lark_oapi")
    fake_lark.LogLevel = MagicMock(INFO=0, DEBUG=1, WARNING=2, ERROR=3)
    fake_api = types.ModuleType("lark_oapi.api")
    fake_im = types.ModuleType("lark_oapi.api.im")
    fake_im_v1 = types.ModuleType("lark_oapi.api.im.v1")
    fake_im_v1.CreateMessageRequest = MagicMock()
    fake_im_v1.CreateMessageRequestBody = MagicMock()
    fake_im.v1 = fake_im_v1
    fake_api.im = fake_im
    fake_lark.api = fake_api
    with patch.dict(sys.modules, {
        "lark_oapi": fake_lark,
        "lark_oapi.api": fake_api,
        "lark_oapi.api.im": fake_im,
        "lark_oapi.api.im.v1": fake_im_v1,
    }):
        result = asyncio.run(svc.send_test_message(
            target_id=1, channel_type="feishu", content="hi"
        ))
    assert result["success"] is False
    assert "chat_id 为空" in result["error"]


# =============================================================================
# 异常体系
# =============================================================================


def test_exception_hierarchy():
    """异常体系：NotFound/Validation 都是 Error 子类。"""
    assert issubclass(NotificationConfigNotFoundError, NotificationConfigError)
    assert issubclass(NotificationConfigValidationError, NotificationConfigError)
