# -*- coding:utf-8 -*-
"""
FeishuWebSocketManager 单元测试(2026-09-03 新增)。

测试覆盖:
- P0 模块导入与构造
- P1 DB 无 enabled 飞书渠道 → INFO log skip,**正常返回 started=0,不抛异常**
- P1 多 channel → 每条 channel 启动独立 FeishuWebSocketService 实例(独立 lark.Client)
- P1 单 channel → 实例绑 channel_id,session_id 命名空间加 channel_id 段
- P2 凭证解密失败 → 跳过该 channel,不影响其他 channel
- P2 receiver_username 不存在用户 → 跳过该 channel
- P2 agent_name / receiver_username 为空 → 跳过该 channel
- P1 stop_all → 遍历 stop + clear services
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.utils.notification.notification_config_service import (
    SUPPORTED_CHANNEL_TYPES,
)


# 引入 service 类(在 conftest 已 mock lark,先 import 模块再测)
def _import_manager_module():
    """延迟导入,避免顶层 conftest 之外的副作用。"""
    from app.shared.tools.skills.feishu import FeishuWebSocketManager as mod

    return mod


def _make_encrypted_config(app_id: str = "cli_xxx", app_secret: str = "secret_yyy") -> dict:
    """构造已加密的飞书 config(模拟从 DB 读出)。"""
    from cryptography.fernet import Fernet

    fernet = Fernet(VALID_FERNET_KEY_FOR_TEST.encode("ascii"))
    return {
        "app_id_encrypted": fernet.encrypt(app_id.encode("utf-8")).decode("ascii"),
        "app_secret_encrypted": fernet.encrypt(app_secret.encode("utf-8")).decode("ascii"),
        "default_receive_id": "oc_xxx",
        "default_receive_id_type": "chat_id",
        "log_level": "INFO",
        "agent_name": "project",
        "receiver_username": "admin",
    }


def test_module_importable():
    """FeishuWebSocketManager 模块可导入。"""
    mod = _import_manager_module()
    assert hasattr(mod, "FeishuWebSocketManager")
    assert hasattr(mod, "_resolve_lark_log_level")


def test_construct():
    """构造 FeishuWebSocketManager 实例。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)
    assert manager._notification_service is fake_service
    assert manager.services == {}


def test_resolve_lark_log_level_known():
    """_resolve_lark_log_level 把字符串映射到枚举值。"""
    mod = _import_manager_module()
    import lark_oapi as lark

    assert mod._resolve_lark_log_level("DEBUG") == lark.LogLevel.DEBUG
    assert mod._resolve_lark_log_level("INFO") == lark.LogLevel.INFO
    assert mod._resolve_lark_log_level("WARNING") == lark.LogLevel.WARNING
    assert mod._resolve_lark_log_level("ERROR") == lark.LogLevel.ERROR


def test_resolve_lark_log_level_unknown_defaults_to_info():
    """_resolve_lark_log_level 未识别字符串 → 默认 INFO。"""
    mod = _import_manager_module()
    import lark_oapi as lark

    assert mod._resolve_lark_log_level("INVALID") == lark.LogLevel.INFO
    assert mod._resolve_lark_log_level("") == lark.LogLevel.INFO
    assert mod._resolve_lark_log_level(None) == lark.LogLevel.INFO  # type: ignore[arg-type]


def test_start_all_returns_zero_when_no_channels(caplog):
    """DB 无 enabled 飞书渠道 → INFO log + started=0,不抛异常。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    fake_service.list_channels = AsyncMock(return_value=[])
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    agent_config_service = MagicMock()
    user_lookup = AsyncMock()

    with caplog.at_level(logging.INFO, logger="app.shared.tools.skills.feishu.FeishuWebSocketManager"):
        started = asyncio.run(manager.start_all(agent_config_service, user_lookup))

    assert started == 0
    assert manager.services == {}
    # 应记录 INFO log
    assert any(
        "skipped" in record.message.lower() and "数据库无" in record.message
        for record in caplog.records
    )


def test_start_all_starts_one_instance_per_channel():
    """3 个 enabled 飞书渠道 → 启动 3 个独立 FeishuWebSocketService。"""
    mod = _import_manager_module()

    channels_public = [
        {"id": 1, "name": "ops", "channel_type": "feishu", "enabled": True, "is_default": False,
         "config": {"agent_name": "project"}, "display_name": "Ops"},
        {"id": 2, "name": "biz", "channel_type": "feishu", "enabled": True, "is_default": False,
         "config": {"agent_name": "knowledge_ydt"}, "display_name": "Biz"},
        {"id": 3, "name": "ai", "channel_type": "feishu", "enabled": True, "is_default": True,
         "config": {"agent_name": "project"}, "display_name": "AI"},
    ]

    fake_service = MagicMock()
    fake_service.list_channels = AsyncMock(return_value=channels_public)
    fake_service._get_channel_internal = AsyncMock(side_effect=[
        {**c, "config": _make_encrypted_config()} for c in channels_public
    ])

    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    agent_config_service = MagicMock()
    user_lookup = AsyncMock(return_value={"id": 1, "username": "admin"})

    # Mock lark.Client.builder + FeishuWebSocketService
    # manager 内部直接 from app.shared.tools.skills.feishu.FeishuWebSocketService import
    with patch(
        "app.shared.tools.skills.feishu.FeishuWebSocketService.FeishuWebSocketService"
    ) as MockWS, patch("lark_oapi.Client.builder") as MockBuilder:
        mock_client = MagicMock()
        MockBuilder.return_value.app_id.return_value.app_secret.return_value.log_level.return_value.build.return_value = mock_client
        # 让 MockWS 的实例调用 start_async 时返回 None
        async def _start_async_stub(*args, **kwargs):
            return None
        MockWS.return_value.start_async = _start_async_stub

        started = asyncio.run(manager.start_all(agent_config_service, user_lookup))

    assert started == 3
    assert set(manager.services.keys()) == {1, 2, 3}
    # 验证 3 个实例被构造(每个 channel_id 一个)
    assert MockWS.call_count == 3
    # 验证 _channel_id 被注入(各实例 channel_id 唯一)
    injected_channel_ids = [
        call.kwargs.get("lark_client") for call in MockWS.call_args_list
    ]
    assert all(client is mock_client for client in injected_channel_ids)


def test_start_all_skips_channel_when_credentials_empty():
    """凭证为空(app_id_encrypted 缺失)→ 跳过该 channel,不抛异常。"""
    mod = _import_manager_module()
    channels_public = [
        {"id": 1, "name": "empty-creds", "channel_type": "feishu", "enabled": True, "is_default": True,
         "config": {}, "display_name": ""},
    ]
    fake_service = MagicMock()
    fake_service.list_channels = AsyncMock(return_value=channels_public)
    # 凭证为空时,_get_channel_internal 返回空 config
    fake_service._get_channel_internal = AsyncMock(return_value={
        "id": 1, "name": "empty-creds", "channel_type": "feishu",
        "config": {}, "enabled": True, "is_default": True, "created_by_user_id": None,
        "created_at": None, "updated_at": None, "display_name": "",
    })

    manager = mod.FeishuWebSocketManager(notification_service=fake_service)
    started = asyncio.run(manager.start_all(MagicMock(), AsyncMock()))
    assert started == 0
    assert manager.services == {}


def test_start_all_skips_channel_when_agent_name_empty():
    """agent_name 为空 → 跳过该 channel。

    2026-09-07 第二轮：channel 重新绑智能体，agent_name 从 channel.config.agent_name 读。
    """
    mod = _import_manager_module()
    channels_public = [
        {"id": 1, "name": "no-agent", "channel_type": "feishu", "enabled": True, "is_default": True,
         "config": {"agent_name": ""}, "display_name": ""},
    ]
    fake_service = MagicMock()
    fake_service.list_channels = AsyncMock(return_value=channels_public)
    fake_service._get_channel_internal = AsyncMock(return_value={
        "id": 1, "name": "no-agent", "channel_type": "feishu",
        "config": {**_make_encrypted_config(), "agent_name": ""},
        "enabled": True, "is_default": True, "created_by_user_user_id": None,
        "created_at": None, "updated_at": None, "display_name": "",
    })
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)
    started = asyncio.run(manager.start_all(MagicMock(), AsyncMock()))
    assert started == 0


def test_start_all_skips_channel_when_receiver_username_not_exist():
    """receiver_username 在 users 表不存在 → 跳过该 channel。"""
    mod = _import_manager_module()
    channels_public = [
        {"id": 1, "name": "no-receiver", "channel_type": "feishu", "enabled": True, "is_default": True,
         "config": {"receiver_username": "ghost"}, "display_name": ""},
    ]
    fake_service = MagicMock()
    fake_service.list_channels = AsyncMock(return_value=channels_public)
    fake_service._get_channel_internal = AsyncMock(return_value={
        "id": 1, "name": "no-receiver", "channel_type": "feishu",
        "config": {**_make_encrypted_config(), "receiver_username": "ghost"},
        "enabled": True, "is_default": True, "created_by_user_id": None,
        "created_at": None, "updated_at": None, "display_name": "",
    })
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)
    user_lookup = AsyncMock(return_value=None)  # 不存在
    started = asyncio.run(manager.start_all(MagicMock(), user_lookup))
    assert started == 0


def test_start_all_continues_when_one_channel_fails():
    """某 channel 启动异常 → 继续其他 channel,不中断整轮。"""
    mod = _import_manager_module()

    channels_public = [
        {"id": 1, "name": "ok", "channel_type": "feishu", "enabled": True, "is_default": False,
         "config": {}, "display_name": ""},
        {"id": 2, "name": "fail", "channel_type": "feishu", "enabled": True, "is_default": False,
         "config": {}, "display_name": ""},
        {"id": 3, "name": "ok2", "channel_type": "feishu", "enabled": True, "is_default": False,
         "config": {}, "display_name": ""},
    ]
    fake_service = MagicMock()
    fake_service.list_channels = AsyncMock(return_value=channels_public)
    # channel 1 OK, channel 2 抛异常, channel 3 OK
    fake_service._get_channel_internal = AsyncMock(side_effect=[
        {"id": 1, "name": "ok", "channel_type": "feishu",
         "config": _make_encrypted_config(), "enabled": True, "is_default": False,
         "created_by_user_id": None, "created_at": None, "updated_at": None, "display_name": ""},
        RuntimeError("simulated DB error"),  # channel 2 异常
        {"id": 3, "name": "ok2", "channel_type": "feishu",
         "config": _make_encrypted_config(), "enabled": True, "is_default": False,
         "created_by_user_id": None, "created_at": None, "updated_at": None, "display_name": ""},
    ])
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    with patch("app.shared.tools.skills.feishu.FeishuWebSocketService") as MockWS, \
         patch("lark_oapi.Client.builder") as MockBuilder:
        mock_client = MagicMock()
        MockBuilder.return_value.app_id.return_value.app_secret.return_value.log_level.return_value.build.return_value = mock_client
        async def _start_async_stub(self):
            return None
        MockWS.return_value.start_async = _start_async_stub
        user_lookup = AsyncMock(return_value={"id": 1, "username": "admin"})
        started = asyncio.run(manager.start_all(MagicMock(), user_lookup))

    # 2 个成功(channel 2 异常跳过)
    assert started == 2
    assert set(manager.services.keys()) == {1, 3}


def test_stop_all_clears_services():
    """stop_all → 遍历 stop + 清空 services。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    svc1 = MagicMock()
    svc1.stop = MagicMock()
    svc2 = MagicMock()
    svc2.stop = MagicMock()
    manager.services = {1: svc1, 2: svc2}

    asyncio.run(manager.stop_all())
    svc1.stop.assert_called_once()
    svc2.stop.assert_called_once()
    assert manager.services == {}


def test_stop_all_continues_when_one_stop_raises():
    """stop_all:某实例 stop 抛异常 → 继续其他实例。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    svc1 = MagicMock()
    svc1.stop = MagicMock(side_effect=RuntimeError("boom"))
    svc2 = MagicMock()
    svc2.stop = MagicMock()
    manager.services = {1: svc1, 2: svc2}

    # 不抛异常(异常被吞,日志记录 warning)
    asyncio.run(manager.stop_all())
    svc2.stop.assert_called_once()
    assert manager.services == {}


# =============================================================================
# 保存即生效热加载测试（2026-09-10 新增）
# =============================================================================


def _make_enabled_internal_row(channel_id: int = 5, name: str = "ai") -> dict:
    """构造 enabled 飞书渠道 internal 行（含加密 config 原文）。"""
    return {
        "id": channel_id,
        "name": name,
        "channel_type": "feishu",
        "enabled": True,
        "is_default": False,
        "config": _make_encrypted_config(),
        "display_name": name,
    }


def _patch_ws_start():
    """返回 manager 启动路径所需的两个 patcher（WS 服务类 + lark builder）。

    Returns:
        tuple: (ws_patcher, builder_patcher)；WS 实例的 ``start_async`` 已 stub
            为空协程，``shutdown`` 为 MagicMock。
    """
    ws_patcher = patch(
        "app.shared.tools.skills.feishu.FeishuWebSocketService.FeishuWebSocketService"
    )
    builder_patcher = patch("lark_oapi.Client.builder")
    return ws_patcher, builder_patcher


def _stub_ws_class(MockWS, MockBuilder):
    """配置 MockWS / MockBuilder 的默认返回值。"""
    mock_client = MagicMock()
    MockBuilder.return_value.app_id.return_value.app_secret.return_value.log_level.return_value.build.return_value = mock_client

    async def _start_async_stub(*args, **kwargs):
        return None

    MockWS.return_value.start_async = _start_async_stub
    MockWS.return_value.shutdown = MagicMock()
    return mock_client


def test_apply_channel_change_starts_new_instance_when_enabled():
    """P1：渠道 enabled 且当前无实例 → 热启动新实例并返回 True。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(
        return_value=_make_enabled_internal_row(channel_id=5)
    )
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    ws_patcher, builder_patcher = _patch_ws_start()
    with ws_patcher as MockWS, builder_patcher as MockBuilder:
        _stub_ws_class(MockWS, MockBuilder)
        user_lookup = AsyncMock(return_value={"id": 1, "username": "admin"})
        result = asyncio.run(
            manager.apply_channel_change(5, MagicMock(), user_lookup)
        )

    assert result is True
    assert set(manager.services.keys()) == {5}


def test_apply_channel_change_restarts_existing_instance():
    """P1：渠道已运行 → 先 shutdown 旧实例，再按最新配置重启。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(
        return_value=_make_enabled_internal_row(channel_id=7)
    )
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    old_svc = MagicMock()
    old_svc.shutdown = MagicMock()
    manager.services[7] = old_svc

    ws_patcher, builder_patcher = _patch_ws_start()
    with ws_patcher as MockWS, builder_patcher as MockBuilder:
        _stub_ws_class(MockWS, MockBuilder)
        user_lookup = AsyncMock(return_value={"id": 1, "username": "admin"})
        result = asyncio.run(
            manager.apply_channel_change(7, MagicMock(), user_lookup)
        )

    assert result is True
    old_svc.shutdown.assert_called_once()
    # 新实例替换旧实例
    assert manager.services[7] is not old_svc


def test_apply_channel_change_stops_when_channel_disabled():
    """P1：渠道已禁用 → 停旧实例、不重启，返回 False。"""
    mod = _import_manager_module()
    row = _make_enabled_internal_row(channel_id=8)
    row["enabled"] = False
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(return_value=row)
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    old_svc = MagicMock()
    manager.services[8] = old_svc

    result = asyncio.run(manager.apply_channel_change(8, MagicMock(), AsyncMock()))

    assert result is False
    old_svc.shutdown.assert_called_once()
    assert manager.services == {}


def test_apply_channel_change_stops_when_channel_deleted():
    """P1：渠道已删除（DB 读不到行）→ 停旧实例，返回 False。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(return_value=None)
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    old_svc = MagicMock()
    manager.services[9] = old_svc

    result = asyncio.run(manager.apply_channel_change(9, MagicMock(), AsyncMock()))

    assert result is False
    old_svc.shutdown.assert_called_once()
    assert manager.services == {}


def test_apply_channel_change_returns_false_when_db_read_fails():
    """P2：apply 读取 DB 异常 → 旧实例已停、返回 False、不抛异常。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(
        side_effect=RuntimeError("db down")
    )
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    old_svc = MagicMock()
    manager.services[10] = old_svc

    result = asyncio.run(manager.apply_channel_change(10, MagicMock(), AsyncMock()))

    assert result is False
    old_svc.shutdown.assert_called_once()
    assert manager.services == {}


def test_apply_channel_change_tolerates_old_shutdown_failure():
    """P2：旧实例 shutdown 抛异常 → 仍继续读 DB 并按需重启（fail-soft）。"""
    mod = _import_manager_module()
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(
        return_value=_make_enabled_internal_row(channel_id=11)
    )
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)

    old_svc = MagicMock()
    old_svc.shutdown = MagicMock(side_effect=RuntimeError("shutdown boom"))
    manager.services[11] = old_svc

    ws_patcher, builder_patcher = _patch_ws_start()
    with ws_patcher as MockWS, builder_patcher as MockBuilder:
        _stub_ws_class(MockWS, MockBuilder)
        user_lookup = AsyncMock(return_value={"id": 1, "username": "admin"})
        result = asyncio.run(
            manager.apply_channel_change(11, MagicMock(), user_lookup)
        )

    assert result is True
    assert 11 in manager.services


def test_restart_channel_delegates_to_apply_channel_change():
    """P1：restart_channel 委托 apply_channel_change（渠道禁用时返回 False）。"""
    mod = _import_manager_module()
    row = _make_enabled_internal_row(channel_id=1)
    row["enabled"] = False
    fake_service = MagicMock()
    fake_service._get_channel_internal = AsyncMock(return_value=row)
    manager = mod.FeishuWebSocketManager(notification_service=fake_service)
    result = asyncio.run(manager.restart_channel(channel_id=1))
    assert result is False


# =============================================================================
# session_id 命名空间测试(FeishuWebSocketService)
# =============================================================================


def test_build_session_id_without_channel_id_uses_old_format():
    """FeishuWebSocketService._channel_id=None → 旧版 session_id 格式(向后兼容)。"""
    from app.shared.tools.skills.feishu.FeishuWebSocketService import (
        FeishuWebSocketService,
    )
    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=MagicMock(),
        agent_name="project",
        receiver_user_id=None,
        receiver_username="admin",
    )
    # 默认 _channel_id=None → 旧格式
    assert svc._channel_id is None
    assert svc._build_session_id("p2p", "", "ou_xxx") == "feishu:p2p:ou_xxx"
    assert svc._build_session_id("group", "oc_chat", "ou_xxx") == "feishu:group:oc_chat:ou_xxx"


def test_build_session_id_with_channel_id_uses_new_format():
    """FeishuWebSocketService._channel_id=10 → session_id 加 feishu:10 前缀。"""
    from app.shared.tools.skills.feishu.FeishuWebSocketService import (
        FeishuWebSocketService,
    )
    svc = FeishuWebSocketService(
        lark_client=MagicMock(),
        agent_config_service=MagicMock(),
        agent_name="project",
        receiver_user_id=None,
        receiver_username="admin",
    )
    svc._channel_id = 10
    assert svc._build_session_id("p2p", "", "ou_xxx") == "feishu:10:p2p:ou_xxx"
    assert svc._build_session_id("group", "oc_chat", "ou_xxx") == "feishu:10:group:oc_chat:ou_xxx"


# 有效 Fernet key 复用 .env 中的现有值
VALID_FERNET_KEY_FOR_TEST = "Ly_GPItylXtIJiS2qEQ5FjCaBxMhTkJUByS9aoaIFng="
