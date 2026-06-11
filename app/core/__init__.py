#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
app.core 核心模块包

本包是 feature-agent-core 的核心基础设施层，提供：
- agent：Agent 基类与运行框架（agent.py、AgentConfig.py、AgentContext.py）
- config：全局配置加载（config.py、settings.py）
- database：PostgreSQL 异步连接池与数据访问
- dependencies：FastAPI 依赖注入
- format/stream：SSE 流式输出格式化（base、default、ollama、context）
- llmcalls：大语言模型统一工厂与多 provider 适配（model_factory、deepseek/ollama/openai/anthropic）
- messages：消息转换与裁剪（converter、trim）
- prompts：三层提示词架构的通用基类提示词
- router：核心文件上传/下载路由
- server：FastAPI 应用工厂（生命周期、中间件、CORS）
- tools：核心工具基类与 MCP 适配器（BaseTools、HumanInTheLoopTools、mcp_*）

注意：本 __init__.py 仅为将 app.core 标识为 Python 包而存在，
导入子模块时请使用绝对导入，例如：
    from app.core.llmcalls.model_factory import ModelFactory
    from app.core.config.config import LLM_CONFIG
"""
