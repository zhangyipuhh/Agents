#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AICodingCheckAgent 配置加载模块

从 .env 文件加载环境变量，初始化 AICodingCheckSettings 单例。

Date: 2026-04-21
Author: 张镒谱
"""

from dotenv import load_dotenv

# 加载 .env 文件中的环境变量到系统环境中，确保后续 BaseSettings 能正确读取
load_dotenv()

from app.features.AI_Coding_Check_agent.config.AICodingCheckSettings import AICodingCheckSettings

# 创建全局配置单例实例，供其他模块直接引用
ai_coding_check_settings = AICodingCheckSettings()
