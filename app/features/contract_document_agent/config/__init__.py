#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocAgent 配置模块

提供文档处理Agent的配置类和上下文类。

Date: 2026-03-19
Author: 张镒谱
"""

from app.features.contract_document_agent.config.DocAgentConfig import (
    DocAgentConfig,
    DocAgentState,
    DocExecuteConfig,
    DocConfigurableConfig,
)
from app.features.contract_document_agent.config.DocAgentContext import DocAgentContext
from app.features.contract_document_agent.config.prompts import DEFAULT_SYSTEM_PROMPT

__all__ = [
    "DocAgentConfig",
    "DocAgentState",
    "DocAgentContext",
    "DocExecuteConfig",
    "DocConfigurableConfig",
    "DEFAULT_SYSTEM_PROMPT",
]
