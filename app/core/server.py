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

    print("[DEBUG] lifespan yield 即将执行")
    yield
    print("[DEBUG] lifespan yield 后，清理资源")

    # 关闭 MCPToolsRegistry
    if hasattr(app.state, "mcp_registry") and app.state.mcp_registry is not None:
        await app.state.mcp_registry.shutdown()
        logging.info("MCPToolsRegistry shutdown complete")

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
