#!usr/bin/env python
# -*- coding: utf-8 -*-
# File: main.py
# Date: 2025/4/11 12:07
# Author: 张镒谱
# Description:
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.agent_router import router as agent_router

# 移除对不存在的模块的引用
# from core.exception import register_exceptions


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app():
    """Create the FastAPI app and include the router."""
    app = FastAPI(lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(agent_router)
    
    # 移除对不存在的路由器的引用
    # 移除对不存在的异常处理器的引用
    # register_exceptions(app)
    return app


app = create_app()

if __name__ == '__main__':

    # init_database_tables()
    # 使用硬编码端口8000替代不存在的server_port变量
    uvicorn.run("app.MainServer:app", host='0.0.0.0', port=8000, reload=False)