#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP 中转站入口

启动 MCP Server 服务。

Date: 2026-04-20
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

_PACKAGE_ROOT = Path(__file__).parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

_APP_ROOT = Path(__file__).parent.parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from mcpClient.routers.mcp_router import router as mcp_router, set_unified_client

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app):
    from mcpClient.shared.config_loader import load_mcp_config
    from mcpClient.core.unified_mcp_client import UnifiedMCPClient

    config = load_mcp_config()
    client = None
    if config:
        client = UnifiedMCPClient(config)
        set_unified_client(client)
        logger.info("UnifiedMCPClient initialized with %d server(s)", len(config))
    else:
        logger.warning("No MCP server configuration found")

    yield

    logger.info("Shutting down...")
    if client:
        await client.shutdown()


def create_app():
    from fastapi import FastAPI

    setup_logging()

    app = FastAPI(title="mcpClient", version="0.2.0")
    app.router.lifespan_context = lifespan

    return app


app = create_app()


def register_routers():
    app.include_router(mcp_router)


register_routers()


def main():
    uvicorn.run(
        "mcpClient.main:app",
        host="0.0.0.0",
        port=10002,
        reload=False,
    )


if __name__ == "__main__":
    main()
