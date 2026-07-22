#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FastAPI服务器配置模块

负责FastAPI应用的配置，包括：
- 生命周期管理
- 中间件配置
- CORS配置

Date: 2025/4/11
Author: 张镒谱
"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config.settings import settings
from app.core.tools.mcp_registry import MCPToolsRegistry
from app.shared.utils.auth.Safety import (
    jwt_auth,
    auth_middleware,
    session_auth_middleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器

    Yields:
        None: 应用运行期间的控制权
    """
    print("[DEBUG] lifespan 函数开始执行")

    # 初始化数据库连接池
    from app.core.database import DatabasePool
    #print(f"[诊断-server] 调用 DatabasePool.initialize() 前: is_enabled={DatabasePool.is_enabled()}")
    await DatabasePool.initialize()
    #print(f"[诊断-server] 调用 DatabasePool.initialize() 后: is_enabled={DatabasePool.is_enabled()}")
    if DatabasePool.is_enabled():
        # 注册并初始化所有 Schema
        await DatabasePool.register_schemas()

    # 启动时加载 Session 到内存缓存
    from app.shared.utils.auth.session_db import SessionDB
    await SessionDB.initialize()

    # 2026-06-30 新增：启动时加载项目元数据到内存缓存
    from app.shared.utils.project.project_db import ProjectDB
    await ProjectDB.initialize()

    # 确保管理员账户存在
    from app.shared.utils.auth.user_db import UserDB
    await UserDB.ensure_admin_exists()

    # 初始化 LangGraph Checkpointer（创建 checkpoints 表）
    if DatabasePool.is_enabled():
        from app.shared.utils.memory.checkpoint import get_async_checkpointer
        try:
            checkpointer = await get_async_checkpointer()
            print("[DEBUG] LangGraph Checkpointer 初始化成功")
        except Exception as e:
            print(f"[DEBUG] LangGraph Checkpointer 初始化失败: {e}")

    # 添加 Swagger 文档路径到白名单
    jwt_auth.add_to_whitelist("/api/auth/login")
    print("[DEBUG] 已添加 /api/auth/login 到白名单")
    jwt_auth.add_to_whitelist("/api/auth/login-api")
    print("[DEBUG] 已添加 /api/auth/login-api 到白名单")
    jwt_auth.add_to_whitelist("/api/auth/captcha")
    print("[DEBUG] 已添加 /api/auth/captcha 到白名单")
    jwt_auth.add_to_whitelist("/api/auth/register")
    print("[DEBUG] 已添加 /api/auth/register 到白名单")
    jwt_auth.add_to_whitelist("/api/auth/refresh")
    print("[DEBUG] 已添加 /api/auth/refresh 到白名单")
    jwt_auth.add_to_whitelist("/api/auth/validate")
    print("[DEBUG] 已添加 /api/auth/validate 到白名单")
    jwt_auth.add_to_whitelist("/docs")
    print("[DEBUG] 已添加 /docs 到白名单")
    jwt_auth.add_to_whitelist("/openapi.json")
    jwt_auth.add_to_whitelist("/redoc")
    # Swagger UI 静态资源路径到白名单
    jwt_auth.add_to_whitelist("/swagger-ui-bundle.js")
    jwt_auth.add_to_whitelist("/swagger-ui-standalone-preset.js")
    jwt_auth.add_to_whitelist("/swagger-ui.css")
    jwt_auth.add_to_whitelist("/oauth2-redirect.html")
    jwt_auth.add_to_whitelist("/")
    jwt_auth.add_to_whitelist("/htagent.html")
    jwt_auth.add_to_whitelist("/static")

    # session/create 需要 JWT 认证，所以不在白名单中
    # session/delete 需要 JWT + session 验证，所以也不在白名单中
    # 其他所有接口都需要验证 session（由 session_auth_middleware 处理）

    # === 初始化 AgentConfigService / McpConfigService / MCPToolsRegistry ===
    # DB 为 source of truth：lifespan 从 DB 读 MCP 配置，yaml 仅作种子。
    # 降级路径：DB 不可用 / mcp_config_service 未初始化 / list_servers 返回空 → 用 yaml。
    # 注意：不在此处预设 app.state.mcp_config_service = None，避免覆盖测试 fixture
    # 的注入（测试 conftest 在 lifespan 之后执行，但 client fixture 的
    # TestClient context manager 会触发 lifespan，若预设 None 会覆盖 fixture）。

    db_pool = DatabasePool._pool
    mcp_configs = None  # 优先从 DB 读，降级为 yaml

    # 2026-07-18：初始化 EmailConfigService（数据库为 SMTP 配置真相源）
    # 顺序约束：EmailConfigService 必须在 TaskSchedulerService 之前构造完成，
    # 否则脚本任务邮件通知会在 _dispatch_script_email 内命中
    # "email_config_service 未注入" 短路分支。复用 DEVOPS_CREDENTIAL_KEY
    # 作为 Fernet 密钥加密 SMTP 密码字段；诊断失败 / 邮件禁用 / DB 不可用
    # 时挂 None，保留系统降级行为。
    if DatabasePool.is_enabled() and DatabasePool._pool is not None and settings.email_enabled:
        try:
            from app.core.config.devops_diagnostics import diagnose_credential_key
            from app.shared.utils.email.email_config_service import EmailConfigService

            email_diag = diagnose_credential_key()
            if not email_diag.ok:
                app.state.email_config_service = None
                logging.warning(
                    "[lifespan] EmailConfigService skipped: %s | %s",
                    email_diag.reason, email_diag.hint,
                )
            else:
                app.state.email_config_service = EmailConfigService(
                    db=DatabasePool._pool,
                    credential_key=settings.devops.credential_key,
                )
                await app.state.email_config_service.preload_all()
                logging.info("[lifespan] EmailConfigService initialized")
        except Exception as email_exc:
            logging.warning(
                "[lifespan] Failed to initialize EmailConfigService: %s",
                type(email_exc).__name__,
            )
    else:
        logging.warning(
            "[lifespan] Database pool not available or email disabled, "
            "EmailConfigService not initialized"
        )

    if db_pool:
        try:
            from app.shared.utils.agent.agent_config_service import AgentConfigService
            from app.shared.utils.agent.agents_md_loader import AgentsMdLoader
            from app.shared.utils.agent.mcp_service import McpConfigService

            agents_md_loader = AgentsMdLoader()
            app.state.agent_config_service = AgentConfigService(db_pool, agents_md_loader)
            app.state.mcp_config_service = McpConfigService(db_pool)

            # DB 为空时从 yaml 导入种子
            await app.state.mcp_config_service.seed_from_yaml_if_empty()
            logging.info("AgentConfigService and McpConfigService initialized")

            # 初始化 ToolRegistryService（预加载内置工具元数据 + 实例到缓存）
            # 单独 try/except：失败不应阻止 AgentConfigService/McpConfigService 后续逻辑
            from app.shared.utils.agent.tool_service import ToolRegistryService
            try:
                app.state.tool_service = ToolRegistryService(db_pool)
                await app.state.tool_service.preload_all()
            except Exception as e:
                logging.warning(
                    "Failed to initialize ToolRegistryService: %s", e, exc_info=True
                )

            # 初始化 SkillRegistryService（预加载 skills 表到缓存）
            # 单独 try/except：失败不应阻断 AgentConfigService 后续逻辑
            from app.shared.utils.agent.skill_service import SkillRegistryService
            try:
                app.state.skill_service = SkillRegistryService(db_pool)
                await app.state.skill_service.preload_all()
            except Exception as e:
                logging.warning(
                    "Failed to initialize SkillRegistryService: %s", e, exc_info=True
                )

            # 2026-06-24 新增：将 AgentConfigService 设置到 knowledge_router 全局变量，
            # 供 get_map_agent 等模块级函数使用（无法直接访问 request.app.state）
            from app.routers.knowledge_router import set_agent_config_service
            set_agent_config_service(app.state.agent_config_service)

            # 从 DB 读 enabled=true 的 server 配置（DB 为 source of truth）
            all_servers = await app.state.mcp_config_service.list_servers()
            mcp_configs = {s["name"]: s for s in all_servers if s.get("enabled")}
            if not mcp_configs:
                logging.warning(
                    "DB list_servers returned empty or all disabled, fallback to yaml"
                )
        except Exception as e:
            logging.warning(
                "Failed to initialize AgentConfigService/McpConfigService: %s", e, exc_info=True
            )
    else:
        logging.warning(
            "Database pool not available, AgentConfigService/McpConfigService not initialized"
        )

    # 降级路径：DB 不可用 / 初始化失败 / 返回空 → 从 yaml 读
    if not mcp_configs:
        try:
            yaml_configs = settings.mcp.get_mcp_config()
            # 防御性：确保是 dict 类型（测试 mock 或配置异常可能返回其他类型）
            if isinstance(yaml_configs, dict) and yaml_configs:
                mcp_configs = yaml_configs
        except Exception as e:
            logging.warning("Failed to load MCP configs from yaml: %s", e)
        logging.info(
            "MCP configs loaded from yaml (fallback), %d server(s)",
            len(mcp_configs) if mcp_configs else 0,
        )

    # 初始化 MCPToolsRegistry（无论配置来源是 DB 还是 yaml）
    if mcp_configs:
        registry = MCPToolsRegistry.get_instance()
        try:
            await registry.initialize(mcp_configs)
            app.state.mcp_registry = registry
            logging.info(
                "MCPToolsRegistry initialized with %d server(s)", len(mcp_configs)
            )
        except Exception as e:
            logging.error("Failed to initialize MCPToolsRegistry: %s", e, exc_info=True)

    # === 注入依赖到 AgentConfigService 并预加载缓存 ===
    # 顺序约束：ToolRegistryService 必须先初始化，才能注入到 AgentConfigService；
    # AgentConfigService 注入依赖后才能 preload_all（preload_all 只加载 DB 配置，
    # tools=None 延迟加载，保持 MCP 懒加载）
    if hasattr(app.state, "agent_config_service") and app.state.agent_config_service:
        try:
            # 注入依赖到 AgentConfigService
            tool_service_injected = False
            if hasattr(app.state, "tool_service") and app.state.tool_service:
                app.state.agent_config_service.set_tool_service(app.state.tool_service)
                tool_service_injected = True
                logging.info("[lifespan] ToolRegistryService injected into AgentConfigService")
            else:
                logging.warning("[lifespan] ToolRegistryService not available, skipping injection")

            mcp_registry_injected = False
            if hasattr(app.state, "mcp_registry") and app.state.mcp_registry:
                app.state.agent_config_service.set_mcp_registry(app.state.mcp_registry)
                mcp_registry_injected = True
                logging.info("[lifespan] MCPToolsRegistry injected into AgentConfigService")
            else:
                logging.warning("[lifespan] MCPToolsRegistry not available, skipping injection")

            # 2026-06-29 新增：注入 SkillRegistryService，供 AgentConfigService
            # 通过 get_available_skills 列出可绑定的 skill 元数据
            skill_service_injected = False
            if hasattr(app.state, "skill_service") and app.state.skill_service:
                app.state.agent_config_service.set_skill_service(app.state.skill_service)
                skill_service_injected = True
                logging.info("[lifespan] SkillRegistryService injected into AgentConfigService")
            else:
                logging.warning("[lifespan] SkillRegistryService not available, skipping injection")

            # 预加载 agent 配置缓存（仅 DB 配置，tools=None 延迟加载，保持 MCP 懒加载）
            await app.state.agent_config_service.preload_all()
            await app.state.mcp_config_service.preload_all()

            # 2026-07-22 修复:在 TaskSchedulerService 构造之前初始化 DevOpsServerService。
            # 此前 DevOpsServerService 在 lifespan 末段(约 L339-388)初始化,晚于
            # TaskSchedulerService 在 L270-315 通过 ``getattr(app.state, 'devops_server_service', None)``
            # 读取服务,导致 ``self._devops_server_service`` 永久为 None,后续脚本任务执行
            # ``run_server_ops`` 抛出 ``ScriptExecutionError: devops_server_service 不可用``。
            # 修复触发:ops_inspection_sweep 触发定时任务 #4 报该错(2026-07-22)。
            # 顺序约束:DB 池就绪后;密钥诊断 + config_path 解析与旧实现完全一致。
            if DatabasePool.is_enabled() and DatabasePool._pool is not None:
                try:
                    from app.core.config.devops_diagnostics import diagnose_credential_key
                    from app.core.config.paths import resolve_devops_server_config_path
                    from app.shared.utils.devops_server_service import DevOpsServerService

                    diag = diagnose_credential_key()
                    if not diag.ok:
                        # 不挂载 app.state；router 会以 diag.hint 作为 500 detail 返回
                        # 把 hint 缓存到 app.state，供 router 读取
                        app.state.devops_server_service = None
                        app.state.devops_server_service_hint = diag.hint
                        logging.warning(
                            "[lifespan] DevOpsServerService skipped: %s | %s",
                            diag.reason,
                            diag.hint,
                        )
                    else:
                        cfg_path = resolve_devops_server_config_path(
                            settings.devops.servers_config_path
                        )
                        svc = DevOpsServerService(
                            db=DatabasePool._pool,
                            config_path=str(cfg_path),
                            credential_key=settings.devops.credential_key,
                        )
                        try:
                            await svc.preload_all()
                        except Exception as preload_exc:
                            logging.warning(
                                "[lifespan] DevOpsServerService preload failed: %s",
                                type(preload_exc).__name__,
                            )
                        DevOpsServerService.set_instance(svc)
                        app.state.devops_server_service = svc
                        # 诊断通过,清理 hint
                        app.state.devops_server_service_hint = None
                        logging.info(
                            "[lifespan] DevOpsServerService initialized: %d server(s)",
                            len(svc._cache),
                        )
                except Exception as devops_exc:
                    logging.warning(
                        "[lifespan] Failed to initialize DevOpsServerService: %s",
                        type(devops_exc).__name__,
                    )
            else:
                logging.warning(
                    "[lifespan] Database pool not available, DevOpsServerService not initialized"
                )

            # 2026-07-22 修复:在 TaskSchedulerService 构造之前初始化 ApiConfigService。
            # 与 DevOpsServerService 同源顺序 bug;此前在 lifespan 末段(约 L393-408)初始化,
            # 导致 ``self._api_config_service`` 永久为 None。当前 ops_inspection_sweep /
            # hello_script 默认 api_list=[] 走空数组短路未暴露,但只要用户配置 api_list 即报错。
            # 顺序约束:DB 池就绪后;仅依赖连接池,无其他 service 依赖。
            if DatabasePool.is_enabled() and DatabasePool._pool is not None:
                try:
                    from app.shared.utils.api_config_service import ApiConfigService

                    app.state.api_config_service = ApiConfigService(db=DatabasePool._pool)
                    await app.state.api_config_service.preload_all()
                    logging.info("[lifespan] ApiConfigService initialized")
                except Exception as api_cfg_exc:
                    logging.warning(
                        "[lifespan] Failed to initialize ApiConfigService: %s",
                        type(api_cfg_exc).__name__,
                    )
            else:
                logging.warning(
                    "[lifespan] Database pool not available, ApiConfigService not initialized"
                )

            # 初始化智能体定时任务服务：数据库为任务定义真相源，应用内调度器负责触发。
            # 顺序要求：必须晚于 AgentConfigService 依赖注入与缓存预加载，确保执行时可复用 build_agent_instance。
            # 2026-07-22 强化:同时必须晚于 DevOpsServerService 与 ApiConfigService 初始化,否则
            # ``getattr(app.state, 'devops_server_service'/'api_config_service', None)`` 拿到
            # None 并永久缓存到 self._xxx_service,脚本任务执行时触发
            # ``ScriptExecutionError: xxx_service 不可用``。
            if settings.task_scheduler_enabled and db_pool:
                try:
                    # 先初始化脚本发现服务（独立于 TaskSchedulerService，但会被注入）
                    script_discovery_service = None
                    if settings.script_scan_enabled:
                        try:
                            from pathlib import Path
                            from app.core.config.paths import SCRIPTS_DIR
                            from app.shared.utils.agent.script_discovery_service import ScriptDiscoveryService
                            script_discovery_service = ScriptDiscoveryService(Path(SCRIPTS_DIR))
                            await script_discovery_service.scan()
                            app.state.script_discovery_service = script_discovery_service
                            logging.info(
                                "[lifespan] ScriptDiscoveryService initialized and scanned"
                            )
                        except Exception as scan_exc:
                            logging.warning(
                                "[lifespan] ScriptDiscoveryService init failed: %s",
                                type(scan_exc).__name__,
                            )
                            app.state.script_discovery_service = None
                    # 再初始化 TaskSchedulerService，注入 script_discovery_service
                    from app.shared.utils.agent.task_scheduler_service import TaskSchedulerService
                    app.state.task_scheduler_service = TaskSchedulerService(
                        db_pool,
                        app.state.agent_config_service,
                        script_discovery_service=script_discovery_service,
                        email_config_service=getattr(
                            app.state, "email_config_service", None
                        ),
                        api_config_service=getattr(
                            app.state, "api_config_service", None
                        ),
                        devops_server_service=getattr(
                            app.state, "devops_server_service", None
                        ),
                    )
                    await app.state.task_scheduler_service.preload_all()
                    await app.state.task_scheduler_service.start()
                    logging.info("[lifespan] TaskSchedulerService initialized and started")
                except Exception as scheduler_exc:
                    logging.warning(
                        "[lifespan] Failed to initialize TaskSchedulerService: %s",
                        scheduler_exc,
                        exc_info=True,
                    )
            logging.info(
                "[lifespan] All config caches preloaded (tool_service=%s, mcp_registry=%s, skill_service=%s)",
                tool_service_injected, mcp_registry_injected, skill_service_injected,
            )
        except Exception as e:
            logging.warning("[lifespan] Failed to preload config caches: %s", e, exc_info=True)

    # 初始化全局 Skill 系统（懒加载单例；agent 维度实例在 _llm_call 中按需创建）
    from app.core.skills.service import SkillsService

    skills_config = settings.skills.to_skills_config()
    SkillsService.get_instance(skills_config)
    if skills_config.enabled:
        logging.info(
            "SkillsService initialized with %d global skill(s)",
            len(SkillsService.get_instance().all()),
        )

    # 2026-07-19 新增：注册多渠道消费者（飞书 / 未来钉钉 / 企微 / Slack 等）
    # 通过 import 触发各渠道包 __init__.py 内的 channel_registry.register(...) 调用。
    # 顺序约束：必须在 FeishuWebSocketService 启动之前完成注册，否则
    # FeishuWebSocketService._call_agent 调用 channel_registry.resolve(session_id)
    # 时会抛 ValueError（未命中已注册前缀）。
    # 注意：必须用 ``from app.shared.tools.channels import feishu`` 而非
    # ``import app.shared.tools.channels.feishu`` —— 后者会让 Python 把 ``app``
    # 绑定为 ``sys.modules['app']`` 模块对象，覆盖 lifespan 函数参数 ``app: FastAPI``，
    # 导致后续 ``app.state.xxx`` 抛 ``AttributeError: module 'app' has no attribute 'state'``。
    try:
        from app.shared.tools.channels import feishu  # noqa: F401 触发自动注册
        from app.shared.tools.channels.registry import channel_registry
        logging.info(
            "[lifespan] ChannelRegistry initialized with prefixes: %s",
            channel_registry.list_prefixes(),
        )
    except Exception as channel_exc:
        logging.warning(
            "[lifespan] Channel registry initialization failed: %s",
            type(channel_exc).__name__,
            exc_info=True,
        )

    # 2026-07-16 新增：飞书 WebSocket 长连接（订阅 im.message.receive_v1，被动接收消息）
    # 受 settings.feishu.feishu_ws_enabled 控制；默认关闭，凭证就绪后开启
    try:
        from app.shared.tools.skills.feishu.FeishuClient import get_lark_client
        if settings.feishu.feishu_ws_enabled:
            if not hasattr(app.state, "agent_config_service") or app.state.agent_config_service is None:
                logging.warning(
                    "[lifespan] FeishuWebSocketService skipped: agent_config_service 未初始化"
                )
                app.state.feishu_ws_service = None
            else:
                from app.shared.tools.skills.feishu.FeishuWebSocketService import (
                    FeishuWebSocketService,
                )
                # 2026-07-17 新增：解析飞书会话接收账号
                #   飞书消息产生的 session（feishu:p2p:{open_id} / feishu:group:{chat_id}:{open_id}）
                #   归属到 feishu_ws_receiver_username 指定的固定系统用户，便于前端会话列表可见。
                #   该用户必须预先存在；缺失则 WS 服务不启动（与 EmailConfigService 失败策略一致）。
                from app.shared.utils.auth.user_db import UserDB

                receiver_username = settings.feishu.feishu_ws_receiver_username
                receiver_user = await UserDB.get_user_by_username(receiver_username)
                if receiver_user is None:
                    logging.error(
                        "[lifespan] FeishuWebSocketService skipped: 接收账号 %r 不存在,"
                        "请先在系统中创建该用户或在 .env 调整 feishu_ws_receiver_username",
                        receiver_username,
                    )
                    app.state.feishu_ws_service = None
                else:
                    ws_service = FeishuWebSocketService(
                        lark_client=get_lark_client(),
                        agent_config_service=app.state.agent_config_service,
                        agent_name=settings.feishu.feishu_ws_agent_name,
                        receiver_user_id=receiver_user["id"],
                        receiver_username=receiver_username,
                        log_level=settings.feishu.feishu_log_level,
                    )
                    # 注入主事件循环，供后台 SDK 回调投递协程
                    import asyncio as _asyncio
                    ws_service.set_event_loop(_asyncio.get_event_loop())
                    await ws_service.start_async()
                    app.state.feishu_ws_service = ws_service
                    logging.info(
                        "[lifespan] FeishuWebSocketService started "
                        "(agent_name=%s, receiver=%s, receiver_user_id=%s)",
                        settings.feishu.feishu_ws_agent_name,
                        receiver_username,
                        receiver_user["id"],
                    )
        else:
            app.state.feishu_ws_service = None
            logging.info(
                "[lifespan] FeishuWebSocketService disabled (feishu_ws_enabled=false)"
            )
    except Exception as ws_exc:
        logging.warning(
            "[lifespan] FeishuWebSocketService start failed: %s",
            type(ws_exc).__name__,
            exc_info=True,
        )
        app.state.feishu_ws_service = None

    print("[DEBUG] lifespan yield 即将执行")
    yield
    print("[DEBUG] lifespan yield 后，清理资源")

    # 关闭 MCPToolsRegistry
    if hasattr(app.state, "mcp_registry") and app.state.mcp_registry is not None:
        await app.state.mcp_registry.shutdown()
        logging.info("MCPToolsRegistry shutdown complete")

    # 2026-07-15 新增：清理 DevOpsServerService 单例
    try:
        from app.shared.utils.devops_server_service import DevOpsServerService

        DevOpsServerService.reset()
        if hasattr(app.state, "devops_server_service"):
            app.state.devops_server_service = None
        logging.info("[lifespan] DevOpsServerService singleton cleared")
    except Exception as cleanup_exc:
        logging.warning(
            "[lifespan] Failed to cleanup DevOpsServerService: %s",
            type(cleanup_exc).__name__,
        )

    # 2026-07-16 新增：清理 ScriptDiscoveryService 引用
    try:
        if hasattr(app.state, "script_discovery_service"):
            app.state.script_discovery_service = None
        logging.info("[lifespan] ScriptDiscoveryService reference cleared")
    except Exception as cleanup_exc:
        logging.warning(
            "[lifespan] Failed to cleanup ScriptDiscoveryService: %s",
            type(cleanup_exc).__name__,
        )

    # 2026-07-16 新增：清理飞书 WebSocket 服务
    try:
        if hasattr(app.state, "feishu_ws_service") and app.state.feishu_ws_service is not None:
            app.state.feishu_ws_service.stop()
            app.state.feishu_ws_service = None
            logging.info("[lifespan] FeishuWebSocketService stopped")
    except Exception as cleanup_exc:
        logging.warning(
            "[lifespan] Failed to stop FeishuWebSocketService: %s",
            type(cleanup_exc).__name__,
        )

    # 关闭 Skill 系统单例
    SkillsService.reset()
    logging.info("SkillsService singleton cleared")

    # 关闭数据库连接池
    if DatabasePool.is_enabled():
        await DatabasePool.close()


def setup_middleware(app: FastAPI):
    """
    配置中间件

    Args:
        app: FastAPI应用实例
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(session_auth_middleware)
    app.middleware("http")(auth_middleware)


def setup_logging():
    """
    配置日志
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%H:%M:%S",
    )


def setup_static_files(app: FastAPI):
    """
    配置静态文件

    Args:
        app: FastAPI应用实例
    """
    frontend_path = Path(__file__).parent.parent / "html" / "clint"
    if frontend_path.exists():
        app.mount(
            "/", StaticFiles(directory=str(frontend_path), html=True), name="static"
        )


def create_app() -> FastAPI:
    """
    创建FastAPI应用实例

    Returns:
        FastAPI: 配置完成的FastAPI应用实例
    """
    setup_logging()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    setup_middleware(app)
    setup_static_files(app)

    return app
