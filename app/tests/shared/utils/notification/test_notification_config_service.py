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
import inspect
import json
import re
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
        "log_level": "INFO",
        "agent_name": "project",
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
        "log_level": "INFO",
        "agent_name": "project",
    }
    # 不抛异常
    svc._validate_config("feishu", config)


def test_feishu_channel_requires_agent_name():
    """2026-09-07 第二轮：channel 必须包含 agent_name（应用绑智能体）。

    - receiver_username / default_receive_id* 仍不在必填项
    - agent_name 重新成为必填
    """
    from app.shared.utils.notification.notification_config_service import (
        FEISHU_REQUIRED_CONFIG_KEYS,
        FEISHU_LEGACY_CHANNEL_CONFIG_KEYS,
    )
    # agent_name 必须重新在必填项
    assert "agent_name" in FEISHU_REQUIRED_CONFIG_KEYS
    assert "receiver_username" not in FEISHU_REQUIRED_CONFIG_KEYS
    assert "default_receive_id" not in FEISHU_REQUIRED_CONFIG_KEYS
    assert "default_receive_id_type" not in FEISHU_REQUIRED_CONFIG_KEYS
    # 必填项 = 凭证 + log_level + agent_name
    assert set(FEISHU_REQUIRED_CONFIG_KEYS) == {
        "app_id_encrypted", "app_secret_encrypted", "log_level", "agent_name",
    }
    # legacy 字段不含 agent_name（重新成为必填）
    assert "agent_name" not in FEISHU_LEGACY_CHANNEL_CONFIG_KEYS
    # legacy 仍剥除 receiver_username / default_receive_id*
    assert set(FEISHU_LEGACY_CHANNEL_CONFIG_KEYS) >= {
        "receiver_username", "default_receive_id", "default_receive_id_type",
    }

    # _validate_config 缺 agent_name 时抛错
    svc = _make_service_with_valid_fernet()
    bad_config = {
        "app_id_encrypted": svc.encrypt_field("cli_xxx"),
        "app_secret_encrypted": svc.encrypt_field("secret"),
        "log_level": "INFO",
        # 缺 agent_name
    }
    with pytest.raises(NotificationConfigValidationError) as exc_info:
        svc._validate_config("feishu", bad_config)
    assert "agent_name" in str(exc_info.value)

    # 完整必填 → 校验通过
    good_config = dict(bad_config)
    good_config["agent_name"] = "project"
    svc._validate_config("feishu", good_config)  # 不抛


def test_upsert_channel_strips_legacy_fields():
    """2026-09-07 第二轮：upsert_channel 写入前自动剥除 legacy 字段。

    agent_name 不再属于 legacy（必填项保留）；其他 3 个 legacy 字段仍剥除。
    """
    svc, db = _make_service_with_mock_db()
    # 不存在 → INSERT 路径
    db.fetchrow = AsyncMock(side_effect=[
        None,  # existing 查询 → None
        {"id": 100, "updated_at": "2026-09-07"},  # INSERT RETURNING
    ])
    config = _valid_feishu_config(svc)
    # agent_name 必填,这里显式传入;legacy 字段额外附加测剥除
    config["agent_name"] = "project"
    config["receiver_username"] = "admin"
    config["default_receive_id"] = "oc_xxx"
    config["default_receive_id_type"] = "chat_id"

    asyncio.run(svc.upsert_channel(
        channel_type="feishu",
        name="ops-bot",
        display_name="运维机器人",
        config=config,
        enabled=True,
        is_default=False,
        created_by_user_id=1,
    ))
    # INSERT 时传给 DB 的 config JSON 应不含 receiver_username / default_receive_id*
    # agent_name 必须保留
    insert_calls = [
        c for c in db.fetchrow.call_args_list
        if len(c.args) > 0 and "INSERT INTO notification_channels" in str(c.args[0])
    ]
    assert len(insert_calls) == 1, (
        f"未找到 INSERT 调用: calls={[str(c)[:80] for c in db.fetchrow.call_args_list]}"
    )
    insert_call = insert_calls[0]
    # service.upsert_channel INSERT 签名：
    # fetchrow(sql, name, display_name, channel_type, config, enabled, is_default, created_by_user_id)
    # → args[0]=sql, args[1]=name, args[2]=display_name, args[3]=channel_type, args[4]=config
    # 契约(2026-09-10 生产 23514 修复)：config 必须是 dict,由连接级 jsonb codec
    # (database.py::_init_connection, encoder=json.dumps) 自动 encode;禁止传
    # json.dumps 后的 str(codec 对 str 二次编码 → JSONB string → CHECK 拒绝)。
    cfg = insert_call.args[4]
    assert isinstance(cfg, dict), (
        f"jsonb 参数必须传 dict(codec 自动 encode),实际 {type(cfg).__name__}: "
        f"{str(cfg)[:120]}"
    )
    # agent_name 保留
    assert cfg.get("agent_name") == "project"
    # legacy 字段被剥除
    assert "receiver_username" not in cfg, f"残留字段: {list(cfg.keys())}"
    assert "default_receive_id" not in cfg, f"残留字段: {list(cfg.keys())}"
    assert "default_receive_id_type" not in cfg, f"残留字段: {list(cfg.keys())}"
    # 必填字段保留
    assert "app_id_encrypted" in cfg
    assert "app_secret_encrypted" in cfg
    assert cfg["log_level"] == "INFO"


def test_target_read_agent_name_falls_back_to_channel():
    """2026-09-07 第二轮：target.agent_name 读取时回退到 channel.agent_name。

    智能体绑定收口在 channel 层；target 行可能存 NULL agent_name，读取时
    必须回退到 channel.config.agent_name（兼容性向后）。
    """
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value={
        "id": 10,
        "channel_id": 1,
        "channel_type": "feishu",
        "channel_name": "ops-bot",
        # target 行 agent_name 为 NULL（旧数据 / 写入剥除）
        "agent_name": "",
        "target_type": "feishu.chat",
        "name": "alert-group",
        "config": json.dumps({"chat_id": "oc_xxx", "chat_type": "chat_id"}),
        "subject_template": "",
        "body_template": "",
        "enabled": True,
        "created_by_user_id": 1,
        "created_at": None,
        "updated_at": None,
        # channel.config.agent_name JSON 提取
        "channel_agent_name": "project",
    })
    result = asyncio.run(svc.get_target(10))
    assert result is not None
    assert result["agent_name"] == "project"


def test_target_read_agent_name_prefers_target_row_over_channel_fallback():
    """target.agent_name 非空时优先使用 target 行值，不回退 channel。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(return_value={
        "id": 10,
        "channel_id": 1,
        "channel_type": "feishu",
        "channel_name": "ops-bot",
        "agent_name": "legacy-target-agent",  # 存量值（向后兼容读取）
        "target_type": "feishu.chat",
        "name": "alert-group",
        "config": json.dumps({"chat_id": "oc_xxx", "chat_type": "chat_id"}),
        "subject_template": "",
        "body_template": "",
        "enabled": True,
        "created_by_user_id": 1,
        "created_at": None,
        "updated_at": None,
        "channel_agent_name": "channel-agent",  # 即使有 channel agent,也不覆盖
    })
    result = asyncio.run(svc.get_target(10))
    assert result["agent_name"] == "legacy-target-agent"


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
    """构造完整飞书 config（含 Fernet 加密字段）。

    2026-09-07 第二轮：channel 必填 4 字段（凭证 + log_level + agent_name）；
    legacy 字段（receiver_username / default_receive_id*）额外传入用于测剥除。
    """
    return {
        "app_id_encrypted": svc.encrypt_field("cli_xxx"),
        "app_secret_encrypted": svc.encrypt_field("secret"),
        "log_level": "INFO",
        "agent_name": "project",  # 2026-09-07 第二轮：channel 必填
        "receiver_username": "admin",  # legacy（写入剥除）
        "default_receive_id": "oc_xxx",  # legacy（写入剥除）
        "default_receive_id_type": "chat_id",  # legacy（写入剥除）
    }


def _simulate_pg_jsonb_object_write(value):
    """模拟生产 jsonb 写入全链路（完整语义层 fake helper）。

    复刻 ``app/core/database.py::_init_connection`` 注册的
    ``set_type_codec('jsonb', encoder=json.dumps)`` 语义：codec 对绑定到
    jsonb 的参数**无条件**调用 ``json.dumps``——

    - 传 dict → ``'{"a": 1}'`` → PG 解析为 JSONB object ✓
    - 传 str（应用层已 ``json.dumps``） → ``'"{\\"a\\": 1}"'`` → PG 解析为
      JSONB **string** ✗ → 触发 ``notification_*_config_object_chk``
      （sqlstate 23514，即 2026-09-10 生产 500 的根因）

    参数:
        value: service 层传给 ``$n::jsonb`` 位置的原始参数。

    返回:
        模拟落库后读取的 Python 形态（``json.loads(codec 输出)``）。

    异常:
        AssertionError: 落库形态非 dict（等价于生产 CHECK 约束拒绝）。
    """
    wire_text = json.dumps(value, ensure_ascii=False)  # codec encoder 无条件调用
    stored = json.loads(wire_text)  # PG 端解析 JSONB 文本
    if not isinstance(stored, dict):
        raise AssertionError(
            "模拟 notification_*_config_object_chk 拒绝(23514): "
            f"落库 jsonb_typeof={type(stored).__name__} != object; "
            "根因=jsonb 参数传了 str 被 codec 二次编码"
        )
    return stored


def _assert_write_calls_jsonb_params_are_dicts(db: MagicMock) -> None:
    """断言 mock db 所有写调用中 ``$n::jsonb`` 位置的参数均为 dict。

    按 SQL 文本中的 ``$n::jsonb`` 标记定位参数下标,逐一断言类型并通过
    ``_simulate_pg_jsonb_object_write`` 走完 codec + CHECK 模拟链路。

    参数:
        db: ``_make_service_with_mock_db`` 返回的 mock db。

    异常:
        AssertionError: 任一 jsonb 参数非 dict 或 codec 模拟后落库非 object。
    """
    for method_name in ("fetchrow", "execute"):
        for call in getattr(db, method_name).call_args_list:
            if not call.args:
                continue
            sql = str(call.args[0])
            for match in re.finditer(r"\$(\d+)::jsonb", sql):
                idx = int(match.group(1))  # $n 是 1-based,对应 args[n]
                value = call.args[idx]
                assert isinstance(value, dict), (
                    f"{method_name} 的 ${idx}::jsonb 参数必须传 dict(codec 自动 "
                    f"encode),实际 {type(value).__name__}: {str(value)[:120]}"
                )
                _simulate_pg_jsonb_object_write(value)


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
# P1: JSONB 传参契约回归（2026-09-10 生产 23514 CheckViolationError）
# =============================================================================


def test_upsert_channel_passes_dict_to_jsonb_param():
    """回归：upsert_channel INSERT/UPDATE 的 config 参数必须传 dict 而非 str。

    根因（2026-09-10 生产 500）：连接级 jsonb codec(encoder=json.dumps)对
    str 参数二次编码 → 落库 JSONB string → notification_channels_config_object_chk
    (jsonb_typeof='object') 拒绝。本用例锁定「传 dict」契约,防回退。
    """
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        None,  # SELECT existing → None → INSERT
        {"id": 10, "updated_at": "2026-09-10"},
        {"id": 10},  # SELECT existing → 已存在 → UPDATE
        {"id": 10, "updated_at": "2026-09-10"},
    ])
    config = _valid_feishu_config(svc)
    asyncio.run(svc.upsert_channel(
        channel_type="feishu", name="ops-bot", display_name="运维机器人",
        config=config, enabled=True, is_default=False, created_by_user_id=1,
    ))
    asyncio.run(svc.upsert_channel(
        channel_type="feishu", name="ops-bot", display_name="运维机器人",
        config=config, enabled=True, is_default=False, created_by_user_id=1,
    ))
    _assert_write_calls_jsonb_params_are_dicts(db)


def test_upsert_target_passes_dict_to_jsonb_param():
    """回归：upsert_target INSERT/UPDATE 的 config 参数必须传 dict 而非 str。"""
    svc, db = _make_service_with_mock_db()
    db.fetchrow = AsyncMock(side_effect=[
        {"channel_type": "feishu"},  # SELECT channel_type（channel 存在）
        {"id": 20, "updated_at": "2026-09-10"},  # INSERT RETURNING
        {"channel_type": "feishu"},  # SELECT channel_type（第二次调用）
        {"created_by_user_id": 1},  # SELECT existing（UPDATE 路径）
        {"id": 20, "updated_at": "2026-09-10"},  # UPDATE RETURNING
    ])
    config = {"chat_id": "oc_xxx", "chat_type": "chat_id"}
    asyncio.run(svc.upsert_target(
        channel_id=1, target_type="feishu.chat", name="alert-group",
        config=dict(config), agent_name="project", subject_template="",
        body_template="", enabled=True, created_by_user_id=1,
    ))
    asyncio.run(svc.upsert_target(
        channel_id=1, target_type="feishu.chat", name="alert-group",
        config=dict(config), agent_name="project", subject_template="",
        body_template="", enabled=True, created_by_user_id=1, target_id=20,
    ))
    _assert_write_calls_jsonb_params_are_dicts(db)


def test_jsonb_codec_guard_rejects_str_param():
    """反向用例：证明 codec 模拟 guard 能捕获「传 str 给 jsonb 参数」回归。

    若未来有人把 service 改回 json.dumps 传 str,guard 必须像生产 CHECK 一样
    拒绝;仅正向断言 happy path = 100% 漏检该根因（本次生产事故的教训）。
    """
    # 旧反模式：应用层先 json.dumps → codec 二次编码 → JSONB string → 拒绝
    with pytest.raises(AssertionError, match="二次编码"):
        _simulate_pg_jsonb_object_write(json.dumps({"a": 1}, ensure_ascii=False))
    # 正确契约：传 dict → codec 一次编码 → JSONB object → 通过
    assert _simulate_pg_jsonb_object_write({"a": 1}) == {"a": 1}


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


# =============================================================================
# 2026-09-10：asyncpg 异常映射 + DB 索引 regression（second enabled channel）
# =============================================================================


def test_db_exception_extracts_sqlstate_and_constraint():
    """_extract_db_error_detail：从异常提取 sqlstate/constraint_name/message。

    测试环境 asyncpg 是 Mock 对象，需要 patch 出真实的 PostgresError 基类让 isinstance 工作。
    """
    from app.shared.utils.notification import notification_config_service as svc_mod
    from app.shared.utils.notification.notification_config_service import (
        NotificationConfigService,
    )

    class FakePostgresErrorBase(Exception):
        """模拟 asyncpg.PostgresError 基类。"""

    class FakePostgresError(FakePostgresErrorBase):
        sqlstate = "23505"
        constraint_name = "idx_notification_channels_enabled"
        table_name = "notification_channels"
        detail = "Key (channel_type)=(feishu) already exists."

    # 临时把 svc_mod.asyncpg 替换成含 PostgresError 真实类
    original_asyncpg = svc_mod.asyncpg
    svc_mod.asyncpg = type("FakeAsyncpgModule", (), {"PostgresError": FakePostgresErrorBase})
    try:
        err = FakePostgresError("duplicate key value violates unique constraint")
        detail = NotificationConfigService._extract_db_error_detail(err)
    finally:
        svc_mod.asyncpg = original_asyncpg

    assert detail["exception_type"] == "FakePostgresError"
    assert detail["sqlstate"] == "23505"
    assert detail["constraint_name"] == "idx_notification_channels_enabled"
    assert detail["table_name"] == "notification_channels"
    assert detail["detail"] == "Key (channel_type)=(feishu) already exists."
    assert "duplicate key" in detail["message"]


def test_db_exception_extract_handles_non_postgres_error():
    """_extract_db_error_detail：非 asyncpg 异常只返回基础字段（type + str）。

    注意：根 conftest 会话级把 ``sys.modules["asyncpg"]`` 替换为 ``Mock()``，
    导致 service 模块级 ``asyncpg.PostgresError`` 不是 type（isinstance 会
    TypeError）。仿照邻居用例，临时把 ``svc_mod.asyncpg`` 换成带真实异常
    基类的 fake 模块。
    """
    from app.shared.utils.notification import notification_config_service as svc_mod
    from app.shared.utils.notification.notification_config_service import (
        NotificationConfigService,
    )

    class FakePostgresErrorBase(Exception):
        """模拟 asyncpg.PostgresError 基类。"""

    original_asyncpg = svc_mod.asyncpg
    svc_mod.asyncpg = type(
        "FakeAsyncpgModule", (), {"PostgresError": FakePostgresErrorBase}
    )
    try:
        err = ValueError("普通 Python 异常")
        detail = NotificationConfigService._extract_db_error_detail(err)
    finally:
        svc_mod.asyncpg = original_asyncpg

    assert detail["exception_type"] == "ValueError"
    assert detail["message"] == "普通 Python 异常"
    # 非 PostgresError 不应有 sqlstate / constraint_name
    assert "sqlstate" not in detail
    assert "constraint_name" not in detail


def test_upsert_target_insert_sql_does_not_write_agent_name_column():
    """upsert_target INSERT SQL 必须不写 agent_name 列(2026-09-10 回归保护)。

    背景:第二轮契约 target 不绑智能体,agent_name 读取时回退 channel.config.agent_name;
    notification_targets.agent_name 列 2026-09-10 落地为 NULLABLE,但 INSERT 必须仍然不写
    该列,否则:
    1) 前端不传 agent_name → service 写入 NULL → 仍依赖列 NULLABLE 才能成功
       (单一真相源依赖变窄,任意一侧未来变更都可能回归)
    2) INSERT 多写一列增加带宽 / 失去「target 仅管接收方」的语义清晰度

    本测试直接对源码字符串做 grep-style 断言,捕获任何恢复写 agent_name 列的修改。
    """
    import re
    from app.shared.utils.notification import notification_config_service as svc_mod

    src = inspect.getsource(svc_mod.NotificationConfigService.upsert_target)

    # 抽 INSERT INTO notification_targets 段(到 RETURNING 之前)
    m = re.search(
        r"INSERT INTO notification_targets\s*(?P<body>.*?)RETURNING",
        src, flags=re.DOTALL,
    )
    assert m is not None, "upsert_target 中找不到 INSERT INTO notification_targets 语句"

    body = m.group("body")
    # 列名列表
    cols_match = re.search(r"\((?P<cols>[^)]+)\)\s*VALUES", body)
    assert cols_match is not None, "INSERT 无法解析列名列表"
    cols_text = cols_match.group("cols")
    cols = {c.strip() for c in cols_text.split(",")}

    assert "agent_name" not in cols, (
        f"upsert_target INSERT 必须不写 agent_name 列(读取回退 channel.config.agent_name);"
        f"当前列列表={sorted(cols)}。"
        "如果业务确实需要 target 重新绑智能体,请同时改 DB 列改回 NOT NULL + "
        "调整 _target_to_public 回退逻辑,并删除本测试。"
    )

    # VALUES 占位符数量必须等于列数
    placeholders = re.findall(r"\$\d+", body[body.index("VALUES"):])
    assert len(placeholders) == len(cols), (
        f"VALUES 占位符 {len(placeholders)} != 列数 {len(cols)}: cols={sorted(cols)}"
    )


def test_upsert_target_update_sql_does_not_write_agent_name_column():
    """upsert_target UPDATE SQL 必须不更新 agent_name 列(2026-09-10 回归保护)。

    背景:第二轮契约规定 target 不再绑智能体,UPDATE 必须不写 agent_name 列以
    保留存量值(读取时回退 chain 优先 target 行值)。
    """
    import re
    from app.shared.utils.notification import notification_config_service as svc_mod

    src = inspect.getsource(svc_mod.NotificationConfigService.upsert_target)

    # UPDATE notification_targets 段
    m = re.search(
        r"UPDATE notification_targets\s*SET\s*(?P<sets>.*?)WHERE",
        src, flags=re.DOTALL,
    )
    assert m is not None, "upsert_target 中找不到 UPDATE notification_targets 语句"

    sets = m.group("sets")
    # 把 SET 子句拆成单条: column = $n (允许复杂赋值,但 target 这里都是简单赋值)
    pairs = [p.strip() for p in sets.split(",")]
    set_cols = []
    for p in pairs:
        # 形如 "name = $2" / "config = $3::jsonb"
        col_match = re.match(r"(?P<col>\w+)\s*=", p)
        if col_match:
            set_cols.append(col_match.group("col"))

    assert "agent_name" not in set_cols, (
        f"upsert_target UPDATE 必须不更新 agent_name 列;"
        f"当前 SET 子句列={set_cols}。"
        "如果业务确实需要 target 重新绑智能体,请同步前端 / DB / 读取逻辑,并删除本测试。"
    )


def test_log_and_raise_db_error_wraps_as_notification_config_error():
    """_log_and_raise_db_error 把 DB 异常封装为 NotificationConfigError（含 sqlstate/constraint）。

    关键契约：service 层不再让 raw asyncpg 异常逃逸，必须抛 NotificationConfigError
    让 router 层 _handle_service_error 能映射 500 + 把可读 message 透给前端。
    """
    from app.shared.utils.notification import notification_config_service as svc_mod
    from app.shared.utils.notification.notification_config_service import (
        NotificationConfigService,
    )

    class FakePostgresErrorBase(Exception):
        """模拟 asyncpg.PostgresError 基类。"""

    class FakeUniqueViolation(FakePostgresErrorBase):
        sqlstate = "23505"
        constraint_name = "notification_channels_name_type_uniq"
        table_name = "notification_channels"
        detail = "Key (name, channel_type)=(运维通知, feishu) already exists."

    original_asyncpg = svc_mod.asyncpg
    svc_mod.asyncpg = type("FakeAsyncpgModule", (), {"PostgresError": FakePostgresErrorBase})
    try:
        svc = _make_service_with_valid_fernet()
        with pytest.raises(NotificationConfigError) as exc_info:
            svc._log_and_raise_db_error(
                FakeUniqueViolation("duplicate key value violates unique constraint"),
                op="upsert_channel.insert",
                ctx={"name": "运维通知", "channel_type": "feishu"},
            )
    finally:
        svc_mod.asyncpg = original_asyncpg

    msg = str(exc_info.value)
    assert "upsert_channel.insert 失败" in msg
    assert "notification_channels_name_type_uniq" in msg, (
        "message 必须含 constraint_name，便于前端一眼看懂"
    )
    assert "23505" in msg, "message 必须含 sqlstate"


def test_upsert_channel_wraps_db_errors_as_notification_config_error():
    """upsert_channel INSERT 抛 DB 异常 → NotificationConfigError（不再 raw asyncpg）。"""
    from app.shared.utils.notification import notification_config_service as svc_mod

    class FakePostgresErrorBase(Exception):
        """模拟 asyncpg.PostgresError 基类。"""

    class UniqueViolationFake(FakePostgresErrorBase):
        sqlstate = "23505"
        constraint_name = "notification_channels_name_type_uniq"
        table_name = "notification_channels"
        detail = "Key (name, channel_type)=(运维通知, feishu) already exists."

    svc, db = _make_service_with_mock_db()
    # mock fetchrow 调用顺序：existing=None → INSERT 抛 UniqueViolation
    db.fetchrow = AsyncMock(side_effect=[
        None,  # existing 查询 → None
        UniqueViolationFake("duplicate key value"),  # INSERT 失败
    ])
    config = _valid_feishu_config(svc)

    original_asyncpg = svc_mod.asyncpg
    svc_mod.asyncpg = type("FakeAsyncpgModule", (), {"PostgresError": FakePostgresErrorBase})
    try:
        with pytest.raises(NotificationConfigError) as exc_info:
            asyncio.run(svc.upsert_channel(
                channel_type="feishu",
                name="运维通知",
                display_name="",
                config=config,
                enabled=True,
                is_default=False,
                created_by_user_id=1,
            ))
    finally:
        svc_mod.asyncpg = original_asyncpg

    msg = str(exc_info.value)
    assert "upsert_channel.insert 失败" in msg
    assert "notification_channels_name_type_uniq" in msg
    assert "23505" in msg


def test_upsert_channel_inserts_second_enabled_channel_same_channel_type():
    """2026-09-10 regression: 同 channel_type 下插入第二条 enabled=TRUE 行不再 unique 冲突。

    历史 bug: idx_notification_channels_enabled UNIQUE 索引误继承自 email 单 SMTP 表，
    与 WS 多实例架构（每应用独立 WS）冲突。修复后此用例应通过。
    本用例在 service 层 mock 模拟：用 existing=None + INSERT 不抛 unique violation 验证。
    （真实 DB 层验证由 init_all_tables.sql DROP INDEX 段保证）
    """
    svc, db = _make_service_with_mock_db()
    # mock execute（第一条 is_default=True 触发原子切换）
    db.execute = AsyncMock(return_value="UPDATE 0")
    # 模拟 INSERT 成功（不被 unique 索引阻挡）
    db.fetchrow = AsyncMock(side_effect=[
        None,  # existing 第一条
        {"id": 1, "updated_at": "2026-09-10"},  # 第一条 INSERT
    ])
    config = _valid_feishu_config(svc)
    result = asyncio.run(svc.upsert_channel(
        channel_type="feishu",
        name="app-1",
        display_name="应用1",
        config=config,
        enabled=True,
        is_default=True,
        created_by_user_id=1,
    ))
    assert result["created"] is True
    assert result["id"] == 1
    # 关键断言：第二条 enabled=TRUE 行也允许插入
    db.fetchrow = AsyncMock(side_effect=[
        None,  # existing 第二条
        {"id": 2, "updated_at": "2026-09-10"},  # 第二条 INSERT
    ])
    result2 = asyncio.run(svc.upsert_channel(
        channel_type="feishu",
        name="app-2",
        display_name="应用2",
        config=config,
        enabled=True,
        is_default=False,
        created_by_user_id=1,
    ))
    assert result2["created"] is True
    assert result2["id"] == 2


# 内部 helper：模拟 asyncpg UniqueViolationError
# （已迁移到各 test 函数内部定义，避免模块级类污染其他用例的 isinstance 路径）
# class UniqueViolationFake(Exception):
#     """模拟 asyncpg.UniqueViolationError，仅供测试。"""
#     sqlstate = "23505"
#     constraint_name = "notification_channels_name_type_uniq"
#     table_name = "notification_channels"
#     detail = "Key (name, channel_type)=(app-1, feishu) already exists."
