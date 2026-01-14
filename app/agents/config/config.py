#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Agent配置模块

本模块负责加载和管理Agent运行所需的配置信息。
主要功能包括：
- 从环境变量中加载大模型配置信息
- 定义提示词模板
- 提供统一的配置接口供其他模块使用

配置项说明：
- LLM_CONFIG: 大语言模型相关配置，包括模型名称、API密钥、基础URL等
- PROMPT_TEMPLATE: Agent的提示词模板，定义Agent的角色和行为准则
date 2026/1/9 12:07
author 张镒谱
"""
import os
from dotenv import load_dotenv
from enum import Enum

# 从.env文件中加载环境变量
# 这会将.env文件中的变量加载到os.environ中，供后续代码使用
load_dotenv()


# 大模型配置字典
# 存储大语言模型连接和调用所需的配置信息
LLM_CONFIG = {
    # 模型名称：指定使用的大语言模型，如"gpt-4"、"claude-3"等
    "model_name": os.getenv("model_name"),
    # API密钥：用于认证的大模型服务提供商的密钥
    "api_key": os.getenv("model_api_key"),
    # 基础URL：大模型API服务的地址端点
    "base_url": os.getenv("model_api_base"),
    # 模型类型：标识模型的类型或版本，用于区分不同类型的模型
    "model_type": os.getenv("model_type")
}

# 提示词模板字典
# 存储Agent使用的各种提示词模板，用于指导Agent的行为和响应方式
PROMPT_TEMPLATE = {
    # 主提示词：定义Agent的核心角色和行为准则
    # 该提示词告诉Agent它是自然资源业务任务，需要通过工具回答问题，不能凭空编造答案
    "main": "你是自然资源业务任务，通过合适的工具回答问题，不能凭空回答。"
}
class SubGraphType(str, Enum):
    """
    子图类型枚举类

    用于标识和区分不同的子图类型，便于在代码中统一引用和管理。
    """
    audit_contract_clause = "audit_contract_clause"
    search_database = "search_database"

