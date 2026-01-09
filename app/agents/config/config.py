#!usr/bin/env python
# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()


# 大模型配置
LLM_CONFIG = {
    "model_name": os.getenv("model_name"),
    "api_key": os.getenv("model_api_key"),
    "base_url": os.getenv("model_api_base"),
    "model_type":os.getenv("model_type")
}

PROMPT_TEMPLATE = {
    #主提示词
    "main":"你是自然资源业务任务，通过合适的工具回答问题，不能凭空回答。"
}

