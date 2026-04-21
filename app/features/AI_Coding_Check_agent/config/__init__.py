#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AICodingCheckAgent 配置模块

该模块导出 AI 辅助编程效果评审智能体的配置类和提示词。

Date: 2026-04-21
Author: 张镒谱
"""

# 导入 AICodingCheckAgent 的核心配置类，包括可配置参数、执行配置、状态类和主配置类
from app.features.AI_Coding_Check_agent.config.AICodingCheckConfig import (
    AICodingCheckConfigurableConfig,
    AICodingCheckExecuteConfig,
    AICodingCheckState,
    AICodingCheckConfig
)
# 导入 AICodingCheckAgent 的上下文类，用于会话隔离和上下文传递
from app.features.AI_Coding_Check_agent.config.AICodingCheckContext import AICodingCheckContext
# 导入 AICodingCheckAgent 的系统提示词和评审模板提示词
from app.features.AI_Coding_Check_agent.config.prompts import REVIEW_SYSTEM_PROMPT, REVIEW_PROMPT_TEMPLATE

# 模块公开接口列表，定义 from module import * 时可导出的符号
__all__ = [
    "AICodingCheckConfigurableConfig",
    "AICodingCheckExecuteConfig",
    "AICodingCheckState",
    "AICodingCheckConfig",
    "AICodingCheckContext",
    "REVIEW_SYSTEM_PROMPT",
    "REVIEW_PROMPT_TEMPLATE",
]
