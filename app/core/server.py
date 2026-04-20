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
    # 添加 Swagger 文档路径到白名单
    jwt_auth.add_to_whitelist("/api/auth/login")
    jwt_auth.add_to_whitelist("/docs")
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

    # 初始化 MCPToolsRegistry
    mcp_configs = settings.mcp.get_mcp_config()
    app.state.mcp_registry = None
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

    yield

    # 关闭 MCPToolsRegistry
    if hasattr(app.state, "mcp_registry") and app.state.mcp_registry is not None:
        await app.state.mcp_registry.shutdown()
        logging.info("MCPToolsRegistry shutdown complete")


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

    setup_middleware(app)
    setup_static_files(app)

    return app
