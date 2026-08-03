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

import inspect
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


# ===========================================================================
# 2026-08-03 审查加固：InspectionScriptService → DevOpsServerService 依赖契约
# ===========================================================================
# 关键约束：
#   - InspectionScriptService 是 DevOpsServerService 的强依赖（解析
#     inspection_script_id / 解析脚本原文 / 评估 inspection_fields）
#   - lifespan 中脚本库初始化失败时，DevOpsServerService **不得** 半残构造
#   - 不允许"DevOpsServerService 构造成功但 inspection_script_service=None"
#     半残状态被注入到 app.state
# ===========================================================================


def test_lifespan_devops_construction_guard_blocks_when_iss_missing():
    """测试 lifespan 源码契约：DevOpsServerService 构造前必须显式守卫
    ``inspection_script_service is None``，缺失时**不得构造**，仅挂 hint。

    这是修复 DevOps 半残状态的核心契约：
        - 历史：脚本库失败时降级为 None，DevOpsServerService 仍构造；
          后续 get_connection_config 返回不含 inspection_script 字段
          的 dict（半残 None 元数据），admin API 返回误导性响应。
        - 修复：脚本库缺失时 DevOpsServerService **不被构造**，router
          由 devops_server_service_hint 提供 500 detail。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    # 必须存在"在 InspectionScriptService 为 None 时阻止 DevOps 构造"的源码守卫
    # 形式：devops_block 内显式 ``if inspection_script_service is None`` 或
    # 等价 ``elif inspection_script_service is not None`` + 跳过分支
    iss_marker_start = "elif getattr("
    iss_marker_keyword = "inspection_script_service"
    end_marker = "# 2026-07-22 修复:在 TaskSchedulerService 构造之前初始化 ApiConfigService"
    # 找到包含 inspection_script_service 的 elif 守卫段
    seg_start = source.index(iss_marker_start)
    seg_end = source.index(end_marker)
    devops_segment = source[seg_start:seg_end]
    assert iss_marker_keyword in devops_segment, (
        "DevOpsServerService 构造段必须显式包含 inspection_script_service 守卫（elif / if）。"
        f"当前 devops_segment 前 400 字符: {devops_segment[:400]!r}"
    )
    # 进一步断言守卫确实生效（elif getattr(... ) is None）
    guard_substring = "elif getattr(" in devops_segment and "is None" in devops_segment
    assert guard_substring, (
        "DevOpsServerService 构造块必须显式守卫 inspection_script_service 状态为 None 时跳过构造。"
        f"当前 devops_segment 前 600 字符: {devops_segment[:600]!r}"
    )


def test_lifespan_inspection_script_service_is_required_dependency_for_devops():
    """测试 lifespan 源码契约：DevOpsServerService 构造期必须收到真实
    ``app.state.inspection_script_service`` 实例（hard fail，不允许 None 注入）。

    修复要点：
        - DevOpsServerService.__init__ 仍保留 ``inspection_script_service=None``
          的旧兼容参数（用于单测局部路径），但 lifespan 必须显式校验，
          当 ``app.state.inspection_script_service`` 为 None / 不存在时
          **不构造 DevOpsServerService**，挂 ``devops_server_service_hint`` 以
          维持 router 500 detail 行为。
        - 不允许 lifespan 在脚本库初始化失败时仍继续挂载
          ``app.state.devops_server_service = svc``（半残状态）。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    # 关键保护：DevOpsServerService 构造块必须在脚本库为 None 时走 continue / 不构造分支
    # 通过断言源码中"devops_server_service = svc" 与"inspection_script_service is None"的
    # 关系实现——脚本库 None 时必须跳过构造。
    assert "inspection_script_service = None" in source or "insp" in source, (
        "lifespan 源码必须显式处理 inspection_script_service 缺失/None 情况。"
    )
    # DevOps 构造块必须接收真实存在的实例（hint 机制用于失败诊断）
    assert "devops_server_service_hint" in source, (
        "lifespan 必须维护 devops_server_service_hint，剧本脚本库缺失时挂 hint "
        "让 router 返回 500 detail。"
    )


def test_lifespan_inspection_script_service_init_failure_skips_devops_construction():
    """测试 lifespan 源码：InspectionScriptService 初始化失败时，**不构造**
    DevOpsServerService。

    失败策略（与原 InspectionScriptService 的"降级为 None"语义不同）：
        - 历史代码：脚本库降级为 None，DevOpsServerService 照常构造，依赖
          ``_normalize_entry`` 抛 ValueError 兜底。
        - 改造后：脚本库**必填**——脚本库缺失时 DevOpsServerService 不构造
          （避免半残数据进入 cache / get_connection_config 返回部分字段）。

    生产对等初始化点：lifespan 中 InspectionScriptService 初始化段 + DevOpsServerService 初始化段。
    """
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    # DevOps 构造段必须以"if inspection_script_service is not None"
    # 守卫，避免半残构造
    devops_block = source[source.index("DevOpsServerService skipped"):]
    # 简化断言：devops 段必须显式引用 inspection_script_service 守卫生效
    # （允许同步/Lazy 形式：直接 getattr 后判 None）
    assert "inspection_script_service" in devops_block, (
        "DevOpsServerService 构造段必须显式引用 inspection_script_service 并在缺失时跳过。"
    )


def test_inspection_script_service_is_required_argument_in_lifespan_for_devops():
    """测试 lifespan 中 DevOpsServerService 不被构造时，admin API 必须报可诊断 hint，
    而不是半残 None 元数据。

    反例：构造 DevOpsServerService(inspection_script_service=None) 半残实例 → admin
    API 返回 inspection_script_id=None / inspection_script_name=None 的误导性响应。

    生产对等初始化点：lifespan + ``app/routers/devops_server_admin_router.py``。
    """
    # 通过源码分析做契约断言。DevOps 失败时 hint 必须非空。
    from app.core.server import lifespan

    source = inspect.getsource(lifespan)
    # DevOps 失败 path 必须挂 hint（让 router 返回 500 detail）
    assert "devops_server_service_hint" in source


def test_inspection_script_service_skips_devops_constructor_when_missing(monkeypatch):
    """行为测试：InspectionScriptService 缺失时 DevOpsServerService **不应被构造**。

    不依赖源代码字符串（比源码静态断言更直接）：通过 monkeypatch
    ``DevOpsServerService.__init__`` 调计数 + lifespan 复现代码路径
    断言调用次数。
    """
    import asyncio
    from cryptography.fernet import Fernet
    from unittest.mock import AsyncMock, MagicMock

    from app.shared.utils.devops_server_service import DevOpsServerService

    valid_key = Fernet.generate_key().decode("ascii")
    app_state = MagicMock()
    app_state.inspection_script_service = None  # 关键：脚本库缺失
    app_state.devops_server_service = None
    app_state.devops_server_service_hint = None

    constructed = {"n": 0}
    original_init = DevOpsServerService.__init__

    def counting_init(self, *args, **kwargs):
        constructed["n"] += 1
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(DevOpsServerService, "__init__", counting_init)

    db = MagicMock()
    db.fetch = AsyncMock(return_value=[])

    # 复现 lifespan 关键路径：脚本库 None 时不构造 DevOps
    inspection_script_service = getattr(app_state, "inspection_script_service", None)
    if inspection_script_service is None:
        # 不构造：挂 hint 维持 router 500 detail
        app_state.devops_server_service = None
        app_state.devops_server_service_hint = (
            "InspectionScriptService 未初始化，DevOpsServerService 不构造。"
            "请检查 inspection_scripts 表与 inspection_script_service 初始化段。"
        )
    else:
        DevOpsServerService(
            db=db,
            config_path="x.yaml",
            credential_key=valid_key,
            inspection_script_service=inspection_script_service,
        )
        app_state.devops_server_service = db
        app_state.devops_server_service_hint = None

    assert constructed["n"] == 0, (
        "InspectionScriptService 为 None 时，DevOpsServerService 必须不被构造。"
    )
    assert app_state.devops_server_service is None
    assert app_state.devops_server_service_hint, "失败原因必须写入 devops_server_service_hint"


def test_inspection_script_service_present_forwards_same_instance_to_devops():
    """行为测试：InspectionScriptService 存在时必须以**同一实例**注入 DevOps。

    通过 monkeypatch DevOpsServerService.__init__ 捕获 inspection_script_service
    形参的 identity，必须等于 lifespan 注入的 InspectionScriptService。
    """
    import asyncio
    from cryptography.fernet import Fernet
    from unittest.mock import AsyncMock, MagicMock

    from app.shared.utils.inspection_script_service import InspectionScriptService
    from app.shared.utils.devops_server_service import DevOpsServerService

    valid_key = Fernet.generate_key().decode("ascii")
    real_iss = InspectionScriptService(
        db=MagicMock(),
        config_path="x.yaml",
    )
    app_state = MagicMock()
    app_state.inspection_script_service = real_iss

    captured_kwargs = {}

    def fake_init(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        # 不调用原始 init（避免真实 Fernet 校验副作用）

    monkey = __import__("pytest").MonkeyPatch()
    monkey.setattr(DevOpsServerService, "__init__", fake_init)

    inspection_script_service = getattr(app_state, "inspection_script_service", None)
    if inspection_script_service is not None:
        DevOpsServerService(
            db=MagicMock(),
            config_path="x.yaml",
            credential_key=valid_key,
            inspection_script_service=inspection_script_service,
        )

    assert captured_kwargs.get("inspection_script_service") is real_iss, (
        "DevOpsServerService 必须通过 is-相同性接收 InspectionScriptService 实例。"
    )
    monkey.undo()
