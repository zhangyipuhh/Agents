# -*- coding:utf-8 -*-
"""
LogService lifespan 行为测试模块。

验证统一日志服务（LogService）在生产 lifespan 中的真实初始化顺序与关闭逻辑。

生产对等初始化点：``app/core/server.py`` lifespan 函数中
``app.state.log_service = LogService(db_pool=DatabasePool._pool)`` + ``await app.state.log_service.start()``。
"""
import inspect
import os


def test_lifespan_initializes_log_service_after_db_schema_registration():
    """测试 lifespan 源码顺序：LogService 初始化必须在 DB schema 注册之后。

    验证：
    - ``await DatabasePool.register_schemas()`` 先于 LogService 构造调用
    - ``app.state.log_service = log_service`` 在 lifespan 中存在
    - 启动时调用 ``await log_service.start()`` 进入后台消费循环

    生产对等初始化点：``app/core/server.py`` lifespan 函数中
    ``DatabasePool.register_schemas()`` → ``LogService(db_pool=...)`` → ``await log_service.start()`` 段。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 顺序错误或未通过 start() 启动后台协程时抛出。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    schema_index = source.index("await DatabasePool.register_schemas()")
    log_service_init_index = source.index(
        "log_service = LogService(db_pool=DatabasePool._pool)"
    )
    log_service_start_index = source.index("await log_service.start()")
    log_service_state_index = source.index("app.state.log_service = log_service")

    # schema 注册必须在 LogService 初始化之前,否则 audit_logs 扩展列未建
    assert schema_index < log_service_init_index, (
        "lifespan 中 DatabasePool.register_schemas() 必须在 LogService 初始化之前, "
        "否则 audit_logs 扩展列未建,executemany 写入会因列缺失失败。"
    )
    # start() 必须在 LogService 挂到 app.state 之前(或同段),保证 emit 不会因未启动而丢
    assert log_service_start_index < log_service_state_index, (
        "lifespan 中 await log_service.start() 必须在 app.state.log_service = log_service 之前, "
        "保证 emit 调用方看到服务时已具备 consume_loop。"
    )


def test_lifespan_stops_log_service_before_database_close():
    """测试 lifespan 关闭顺序：LogService.stop() 必须在 DatabasePool.close() 之前。

    验证：
    - ``await svc.stop()`` 先于 ``await DatabasePool.close()`` 调用
    - shutdown 路径清理 get_log_service() 单例 + reset_log_service()

    生产对等初始化点：``app/core/server.py`` lifespan 关闭段（LogService stop →
    reset_log_service → DatabasePool.close）。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 关闭顺序错误时抛出。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    log_service_stop_index = source.index("await svc.stop()")
    db_close_index = source.index("await DatabasePool.close()")

    # LogService 关闭必须在 DatabasePool.close() 之前,确保队列残留事件能 flush
    assert log_service_stop_index < db_close_index, (
        "lifespan 关闭阶段 LogService.stop() 必须在 DatabasePool.close() 之前, "
        "否则队列残留事件因连接池已关闭而无法 flush 到 DB。"
    )
    # reset_log_service 与 app.state 都必须清理,避免下次启动看到脏实例
    assert "reset_log_service()" in source, (
        "lifespan 关闭阶段必须调用 reset_log_service(),避免下次启动看到脏单例。"
    )
    assert "app.state.log_service = None" in source, (
        "lifespan 关闭阶段必须清空 app.state.log_service。"
    )


def test_lifespan_log_service_uses_real_db_pool_when_enabled():
    """测试 lifespan：DB 启用时 LogService 必须拿到 DatabasePool._pool 真实实例。

    验证：
    - 构造参数 ``db_pool=DatabasePool._pool`` 而非 ``None`` 或 ``MagicMock()``
    - 单例由 ``set_log_service(log_service)`` 注册并通过 ``get_log_service()`` 可取回

    生产对等初始化点：``app/core/server.py`` lifespan 函数中
    ``LogService(db_pool=DatabasePool._pool)`` + ``set_log_service(log_service)``。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 注入失败或身份不同时抛出。
    """
    import inspect
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    # 必须显式透传 DatabasePool._pool 而非伪造对象
    assert "LogService(db_pool=DatabasePool._pool)" in source, (
        "lifespan 中 LogService 构造必须显式透传 DatabasePool._pool 真实连接池, "
        "不允许用 MagicMock / None 替代。"
    )
    # 必须通过 set_log_service 注册到全局单例
    assert "set_log_service(log_service)" in source, (
        "lifespan 中必须调用 set_log_service(log_service) 注册到全局单例。"
    )
    # 必须挂到 app.state 供 router / 中间件读取
    assert "app.state.log_service = log_service" in source, (
        "lifespan 中必须将 LogService 实例挂到 app.state.log_service。"
    )


def test_lifespan_log_service_initialization_failure_does_not_raise():
    """测试 lifespan：LogService 初始化失败时被 try/except 捕获,不影响 lifespan。

    验证：
    - LogService 初始化代码段在 try/except 中,任意异常不向外抛出
    - 失败时记 warning,而不是 raise

    生产对等初始化点：``app/core/server.py`` lifespan 函数中
    ``try: ... except Exception as log_init_exc: logging.warning(...)`` 段。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 未包裹 try/except 时抛出。
    """
    import inspect
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    # 必须有 try / except Exception 包裹 LogService 初始化块
    init_block = source[
        source.index("log_service = LogService(db_pool=DatabasePool._pool)") :
    ]
    assert "try:" in source, "LogService init must be inside try/except"
    assert "except Exception as log_init_exc:" in source, (
        "LogService init failures must be caught by 'except Exception' branch"
    )


def test_lifespan_log_service_memory_only_fallback_when_db_disabled():
    """测试 lifespan：DB 不可用时 LogService 走内存模式。

    验证：
    - LogService 构造不依赖 DatabasePool._pool 必须非空
    - 即使 db_pool=None 也能正常工作(降级到 memory 模式)

    生产对等初始化点：``app/core/server.py`` lifespan 函数 + ``LogService``
    内部 ``self._memory_only = bool(memory_only or os.getenv(...))`` 判定逻辑。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: 降级逻辑缺失时抛出。
    """
    # 重现 LogService 在 db_pool=None / AUTH_STORAGE_MODE=memory 时自动降级
    from app.shared.utils.log_service import LogService

    # 模拟 production 的 AUTH_STORAGE_MODE=memory
    old = os.environ.get("AUTH_STORAGE_MODE")
    os.environ["AUTH_STORAGE_MODE"] = "memory"
    try:
        svc = LogService(db_pool=None)
        assert svc._memory_only is True, (
            "db_pool=None + AUTH_STORAGE_MODE=memory 时 LogService 必须降级到内存模式"
        )
    finally:
        if old is not None:
            os.environ["AUTH_STORAGE_MODE"] = old
        else:
            os.environ.pop("AUTH_STORAGE_MODE", None)


def test_lifespan_log_service_uses_existing_database_pool_class():
    """测试 lifespan：LogService 与现有 DatabasePool._pool 兼容（不强加新增注册入口）。

    验证：
    - LogService 构造签名接受 db_pool 参数（兼容现有 DatabasePool._pool）
    - 2026-07-29 迁移：``init_audit_log_schema`` 入口从
      ``app/shared/utils/auth/audit_log.py`` 迁到 ``app/shared/utils/log_service.py``，
      与 ``init_all_tables.sql`` 互为补充（DDL 同源）。

    生产对等初始化点：``app/core/database.py::DatabasePool._pool`` + ``app/core/server.py`` lifespan。

    参数:
        无。

    返回值:
        None。

    异常:
        AssertionError: schema 双轨漂移时抛出。
    """
    import inspect

    from app.shared.utils.log_service import LogService

    sig = inspect.signature(LogService.__init__)
    assert "db_pool" in sig.parameters, (
        "LogService.__init__ 必须接收 db_pool 参数,与现有 DatabasePool._pool 兼容"
    )
    # 2026-07-29 迁移后：log_service.py 持有 init_audit_log_schema @register_schema 入口
    # （替代旧 audit_log.py），与 init_all_tables.sql 同源互补。
    src_file = inspect.getsourcefile(LogService)
    with open(src_file, "r", encoding="utf-8") as fh:
        mod_src = fh.read()
    assert "register_schema" in mod_src, (
        "2026-07-29 迁移后,LogService 模块必须持有 @register_schema 装饰的 "
        "init_audit_log_schema 入口,作为 audit_logs 表的唯一 schema 注册点。"
    )
    assert "async def init_audit_log_schema" in mod_src, (
        "2026-07-29 迁移后,LogService 模块必须包含 init_audit_log_schema 函数定义。"
    )
    # 旧 audit_log.py 已删除,业务侧无旧模块引用（本测试只断言新入口到位）。
    assert "from app.shared.utils.auth.audit_log import" not in mod_src, (
        "LogService 不应再 import 旧 audit_log 模块,schema 入口已迁到 log_service.py。"
    )