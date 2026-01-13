#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FastAPI主服务器模块

本模块作为应用程序的入口点，负责创建和配置FastAPI应用实例。
主要功能包括：
- 配置CORS中间件以支持跨域请求
- 注册路由器以处理API端点
- 管理应用生命周期

Date: 2025/4/11 12:07
Author: 张镒谱
"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.agent_router import router as agent_router

# 移除对不存在的模块的引用
# from core.exception import register_exceptions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器
    
    使用异步上下文管理器管理FastAPI应用的启动和关闭事件。
    当前实现为空，未来可在yield前添加启动逻辑，
    在yield后添加清理逻辑（如数据库连接关闭、资源释放等）。
    
    Args:
        app: FastAPI应用实例
    
    Yields:
        None: 应用运行期间的控制权
    """
    yield


def create_app():
    """
    创建并配置FastAPI应用实例
    
    此函数负责：
    1. 初始化FastAPI应用并设置生命周期管理器
    2. 配置CORS中间件以允许跨域请求
    3. 注册agent路由器到应用中
    
    Returns:
        FastAPI: 配置完成的FastAPI应用实例
    """
    # 创建FastAPI应用实例，传入生命周期管理器
    app = FastAPI(lifespan=lifespan)

    # 配置CORS中间件，允许所有来源、方法和请求头的跨域请求
    # allow_origins=["*"]: 允许所有来源的请求
    # allow_credentials=True: 允许携带凭证（如cookies）
    # allow_methods=["*"]: 允许所有HTTP方法（GET, POST, PUT, DELETE等）
    # allow_headers=["*"]: 允许所有请求头
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 将agent路由器注册到应用中，处理agent相关的API请求
    app.include_router(agent_router)
    
    # 移除对不存在的路由器的引用
    # 移除对不存在的异常处理器的引用
    # register_exceptions(app)
    return app


# 创建FastAPI应用实例
app = create_app()

if __name__ == '__main__':
    """
    主程序入口
    
    当直接运行此文件时，启动uvicorn服务器。
    使用硬编码的端口8000监听所有网络接口（0.0.0.0），
    reload=False表示不启用热重载，适合生产环境。
    """

    # init_database_tables()
    # 使用硬编码端口8000替代不存在的server_port变量
    # host='0.0.0.0': 监听所有网络接口，允许外部访问
    # port=8000: 指定服务监听端口
    # reload=False: 关闭热重载模式，提高性能
    uvicorn.run("app.MainServer:app", host='0.0.0.0', port=8000, reload=False)