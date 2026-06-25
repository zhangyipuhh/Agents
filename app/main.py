#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FastAPI应用入口

总入口，只负责：
1. 创建 FastAPI 实例
2. 注册所有路由
3. 启动服务器

Date: 2025/4/11
Author: 张镒谱
"""
import logging
import warnings
import argparse

import os
from dotenv import load_dotenv, find_dotenv

_dotenv_path = find_dotenv()
#print(f"[诊断-main] find_dotenv 找到的 .env 文件: {_dotenv_path}")
if _dotenv_path:
    _loaded = load_dotenv(dotenv_path=_dotenv_path, verbose=True)
    #print(f"[诊断-main] load_dotenv 返回: {_loaded}")
else:
    print("[诊断-main] 未找到 .env 文件！")
#print(f"[诊断-main] os.environ['AUTH_STORAGE_MODE'] = {os.environ.get('AUTH_STORAGE_MODE', '<<未设置>>')}")

from app.shared.tools.middleware.filesystem_encoding_fix import apply_fix

apply_fix()

import uvicorn

logging.getLogger("root").addFilter(
    lambda record: not (
        "Failed to validate notification" in record.getMessage() or
        "validation errors for ServerNotification" in record.getMessage()
    )
)

warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module="pydantic.main"
)

from app.core.server import create_app
from app.shared.routers.file_router import router as file_router
from app.shared.routers.session_router import router as session_router
from app.shared.routers.auth_router import router as auth_router
from app.shared.routers.user_router import router as user_router
from app.features.contract_host_agent.router.contract_router import router as contract_router
from app.routers.knowledge_router import router as knowledge_router
from app.features.AI_Coding_Check_agent.router.ai_coding_check_router import router as ai_coding_check_router
from app.core.router import file_upload_router as core_file_upload_router
from app.core.router import file_download_router as core_file_download_router
from app.routers.mcp_admin_router import router as mcp_admin_router
from app.routers.agent_router import router as agent_router
from app.routers.agent_admin_router import router as agent_admin_router
from app.routers.tool_admin_router import router as tool_admin_router


app = create_app()


def register_routers(target_app=None):
    """
    注册所有路由

    Args:
        target_app: 目标 FastAPI 应用实例；未传入时使用模块级全局 app
    """
    _app = target_app or app
    _app.include_router(auth_router)
    _app.include_router(user_router)
    _app.include_router(file_router)
    _app.include_router(session_router)
    _app.include_router(contract_router)
    _app.include_router(knowledge_router)
    _app.include_router(ai_coding_check_router)
    _app.include_router(core_file_upload_router)
    _app.include_router(core_file_download_router)
    _app.include_router(mcp_admin_router)
    _app.include_router(agent_router)
    _app.include_router(agent_admin_router)
    _app.include_router(tool_admin_router)


register_routers()


def parse_args():
    parser = argparse.ArgumentParser(description='Feature Agent Core Server')
    parser.add_argument('--port', type=int, default=8001, help='Server port (default: 8001)')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Server host (default: 0.0.0.0)')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
