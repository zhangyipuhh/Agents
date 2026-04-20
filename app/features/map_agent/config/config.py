#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 配置加载模块

从 .env 文件加载环境变量，初始化 MapAgentSettings 单例。

Date: 2026-04-20
"""

from dotenv import load_dotenv

load_dotenv()

from app.features.map_agent.config.settings import MapAgentSettings

map_agent_settings = MapAgentSettings()
