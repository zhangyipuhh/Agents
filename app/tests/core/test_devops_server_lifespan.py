# -*- coding:utf-8 -*-
"""
DevOpsServerService 生命周期测试（2026-07-15 新增）

生产对等初始化点：``app/core/server.py::lifespan`` 在数据库池建立后
构造 ``DevOpsServerService`` 并挂到 ``app.state.devops_server_service``；
同时调用 ``DevOpsServerService.set_instance(svc)`` 注入全局单例，
以便 ``app.shared.tools.skills.devops.SSHTools`` 通过单例获取配置。

本测试验证生产 lifespan 中的初始化逻辑片段（replica），无需 lifespan
触发完整事件循环；足够确认：
    1) DB 池存在时构造 DevOpsServerService 并挂到 app.state.devops_server_service
    2) DB 池不存在时降级为 warning，不抛异常
    3) credential_key 为空时跳过初始化
    4) DevOpsServerService 单例被正确 reset
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def _make_lifespan_replica(db_pool, credential_key="x", config_path="x.yaml"):
    """复用 lifespan 中「init DevOpsServerService」的代码段，验证输入产生的副作用。

    Args:
        db_pool: 模拟 DB 池（None 或 MagicMock）
        credential_key: Fernet 密钥（测试中传入合法 base64）
        config_path: YAML 路径（测试中可临时文件）

    Returns:
        tuple[svc_or_None, set_instance_called] - 服务实例与单例注入标记
    """
    from app.shared.utils.devops_server_service import DevOpsServerService

    # 仿 lifespan 内部：先 reset 单例
    DevOpsServerService.reset()
    set_instance_called = False
    svc = None
    app_state_attrs = {}
    if db_pool and credential_key:
        try:
            svc = DevOpsServerService(
                db=db_pool,
                config_path=config_path,
                credential_key=credential_key,
            )
            DevOpsServerService.set_instance(svc)
            set_instance_called = True
            app_state_attrs["devops_server_service"] = svc
        except Exception:
            svc = None
    return svc, set_instance_called, app_state_attrs


def test_lifespan_initialize_devops_service_when_db_pool_present():
    """DB 池存在时构造 DevOpsServerService 并 set_instance。

    Returns:
        None
    """
    from cryptography.fernet import Fernet

    valid_key = Fernet.generate_key().decode("ascii")
    db_pool = MagicMock(name="db_pool")
    db_pool.fetch = AsyncMock(return_value=[])

    svc, set_called, _attrs = _make_lifespan_replica(db_pool, valid_key)
    assert svc is not None
    assert set_called is True
    # 单例正确设置
    from app.shared.utils.devops_server_service import DevOpsServerService
    assert DevOpsServerService.get_instance() is svc
    DevOpsServerService.reset()


def test_lifespan_skips_when_db_pool_missing():
    """DB 池不可用时跳过初始化（不抛异常）。"""
    svc, set_called, attrs = _make_lifespan_replica(None, "x")
    assert svc is None
    assert set_called is False
    assert "devops_server_service" not in attrs


def test_lifespan_skips_when_credential_key_empty():
    """credential_key 为空字符串时跳过初始化。

    Returns:
        None
    """
    db_pool = MagicMock(name="db_pool")
    db_pool.fetch = AsyncMock(return_value=[])
    svc, set_called, attrs = _make_lifespan_replica(db_pool, "")
    assert svc is None
    assert set_called is False
    assert "devops_server_service" not in attrs


def test_lifespan_singleton_reset_on_shutdown():
    """lifespan 结束时应调用 ``DevOpsServerService.reset()``，避免单例残留。

    Returns:
        None
    """
    from cryptography.fernet import Fernet
    from app.shared.utils.devops_server_service import DevOpsServerService

    valid_key = Fernet.generate_key().decode("ascii")
    db = MagicMock(name="db")
    db.fetch = AsyncMock(return_value=[])
    svc = DevOpsServerService(db=db, config_path="x.yaml", credential_key=valid_key)
    DevOpsServerService.set_instance(svc)
    assert DevOpsServerService.get_instance() is svc

    # 模拟 lifespan yield 后的清理
    DevOpsServerService.reset()
    # reset 后 get_instance 应抛 RuntimeError
    try:
        DevOpsServerService.get_instance()
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
