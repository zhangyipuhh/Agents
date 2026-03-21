#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ApprovalAgent 配置模块

提供审批Agent的配置类和上下文类。

Date: 2026-03-19
Author: 张镒谱
"""

from app.agents.subgraphs.ApprovalAgent.config.ApprovalAgentConfig import (
    ApprovalAgentConfig,
    ApprovalAgentState,
    ApprovalExecuteConfig,
    ApprovalConfigurableConfig,
)
from app.agents.subgraphs.ApprovalAgent.config.ApprovalAgentContext import ApprovalAgentContext
from app.features.contract_approval_agent.config.prompts import DEFAULT_SYSTEM_PROMPT

__all__ = [
    "ApprovalAgentConfig",
    "ApprovalAgentState",
    "ApprovalAgentContext",
    "ApprovalExecuteConfig",
    "ApprovalConfigurableConfig",
    "DEFAULT_SYSTEM_PROMPT",
]
