#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
安全认证模块

本模块提供JWT令牌的生成和验证功能。
主要功能包括：
- 生成JWT令牌
- 验证JWT令牌
- 认证中间件
- 白名单管理
- Session 认证中间件

Date: 2026/2/6
Author: 张镒谱
"""
import jwt
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.Session.SessionCache import session_cache


class JWTAuth:
    """
    JWT认证工具类
    
    提供JWT令牌的生成、验证和中间件功能。
    后续将密钥写入环境变量 ，暂时明文
    """
    
    def __init__(self, secret_key: str = "zlnWZlEydbodC0D8oJ_9Pdw3C73rHU23k8PEJfaJlso", algorithm: str = "HS256"):
        """
        初始化JWT认证工具
        
        Args:
            secret_key (str): JWT密钥，用于签名和验证令牌
            algorithm (str): JWT算法，默认为HS256
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expiration_minutes = 5
        self.whitelist: List[str] = []
        
        self.username = "admin"
        self.password = "123456"
    
    def add_to_whitelist(self, path: str):
        """
        添加路径到白名单
        
        白名单中的路径不需要JWT认证。
        
        Args:
            path (str): 要添加到白名单的路径
        """
        if path not in self.whitelist:
            self.whitelist.append(path)
    
    def is_whitelisted(self, path: str) -> bool:
        """
        检查路径是否在白名单中
        
        Args:
            path (str): 要检查的路径
            
        Returns:
            bool: 如果路径在白名单中返回True，否则返回False
        """
        return path in self.whitelist
    
    async def verify_credentials(self, username: str, password: str) -> bool:
        """
        验证用户凭据
        
        Args:
            username (str): 用户名
            password (str): 密码
            
        Returns:
            bool: 验证成功返回True，否则返回False
        """
        return username == self.username and password == self.password
    
    async def generate_token(self, username: str) -> str:
        """
        生成JWT令牌
        
        Args:
            username (str): 用户名
            
        Returns:
            str: JWT令牌
            
        Raises:
            HTTPException: 当生成令牌失败时抛出
        """
        try:
            payload = {
                "username": username,
                "exp": datetime.utcnow() + timedelta(minutes=self.expiration_minutes),
                "iat": datetime.utcnow()
            }
            
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            return token
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"生成令牌失败: {str(e)}"
            )
    
    async def verify_token(self, token: str) -> dict:
        """
        验证JWT令牌
        
        Args:
            token (str): JWT令牌
            
        Returns:
            dict: 解码后的令牌payload
            
        Raises:
            HTTPException: 当令牌无效或过期时抛出
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已过期"
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"验证令牌失败: {str(e)}"
            )
    
    async def authenticate(self, request: Request) -> Optional[dict]:
        """
        认证请求
        
        从请求中提取并验证JWT令牌。
        
        Args:
            request (Request): FastAPI请求对象
            
        Returns:
            Optional[dict]: 认证成功返回payload，失败返回None
            
        Raises:
            HTTPException: 当认证失败时抛出
        """
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少认证信息"
            )
        
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证格式"
            )
        
        token = auth_header.split(" ")[1]
        payload = await self.verify_token(token)
        
        # 将用户信息存储到 request.state，方便后续使用
        request.state.username = payload.get("username")
        request.state.payload = payload
        
        return payload


async def auth_middleware(request: Request, call_next):
    """
    JWT认证中间件
    
    拦截所有请求，验证JWT令牌（白名单路径除外）。
    
    Args:
        request (Request): FastAPI请求对象
        call_next: 下一个中间件或路由处理器
        
    Returns:
        Response: 处理后的响应
    """
    path = request.url.path
    
    # 检查路径是否在白名单中
    if jwt_auth.is_whitelisted(path):
        return await call_next(request)
    
    try:
        # 验证JWT令牌
        await jwt_auth.authenticate(request)
        return await call_next(request)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(e)}
        )


async def session_auth_middleware(request: Request, call_next):
    """
    Session 认证中间件
    
    验证 session_id 是否与当前登录用户名对应。
    白名单路径跳过验证。
    /api/session/create 路径跳过验证（因为创建 session 时还没有 session_id）。
    
    Args:
        request (Request): FastAPI请求对象
        call_next: 下一个中间件或路由处理器
        
    Returns:
        Response: 处理后的响应
    """
    path = request.url.path
    
    # 检查路径是否在白名单中（白名单路径不需要 session 验证）
    if jwt_auth.is_whitelisted(path):
        return await call_next(request)
    
    # /api/session/create 路径跳过 session 验证（创建 session 时还没有 session_id）
    if path.startswith("/api/session/create"):
        return await call_next(request)
    
    try:
        # 获取当前用户名
        username = getattr(request.state, "username", None)
        
        if not username:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "缺少用户认证信息"}
            )
        
        # 从请求头中获取 session_id
        session_id = request.headers.get("X-Session-ID")
        
        if not session_id:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "缺少 X-Session-ID 请求头"}
            )
        
        # 验证 session_id 是否属于该用户
        is_valid = session_cache.verify_session(session_id, username)
        
        if not is_valid:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "无权访问该会话"}
            )
        
        # 将 session_id 存储到 request.state，方便后续使用
        request.state.session_id = session_id
        
        return await call_next(request)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Session 认证失败: {str(e)}"}
        )


# 创建全局JWT认证实例
jwt_auth = JWTAuth()
