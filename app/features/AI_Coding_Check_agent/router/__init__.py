#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AI辅助编程效果评审智能体路由模块

Date: 2026-04-21
Author: 张镒谱
"""

# 从子模块导入路由实例，供上层模块统一注册
from app.features.AI_Coding_Check_agent.router.ai_coding_check_router import router

__all__ = ['router']
