# -*- coding:utf-8 -*-
"""
脚本注册表。

提供 ``@register_script`` 装饰器，把符合契约的异步函数连同元数据注册到
进程内全局注册表 ``_SCRIPT_REGISTRY``，供 ``ScriptDiscoveryService`` 与
``TaskSchedulerService`` 查询。

契约：
    * 被装饰函数必须是协程函数（``async def``）
    * 函数签名为 ``(context: ScriptContext)``，返回 ``str``
    * ``name`` 全局唯一，重复注册抛 ``ValueError``

使用示例::

    from app.scripts.base import ScriptContext
    from app.scripts.registry import register_script

    @register_script(
        name="hello_script",
        display_name="示例问候脚本",
        description="每分钟输出一条问候日志",
    )
    async def run(context: ScriptContext) -> str:
        context.log_logger.info("hello")
        return "ok"
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Dict, Optional

from app.scripts.base import RegisteredScript, ScriptContext


# 进程内全局注册表：name -> RegisteredScript
# 注意：多进程部署时每个 worker 各自维护一份；脚本调度由 APScheduler 单 worker 触发，
# 不会出现跨 worker 重复执行的问题。
_SCRIPT_REGISTRY: Dict[str, RegisteredScript] = {}


def register_script(
    name: str,
    display_name: str,
    description: str = "",
    params_schema: Optional[Dict[str, Any]] = None,
) -> Callable[[Callable[[ScriptContext], Any]], Callable[[ScriptContext], Any]]:
    """装饰器：把异步函数注册为可调度脚本。

    参数:
        name: 脚本唯一标识。重复注册抛 ``ValueError``。
        display_name: 前端展示名称。
        description: 脚本描述（可选）。
        params_schema: ``script_args`` 的 JSON schema（可选）。

    返回:
        Callable: 装饰器函数，原样返回被装饰函数。

    异常:
        ValueError: ``name`` 已存在或参数非法时抛出。
        TypeError: 被装饰对象不是协程函数时抛出。
    """

    if not name or not isinstance(name, str):
        raise ValueError("register_script: name 必须是非空字符串")
    if not display_name or not isinstance(display_name, str):
        raise ValueError("register_script: display_name 必须是非空字符串")
    if name in _SCRIPT_REGISTRY:
        raise ValueError(f"register_script: 脚本名 '{name}' 已被注册")

    schema = params_schema or {}

    def decorator(func: Callable[[ScriptContext], Any]) -> Callable[[ScriptContext], Any]:
        """实际装饰器，校验函数契约并写入注册表。

        参数:
            func: 被装饰的异步函数。

        返回:
            原函数（未包装）。

        异常:
            TypeError: 函数不是协程函数时抛出。
            ValueError: 函数签名不接受单个位置参数时抛出。
        """
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(
                f"register_script: '{name}' 必须是 async def 协程函数"
            )

        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        if len(params) != 1 or params[0].kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            raise ValueError(
                f"register_script: '{name}' 必须接受单个位置参数 (context: ScriptContext)"
            )

        module_path = f"{func.__module__}.{func.__name__}"
        _SCRIPT_REGISTRY[name] = RegisteredScript(
            name=name,
            display_name=display_name,
            description=description,
            params_schema=schema,
            module_path=module_path,
            func=func,
        )
        return func

    return decorator


def get_registered_scripts() -> Dict[str, RegisteredScript]:
    """返回注册表浅拷贝。

    返回:
        Dict[str, RegisteredScript]: name -> RegisteredScript 的字典副本。
    """
    return dict(_SCRIPT_REGISTRY)


def get_registered_script(name: str) -> Optional[RegisteredScript]:
    """按名称查询已注册脚本。

    参数:
        name: 脚本唯一标识。

    返回:
        Optional[RegisteredScript]: 找到则返回，否则返回 None。
    """
    return _SCRIPT_REGISTRY.get(name)


def clear_registry() -> None:
    """清空注册表（仅供测试使用）。

    返回:
        None。
    """
    _SCRIPT_REGISTRY.clear()
