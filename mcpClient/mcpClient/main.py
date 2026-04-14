#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP 中转站入口

启动 MCP Server 服务。

Date: 2026-04-14
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

_PACKAGE_ROOT = Path(__file__).parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

# 添加父目录到路径，以便导入 app 模块
_APP_ROOT = Path(__file__).parent.parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

# 加载 .env 文件
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# 路径设置完成后再导入
from mcpClient.routers.page_router import router as page_router
from mcpClient.routers.mcp_router import router as mcp_router, set_client_pool

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """
    配置日志
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app):
    """
    应用生命周期管理
    """
    from mcpClient.shared.config_loader import load_mcp_config

    config = load_mcp_config()
    pool = None
    if config:
        from mcpClient.core.mcp_client.client_pool import MCPClientPool

        pool = MCPClientPool()
        # 设置全局连接池，供路由使用
        set_client_pool(pool)
        for name, cfg in config.items():
            try:
                await pool.connect(name, cfg)
                logger.info(f"MCP server '{name}' connected")
            except Exception as e:
                logger.error(f"Failed to connect MCP server '{name}': {e}")

    yield

    logger.info("Shutting down...")
    if pool:
        await pool.shutdown()


def create_app():
    """
    创建 FastAPI 应用
    """
    from fastapi import FastAPI

    setup_logging()

    app = FastAPI(title="mcpClient", version="0.1.0")
    app.router.lifespan_context = lifespan

    return app


app = create_app()


def register_routers():
    """
    注册所有路由
    """
    app.include_router(page_router)
    app.include_router(mcp_router)


register_routers()


def main():
    """
    主入口
    """
    uvicorn.run(
        "mcpClient.main:app",
        host="0.0.0.0",
        port=10001,
        reload=False,
    )


if __name__ == "__main__":
    main()
