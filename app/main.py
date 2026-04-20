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
import warnings

warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module="pydantic.main"
)

import uvicorn

from app.core.server import create_app
from app.shared.routers.file_router import router as file_router
from app.shared.routers.session_router import router as session_router
from app.shared.routers.auth_router import router as auth_router
from app.features.contract_host_agent.router.contract_router import router as contract_router
from app.features.map_agent.router.map_router import router as map_router


app = create_app()


def register_routers():
    """
    注册所有路由
    """
    app.include_router(auth_router)
    app.include_router(file_router)
    app.include_router(session_router)
    app.include_router(contract_router)
    app.include_router(map_router)


register_routers()


if __name__ == '__main__':
    #开发环境
    #uvicorn.run("app.main:app", host='0.0.0.0', port=8000, reload=True, reload_dirs=["app"], reload_delay=0.5)
    #生产环境
    uvicorn.run("app.main:app", host='0.0.0.0', port=8001, reload=False)
