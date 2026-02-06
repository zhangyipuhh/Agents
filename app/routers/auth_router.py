#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
认证路由模块

本模块定义了认证相关的API路由。
主要功能包括：
- 用户登录获取JWT令牌

Date: 2026/2/6
Author: 张镒谱
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.utils.auth.Safety import jwt_auth


class LoginRequest(BaseModel):
    """
    登录请求模型
    
    定义登录时需要的数据结构。
    
    Attributes:
        username (str): 用户名
        password (str): 密码
    """
    username: str
    password: str


class LoginResponse(BaseModel):
    """
    登录响应模型
    
    定义登录操作后的响应数据结构。
    
    Attributes:
        access_token (str): JWT访问令牌
        token_type (str): 令牌类型
        expires_in (int): 令牌过期时间（分钟）
    """
    access_token: str
    token_type: str
    expires_in: int


# 创建API路由实例，设置前缀和标签
# prefix='/api/auth': 所有路由路径将以/api/auth开头
# tags=['Authentication']: 用于API文档分组，便于在Swagger UI中查看
router = APIRouter(prefix='/api/auth', tags=['Authentication'])


@router.post('/login', response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    用户登录API端点
    
    验证用户凭据并返回JWT令牌。
    使用HTTPS传输确保安全性。
    
    工作流程：
    1. 接收用户名和密码
    2. 验证用户凭据
    3. 生成JWT令牌
    4. 返回令牌信息
    
    Args:
        request (LoginRequest): 包含用户名和密码的请求对象
        
    Returns:
        LoginResponse: 包含访问令牌、令牌类型和过期时间的响应对象
        
    Raises:
        HTTPException: 当用户名或密码错误时抛出401错误
    """
    is_valid = await jwt_auth.verify_credentials(request.username, request.password)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    token = await jwt_auth.generate_token(request.username)
    
    return LoginResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=jwt_auth.expiration_minutes
    )
