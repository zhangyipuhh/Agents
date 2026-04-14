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

logger = logging.getLogger(__name__)

# 加载 .env 文件
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


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
    from mcpClient.core.mcp_client.client_pool import _ensure_mcp_loop
    from mcpClient.shared.config_loader import load_mcp_config

    _ensure_mcp_loop()

    config = load_mcp_config()
    if config:
        from mcpClient.core.mcp_client.client_pool import MCPClientPool

        pool = MCPClientPool()
        for name, cfg in config.items():
            try:
                await pool.connect(name, cfg)
                logger.info(f"MCP server '{name}' connected")
            except Exception as e:
                logger.error(f"Failed to connect MCP server '{name}': {e}")

    yield

    logger.info("Shutting down...")


def create_app():
    """
    创建 FastAPI 应用
    """
    from fastapi import FastAPI

    setup_logging()

    app = FastAPI(title="mcpClient", version="0.1.0")
    app.router.lifespan_context = lifespan

    return app


def main():
    """
    主入口
    """
    uvicorn.run(
        "mcpClient.main:create_app",
        host="0.0.0.0",
        port=10000,
        reload=False,
    )


if __name__ == "__main__":
    main()
