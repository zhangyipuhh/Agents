#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
页面路由模块

提供 HTML 页面路由
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def root():
    """
    首页
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCP Client</title>
        <meta charset="utf-8">
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }
            .container {
                background: white;
                border-radius: 16px;
                padding: 40px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
            }
            .status {
                display: inline-block;
                background: #4CAF50;
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 14px;
                margin-bottom: 20px;
            }
            .info {
                background: #f5f5f5;
                padding: 20px;
                border-radius: 8px;
                margin-top: 20px;
            }
            .info h2 {
                margin-top: 0;
                color: #555;
            }
            .info p {
                color: #666;
                line-height: 1.6;
            }
            code {
                background: #e0e0e0;
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 MCP Client 服务</h1>
            <span class="status">运行中</span>
            <div class="info">
                <h2>服务信息</h2>
                <p><strong>应用名称:</strong> mcpClient</p>
                <p><strong>版本:</strong> 0.1.0</p>
                <p><strong>API 文档:</strong> <a href="/docs">/docs</a> (Swagger UI)</p>
                <p><strong>备用文档:</strong> <a href="/redoc">/redoc</a> (ReDoc)</p>
            </div>
            <div class="info">
                <h2>使用说明</h2>
                <p>这是一个 MCP (Model Context Protocol) 中转站服务。</p>
                <p>您可以通过 API 端点与 MCP Server 进行交互。</p>
            </div>
        </div>
    </body>
    </html>
    """
