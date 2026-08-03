# -*- coding:utf-8 -*-
"""server.py 配置服务预加载后发布行为测试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


SERVICE_CASES = (
    ("inspection_script_service", "InspectionScriptService"),
    ("devops_server_service", "DevOpsServerService"),
)


def _get_publish_helper():
    """获取生产环境预加载并发布服务的统一辅助函数。

    Returns:
        Callable: ``app.core.server`` 中的异步发布辅助函数。

    Raises:
        AssertionError: 生产代码尚未提供该辅助函数时抛出。
    """
    from app.core import server

    helper = getattr(server, "_preload_and_publish_service", None)
    assert callable(helper), "server.py 必须提供预加载成功后才发布服务的统一入口"
    return helper


@pytest.mark.parametrize(("state_attribute", "service_name"), SERVICE_CASES)
def test_preload_failure_does_not_publish_service(state_attribute, service_name):
    """预加载异常时必须写入 None，且不得注册单例。

    Args:
        state_attribute: ``app.state`` 上的服务属性名。
        service_name: 用于日志的服务名称。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 失败服务仍被发布时抛出。
    """
    helper = _get_publish_helper()
    app = SimpleNamespace(state=SimpleNamespace())
    service = SimpleNamespace(
        preload_all=AsyncMock(side_effect=RuntimeError("preload failed"))
    )
    service_class = MagicMock(return_value=service)
    service_class.set_instance = MagicMock()

    result = asyncio.run(
        helper(
            app=app,
            service_class=service_class,
            service_name=service_name,
            state_attribute=state_attribute,
            constructor_kwargs={"db": object()},
        )
    )

    assert result is None
    assert getattr(app.state, state_attribute) is None
    service_class.set_instance.assert_not_called()


@pytest.mark.parametrize(("state_attribute", "service_name"), SERVICE_CASES)
def test_constructor_failure_does_not_publish_service(state_attribute, service_name):
    """构造异常时必须写入 None，且不得注册单例。

    Args:
        state_attribute: ``app.state`` 上的服务属性名。
        service_name: 用于日志的服务名称。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 构造失败后仍发布服务时抛出。
    """
    helper = _get_publish_helper()
    app = SimpleNamespace(state=SimpleNamespace())
    service_class = MagicMock(side_effect=ValueError("constructor failed"))
    service_class.set_instance = MagicMock()

    result = asyncio.run(
        helper(
            app=app,
            service_class=service_class,
            service_name=service_name,
            state_attribute=state_attribute,
            constructor_kwargs={"db": object()},
        )
    )

    assert result is None
    assert getattr(app.state, state_attribute) is None
    service_class.set_instance.assert_not_called()


@pytest.mark.parametrize(("state_attribute", "service_name"), SERVICE_CASES)
def test_preload_success_publishes_same_service_instance(state_attribute, service_name):
    """只有预加载成功才发布同一服务实例。

    Args:
        state_attribute: ``app.state`` 上的服务属性名。
        service_name: 用于日志的服务名称。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 单例或应用状态未发布同一实例时抛出。
    """
    helper = _get_publish_helper()
    app = SimpleNamespace(state=SimpleNamespace())
    service = SimpleNamespace(preload_all=AsyncMock(return_value=None))
    service_class = MagicMock(return_value=service)
    service_class.set_instance = MagicMock()

    result = asyncio.run(
        helper(
            app=app,
            service_class=service_class,
            service_name=service_name,
            state_attribute=state_attribute,
            constructor_kwargs={"db": object()},
        )
    )

    assert result is service
    assert getattr(app.state, state_attribute) is service
    service_class.set_instance.assert_called_once_with(service)
