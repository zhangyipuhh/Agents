#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocAgent 配置模块

提供文档处理Agent的配置类和上下文类。

Date: 2026-03-19
Author: 张镒谱
"""

from app.agents.subgraphs.Doc_Agent.config.DocAgentConfig import (
    DocAgentConfig,
    DocAgentState,
    DocExecuteConfig,
    DocConfigurableConfig,
)
from app.agents.subgraphs.Doc_Agent.config.DocAgentContext import DocAgentContext
from app.agents.subgraphs.Doc_Agent.config.config import DEFAULT_SYSTEM_PROMPT

__all__ = [
    "DocAgentConfig",
    "DocAgentState",
    "DocAgentContext",
    "DocExecuteConfig",
    "DocConfigurableConfig",
    "DEFAULT_SYSTEM_PROMPT",
]
